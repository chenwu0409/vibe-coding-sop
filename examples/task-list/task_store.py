"""Local task persistence. Public contracts are documented in sop-docs/design.md."""
import sqlite3
from contextlib import closing
from pathlib import Path


class TaskStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS tasks ("
                "id INTEGER PRIMARY KEY, title TEXT NOT NULL, "
                "status TEXT NOT NULL CHECK(status IN ('pending', 'done')))"
            )

    def _connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        return db

    def add(self, title):
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 120:
            raise ValueError("title length after trimming must be 1 to 120 characters")
        with closing(self._connect()) as db, db:
            row = db.execute("INSERT INTO tasks(title,status) VALUES (?, 'pending')",
                             (title.strip(),))
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (row.lastrowid,)).fetchone())

    def list_tasks(self):
        with closing(self._connect()) as db:
            return [dict(row) for row in db.execute("SELECT * FROM tasks ORDER BY id")]

    def complete(self, task_id):
        if type(task_id) is not int or task_id <= 0:
            raise ValueError("id must be a positive integer")
        with closing(self._connect()) as db, db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise KeyError("task not found")
            db.execute("UPDATE tasks SET status='done' WHERE id=?", (task_id,))
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
