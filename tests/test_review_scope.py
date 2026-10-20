import tempfile
import unittest
from pathlib import Path

import sop


class ReviewScopeTests(unittest.TestCase):
    def setUp(self):
        test_temp_root = Path(__file__).resolve().parent / ".test-temp"
        test_temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=test_temp_root)
        self.root = Path(self.temp.name)
        docs = self.root / ".sop/docs"
        docs.mkdir(parents=True)
        for name in ("constitution", "requirements", "design", "plan", "validation"):
            (docs / f"{name}.md").write_text(f"{name} v1", encoding="utf-8")
        (self.root / ".sop").mkdir(exist_ok=True)
        (self.root / ".sop/tasks.json").write_text(
            '{"release":{"required_task_ids":["T-1"],"required_ac_ids":["AC-1"]}}',
            encoding="utf-8")
        (self.root / ".sop/platform-flows.json").write_text(
            '{"flows":[{"id":"MP-1","required":true,"status":"planned"}]}',
            encoding="utf-8")
        (self.root / "app.ts").write_text("const version = 1;", encoding="utf-8")
        self.config = {"profile": "M", "risk": "normal", "stack": "default"}
        self.spec = {"documents": ["constitution", "requirements", "design", "plan", "validation"]}

    def tearDown(self):
        self.temp.cleanup()

    def test_acceptance_scope_tracks_acceptance_criteria_not_code_or_validation_notes(self):
        first = sop.review_scope(self.root, self.config, self.spec, "acceptance")
        (self.root / "app.ts").write_text("const version = 2;", encoding="utf-8")
        (self.root / ".sop/docs/validation.md").write_text("new test log", encoding="utf-8")
        self.assertEqual(first, sop.review_scope(self.root, self.config, self.spec, "acceptance"))
        (self.root / ".sop/docs/requirements.md").write_text("requirements v2", encoding="utf-8")
        self.assertNotEqual(first, sop.review_scope(self.root, self.config, self.spec, "acceptance"))

    def test_release_scope_tracks_code_release_tasks_and_platform_flows(self):
        first = sop.review_scope(self.root, self.config, self.spec, "release")
        (self.root / "app.ts").write_text("const version = 2;", encoding="utf-8")
        self.assertNotEqual(first, sop.review_scope(self.root, self.config, self.spec, "release"))
        second = sop.review_scope(self.root, self.config, self.spec, "release")
        (self.root / ".sop/platform-flows.json").write_text(
            '{"flows":[{"id":"MP-1","required":true,"status":"passed"}]}',
            encoding="utf-8")
        self.assertNotEqual(second, sop.review_scope(self.root, self.config, self.spec, "release"))

    def test_design_scope_ignores_command_tuning_but_tracks_platform_boundary(self):
        first = sop.review_scope(self.root, self.config, self.spec, "design")
        self.config["timeout_seconds"] = 900
        self.assertEqual(first, sop.review_scope(self.root, self.config, self.spec, "design"))
        self.config["platform"] = {"required": True, "name": "mobile"}
        self.assertNotEqual(first, sop.review_scope(self.root, self.config, self.spec, "design"))

    def test_json_records_use_stable_lf_newlines(self):
        path = self.root / ".sop/state.json"
        sop.write_json(path, {"stage": "L4"})
        self.assertNotIn(b"\r\n", path.read_bytes())


if __name__ == "__main__":
    unittest.main()

