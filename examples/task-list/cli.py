"""Offline task CLI; output is JSON and user errors exit with code 2."""
import argparse
import json
import sqlite3
import sys

from task_store import TaskStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="build/tasks.db")
    commands = parser.add_subparsers(dest="action", required=True)
    add = commands.add_parser("add")
    add.add_argument("title")
    commands.add_parser("list")
    complete = commands.add_parser("complete")
    complete.add_argument("id", type=int)
    args = parser.parse_args()
    try:
        store = TaskStore(args.db)
        if args.action == "add":
            result = store.add(args.title)
        elif args.action == "complete":
            result = store.complete(args.id)
        else:
            result = store.list_tasks()
    except (ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError):
        print("storage unavailable; check the database path and permissions", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
