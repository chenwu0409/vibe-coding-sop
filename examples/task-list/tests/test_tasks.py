import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from task_store import TaskStore

ROOT = Path(__file__).resolve().parents[1]


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tasks.db"
        self.store = TaskStore(self.path)

    def test_tc_task_001_persists_after_reopen(self):
        task = self.store.add("  整理发票  ")
        self.assertGreater(task["id"], 0)
        self.assertEqual(TaskStore(self.path).list_tasks(),
                         [{"id": task["id"], "title": "整理发票", "status": "pending"}])

    def test_tc_task_002_invalid_title_never_inserts(self):
        for title in ("", " \t", "a" * 121, None):
            with self.subTest(title=title), self.assertRaises(ValueError):
                self.store.add(title)
        self.assertEqual(self.store.list_tasks(), [])

    def test_tc_task_003_title_boundary(self):
        self.assertEqual(self.store.add("a")["title"], "a")
        self.assertEqual(len(self.store.add("a" * 120)["title"]), 120)

    def test_tc_task_004_complete_is_idempotent(self):
        task = self.store.add("read")
        first = self.store.complete(task["id"])
        second = self.store.complete(task["id"])
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "done")
        self.assertEqual(len(self.store.list_tasks()), 1)

    def test_tc_task_005_missing_and_invalid_ids(self):
        for task_id in (0, -1, True, "1"):
            with self.subTest(task_id=task_id), self.assertRaises(ValueError):
                self.store.complete(task_id)
        with self.assertRaises(KeyError):
            self.store.complete(42)
        self.assertEqual(self.store.list_tasks(), [])

    def test_tc_task_006_regression_order_and_existing_rows(self):
        first = self.store.add("first")
        second = self.store.add("second")
        self.store.complete(second["id"])
        rows = TaskStore(self.path).list_tasks()
        self.assertEqual([row["id"] for row in rows], [first["id"], second["id"]])
        self.assertEqual(rows[0], first)

    def test_tc_task_007_sql_text_is_data(self):
        title = "'); DROP TABLE tasks; --"
        self.assertEqual(self.store.add(title)["title"], title)
        self.assertEqual(len(self.store.list_tasks()), 1)

    def cli(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "cli.py"),
                               "--db", str(self.path), *args],
                              cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def test_tc_task_008_cli_end_to_end(self):
        added = self.cli("add", "整理发票")
        self.assertEqual(added.returncode, 0, added.stderr)
        task_id = json.loads(added.stdout)["id"]
        self.assertEqual(self.cli("complete", str(task_id)).returncode, 0)
        listed = self.cli("list")
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertEqual(json.loads(listed.stdout),
                         [{"id": task_id, "title": "整理发票", "status": "done"}])

    def test_tc_task_009_cli_error_and_empty_list(self):
        invalid = self.cli("add", " ")
        self.assertEqual(invalid.returncode, 2)
        self.assertTrue(invalid.stderr)
        self.assertEqual(json.loads(self.cli("list").stdout), [])


if __name__ == "__main__":
    unittest.main()
