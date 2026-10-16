# 项目执行入口

读取 `.sop/project.json`，运行 `python .sop/runtime/sop.py check` 获取缺失项。按当前任务读取 `.sop/core/workflow.md` 和 `.sop/docs/` 中对应阶段材料。

把目标转成可验证的验收条件，再做纵向切片；已获授权任务连续推进。共享接口、业务歧义、范围变化优先澄清。保留既有风格和无关改动。

测试命令的唯一来源是 `.sop/project.json`。审阅后执行 `python .sop/runtime/sop.py verify`，交付前 `check --stage L4`。报告真实失败和未验证项，依据实际用户意见登记人工复核。

交接时运行 `python .sop/runtime/sop.py handover`，补充设计理由和下一步。新功能更新需求/计划，重新登记受影响的复核和验证结果。
