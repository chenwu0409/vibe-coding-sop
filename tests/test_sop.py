import contextlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import sop


class SopTests(unittest.TestCase):
    def setUp(self):
        test_temp_root = Path(__file__).parent / ".test-temp"
        test_temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "项目 with spaces"

    def call(self, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return sop.main(list(map(str, args)))

    def init(self, profile="S", risk="normal"):
        self.assertEqual(self.call("init", self.root, "--profile", profile, "--risk", risk), 0)

    def config(self):
        return sop.read_json(self.root / ".sop/project.json")

    def save_config(self, config):
        sop.write_json(self.root / ".sop/project.json", config)

    def baseline(self):
        self.assertEqual(self.call("baseline", "--project", self.root), 0)

    def sync(self, stage=None):
        args = ["sync", "--project", self.root]
        if stage:
            args.extend(["--stage", stage])
        self.assertEqual(self.call(*args), 0)

    def tasks_done(self):
        sop.write_json(self.root / ".sop/tasks.json", {
            "schema_version": 1,
            "tasks": [{
                "id": "T-001",
                "status": "done",
                "ac_ids": ["AC-001"],
                "implementation": ["source.py"],
                "tests": ["tests/test_feature.py"],
                "evidence": [".sop/evidence/latest.json"],
                "verification": "passed",
            }],
        })

    def configure_success(self):
        config = self.config()
        for name in sop.requirements(config)["commands"]:
            config["commands"][name] = [sys.executable, "-c", "print('real command output')"]
        self.save_config(config)

    def fill_docs(self):
        sections = sop.read_json(sop.PACKAGE / "gates/document-sections.json")
        for path in (self.root / ".sop/docs").glob("*.md"):
            content = "# Test fixture\n" + "".join(
                "\n## " + heading + "\nTest-only fixture, not a real decision.\n"
                for heading in sections[path.stem])
            path.write_text(content, encoding="utf-8")

    def approve(self, name):
        # Test-only fake reviewer. Production code never writes approved records.
        config = self.config()
        evidence = self.root / ".sop/reviews" / (name + ".md")
        evidence.parent.mkdir(exist_ok=True)
        evidence.write_text("TEST FIXTURE: reviewed acceptance cases", encoding="utf-8")
        state = sop.read_json(self.root / ".sop/state.json")
        state["reviews"][name] = {
            "status": "approved", "reviewer": "test fixture",
            "decision": "synthetic test", "evidence": evidence.relative_to(self.root).as_posix(),
            "sha256": sop.sha(evidence),
            "scope_sha256": sop.review_scope(self.root, config, sop.requirements(config), name)}
        sop.write_json(self.root / ".sop/state.json", state)

    def test_profiles_and_high_risk(self):
        for profile in ("S", "M", "L"):
            for risk in ("normal", "high"):
                target = self.root / (profile + risk)
                self.assertEqual(self.call("init", target, "--profile", profile, "--risk", risk), 0)
                config = sop.read_json(target / ".sop/project.json")
                self.assertEqual("security" in config["commands"], risk == "high")
                self.assertTrue((target / ".sop/runtime/sop.py").exists())
                self.assertEqual(self.call("check", "--project", target, "--stage", "L4"), 1)

    def test_init_conflict_preserves_existing(self):
        self.root.mkdir()
        (self.root / "AGENTS.md").write_text("user content")
        self.assertEqual(self.call("init", self.root), 2)
        self.assertEqual((self.root / "AGENTS.md").read_text(), "user content")
        self.assertFalse((self.root / ".sop").exists())
        self.assertEqual(self.call("init", self.root, "--agent-file", "SOP-AGENTS.md"), 0)

    def test_repeat_init_preserves_config(self):
        self.init()
        config_path = self.root / ".sop/project.json"
        original = config_path.read_bytes()
        self.assertEqual(self.call("init", self.root), 2)
        self.assertEqual(config_path.read_bytes(), original)

    def test_path_escape_rejected_before_creation(self):
        self.assertEqual(self.call("init", self.root, "--agent-file", "../AGENTS.md"), 2)
        self.assertFalse(self.root.exists())

    def test_template_and_header_only_not_ready(self):
        self.init()
        self.assertEqual(self.call("check", "--project", self.root), 1)
        (self.root / ".sop/docs/constitution.md").write_text("# Empty\n")
        self.assertEqual(self.call("check", "--project", self.root), 1)
        self.fill_docs()
        self.baseline()
        self.sync()
        self.assertEqual(self.call("check", "--project", self.root), 0)

    def test_local_git_baseline_and_sync_are_required(self):
        self.init()
        self.fill_docs()
        self.assertTrue((self.root / ".git").exists())
        self.assertEqual(self.call("check", "--project", self.root), 1)
        self.baseline()
        self.assertTrue((self.root / ".sop/git-baseline.json").exists())
        self.assertEqual(self.call("check", "--project", self.root), 1)
        self.sync()
        self.assertEqual(self.call("check", "--project", self.root), 0)
        (self.root / "new-source.py").write_text("x = 1\n", encoding="utf-8")
        self.assertEqual(self.call("check", "--project", self.root), 1)

    def test_audit_checks_ac_and_declared_paths(self):
        self.init("M")
        self.fill_docs()
        self.baseline()
        sop.write_json(self.root / ".sop/tasks.json", {
            "schema_version": 1,
            "tasks": [{
                "id": "T-001", "status": "in_progress", "ac_ids": ["AC-999"],
                "implementation": ["missing.py"], "tests": ["tests/missing.py"],
                "evidence": ["local evidence"], "verification": "partial",
            }],
        })
        self.assertEqual(self.call("audit", "--project", self.root, "--stage", "L3"), 1)
        requirements = self.root / ".sop/docs/requirements.md"
        requirements.write_text(requirements.read_text(encoding="utf-8") + "\nAC-999\n", encoding="utf-8")
        (self.root / "missing.py").write_text("x = 1\n", encoding="utf-8")
        (self.root / "tests").mkdir()
        (self.root / "tests/missing.py").write_text("# test\n", encoding="utf-8")
        self.assertEqual(self.call("audit", "--project", self.root, "--stage", "L3"), 0)

    def test_audit_requires_platform_evidence_when_enabled(self):
        self.init("M")
        self.fill_docs()
        self.baseline()
        config = self.config()
        config["platform"] = {"required": True, "name": "Android"}
        self.save_config(config)
        (self.root / ".sop/docs/requirements.md").write_text(
            (self.root / ".sop/docs/requirements.md").read_text(encoding="utf-8") + "\nAC-001\n",
            encoding="utf-8")
        (self.root / "source.py").write_text("x = 1\n", encoding="utf-8")
        (self.root / "tests").mkdir()
        (self.root / "tests/test.py").write_text("# test\n", encoding="utf-8")
        sop.write_json(self.root / ".sop/tasks.json", {
            "schema_version": 1,
            "tasks": [{
                "id": "T-001", "status": "in_progress", "ac_ids": ["AC-001"],
                "implementation": ["source.py"], "tests": ["tests/test.py"], "evidence": ["local"],
                "verification": "partial",
            }],
        })
        self.assertEqual(self.call("audit", "--project", self.root, "--stage", "L3"), 1)
        record = sop.read_json(self.root / ".sop/platform-verification.json")
        record.update({"platform": "Android", "tool": "Android Emulator",
                       "tool_version": "test", "source_root": "app",
                       "compile": "passed", "smoke": "passed"})
        sop.write_json(self.root / ".sop/platform-verification.json", record)
        self.assertEqual(self.call("audit", "--project", self.root, "--stage", "L3"), 0)

    def test_done_task_requires_test_and_verification_sync(self):
        self.init("M")
        self.fill_docs()
        self.baseline()
        sop.write_json(self.root / ".sop/tasks.json", {
            "schema_version": 1,
            "tasks": [{
                "id": "T-001", "status": "done", "ac_ids": ["AC-001"],
                "implementation": ["source.py"], "tests": ["tests/test.py"],
                "evidence": [".sop/evidence/latest.json"],
                "verification": "pending",
            }],
        })
        self.assertEqual(self.call("sync", "--project", self.root, "--stage", "L3"), 2)
        self.tasks_done()
        self.sync("L3")
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L3"), 1)

    def test_missing_command_does_not_pass(self):
        self.init()
        self.assertEqual(self.call("verify", "--project", self.root), 1)
        report = sop.read_json(self.root / ".sop/evidence/latest.json")
        self.assertEqual(report["results"]["test"]["status"], "failed")

    def test_required_sections_and_quoted_instructions(self):
        self.init()
        self.fill_docs()
        path = self.root / ".sop/docs/constitution.md"
        original = path.read_text(encoding="utf-8")
        path.write_text(original.replace("## 不做什么", "## Different heading"), encoding="utf-8")
        self.assertIn("缺少章节内容: constitution / 不做什么",
                      sop.document_issues(self.root, "constitution"))
        path.write_text(original.replace("Test-only fixture, not a real decision.",
                                         "> Instructions only."), encoding="utf-8")
        self.assertTrue(sop.document_issues(self.root, "constitution"))
        path.write_text(original + "\nNEEDS CLARIFICATION: business rule\n", encoding="utf-8")
        self.assertEqual(self.call("check", "--project", self.root), 1)

    def test_new_modules_and_portable_guides(self):
        self.assertEqual(self.call("init", self.root, "--profile", "S",
                                   "--module", "research", "--module", "development"), 0)
        for name in ("research", "development", "validation", "handover"):
            self.assertTrue((self.root / ".sop/docs" / (name + ".md")).is_file())
        self.assertEqual(len(list((self.root / ".sop/core/stages").glob("*.md"))), 7)
        runtime = self.root / ".sop/runtime"
        self.assertTrue((runtime / "examples/task-list/sop-docs/validation.md").is_file())
        self.assertTrue((runtime / "docs/source-map.md").is_file())
        # Follow the distributed documents without access to Obsidian or the source package.
        for path in runtime.rglob("*.md"):
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                target = target.split("#")[0]
                self.assertTrue((path.parent / target).exists(), (path, target))

    def test_full_stack_stack_generates_cross_boundary_docs(self):
        self.assertEqual(self.call("init", self.root, "--profile", "M",
                                   "--risk", "high", "--stack", "full-stack"), 0)
        config = self.config()
        self.assertEqual(config["stack"], "full-stack")
        for name in ("architecture", "api-contract", "data-migrations", "environments"):
            self.assertTrue((self.root / ".sop/docs" / (name + ".md")).is_file())
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("第一条切片必须穿过真实客户端、API、业务服务和数据库", agents)

    def test_platform_validation_guidance_is_packaged(self):
        self.init()
        validation = (self.root / ".sop/core/stages/05-validation.md").read_text(encoding="utf-8")
        protocol = (self.root / ".sop/runtime/docs/protocol.md").read_text(encoding="utf-8")
        workflow = (self.root / ".sop/core/workflow.md").read_text(encoding="utf-8")
        agents = (self.root / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("目标平台与源码边界", validation)
        self.assertIn("目标平台/运行时", protocol)
        self.assertIn("平台编译/打包", agents)
        self.assertIn("每次任务的强制闭环", workflow)
        self.assertIn("`check --stage L4`", workflow)
        self.assertIn("scope_sha256", protocol)
        self.assertIn("UI 与手势验证", validation)
        self.assertIn("生产级证据链", protocol)
        self.assertIn("重新评估 risk", agents)
        self.assertIn("state.json.target_stage", agents)
        self.assertIn("audit --stage", agents)
        self.assertTrue((self.root / ".sop/platform-verification.json").exists())
        self.assertTrue((self.root / ".sop/runtime/docs/platforms.md").exists())
        self.assertIn("状态、基线与恢复", (self.root / ".sop/docs/plan.md").read_text(encoding="utf-8"))
        self.assertIn("交付门核对", (self.root / ".sop/docs/handover.md").read_text(encoding="utf-8"))

    def test_command_failure_and_log(self):
        self.init()
        config = self.config()
        config["commands"]["test"] = [sys.executable, "-c", "print('failure evidence'); raise SystemExit(7)"]
        self.save_config(config)
        self.assertEqual(self.call("verify", "--project", self.root), 1)
        report = sop.read_json(self.root / ".sop/evidence/latest.json")
        self.assertEqual(report["results"]["test"]["exit_code"], 7)
        self.assertIn("failure evidence", (self.root / report["results"]["test"]["log"]).read_text())

    def test_timeout(self):
        self.init()
        config = self.config()
        config["timeout_seconds"] = 1
        config["commands"]["test"] = [sys.executable, "-c", "import time; time.sleep(5)"]
        self.save_config(config)
        self.assertEqual(self.call("verify", "--project", self.root), 1)
        report = sop.read_json(self.root / ".sop/evidence/latest.json")
        self.assertEqual(report["results"]["test"]["status"], "timeout")

    def test_nonexistent_executable(self):
        self.init()
        config = self.config()
        config["commands"]["test"] = ["vibe-sop-nonexistent-executable"]
        self.save_config(config)
        self.assertEqual(self.call("verify", "--project", self.root), 1)

    def test_success_needs_human_and_source_changes_invalidate(self):
        self.init()
        self.configure_success()
        self.fill_docs()
        self.tasks_done()
        self.baseline()
        self.sync("L4")
        self.assertEqual(self.call("verify", "--project", self.root), 0)
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L4"), 1)
        self.approve("acceptance")
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L4"), 0)
        (self.root / "new-source.py").write_text("x = 1\n")
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L4"), 1)

    def test_config_and_log_changes_invalidate(self):
        self.init()
        self.configure_success()
        self.fill_docs()
        self.tasks_done()
        self.baseline()
        self.sync("L4")
        self.call("verify", "--project", self.root)
        self.approve("acceptance")
        report = sop.read_json(self.root / ".sop/evidence/latest.json")
        log = self.root / report["results"]["test"]["log"]
        original = log.read_bytes()
        log.write_text("tampered")
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L4"), 1)
        log.write_bytes(original)
        config = self.config()
        config["timeout_seconds"] = 10
        self.save_config(config)
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L4"), 1)

    def test_source_change_during_execution(self):
        self.init()
        config = self.config()
        config["commands"]["test"] = [sys.executable, "-c",
                                     "from pathlib import Path; Path('source.py').write_text('changed')"]
        self.save_config(config)
        self.assertEqual(self.call("verify", "--project", self.root), 1)

    def test_document_change_invalidates_review(self):
        self.init("M")
        self.fill_docs()
        self.approve("requirements")
        self.approve("design")
        self.baseline()
        self.sync("L2")
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L2"), 0)
        (self.root / ".sop/docs/requirements.md").write_text("# Requirement\nNew behavior.")
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L2"), 1)

    def test_malformed_config_and_state(self):
        self.init()
        config = self.config()
        config["timeout_seconds"] = True
        self.save_config(config)
        self.assertEqual(self.call("check", "--project", self.root), 2)
        config["timeout_seconds"] = 10
        self.save_config(config)
        sop.write_json(self.root / ".sop/state.json", {"target_stage": "L9", "reviews": {}})
        self.assertEqual(self.call("check", "--project", self.root), 2)

    def test_handover_preserves_blockers(self):
        self.init()
        self.assertEqual(self.call("handover", "--project", self.root), 0)
        record = sop.read_json(next((self.root / ".sop/handover").glob("*.json")))
        self.assertFalse(record["ready"])
        self.assertTrue(record["blockers"])
        self.assertFalse(record["handover_complete"])
        self.assertTrue(record["handover_issues"])

    def test_handover_links_completed_narrative_without_claiming_delivery(self):
        self.init()
        self.fill_docs()
        self.assertEqual(self.call("handover", "--project", self.root), 0)
        record = sop.read_json(next((self.root / ".sop/handover").glob("*.json")))
        self.assertFalse(record["ready"])
        self.assertTrue(record["handover_complete"])
        self.assertEqual(record["narrative"]["sha256"],
                         sop.sha(self.root / record["narrative"]["path"]))

    def test_evidence_path_escape_rejected(self):
        self.init()
        self.configure_success()
        self.fill_docs()
        self.tasks_done()
        self.baseline()
        self.sync("L4")
        self.approve("acceptance")
        path = self.root / ".sop/state.json"
        state = sop.read_json(path)
        state["reviews"]["acceptance"]["evidence"] = "../outside.md"
        sop.write_json(path, state)
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L4"), 2)

    def test_modules_and_high_risk_require_extra_gates(self):
        self.assertEqual(self.call("init", self.root, "--profile", "S", "--risk", "high",
                                   "--module", "wireframe"), 0)
        self.assertTrue((self.root / ".sop/docs/wireframe.md").exists())
        self.configure_success()
        self.fill_docs()
        self.tasks_done()
        self.baseline()
        self.sync("L4")
        self.call("verify", "--project", self.root)
        self.approve("acceptance")
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L4"), 1)
        self.approve("release")
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L4"), 0)

    def test_missing_and_changed_review_evidence(self):
        self.init()
        self.configure_success()
        self.fill_docs()
        self.call("verify", "--project", self.root)
        self.approve("acceptance")
        evidence = self.root / ".sop/reviews/acceptance.md"
        evidence.write_text("different decision")
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L4"), 1)
        evidence.unlink()
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L4"), 1)

    def test_invalid_profile_and_version_fail(self):
        self.init()
        config = self.config()
        config["profile"] = "../S"
        self.save_config(config)
        self.assertEqual(self.call("check", "--project", self.root), 2)
        config["profile"] = "S"
        config["sop_version"] = "99.0.0"
        self.save_config(config)
        self.assertEqual(self.call("check", "--project", self.root), 2)

    def test_pinned_runtime_independent(self):
        self.init()
        run = subprocess.run([sys.executable, str(self.root / ".sop/runtime/sop.py"),
                              "check", "--project", str(self.root), "--json"],
                             capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 1, run.stderr)
        self.assertFalse(json.loads(run.stdout)["ready"])
        demo_data = self.root / ".sop/runtime/examples/task-list/build/demo.db"
        demo_data.parent.mkdir()
        demo_data.write_bytes(b"private demo data must not propagate")
        second = self.root.parent / "second"
        run = subprocess.run([sys.executable, str(self.root / ".sop/runtime/sop.py"),
                              "init", str(second)], capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertFalse((second / ".sop/runtime/examples/task-list/build").exists())

    def test_generated_jest_cache_does_not_invalidate_source_fingerprint(self):
        self.init()
        before = sop.fingerprint(self.root)
        cache = self.root / ".jest-cache"
        cache.mkdir()
        (cache / "transform-cache").write_text("generated", encoding="utf-8")
        self.assertEqual(sop.fingerprint(self.root), before)

    def test_real_example_tests(self):
        shutil.copytree(sop.PACKAGE / "examples/counter", self.root,
                        ignore=shutil.ignore_patterns("__pycache__", ".sop"))
        self.init()
        config = self.config()
        config["commands"]["test"] = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
        self.save_config(config)
        self.assertEqual(self.call("verify", "--project", self.root), 0)
        (self.root / "counter.py").write_text("def count_nonempty(text):\n    return 0\n")
        self.assertEqual(self.call("verify", "--project", self.root), 1)

    def test_documented_task_list_end_to_end_and_mutation(self):
        shutil.copytree(sop.PACKAGE / "examples/task-list", self.root,
                        ignore=shutil.ignore_patterns("__pycache__", ".sop", "build"))
        self.init("M")
        for path in (self.root / "sop-docs").glob("*.md"):
            shutil.copy2(path, self.root / ".sop/docs" / path.name)
        config = self.config()
        config["commands"] = {
            "test": [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            "build": [sys.executable, "-m", "compileall", "-q", "task_store.py", "cli.py"]}
        self.save_config(config)
        for name in sop.requirements(config)["documents"] + ["handover"]:
            self.assertEqual(sop.document_issues(self.root, name), [], name)
        self.tasks_done()
        self.baseline()
        self.sync("L0")
        self.assertEqual(self.call("check", "--project", self.root, "--stage", "L0"), 0)
        self.assertEqual(self.call("verify", "--project", self.root), 0)
        self.sync("L4")
        report = sop.read_json(self.root / ".sop/evidence/latest.json")
        test_log = (self.root / report["results"]["test"]["log"]).read_text(encoding="utf-8")
        self.assertIn("Ran 9 tests", test_log)
        blockers = sop.inspection(self.root, config, 4)
        self.assertEqual(len(blockers), 3, blockers)
        self.assertTrue(all(item.startswith("人工复核待完成:") for item in blockers))
        self.assertTrue(all(record["status"] == "pending" for record in
                            sop.read_json(self.root / ".sop/state.json")["reviews"].values()))
        path = self.root / "task_store.py"
        content = path.read_text(encoding="utf-8")
        self.assertIn("SET status='done'", content)
        path.write_text(content.replace("SET status='done'", "SET status='pending'"),
                        encoding="utf-8")
        self.assertEqual(self.call("verify", "--project", self.root), 1)
        failed = sop.read_json(self.root / ".sop/evidence/latest.json")
        self.assertEqual(failed["results"]["test"]["status"], "failed")
        self.assertEqual(failed["results"]["build"]["status"], "passed")


if __name__ == "__main__":
    unittest.main()
