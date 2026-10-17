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
             "wireframe": 1, "design": 2, "risk": 2, "plan": 3,
             "tasks": 3, "regression": 3, "development": 3,
             "research": 1, "validation": 4}
MODULES = ("glossary", "wireframe", "regression", "research", "development")
REVIEW_STAGE = {"constitution": 0, "requirements": 1, "design": 2,
                "acceptance": 4, "release": 4}
EXCLUDED = {".git", ".sop", "__pycache__", ".venv", "venv", "node_modules",
            "target", "dist", "build", ".pytest_cache", ".mypy_cache",
            ".gradle", "coverage", ".next"}
PLACEHOLDER = re.compile(r"\bTODO\b|\bTBD\b|NEEDS CLARIFICATION|\{\{[^}]+\}\}", re.I)
TASK_STATUSES = {"planned", "in_progress", "blocked", "done"}
VERIFICATION_STATUSES = {"pending", "partial", "passed", "blocked"}


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
    platform = config.get("platform", {})
    if isinstance(platform, dict) and platform.get("required"):
        record_path = root / ".sop/platform-verification.json"
        if not record_path.is_file():
            issues.append("audit: platform.required=true 但缺少 .sop/platform-verification.json")
        else:
            try:
                record = read_json(record_path)
            except (OSError, ValueError, TypeError):
                issues.append("audit: 平台验证记录格式错误")
            else:
                for field in ("platform", "tool", "tool_version", "source_root"):
                    if not isinstance(record.get(field), str) or not record[field].strip():
                        issues.append("audit: 平台验证记录缺少 " + field)
                if record.get("compile") != "passed":
                    issues.append("audit: 真实平台编译尚未 passed")
                if record.get("smoke") != "passed":
                    issues.append("audit: 真实平台冒烟尚未 passed")
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
    spec["documents"] = list(dict.fromkeys(spec["documents"] + config["modules"]))
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
              "risk": args.risk, "modules": args.module,
              "timeout_seconds": 300, "commands": {},
              "platform": {"required": False, "name": ""}}
    spec = requirements(config)
    config["commands"] = {key: [] for key in spec["commands"]}
    root.mkdir(parents=True, exist_ok=True)
    # Build in a staging dir so invalid assets cannot leave half an installation.
    with tempfile.TemporaryDirectory(prefix="vibe-sop-") as temporary:
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
        (stage / "docs").mkdir()
        for name in spec["documents"] + ["handover"]:
            shutil.copy2(PACKAGE / "templates" / (name + ".md"),
                         stage / "docs" / (name + ".md"))
        shutil.copytree(stage, root / ".sop")
        (root / ".sop/.gitignore").write_text(
            "git-baseline.json\nsync.json\nevidence/\nhandover/\n",
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
    blockers.extend(sync_issues(root, config, stage))
    for name in spec["reviews"]:
        if REVIEW_STAGE[name] <= stage:
            issue = check_review(root, config, spec, name, state["reviews"].get(name))
            if issue:
                blockers.append(issue)
    if stage == 4:
        report_path = root / ".sop/evidence/latest.json"
        report = read_json(report_path) if report_path.is_file() else {}
        fresh = (report.get("source_unchanged") is True
                 and report.get("source_sha256") == fingerprint(root)
                 and report.get("config") == config)
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
    issues = task_issues(root, stage) + audit_issues(root, config, stage)
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
    results = {}
    for name in spec["commands"]:
        argv = config["commands"].get(name)
        path = evidence / (name + ".log")
        exit_code = None
        status = "failed"
        if not command_valid(argv):
            path.write_text("未配置有效参数数组\n", encoding="utf-8")
        else:
            print("执行 " + name + ": " + json.dumps(argv, ensure_ascii=False), flush=True)
            with path.open("wb") as stream:
                try:
                    run = subprocess.run(argv, cwd=root, stdout=stream,
                                         stderr=subprocess.STDOUT,
                                         timeout=config["timeout_seconds"],
                                         shell=False)
                    exit_code = run.returncode
                    status = "passed" if exit_code == 0 else "failed"
                except subprocess.TimeoutExpired:
                    stream.write(b"\nSOP: command timed out\n")
                    status = "timeout"
                except OSError as error:
                    stream.write(str(error).encode("utf-8"))
        results[name] = {"status": status, "exit_code": exit_code,
                         "log": path.relative_to(root).as_posix(),
                         "log_sha256": sha(path)}
    after = fingerprint(root)
    stable = before == after and config == load_project(root)
    report = {"schema_version": 1, "generated_at": now(), "config": config,
              "source_sha256": before, "source_unchanged": stable, "results": results}
    write_json(evidence / "report.json", report)
    write_json(root / ".sop/evidence/latest.json", report)
    passed = stable and all(r["status"] == "passed" for r in results.values())
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
