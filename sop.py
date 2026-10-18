#!/usr/bin/env python3
"""Portable SOP bootstrap and evidence checks. Python 3.10+, standard library."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import uuid

PACKAGE = Path(__file__).resolve().parent
DOC_STAGE = {"constitution": 0, "requirements": 1, "glossary": 1,
             "wireframe": 1, "design": 2, "architecture": 2,
             "api-contract": 2, "data-migrations": 2, "risk": 2, "plan": 3,
             "environments": 3,
             "plan": 3,
             "tasks": 3, "regression": 3, "development": 3,
             "research": 1, "validation": 4}
MODULES = ("glossary", "wireframe", "regression", "research", "development",
           "architecture", "api-contract", "data-migrations", "environments")
STACK_MODULES = {
    "default": (),
    "full-stack": ("architecture", "api-contract", "data-migrations", "environments"),
}
STACK_COMMANDS = {
    "default": (),
    "full-stack": ("integration",),
}
REVIEW_STAGE = {"constitution": 0, "requirements": 1, "design": 2,
                "acceptance": 4, "release": 4}
EXCLUDED = {".git", ".sop", "__pycache__", ".venv", "venv", "node_modules",
            "target", "dist", "build", ".pytest_cache", ".mypy_cache", ".jest-cache",
            ".gradle", "coverage", ".next"}
PLACEHOLDER = re.compile(r"\bTODO\b|\bTBD\b|NEEDS CLARIFICATION|\{\{[^}]+\}\}", re.I)
TASK_STATUSES = {"planned", "in_progress", "blocked", "done"}
VERIFICATION_STATUSES = {"pending", "partial", "passed", "blocked"}
ENVIRONMENT_STATUSES = {"not_run", "passed", "failed", "blocked", "not_applicable"}
TASK_TRANSITIONS = {
    "start": ("in_progress", "pending"),
    "block": ("blocked", "blocked"),
    "verify": ("in_progress", "passed"),
    "done": ("done", "passed"),
}
MAX_LOG_BYTES = 10 * 1024 * 1024


class SopError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Replace the entire record only after serialization succeeds.
    content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def json_digest(value):
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def redact_text(value):
    """Remove common credentials before text reaches persistent evidence."""
    text = value if isinstance(value, str) else str(value)
    substitutions = (
        (r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+", r"\1[REDACTED:BEARER]"),
        (r"(?i)(cookie|set-cookie)(\s*:\s*)[^\r\n]+", r"\1\2[REDACTED:COOKIE]"),
        (r"(?i)\b(postgres(?:ql)?|mysql)://[^\s:@/]+:[^@\s/]+@",
         r"\1://[REDACTED:DATABASE_CREDENTIALS]@"),
        (r"(?i)((?:database_url|password|passwd|token|secret|api[_-]?key)\s*[=:]\s*)[^\s'\"]+",
         r"\1[REDACTED:VALUE]"),
        (r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
         "[REDACTED:JWT]"),
    )
    for pattern, replacement in substitutions:
        text = re.sub(pattern, replacement, text)
    return text


def sanitized_value(value, key=""):
    if re.search(r"password|passwd|token|secret|api[_-]?key|database_url", key, re.I):
        return "[REDACTED:CONFIG]"
    if isinstance(value, dict):
        return {item_key: sanitized_value(item, str(item_key))
                for item_key, item in value.items()}
    if isinstance(value, list):
        return [sanitized_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def execute_command(root, argv, timeout, log_path, environment=None):
    exit_code = None
    status = "failed"
    output = ""
    if not command_valid(argv):
        output = "未配置有效参数数组\n"
    else:
        try:
            run = subprocess.run(
                argv, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=timeout, shell=False, env=environment,
            )
            exit_code = run.returncode
            status = "passed" if exit_code == 0 else "failed"
            output = run.stdout.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired as error:
            captured = error.stdout or b""
            output = captured.decode("utf-8", errors="replace") + "\nSOP: command timed out\n"
            status = "timeout"
        except OSError as error:
            output = str(error)
    output = redact_text(output)
    encoded = output.encode("utf-8")
    if len(encoded) > MAX_LOG_BYTES:
        encoded = encoded[:MAX_LOG_BYTES] + b"\nSOP: log truncated\n"
        output = encoded.decode("utf-8", errors="replace")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")
    return {"status": status, "exit_code": exit_code,
            "log": log_path.relative_to(root).as_posix(),
            "log_sha256": sha(log_path)}


def git_run(root, arguments, check=False):
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *arguments],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        raise SopError("本地 Git 不可用: " + str(error)) from error
    if check and result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise SopError("Git 命令失败: " + message)
    return result


def local_git_issues(root):
    result = git_run(root, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        return ["项目必须由本地 Git 管理；请先运行 baseline 初始化基线"]
    try:
        git_root = Path(result.stdout.strip()).resolve()
    except OSError:
        return ["无法解析本地 Git 根目录"]
    if git_root != root.resolve():
        return ["项目必须有自己的本地 Git 根目录，不能只依赖父目录仓库"]
    metadata = root / ".sop/git-baseline.json"
    if not metadata.is_file():
        return ["缺少本地 Git 基线：运行 `python .sop/runtime/sop.py baseline`"]
    try:
        record = read_json(metadata)
    except (OSError, ValueError, TypeError):
        return ["本地 Git 基线文件损坏：重新运行 baseline"]
    commit = record.get("commit") if isinstance(record, dict) else ""
    if not isinstance(commit, str) or not commit:
        return ["本地 Git 基线缺少 commit：重新运行 baseline"]
    exists = git_run(root, ["cat-file", "-e", commit + "^{commit}"])
    if exists.returncode != 0:
        return ["本地 Git 基线提交不存在：重新建立 baseline"]
    return []


def sync_fingerprint(root, config, spec, stage):
    payload = {
        "stage": stage,
        "source": fingerprint(root),
        "config": config,
        "tasks": sha(root / ".sop/tasks.json") if (root / ".sop/tasks.json").is_file() else "MISSING",
        # Hash every configured project document so an Agent cannot leave a later-stage
        # document stale while keeping target_stage at an earlier value.
        "documents": document_digest(root, spec["documents"]),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def task_issues(root, stage):
    path = root / ".sop/tasks.json"
    if stage < 3:
        return []
    if not path.is_file():
        return ["缺少 .sop/tasks.json：必须登记任务、AC、测试和验证状态"]
    try:
        board = read_json(path)
    except (OSError, ValueError, TypeError):
        return [".sop/tasks.json 格式错误"]
    tasks = board.get("tasks") if isinstance(board, dict) else None
    if not isinstance(tasks, list) or not tasks:
        return [".sop/tasks.json 必须至少包含一项任务"]
    issues = []
    seen = set()
    task_ids = {task.get("id") for task in tasks if isinstance(task, dict)}
    schema = board.get("schema_version")
    release = board.get("release", {}) if schema == 2 else {}
    if schema not in (1, 2):
        issues.append(".sop/tasks.json schema_version 必须为 1 或 2")
    if schema == 2:
        if not isinstance(release, dict) or not isinstance(release.get("id"), str) or not release["id"].strip():
            issues.append("tasks schema v2 缺少 release.id")
        for field in ("required_task_ids", "required_ac_ids"):
            values = release.get(field) if isinstance(release, dict) else None
            if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
                issues.append("tasks schema v2 的 release." + field + " 必须为字符串数组")
        required_ids = set(release.get("required_task_ids", [])) if isinstance(release, dict) else set()
        if stage == 4 and not required_ids:
            issues.append("L4 的 release.required_task_ids 不能为空")
        if stage == 4 and not set(release.get("required_ac_ids", [])):
            issues.append("L4 的 release.required_ac_ids 不能为空")
        for missing in sorted(required_ids - task_ids):
            issues.append("release 引用了不存在的任务: " + missing)
    else:
        required_ids = task_ids
    for index, task in enumerate(tasks, 1):
        prefix = f"任务 #{index}"
        if not isinstance(task, dict):
            issues.append(prefix + "必须是对象")
            continue
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id.strip() or task_id in seen:
            issues.append(prefix + "缺少唯一 id")
        seen.add(task_id)
        status = task.get("status")
        verification = task.get("verification")
        if status not in TASK_STATUSES:
            issues.append(prefix + " status 必须为 planned/in_progress/blocked/done")
        if verification not in VERIFICATION_STATUSES:
            issues.append(prefix + " verification 必须为 pending/partial/passed/blocked")
        for field in ("ac_ids", "implementation", "tests", "evidence"):
            if not isinstance(task.get(field), list) or not task[field]:
                issues.append(prefix + " 缺少非空 " + field)
        if status == "done" and verification != "passed":
            issues.append(prefix + " 已标记 done 但 verification 不是 passed")
        if (schema == 2 and stage == 4 and task_id not in required_ids
                and status != "done"):
            if task.get("delivery_disposition") != "backlog":
                issues.append(prefix + " 不在本次 release 且未完成，必须标记 delivery_disposition=backlog")
            for field in ("defer_reason", "owner", "next_action"):
                if not isinstance(task.get(field), str) or not task[field].strip():
                    issues.append(prefix + " backlog 缺少 " + field)
    return issues


def task_entry(root, task_id):
    path = root / ".sop/tasks.json"
    if not path.is_file():
        raise SopError("缺少 .sop/tasks.json：先初始化任务清单")
    board = read_json(path)
    tasks = board.get("tasks") if isinstance(board, dict) else None
    if not isinstance(tasks, list):
        raise SopError(".sop/tasks.json 的 tasks 必须为数组")
    task = next((item for item in tasks
                 if isinstance(item, dict) and item.get("id") == task_id), None)
    if task is None:
        raise SopError("任务不存在: " + task_id)
    return board, task


def task_transition_issues(root, task, action):
    if action not in TASK_TRANSITIONS:
        return ["未知任务动作: " + action]
    target_status, target_verification = TASK_TRANSITIONS[action]
    issues = []
    if action == "start" and task.get("status") not in ("planned", "blocked"):
        issues.append("只有 planned/blocked 任务可以 start")
    if action == "block" and task.get("status") == "done":
        issues.append("done 任务不能直接标记 blocked；先重新打开任务并说明影响")
    if action in ("verify", "done"):
        for field in ("ac_ids", "implementation", "tests", "evidence"):
            values = task.get(field)
            if not isinstance(values, list) or not values:
                issues.append("任务缺少非空 " + field)
        for value in task.get("tests", []):
            if not declared_path_exists(root, value):
                issues.append("tests 路径不存在: " + str(value))
        for value in task.get("evidence", []):
            if not evidence_path_exists(root, value):
                issues.append("evidence 文件不存在或为空: " + str(value))
        if task.get("status") == "planned":
            issues.append("任务必须先 start，再进行验证")
    if action == "block":
        for field in ("defer_reason", "owner", "next_action"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                issues.append("blocked 任务必须填写 " + field)
    if action == "done" and task.get("verification") != "passed":
        issues.append("任务必须先通过 task verify，才能 done")
    return issues


def task_project(args):
    root = Path(args.project).resolve()
    load_project(root)
    board, task = task_entry(root, args.task)
    if args.action == "block":
        if args.reason:
            task["defer_reason"] = args.reason
        if args.owner:
            task["owner"] = args.owner
        if args.next_action:
            task["next_action"] = args.next_action
    issues = task_transition_issues(root, task, args.action)
    if issues:
        raise SopError("任务状态转换被阻止:\n- " + "\n- ".join(issues))
    target_status, target_verification = TASK_TRANSITIONS[args.action]
    task["status"] = target_status
    task["verification"] = target_verification
    if args.action == "block":
        task["delivery_disposition"] = "backlog"
    if args.note:
        task["status_note"] = args.note
    write_json(root / ".sop/tasks.json", board)
    print(f"任务 {args.task} 已转换为 {target_status}/{target_verification}")
    print("下一步必须更新相关文档并运行 sync；本命令不替代测试、audit 或 checkpoint")
    return 0


def delivery_task_issues(root, stage):
    """Delivery readiness is stricter than the structural checks used by sync."""
    if stage < 4:
        return []
    board = read_json(root / ".sop/tasks.json")
    tasks = board.get("tasks", [])
    if board.get("schema_version") == 2:
        required_ids = set(board.get("release", {}).get("required_task_ids", []))
    else:
        required_ids = {task.get("id") for task in tasks if isinstance(task, dict)}
    issues = []
    for task in tasks:
        if not isinstance(task, dict) or task.get("id") not in required_ids:
            continue
        if task.get("status") != "done" or task.get("verification") != "passed":
            issues.append(f"任务 {task.get('id')} 属于本次交付范围，L4 要求 status=done 且 verification=passed")
        else:
            for evidence in task.get("evidence", []):
                if not evidence_path_exists(root, evidence):
                    issues.append(f"任务 {task.get('id')} 的 evidence 不存在或为空: {evidence}")
    return issues


def requirement_ac_ids(root):
    path = root / ".sop/docs/requirements.md"
    if not path.is_file():
        return set()
    return set(re.findall(r"\bAC-\d{3}\b", path.read_text(encoding="utf-8")))


def declared_path_exists(root, value):
    if not isinstance(value, str) or not value.strip():
        return False
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return False
    if any(character in value for character in "*?[]"):
        return any(root.glob(value))
    return (root / path).is_file()


def evidence_path_exists(root, value):
    if not declared_path_exists(root, value):
        return False
    try:
        return (root / value).stat().st_size > 0
    except (OSError, TypeError):
        return False


def audit_issues(root, config, stage):
    """Check task declarations against project facts without modifying files."""
    if stage < 3:
        return []
    path = root / ".sop/tasks.json"
    if not path.is_file():
        return ["audit: 缺少 .sop/tasks.json"]
    try:
        board = read_json(path)
    except (OSError, ValueError, TypeError):
        return ["audit: .sop/tasks.json 格式错误"]
    tasks = board.get("tasks") if isinstance(board, dict) else None
    if not isinstance(tasks, list):
        return ["audit: tasks 必须为数组"]
    ac_ids = requirement_ac_ids(root)
    issues = []
    for index, task in enumerate(tasks, 1):
        if not isinstance(task, dict):
            continue
        prefix = f"audit: 任务 #{index}"
        for ac_id in task.get("ac_ids", []):
            if ac_id not in ac_ids:
                issues.append(prefix + " 引用了不存在的 AC: " + str(ac_id))
        for field in ("implementation", "tests"):
            for declared in task.get(field, []):
                if not declared_path_exists(root, declared):
                    issues.append(prefix + f" {field} 路径不存在: {declared}")
        if task.get("status") == "done" and task.get("verification") != "passed":
            issues.append(prefix + " done 必须对应 verification=passed")
        if task.get("status") == "done" and task.get("verification") == "passed":
            for evidence in task.get("evidence", []):
                if not evidence_path_exists(root, evidence):
                    issues.append(prefix + " evidence 文件不存在或为空: " + str(evidence))
    if stage == 4:
        if board.get("schema_version") == 2:
            release = board.get("release", {})
            required_tasks = set(release.get("required_task_ids", []))
            required_acs = set(release.get("required_ac_ids", []))
            covered = {ac_id for task in tasks if isinstance(task, dict)
                       and task.get("id") in required_tasks
                       for ac_id in task.get("ac_ids", [])}
            for ac_id in sorted(required_acs - ac_ids):
                issues.append("audit: 本次交付 AC 不存在于 requirements: " + ac_id)
            for ac_id in sorted(required_acs - covered):
                issues.append("audit: 本次交付 AC 未被 required task 覆盖: " + ac_id)
    issues.extend(platform_issues(root, config, stage))
    issues.extend(environment_issues(root, config, stage))
    return issues


def platform_issues(root, config, stage):
    platform = config.get("platform", {})
    if not isinstance(platform, dict) or not platform.get("required"):
        return []
    record_path = root / ".sop/platform-verification.json"
    if not record_path.is_file():
        return ["audit: platform.required=true 但缺少 .sop/platform-verification.json"]
    try:
        record = read_json(record_path)
    except (OSError, ValueError, TypeError):
        return ["audit: 平台验证记录格式错误"]
    if stage < 4 and (record.get("schema_version") == 1 or
                      (record.get("compile") == "passed" and record.get("smoke") == "passed")):
        issues = []
        for field in ("platform", "tool", "tool_version", "source_root"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                issues.append("audit: 平台验证记录缺少 " + field)
        if record.get("compile") != "passed":
            issues.append("audit: 真实平台编译尚未 passed")
        if record.get("smoke") != "passed":
            issues.append("audit: 真实平台冒烟尚未 passed")
        return issues
    if record.get("schema_version") != 2 or record.get("attested_by") != "sop.py":
        return ["audit: L4 平台结果必须由 attest-platform 生成机器凭据，手工 passed 无效"]
    issues = []
    for field in ("platform", "tool", "tool_version", "source_root", "environment", "attested_at"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            issues.append("audit: 平台凭据缺少 " + field)
    source = record.get("source", {})
    if source.get("sha256") != fingerprint(root):
        issues.append("audit: 平台凭据对应的源码已变化")
    commit = source.get("git_commit")
    if not isinstance(commit, str) or git_run(
            root, ["merge-base", "--is-ancestor", commit, "HEAD"]).returncode != 0:
        issues.append("audit: 平台凭据绑定的 Git commit 不在当前历史中")
    else:
        tree = git_run(root, ["rev-parse", commit + "^{tree}"])
        if tree.returncode != 0 or source.get("git_tree") != tree.stdout.strip():
            issues.append("audit: 平台凭据的 Git tree 无法核验")
    checks = record.get("checks", {})
    for name in ("compile", "smoke"):
        check = checks.get(name, {}) if isinstance(checks, dict) else {}
        if check.get("status") != "passed":
            issues.append("audit: 真实平台" + name + "尚未 passed")
            continue
        evidence = check.get("evidence", {})
        try:
            path = relative_path(root, evidence.get("path", ""))
        except SopError:
            issues.append("audit: 平台" + name + "证据路径无效")
            continue
        if not path.is_file() or sha(path) != evidence.get("sha256"):
            issues.append("audit: 平台" + name + "证据缺失或已变化")
    return issues


def environment_issues(root, config, stage):
    settings = config.get("environments", {})
    required = config.get("stack") == "full-stack" or (
        isinstance(settings, dict) and settings.get("required"))
    if stage < 4 or not required:
        return []
    path = root / ".sop/environment-verification.json"
    if not path.is_file():
        return ["audit: 全栈 L4 缺少分环境验证记录 .sop/environment-verification.json"]
    try:
        record = read_json(path)
    except (OSError, ValueError, TypeError):
        return ["audit: environment-verification.json 格式错误"]
    delivery = settings.get("delivery") if isinstance(settings, dict) else None
    delivery = delivery or record.get("delivery_environment")
    if not isinstance(delivery, str) or not delivery:
        return ["audit: 未声明本次交付环境"]
    if record.get("delivery_environment") != delivery:
        return ["audit: 环境记录与项目声明的交付环境不一致"]
    environments = record.get("environments", {})
    checks = environments.get(delivery) if isinstance(environments, dict) else None
    if not isinstance(checks, dict) or not checks:
        return ["audit: 交付环境没有检查项: " + delivery]
    required_checks = settings.get("required_checks", []) if isinstance(settings, dict) else []
    names = required_checks or list(checks)
    issues = []
    for name in names:
        check = checks.get(name, {}) if isinstance(checks, dict) else {}
        status = check.get("status")
        if status not in ENVIRONMENT_STATUSES:
            issues.append(f"audit: {delivery}/{name} 状态无效")
        elif status != "passed":
            blocker = check.get("blocker", "")
            issues.append(f"audit: {delivery}/{name} 未通过: {status}" +
                          ((" / " + blocker) if blocker else ""))
        else:
            evidence = check.get("evidence")
            if not isinstance(evidence, list) or not evidence:
                issues.append(f"audit: {delivery}/{name} passed 但缺少证据路径")
            else:
                for value in evidence:
                    if not declared_path_exists(root, value):
                        issues.append(f"audit: {delivery}/{name} 证据不存在: {value}")
    return issues


def sync_issues(root, config, stage):
    spec = requirements(config)
    path = root / ".sop/sync.json"
    if not path.is_file():
        return ["缺少同步记录：先完成当前环节的文档/任务/验证同步，再运行 `sop.py sync`"]
    try:
        record = read_json(path)
    except (OSError, ValueError, TypeError):
        return [".sop/sync.json 格式错误：重新运行 sync"]
    expected = sync_fingerprint(root, config, spec, stage)
    if record.get("stage") != stage or record.get("fingerprint") != expected:
        return ["同步记录已过期：需求、计划、源码或配置发生变化；完成同步后运行 `sop.py sync`"]
    state = read_json(root / ".sop/state.json")
    last_sync = state.get("last_sync") if isinstance(state, dict) else None
    if not isinstance(last_sync, dict) or last_sync.get("fingerprint") != record.get("fingerprint"):
        return ["state.json 的 last_sync 与 sync.json 不一致：重新运行 `sop.py sync`"]
    return []


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_path(root, value):
    if not isinstance(value, str) or not value:
        raise SopError("路径必须是非空字符串")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise SopError("路径必须位于项目内: " + value)
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()):
        raise SopError("路径越出项目: " + value)
    return target


def load_project(root):
    config = read_json(root / ".sop/project.json")
    if not isinstance(config, dict) or config.get("schema_version") != 1:
        raise SopError("不支持的 project.json 协议")
    if config.get("sop_version") != (PACKAGE / "VERSION").read_text().strip():
        raise SopError("运行时与锁定版本不一致，请使用项目内运行时")
    if config.get("profile") not in ("S", "M", "L"):
        raise SopError("profile 必须为 S/M/L")
    if config.get("stack", "default") not in STACK_MODULES:
        raise SopError("stack 必须为 default/full-stack")
    if config.get("risk") not in ("normal", "high"):
        raise SopError("risk 必须为 normal/high")
    modules = config.get("modules")
    if not isinstance(modules, list) or any(
            item not in MODULES for item in modules):
        raise SopError("modules 含未知项")
    if not isinstance(config.get("commands"), dict):
        raise SopError("commands 必须是对象")
    platform = config.get("platform", {"required": False})
    if not isinstance(platform, dict) or type(platform.get("required", False)) is not bool:
        raise SopError("platform.required 必须为布尔值")
    lifecycle = config.get("test_lifecycle", {})
    if not isinstance(lifecycle, dict):
        raise SopError("test_lifecycle 必须为对象")
    for name in ("setup", "cleanup"):
        command = lifecycle.get(name, [])
        if command and not command_valid(command):
            raise SopError("test_lifecycle." + name + " 必须是参数数组")
    environments = config.get("environments", {})
    if not isinstance(environments, dict) or type(environments.get("required", False)) is not bool:
        raise SopError("environments.required 必须为布尔值")
    doctor_checks = config.get("doctor_checks", {})
    if not isinstance(doctor_checks, dict):
        raise SopError("doctor_checks 必须为对象")
    for name, command in doctor_checks.items():
        if not isinstance(name, str) or not name or not command_valid(command):
            raise SopError("doctor_checks 的名称和命令必须有效")
    timeout = config.get("timeout_seconds")
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise SopError("timeout_seconds 必须为 1–3600 整数")
    return config


def requirements(config):
    spec = read_json(PACKAGE / "profiles" / (config["profile"] + ".json"))
    if config["risk"] == "high":
        extra = read_json(PACKAGE / "gates/high-risk.json")
        for key in spec:
            spec[key] += extra[key]
    stack = config.get("stack", "default")
    spec["documents"] = list(dict.fromkeys(
        spec["documents"] + list(STACK_MODULES[stack]) + config["modules"]
    ))
    spec["commands"] = list(dict.fromkeys(spec["commands"] + list(STACK_COMMANDS[stack])))
    return spec


def fingerprint(root):
    """Hash project inputs; generated outputs must use documented excluded dirs."""
    digest = hashlib.sha256()
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
        for d in dirs:
            if (Path(directory) / d).is_symlink():
                raise SopError("源码目录含符号链接，需先明确输入边界: " + d)
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix in (".pyc", ".pyo"):
                continue
            if path.is_symlink():
                raise SopError("源码含符号链接，需先明确输入边界: " + str(path))
            digest.update(path.relative_to(root).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def init_project(args):
    root = Path(args.target).resolve()
    if root.exists() and not root.is_dir():
        raise SopError("目标不是目录")
    agent = relative_path(root, args.agent_file)
    if len(Path(args.agent_file).parts) != 1 or args.agent_file == ".sop":
        raise SopError("agent-file 必须是项目根目录下的文件名")
    if (root / ".sop").exists() or (root / ".sop").is_symlink() or agent.exists():
        raise SopError("初始化冲突：.sop 或入口文件已存在；不覆盖")
    config = {"schema_version": 1,
              "sop_version": (PACKAGE / "VERSION").read_text().strip(),
              "name": args.name or root.name, "profile": args.profile,
              "risk": args.risk, "stack": args.stack, "modules": args.module,
              "timeout_seconds": 300, "commands": {},
              "platform": {"required": False, "name": ""},
              "environments": {
                  "required": args.stack == "full-stack",
                  "delivery": "local-dev" if args.stack == "full-stack" else "",
                  "required_checks": (["database_connectivity", "database_migration", "api_smoke"]
                                      if args.stack == "full-stack" else []),
              },
              "test_lifecycle": {"setup": [], "cleanup": []}}
    config["doctor_checks"] = {}
    spec = requirements(config)
    config["commands"] = {key: [] for key in spec["commands"]}
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    # Build in a staging dir so invalid assets cannot leave half an installation.
    staging_parent = root.parent / ".sop-staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vibe-sop-", dir=staging_parent) as temporary:
        stage = Path(temporary) / ".sop"
        runtime = stage / "runtime"
        runtime.mkdir(parents=True)
        for name in ("sop.py", "VERSION", "LICENSE", "README.md", "CHANGELOG.md"):
            shutil.copy2(PACKAGE / name, runtime / name)
        for name in ("profiles", "gates", "templates", "docs", "skills"):
            shutil.copytree(PACKAGE / name, runtime / name,
                            ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(PACKAGE / "examples", runtime / "examples",
                        ignore=shutil.ignore_patterns("__pycache__", ".sop", "build"))
        shutil.copytree(PACKAGE / "core", stage / "core")
        # Keep init usable from the pinned runtime as well.
        shutil.copytree(PACKAGE / "core", runtime / "core")
        write_json(stage / "project.json", config)
        write_json(stage / "state.json", {
            "schema_version": 1, "target_stage": "L0",
            "last_sync": None,
            "git": {"required": True, "baseline": ""},
            "reviews": {key: {"status": "pending", "reviewer": "", "decision": "",
                              "evidence": "", "sha256": ""}
                        for key in spec["reviews"]}})
        shutil.copy2(PACKAGE / "templates/tasks.json", stage / "tasks.json")
        shutil.copy2(PACKAGE / "templates/platform-verification.json",
                     stage / "platform-verification.json")
        shutil.copy2(PACKAGE / "templates/environment-verification.json",
                     stage / "environment-verification.json")
        shutil.copy2(PACKAGE / "templates/checkpoints.json", stage / "checkpoints.json")
        (stage / "docs").mkdir()
        for name in spec["documents"] + ["handover"]:
            shutil.copy2(PACKAGE / "templates" / (name + ".md"),
                         stage / "docs" / (name + ".md"))
        shutil.copytree(stage, root / ".sop")
        (root / ".sop/.gitignore").write_text(
            "/git-baseline.json\n/sync.json\n/checkpoints.json\n/evidence/\n/handover/\n",
            encoding="utf-8",
        )
        # Exclusive create protects existing agent files even if a concurrent writer appears.
        with agent.open("x", encoding="utf-8") as stream:
            stream.write((PACKAGE / "templates/AGENTS.md").read_text(encoding="utf-8"))
    git = git_run(root, ["init"])
    if git.returncode != 0:
        raise SopError("无法初始化项目本地 Git: " + (git.stderr or git.stdout).strip())
    if git_run(root, ["config", "--get", "user.name"]).returncode != 0:
        git_run(root, ["config", "user.name", "Vibe Coding SOP"], check=True)
    if git_run(root, ["config", "--get", "user.email"]).returncode != 0:
        git_run(root, ["config", "user.email", "local-sop@localhost"], check=True)
    print("已初始化 " + str(root))
    print("下一步：先填写文档，运行 baseline 建立本地 Git 基线，再运行 check；待填写模板不会通过。")
    return 0


def document_digest(root, names):
    digest = hashlib.sha256()
    for name in sorted(names):
        path = root / ".sop/docs" / (name + ".md")
        digest.update(name.encode())
        digest.update(path.read_bytes() if path.is_file() else b"MISSING")
    return digest.hexdigest()


def review_scope(root, config, spec, name):
    stage = REVIEW_STAGE[name]
    docs = [d for d in spec["documents"] if DOC_STAGE[d] <= stage]
    payload = {"documents": document_digest(root, docs), "config": config}
    if stage == 4:
        payload["source"] = fingerprint(root)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def check_review(root, config, spec, name, record):
    expected = review_scope(root, config, spec, name)
    if not isinstance(record, dict) or record.get("status") != "approved":
        return "人工复核待完成: " + name + " (scope_sha256=" + expected + ")"
    for field in ("reviewer", "decision", "evidence", "sha256"):
        if not isinstance(record.get(field), str) or not record[field].strip():
            return "复核缺少 " + field + ": " + name
    path = relative_path(root, record["evidence"])
    if not path.is_file() or not path.stat().st_size or sha(path) != record["sha256"]:
        return "复核证据缺失或内容已变化: " + name
    if record.get("scope_sha256") != expected:
        return "复核范围已变化: " + name + " (scope_sha256=" + expected + ")"
    return None


def command_valid(argv):
    return isinstance(argv, list) and bool(argv) and all(
        isinstance(arg, str) and arg and "\0" not in arg for arg in argv)


def document_issues(root, name):
    """Check minimum structure, not the truth or quality of the prose."""
    path = root / ".sop/docs" / (name + ".md")
    if not path.is_file():
        return ["缺少文档: " + name]
    content = path.read_text(encoding="utf-8")
    issues = []
    if PLACEHOLDER.search(content):
        issues.append("文档尚未填写或有阻塞澄清: " + name)
    required = read_json(PACKAGE / "gates/document-sections.json")[name]
    chunks = re.split(r"^##[ \t]+(.+?)[ \t]*$", content, flags=re.M)
    sections = dict(zip(chunks[1::2], chunks[2::2]))
    for heading in required:
        body = sections.get(heading, "")
        # Quoted instructions and empty checklist items are not project decisions.
        lines = [line.strip() for line in body.splitlines()
                 if line.strip() and not line.lstrip().startswith((">", "#", "<!--"))]
        lines = [line for line in lines if not re.fullmatch(r"[-| :]+|- \[[ x]\]", line)]
        if not lines:
            issues.append("缺少章节内容: " + name + " / " + heading)
    return issues


def inspection(root, config, stage):
    spec = requirements(config)
    blockers = []
    blockers.extend(local_git_issues(root))
    for name in spec["documents"]:
        if DOC_STAGE[name] > stage:
            continue
        blockers.extend(document_issues(root, name))
    state = read_json(root / ".sop/state.json")
    if not isinstance(state, dict) or not isinstance(state.get("reviews"), dict):
        raise SopError("state.json 的 reviews 必须为对象")
    blockers.extend(task_issues(root, stage))
    if stage == 4:
        blockers.extend(delivery_task_issues(root, stage))
        blockers.extend(audit_issues(root, config, stage))
        blockers.extend(checkpoint_issues(root, stage))
    blockers.extend(sync_issues(root, config, stage))
    for name in spec["reviews"]:
        if REVIEW_STAGE[name] <= stage:
            issue = check_review(root, config, spec, name, state["reviews"].get(name))
            if issue:
                blockers.append(issue)
    if stage == 4:
        report_path = root / ".sop/evidence/latest.json"
        report = read_json(report_path) if report_path.is_file() else {}
        config_fresh = (report.get("config_sha256") == json_digest(config)
                        if "config_sha256" in report else report.get("config") == config)
        fresh = (report.get("source_unchanged") is True
                 and report.get("source_sha256") == fingerprint(root)
                 and config_fresh)
        if not fresh:
            blockers.append("自动检查未运行或已过期：运行 verify")
        results = report.get("results", {})
        for name in spec["commands"]:
            result = results.get(name, {})
            if not command_valid(config["commands"].get(name)):
                blockers.append("未配置命令: " + name)
            if result.get("status") != "passed" or result.get("exit_code") != 0:
                blockers.append("自动门禁未通过: " + name)
            elif not isinstance(result.get("log"), str):
                blockers.append("门禁缺少日志: " + name)
            else:
                log = relative_path(root, result["log"])
                if not log.is_file() or sha(log) != result.get("log_sha256"):
                    blockers.append("门禁日志缺失或变化: " + name)
    return blockers


def checkpoint_issues(root, stage):
    if stage == 3:
        config = load_project(root)
        issues = task_issues(root, 3) + audit_issues(root, config, 3)
        task_path = root / ".sop/tasks.json"
        if not task_path.is_file():
            return issues
        board = read_json(task_path)
        completed = [task for task in board.get("tasks", [])
                     if isinstance(task, dict)
                     and task.get("status") == "done"
                     and task.get("verification") == "passed"]
        if not completed:
            issues.append("L3 至少需要一项通过真实验证的 done 任务")
        report_path = root / ".sop/evidence/latest.json"
        report = read_json(report_path) if report_path.is_file() else {}
        fresh = (report.get("source_unchanged") is True
                 and report.get("source_sha256") == fingerprint(root)
                 and report.get("config_sha256") == json_digest(config))
        if not fresh:
            issues.append("L3 缺少当前源码和配置对应的 verify 证据")
        for name in requirements(config)["commands"]:
            result = report.get("results", {}).get(name, {})
            if result.get("status") != "passed" or result.get("exit_code") != 0:
                issues.append("L3 自动门禁未通过: " + name)
        git_issues = local_git_issues(root)
        if git_issues:
            issues.extend(git_issues)
        else:
            status = git_run(root, ["status", "--porcelain", "--untracked-files=all"])
            if status.stdout.strip():
                issues.append("L3 checkpoint 要求 Git 工作区干净；先审阅并提交实现")
        return issues
    if stage < 4:
        return []
    task_path = root / ".sop/tasks.json"
    if not task_path.is_file():
        return []
    board = read_json(task_path)
    if board.get("schema_version") != 2:
        return []
    required = set(board.get("release", {}).get("required_task_ids", []))
    path = root / ".sop/checkpoints.json"
    if not path.is_file():
        return ["L4 缺少 Git checkpoint 记录"]
    try:
        record = read_json(path)
    except (OSError, ValueError, TypeError):
        return ["Git checkpoint 记录格式错误"]
    tasks = record.get("tasks", {}) if isinstance(record, dict) else {}
    issues = []
    status = git_run(root, ["status", "--porcelain", "--untracked-files=all"])
    if status.returncode != 0 or status.stdout.strip():
        issues.append("L4 Git 工作区不干净；最终 checkpoint 后仍有未提交变化")
    head = git_run(root, ["rev-parse", "HEAD"])
    for task_id in sorted(required):
        checkpoint = tasks.get(task_id, {}) if isinstance(tasks, dict) else {}
        commit = checkpoint.get("commit")
        if not isinstance(commit, str) or not commit:
            issues.append("required task 缺少 Git checkpoint: " + task_id)
            continue
        if git_run(root, ["merge-base", "--is-ancestor", commit, "HEAD"]).returncode != 0:
            issues.append("任务 checkpoint 不在当前 HEAD 历史中: " + task_id)
    stages = record.get("stages", {}) if isinstance(record, dict) else {}
    release = stages.get("L4", {}) if isinstance(stages, dict) else {}
    if release.get("commit") != (head.stdout.strip() if head.returncode == 0 else None):
        issues.append("L4 最终 Git checkpoint 缺失或不是当前 HEAD")
    return issues


def stage_number(value):
    if value not in ("L0", "L1", "L2", "L3", "L4"):
        raise SopError("阶段必须为 L0–L4")
    return int(value[1])


def baseline_project(args):
    root = Path(args.project).resolve()
    config = load_project(root)
    if local_git_issues(root) and not (root / ".sop/git-baseline.json").is_file():
        # A repository may exist but have no baseline yet; only the first issue is relevant here.
        git_root = git_run(root, ["rev-parse", "--show-toplevel"])
        if git_root.returncode != 0:
            raise SopError("项目必须有自己的本地 Git 仓库；请先确认 git 可用")
    git_root = git_run(root, ["rev-parse", "--show-toplevel"])
    if git_root.returncode != 0 or Path(git_root.stdout.strip()).resolve() != root:
        raise SopError("项目必须有自己的本地 Git 根目录")
    status = git_run(root, ["status", "--porcelain"])
    if status.returncode != 0:
        raise SopError("无法读取 Git 工作区状态")
    head = git_run(root, ["rev-parse", "--verify", "HEAD"])
    if status.stdout.strip() or head.returncode != 0:
        git_run(root, ["add", "-A"], check=True)
        message = args.message or "chore: establish local SOP baseline"
        git_run(root, ["commit", "-m", message], check=True)
        head = git_run(root, ["rev-parse", "--verify", "HEAD"], check=True)
    commit = head.stdout.strip()
    metadata = {
        "schema_version": 1,
        "commit": commit,
        "message": args.message or "chore: establish local SOP baseline",
        "created_at": now(),
        "source_sha256": fingerprint(root),
        "recovery": "git checkout " + commit,
    }
    write_json(root / ".sop/git-baseline.json", metadata)
    print("本地 Git 基线已建立: " + commit)
    return 0


def git_snapshot(root, require_clean=True):
    if local_git_issues(root):
        raise SopError("必须先建立有效的本地 Git 基线")
    status = git_run(root, ["status", "--porcelain", "--untracked-files=all"], check=True)
    if require_clean and status.stdout.strip():
        raise SopError("Git 工作区不干净；先审阅并提交本次变更，再登记 checkpoint")
    head = git_run(root, ["rev-parse", "HEAD"], check=True).stdout.strip()
    tree = git_run(root, ["rev-parse", "HEAD^{tree}"], check=True).stdout.strip()
    return {"commit": head, "tree": tree}


def checkpoint_project(args):
    root = Path(args.project).resolve()
    load_project(root)
    snapshot = git_snapshot(root)
    path = root / ".sop/checkpoints.json"
    record = read_json(path) if path.is_file() else {
        "schema_version": 1, "tasks": {}, "stages": {}}
    if not isinstance(record, dict):
        raise SopError("checkpoints.json 格式错误")
    record.setdefault("tasks", {})
    record.setdefault("stages", {})
    item = {**snapshot, "created_at": now(),
            "source_sha256": fingerprint(root),
            "tasks_sha256": sha(root / ".sop/tasks.json")}
    if args.task:
        board = read_json(root / ".sop/tasks.json")
        task = next((entry for entry in board.get("tasks", [])
                     if isinstance(entry, dict) and entry.get("id") == args.task), None)
        if not task:
            raise SopError("任务不存在: " + args.task)
        if task.get("status") != "done" or task.get("verification") != "passed":
            raise SopError("任务尚未完成验证，不能登记 checkpoint: " + args.task)
        message = git_run(root, ["log", "-1", "--pretty=%B"], check=True).stdout
        if args.task not in message:
            raise SopError("当前提交消息必须包含任务 ID: " + args.task)
        record["tasks"][args.task] = item
        label = "任务 " + args.task
    else:
        record["stages"][args.stage] = item
        label = "阶段 " + args.stage
    write_json(path, record)
    print(label + " checkpoint 已登记: " + snapshot["commit"])
    return 0


def attest_platform_project(args):
    root = Path(args.project).resolve()
    config = load_project(root)
    platform = config.get("platform", {})
    if not platform.get("required"):
        raise SopError("platform.required=false，无需生成平台凭据")
    snapshot = git_snapshot(root)

    def evidence(value):
        path = relative_path(root, value)
        if not path.is_file() or not path.stat().st_size:
            raise SopError("平台证据不存在或为空: " + value)
        return {"path": path.relative_to(root).as_posix(), "sha256": sha(path)}

    record = {
        "schema_version": 2,
        "attested_by": "sop.py",
        "attested_at": now(),
        "environment": args.environment,
        "platform": platform.get("name") or "unspecified",
        "tool": args.tool,
        "tool_version": args.tool_version,
        "source_root": args.source_root,
        "source": {"sha256": fingerprint(root),
                   "git_commit": snapshot["commit"], "git_tree": snapshot["tree"]},
        "checks": {
            "compile": {"status": "passed", "evidence": evidence(args.compile_evidence)},
            "smoke": {"status": "passed", "evidence": evidence(args.smoke_evidence)},
        },
    }
    write_json(root / ".sop/platform-verification.json", record)
    print("平台凭据已生成并绑定 Git commit: " + snapshot["commit"])
    return 0


def doctor_project(args):
    root = Path(args.project).resolve()
    config = load_project(root)
    checks = []

    def add(name, status, detail):
        checks.append({"name": name, "status": status, "detail": detail})

    git_issues = local_git_issues(root)
    add("git_baseline", "failed" if git_issues else "passed",
        "；".join(git_issues) if git_issues else "local Git baseline ready")
    tracked = git_run(root, ["ls-files"])
    tracked_secret_files = []
    for line in tracked.stdout.splitlines():
        name = Path(line).name
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            tracked_secret_files.append(line)
    add("tracked_secrets", "failed" if tracked_secret_files else "passed",
        ("敏感环境文件被 Git 跟踪: " + ", ".join(tracked_secret_files))
        if tracked_secret_files else "no tracked secret environment file")
    sample_secrets = []
    for sample in root.rglob(".env.example"):
        if any(part in EXCLUDED for part in sample.relative_to(root).parts):
            continue
        for line in sample.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            url_match = re.search(
                r"(?i)\b(?:postgres(?:ql)?|mysql)://[^\s:@/]+:([^@\s/]+)@", line)
            if url_match:
                password = url_match.group(1)
                if not re.search(r"change|example|placeholder|your[_-]|<.+>|\*{3,}", password, re.I):
                    key = line.split("=", 1)[0].strip() or "DATABASE_URL"
                    sample_secrets.append(sample.relative_to(root).as_posix() + ":" + key)
                continue
            match = re.match(r"\s*([A-Za-z0-9_]*(?:PASSWORD|PASSWD|TOKEN|SECRET|API_KEY)[A-Za-z0-9_]*)\s*=\s*(.+)",
                             line, re.I)
            if not match:
                continue
            value = match.group(2).strip().strip("'\"")
            if value and not re.search(r"change|example|placeholder|your[_-]|<.+>|\*{3,}", value, re.I):
                sample_secrets.append(sample.relative_to(root).as_posix() + ":" + match.group(1))
    add("example_credentials", "failed" if sample_secrets else "passed",
        ("示例环境文件疑似包含明文凭证字段: " + ", ".join(sample_secrets))
        if sample_secrets else "no plaintext credential-shaped sample value")
    reserved = []
    scan_root = root
    project_config = root / "project.config.json"
    if args.profile == "wechat-fullstack" and project_config.is_file():
        try:
            project_data = read_json(project_config)
            scan_root = (root / project_data.get("miniprogramRoot", "")).resolve()
            if root not in scan_root.parents and scan_root != root:
                raise SopError("miniprogramRoot 逃逸项目目录")
        except (OSError, ValueError, TypeError):
            scan_root = root
    if scan_root.is_dir():
        for directory, dirs, _files in os.walk(scan_root):
            for name in list(dirs):
                if re.fullmatch(r"__.+__", name):
                    reserved.append((Path(directory) / name).relative_to(root).as_posix())
            dirs[:] = [name for name in dirs if name not in EXCLUDED]
    add("reserved_directories", "failed" if reserved else "passed",
        ("目标平台保留目录: " + ", ".join(reserved)) if reserved else "none")
    required_commands = requirements(config)["commands"]
    missing = [name for name in required_commands if not command_valid(config["commands"].get(name))]
    add("quality_commands", "failed" if missing else "passed",
        ("未配置: " + ", ".join(missing)) if missing else "all configured")
    if args.profile == "wechat-fullstack":
        add("wechat_project", "passed" if project_config.is_file() else "failed",
            "project.config.json present" if project_config.is_file() else "缺少 project.config.json")
        environment_settings = config.get("environments", {})
        isolated = (config.get("stack") == "full-stack"
                    and environment_settings.get("required")
                    and bool(environment_settings.get("delivery")))
        add("environment_matrix", "passed" if isolated else "failed",
            "full-stack delivery environment declared" if isolated
            else "未启用 full-stack 分环境验证")
        probes = config.get("doctor_checks", {})
        add("project_probes", "passed" if probes else "failed",
            "configured: " + ", ".join(sorted(probes)) if probes
            else "未配置数据库/API 等项目只读探针")
    probe_run_id = "doctor-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    probe_root = root / ".sop/evidence" / probe_run_id
    probe_environment = os.environ.copy()
    probe_environment["SOP_RUN_ID"] = probe_run_id
    for name, command in config.get("doctor_checks", {}).items():
        result = execute_command(root, command, config["timeout_seconds"],
                                 probe_root / (name + ".log"), probe_environment)
        add("probe:" + name, "passed" if result["status"] == "passed" else "failed",
            result["status"] + " / " + result["log"])
    result = {"profile": args.profile, "ready": all(c["status"] == "passed" for c in checks),
              "checks": checks,
              "meaning": "本地前置诊断；不代替目标平台运行、数据库迁移或业务验收"}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("doctor " + ("通过" if result["ready"] else "发现阻塞"))
        for check in checks:
            print(f"- {check['status']}: {check['name']} / {check['detail']}")
    return 0 if result["ready"] else 1


def sync_project(args):
    root = Path(args.project).resolve()
    config = load_project(root)
    git_issues = local_git_issues(root)
    if git_issues:
        raise SopError("同步前必须先建立本地 Git 基线: " + "；".join(git_issues))
    state = read_json(root / ".sop/state.json")
    target = args.stage or state.get("target_stage")
    stage = stage_number(target)
    spec = requirements(config)
    issues = []
    for name in spec["documents"]:
        if DOC_STAGE[name] <= stage:
            issues.extend(document_issues(root, name))
    issues.extend(task_issues(root, stage))
    if issues:
        raise SopError("同步前材料未完成:\n- " + "\n- ".join(issues))
    digest = sync_fingerprint(root, config, spec, stage)
    write_json(root / ".sop/sync.json", {
        "schema_version": 1,
        "stage": stage,
        "fingerprint": digest,
        "synced_at": now(),
        "source_sha256": fingerprint(root),
        "task_board": ".sop/tasks.json",
    })
    state["last_sync"] = {"stage": target, "fingerprint": digest, "synced_at": now()}
    write_json(root / ".sop/state.json", state)
    print("状态同步完成: " + target + " / " + digest)
    return 0


def check_project(args):
    root = Path(args.project).resolve()
    config = load_project(root)
    target = args.stage or read_json(root / ".sop/state.json").get("target_stage")
    blockers = inspection(root, config, stage_number(target))
    result = {"stage": target, "ready": not blockers, "blockers": blockers,
              "meaning": "材料和登记证据检查，不代替业务验收"}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(target + (" 检查通过" if not blockers else " 尚未就绪"))
        for item in blockers:
            print("- " + item)
    return 1 if blockers else 0


def audit_project(args):
    root = Path(args.project).resolve()
    config = load_project(root)
    target = args.stage or read_json(root / ".sop/state.json").get("target_stage")
    stage = stage_number(target)
    issues = (task_issues(root, stage) + delivery_task_issues(root, stage)
              + audit_issues(root, config, stage))
    result = {"stage": target, "ready": not issues, "issues": issues,
              "meaning": "语义一致性检查，不代替测试或人工验收"}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(target + (" audit 通过" if not issues else " audit 发现问题"))
        for item in issues:
            print("- " + item)
    return 1 if issues else 0


def verify_project(args):
    root = Path(args.project).resolve()
    config = load_project(root)
    spec = requirements(config)
    before = fingerprint(root)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
    evidence = root / ".sop/evidence" / run_id
    evidence.mkdir(parents=True)
    environment = os.environ.copy()
    environment["SOP_RUN_ID"] = run_id
    lifecycle_config = config.get("test_lifecycle", {})
    lifecycle = {}
    setup = lifecycle_config.get("setup", [])
    if setup:
        print("执行 test setup: " + json.dumps(sanitized_value(setup), ensure_ascii=False), flush=True)
        lifecycle["setup"] = execute_command(
            root, setup, config["timeout_seconds"], evidence / "setup.log", environment)
    else:
        lifecycle["setup"] = {"status": "not_configured", "exit_code": None}
    results = {}
    try:
        for name in spec["commands"]:
            argv = config["commands"].get(name)
            path = evidence / (name + ".log")
            if lifecycle["setup"]["status"] not in ("passed", "not_configured"):
                path.write_text("SOP: skipped because test setup failed\n", encoding="utf-8")
                results[name] = {"status": "skipped", "exit_code": None,
                                 "log": path.relative_to(root).as_posix(),
                                 "log_sha256": sha(path)}
                continue
            print("执行 " + name + ": " +
                  json.dumps(sanitized_value(argv), ensure_ascii=False), flush=True)
            results[name] = execute_command(
                root, argv, config["timeout_seconds"], path, environment)
    finally:
        cleanup = lifecycle_config.get("cleanup", [])
        if cleanup:
            print("执行 test cleanup: " +
                  json.dumps(sanitized_value(cleanup), ensure_ascii=False), flush=True)
            lifecycle["cleanup"] = execute_command(
                root, cleanup, config["timeout_seconds"], evidence / "cleanup.log", environment)
        else:
            lifecycle["cleanup"] = {"status": "not_configured", "exit_code": None}
    after = fingerprint(root)
    stable = before == after and config == load_project(root)
    report = {"schema_version": 2, "run_id": run_id, "generated_at": now(),
              "config": sanitized_value(config), "config_sha256": json_digest(config),
              "source_sha256": before, "source_unchanged": stable,
              "lifecycle": lifecycle, "results": results}
    write_json(evidence / "report.json", report)
    write_json(root / ".sop/evidence/latest.json", report)
    lifecycle_passed = all(item["status"] in ("passed", "not_configured")
                           for item in lifecycle.values())
    passed = stable and lifecycle_passed and all(
        r["status"] == "passed" for r in results.values())
    print("自动检查通过；人工复核仍需 check" if passed else "自动检查失败或输入在执行时变化，查看 .sop/evidence/")
    return 0 if passed else 1


def handover_project(args):
    root = Path(args.project).resolve()
    config = load_project(root)
    blockers = inspection(root, config, 4)
    record = {"schema_version": 1, "generated_at": now(), "project": config,
              "source_sha256": fingerprint(root), "ready": not blockers,
              "blockers": blockers, "design_decisions": [], "next_actions": [],
              "note": "补充设计理由与下一步；ready 仅表示材料与登记证据合规"}
    narrative = root / ".sop/docs/handover.md"
    narrative_issues = document_issues(root, "handover")
    record["handover_complete"] = not narrative_issues
    record["handover_issues"] = narrative_issues
    record["narrative"] = {"path": ".sop/docs/handover.md",
                           "sha256": sha(narrative) if narrative.is_file() else None}
    path = root / ".sop/handover" / (uuid.uuid4().hex + ".json")
    write_json(path, record)
    print(str(path))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="初始化新项目或已有仓库，拒绝覆盖")
    init.add_argument("target")
    init.add_argument("--name")
    init.add_argument("--profile", choices=["S", "M", "L"], default="M")
    init.add_argument("--risk", choices=["normal", "high"], default="normal")
    init.add_argument("--stack", choices=sorted(STACK_MODULES), default="default")
    init.add_argument("--module", choices=MODULES,
                      action="append", default=[])
    init.add_argument("--agent-file", default="AGENTS.md")
    init.set_defaults(func=init_project)
    for name, function in (("check", check_project), ("audit", audit_project),
                           ("verify", verify_project),
                           ("handover", handover_project), ("baseline", baseline_project),
                           ("sync", sync_project)):
        command = sub.add_parser(name)
        command.add_argument("--project", default=".")
        if name == "check":
            command.add_argument("--stage", choices=["L0", "L1", "L2", "L3", "L4"])
            command.add_argument("--json", action="store_true")
        if name == "audit":
            command.add_argument("--stage", choices=["L0", "L1", "L2", "L3", "L4"])
            command.add_argument("--json", action="store_true")
        if name == "baseline":
            command.add_argument("--message")
        if name == "sync":
            command.add_argument("--stage", choices=["L0", "L1", "L2", "L3", "L4"])
        command.set_defaults(func=function)
    task = sub.add_parser("task", help="通过受控状态转换更新任务清单")
    task.add_argument("action", choices=sorted(TASK_TRANSITIONS),
                      help="start/block/verify/done；verify 只登记已存在的真实证据")
    task.add_argument("task", help="任务 ID，例如 T-001")
    task.add_argument("--project", default=".")
    task.add_argument("--note")
    task.add_argument("--reason", help="block 时的阻塞原因")
    task.add_argument("--owner", help="block 时的责任人")
    task.add_argument("--next-action", help="block 时的下一步")
    task.set_defaults(func=task_project)
    checkpoint = sub.add_parser("checkpoint", help="登记已提交且可恢复的任务或阶段检查点")
    checkpoint.add_argument("--project", default=".")
    target = checkpoint.add_mutually_exclusive_group(required=True)
    target.add_argument("--task")
    target.add_argument("--stage", choices=["L0", "L1", "L2", "L3", "L4"])
    checkpoint.set_defaults(func=checkpoint_project)
    attest = sub.add_parser("attest-platform", help="将真实平台证据绑定到当前 Git 提交")
    attest.add_argument("--project", default=".")
    attest.add_argument("--environment", required=True)
    attest.add_argument("--tool", required=True)
    attest.add_argument("--tool-version", required=True)
    attest.add_argument("--source-root", required=True)
    attest.add_argument("--compile-evidence", required=True)
    attest.add_argument("--smoke-evidence", required=True)
    attest.set_defaults(func=attest_platform_project)
    doctor = sub.add_parser("doctor", help="执行只读环境前置诊断")
    doctor.add_argument("--project", default=".")
    doctor.add_argument("--profile", choices=["default", "wechat-fullstack"], default="default")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=doctor_project)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (SopError, OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        print("SOP 错误: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    # Keep JSON and Chinese diagnostics portable when stdout is piped on Windows.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    sys.exit(main())
