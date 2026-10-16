# 实例：个人离线任务清单（M 档）

这是一个教学项目，用来验证 SOP 的材料能连接真实实现，不是经过真实用户验收的产品。需求约束是为本示例明确设定的，人工审批保持 pending。

代码包含真实 SQLite 持久化、参数校验、状态转换和 CLI。sop-docs 提供已填写的宪法、PRD、设计、Plan、DD、验证和交接说明。先看 [需求](sop-docs/requirements.md)，沿 AC→[开发位置](sop-docs/development.md)→[测试映射](sop-docs/validation.md) 阅读。

## 单独运行（在本示例目录）

```sh
python -m unittest discover -s tests -v
python cli.py --db build/demo.db add "整理发票"
python cli.py --db build/demo.db list
python cli.py --db build/demo.db complete 1
```

使用新的 build/demo.db 时第一个 ID 为 1；已有库使用 add 返回的实际 ID。数据库只用于演示。不要拿已有个人库做演示清理。

## 跑 SOP（从工具包根目录）

```sh
python sop.py init examples/task-list --profile M --name task-list-demo
```

将 sop-docs 的 .md 复制到本示例新生成的 .sop/docs，覆盖演示用空模板：

PowerShell：
```powershell
Copy-Item examples/task-list/sop-docs/*.md examples/task-list/.sop/docs/
```

macOS/Linux：
```sh
cp examples/task-list/sop-docs/*.md examples/task-list/.sop/docs/
```

在生成的 project.json 配置以下命令，保留其余字段：

```json
"commands": {
  "test": ["python", "-m", "unittest", "discover", "-s", "tests", "-v"],
  "build": ["python", "-m", "compileall", "-q", "task_store.py", "cli.py"]
}
```

```sh
python sop.py check --project examples/task-list --stage L0
python sop.py verify --project examples/task-list
python sop.py check --project examples/task-list --stage L4
python sop.py handover --project examples/task-list
```

预期：L0 材料通过；自动测试/编译通过；L4 仍提示 requirements/design/acceptance 的真实复核待完成。实际跑完再更新 validation 的时间、数量、日志和结论，不把本文当作你这次执行证据。记录人工决定的方式见分发包 docs/protocol.md。

工具包测试会在临时目录自动装配并跑这个示例，还会故意把完成操作改错，确认测试真的失败。它验证行为与材料衔接，不模拟真实用户审批。
