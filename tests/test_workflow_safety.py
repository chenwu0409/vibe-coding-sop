"""Regression tests for SOP commands that can affect project history or evidence."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SOP_PATH = Path(__file__).resolve().parents[1] / "sop.py"
spec = importlib.util.spec_from_file_location("project_sop", SOP_PATH)
sop = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sop)


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        encoding="utf-8", check=True,
    ).stdout.strip()


class WorkflowSafetyTests(unittest.TestCase):
    def setUp(self):
        scratch = Path.cwd() / "build" / "sop-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project"
        self.root.mkdir()
        (self.root / ".sop").mkdir()
        (self.root / ".sop/.gitignore").write_text(
            "/git-baseline.json\n/checkpoints.json\n/evidence/\n", encoding="utf-8",
        )
        config = {
            "schema_version": 1,
            "sop_version": (SOP_PATH.parent / "VERSION").read_text().strip(),
            "name": "fixture", "profile": "S", "risk": "normal",
            "stack": "default", "modules": [], "timeout_seconds": 30,
            "commands": {"test": [sys.executable, "-c", "print('full')"],
                         "landing": [sys.executable, "-c", "print('focused')"]},
            "test_lifecycle": {"cleanup": [sys.executable, "-c", "print('cleanup')"]},
        }
        (self.root / ".sop/project.json").write_text(
            json.dumps(config), encoding="utf-8",
        )
        git(self.root, "init")
        git(self.root, "config", "user.name", "SOP Test")
        git(self.root, "config", "user.email", "sop-test@example.invalid")

    def run_sop(self, *args):
        return subprocess.run(
            [sys.executable, str(SOP_PATH), *args, "--project", str(self.root)],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_baseline_requires_explicit_initial_commit_and_never_commits_dirty_existing_repo(self):
        self.assertNotEqual(self.run_sop("baseline").returncode, 0)
        self.assertNotEqual(git(self.root, "status", "--porcelain"), "")
        git(self.root, "add", ".sop/project.json", ".sop/.gitignore")
        initial = self.run_sop("baseline", "--commit-initial")
        self.assertEqual(initial.returncode, 0, initial.stderr)
        first = git(self.root, "rev-parse", "HEAD")
        (self.root / "work.txt").write_text("unfinished", encoding="utf-8")
        result = self.run_sop("baseline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), first)
        self.assertIn("work.txt", git(self.root, "status", "--porcelain"))
        self.assertEqual(json.loads((self.root / ".sop/git-baseline.json").read_text())["commit"], first)

    def test_existing_clean_commit_can_be_named_without_creating_another_commit(self):
        git(self.root, "add", ".sop/project.json", ".sop/.gitignore")
        git(self.root, "commit", "-m", "prepared")
        first = git(self.root, "rev-parse", "HEAD")
        result = self.run_sop("baseline")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(git(self.root, "rev-parse", "HEAD"), first)

    def test_initial_baseline_rejects_staged_env_file(self):
        (self.root / ".env").write_text("PASSWORD=synthetic\n", encoding="utf-8")
        git(self.root, "add", "-f", ".env")
        result = self.run_sop("baseline", "--commit-initial")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(".env", result.stderr)
        self.assertNotEqual(git(self.root, "status", "--porcelain"), "")
        head = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
        )
        self.assertNotEqual(head.returncode, 0)

    def test_initial_baseline_rejects_unstaged_files_before_commit(self):
        git(self.root, "add", ".sop/project.json", ".sop/.gitignore")
        (self.root / "unfinished.txt").write_text("draft", encoding="utf-8")
        result = self.run_sop("baseline", "--commit-initial")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unfinished.txt", git(self.root, "status", "--porcelain"))
        head = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
        )
        self.assertNotEqual(head.returncode, 0)

    def test_focused_verify_keeps_full_latest_evidence_and_runs_cleanup(self):
        latest = self.root / ".sop/evidence/latest.json"
        latest.parent.mkdir()
        latest.write_text('{"run_id":"previous-full"}', encoding="utf-8")
        result = self.run_sop("verify", "--gate", "landing")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(latest.read_text())["run_id"], "previous-full")
        report = json.loads((self.root / ".sop/evidence/focused-latest.json").read_text())
        self.assertEqual(report["scope"], "focused")
        self.assertEqual(list(report["results"]), ["landing"])
        self.assertEqual(report["lifecycle"]["cleanup"]["status"], "passed")
        self.assertNotEqual(self.run_sop("verify", "--gate", "missing").returncode, 0)

    def test_full_verify_runs_declared_release_gates_and_rejects_missing_platform_e2e(self):
        path = self.root / ".sop/project.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["release_gates"] = ["test", "landing"]
        path.write_text(json.dumps(config), encoding="utf-8")
        result = self.run_sop("verify")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads((self.root / ".sop/evidence/latest.json").read_text())
        self.assertEqual(report["gates"], ["test", "landing"])
        config["platform"] = {"required": True, "name": "web-chrome"}
        config["commands"]["e2e"] = [sys.executable, "-c", "print('browser')"]
        path.write_text(json.dumps(config), encoding="utf-8")
        rejected = self.run_sop("verify")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("e2e", rejected.stderr)

    def test_structured_gate_counts_and_artifact_hashes_are_recorded(self):
        path = self.root / ".sop/project.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        config["commands"]["landing"] = [sys.executable, "-c",
            "from pathlib import Path; p=Path('build/screenshot.png'); p.parent.mkdir(exist_ok=True); "
            "p.write_bytes(b'image'); print('# tests 2\\n# pass 2\\n# fail 0\\n# skipped 0')"]
        config["gate_summary_formats"] = {"landing": "node-test"}
        config["gate_artifacts"] = {"landing": ["build/*.png"]}
        path.write_text(json.dumps(config), encoding="utf-8")
        result = self.run_sop("verify", "--gate", "landing")
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        report = json.loads((self.root / ".sop/evidence/focused-latest.json").read_text())
        gate = report["results"]["landing"]
        self.assertEqual(gate["summary"]["total"], 2)
        self.assertEqual(gate["summary"]["skipped"], 0)
        self.assertEqual(gate["artifacts"][0]["path"], "build/screenshot.png")
        config["commands"]["landing"] = [sys.executable, "-c", "print('no counts')"]
        path.write_text(json.dumps(config), encoding="utf-8")
        missing = self.run_sop("verify", "--gate", "landing")
        self.assertNotEqual(missing.returncode, 0)

    def test_task_guard_is_independent_of_release_readiness(self):
        docs = self.root / ".sop/docs"
        docs.mkdir()
        (docs / "requirements.md").write_text("# AC-001\n", encoding="utf-8")
        (self.root / "feature.py").write_text("pass\n", encoding="utf-8")
        (self.root / "test_feature.py").write_text("pass\n", encoding="utf-8")
        evidence = self.root / ".sop/evidence/story.txt"
        evidence.parent.mkdir()
        evidence.write_text("verified", encoding="utf-8")
        board = {
            "schema_version": 2,
            "release": {"id": "future-release", "required_task_ids": ["T-001"],
                        "required_ac_ids": ["AC-001"]},
            "tasks": [{"id": "T-001", "status": "done", "verification": "passed",
                       "ac_ids": ["AC-001"], "implementation": ["feature.py"],
                       "tests": ["test_feature.py"],
                       "evidence": [".sop/evidence/story.txt"]}],
        }
        (self.root / ".sop/tasks.json").write_text(json.dumps(board), encoding="utf-8")
        git(self.root, "add", ".sop", "feature.py", "test_feature.py")
        git(self.root, "commit", "-m", "T-001 verified")
        baseline = self.run_sop("baseline")
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        missing = self.run_sop("guard", "--task", "T-001", "--json")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("checkpoint", json.loads(missing.stdout)["blockers"][0])
        checkpoint = {"schema_version": 1,
                      "tasks": {"T-001": {"commit": git(self.root, "rev-parse", "HEAD")}},
                      "stages": {}}
        (self.root / ".sop/checkpoints.json").write_text(json.dumps(checkpoint), encoding="utf-8")
        result = self.run_sop("guard", "--task", "T-001", "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["ready"])
        self.assertTrue(data["required_for_release"])
        self.assertIn("--stage L4", data["release_check"])

    def test_init_carries_runtime_regressions_and_safe_baseline_instructions(self):
        target = Path(self.temporary.name) / "new-project"
        result = subprocess.run(
            [sys.executable, str(SOP_PATH), "init", str(target), "--name", "fixture"],
            capture_output=True, text=True, encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((target / ".sop/runtime/tests/test_workflow_safety.py").is_file())
        self.assertIn("--commit-initial", (target / "AGENTS.md").read_text(encoding="utf-8"))

    def test_platform_attestation_tracks_app_files_and_flow_definition(self):
        config_path = self.root / ".sop/project.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["platform"] = {"required": True, "name": "web-chrome", "source_paths": ["app"]}
        config_path.write_text(json.dumps(config), encoding="utf-8")
        app = self.root / "app"
        app.mkdir()
        (app / "page.js").write_text("page one", encoding="utf-8")
        flows_path = self.root / ".sop/platform-flows.json"
        flows = {"schema_version": 1, "platform": "web-chrome",
                 "source": ["app/page.js"], "pages": [{"path": "/", "description": "home"}],
                 "flows": [{"id": "FLOW-001", "title": "open", "entry": "/",
                            "required": True, "steps": ["open"], "status": "passed",
                            "evidence": [".sop/evidence/smoke.txt"]}]}
        flows_path.write_text(json.dumps(flows), encoding="utf-8")
        evidence = self.root / ".sop/evidence"
        evidence.mkdir()
        (evidence / "build.txt").write_text("built", encoding="utf-8")
        (evidence / "smoke.txt").write_text("opened", encoding="utf-8")
        git(self.root, "add", ".sop", "app")
        git(self.root, "commit", "-m", "app base")
        baseline = self.run_sop("baseline")
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        result = self.run_sop(
            "attest-platform", "--environment", "local-dev", "--tool", "Chrome",
            "--tool-version", "1", "--source-root", "app",
            "--compile-evidence", ".sop/evidence/build.txt",
            "--smoke-evidence", ".sop/evidence/smoke.txt",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        record = json.loads((self.root / ".sop/platform-verification.json").read_text())
        self.assertEqual(record["schema_version"], 3)
        (self.root / "handover.txt").write_text("docs only", encoding="utf-8")
        self.assertEqual(sop.platform_issues(self.root, config, 4), [])
        flows["flows"][0]["evidence"].append(".sop/evidence/build.txt")
        flows_path.write_text(json.dumps(flows), encoding="utf-8")
        self.assertEqual(sop.platform_issues(self.root, config, 4), [])
        (app / "new.js").write_text("new app file", encoding="utf-8")
        self.assertTrue(any("应用源码已变化" in item for item in sop.platform_issues(self.root, config, 4)))

    def test_new_release_requires_explicit_scope_and_backlog_decision(self):
        docs = self.root / ".sop/docs"
        docs.mkdir()
        (docs / "requirements.md").write_text("AC-001 AC-002", encoding="utf-8")
        board = {"schema_version": 2,
                 "release": {"id": "old", "required_task_ids": ["T-001", "T-002"],
                             "required_ac_ids": ["AC-001", "AC-002"]},
                 "tasks": [
                     {"id": "T-001", "status": "in_progress", "verification": "pending",
                      "ac_ids": ["AC-001"]},
                     {"id": "T-002", "status": "done", "verification": "passed",
                      "ac_ids": ["AC-002"]},
                 ]}
        path = self.root / ".sop/tasks.json"
        path.write_text(json.dumps(board), encoding="utf-8")
        blocked_preview = self.run_sop("release", "open", "new", "--task", "T-002")
        self.assertEqual(blocked_preview.returncode, 0, blocked_preview.stderr)
        self.assertEqual(json.loads(blocked_preview.stdout)["missing_backlog_decision"], ["T-001"])
        rejected = self.run_sop("release", "open", "new", "--task", "T-002", "--apply")
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(json.loads(path.read_text())["release"]["id"], "old")
        board["tasks"][0].update(delivery_disposition="backlog", defer_reason="deferred",
                                 owner="maintainer", next_action="finish test")
        path.write_text(json.dumps(board), encoding="utf-8")
        preview = self.run_sop("release", "open", "new", "--task", "T-002")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertFalse(json.loads(preview.stdout)["applied"])
        self.assertEqual(json.loads(path.read_text())["release"]["id"], "old")
        applied = self.run_sop("release", "open", "new", "--task", "T-002", "--apply")
        self.assertEqual(applied.returncode, 0, applied.stderr)
        changed = json.loads(path.read_text())
        self.assertEqual(changed["release"]["required_task_ids"], ["T-002"])
        self.assertEqual(changed["release"]["required_ac_ids"], ["AC-002"])
        self.assertEqual(changed["release_history"][0]["unfinished_task_ids"], ["T-001"])


if __name__ == "__main__":
    unittest.main()
