# 可运行的 S 档示例

从工具包根目录执行：

```sh
python sop.py init examples/counter --profile S --name line-counter
```

填写生成文档：目标是计算非空行；空输入为 0，空白行不计数，支持中文和 CRLF；不涉及联网、持久化或权限。把计划写成对应这三个行为的测试和实现。去掉模板占位内容。

在 examples/counter/.sop/project.json 设置：

```json
"commands": {
  "test": ["python", "-m", "unittest", "discover", "-s", "tests"]
}
```

```sh
python sop.py verify --project examples/counter
python sop.py check --project examples/counter --stage L4
```

自动测试应通过，L4 仍提示人工 acceptance 待完成；按 docs/protocol.md 记录真实体验验收。这个差异是设计行为。该示例的执行记录由测试套件在临时目录生成，仓库不附伪造审批。

完成后运行 handover 获取带阻塞项的交接快照。不要把示例里的 .sop 生成物提交到工具包仓库。
