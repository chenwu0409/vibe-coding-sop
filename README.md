# Vibe Coding SOP

可迁移、按项目复杂度裁剪的 AI 编程工作流。Python 3.10+，无第三方运行依赖。

## 五分钟开始

```sh
git clone https://github.com/chenwu0409/vibe-coding-sop.git
python vibe-coding-sop/sop.py init ../my-app --name my-app --profile M --risk normal
cd ../my-app
python .sop/runtime/sop.py check
```

初始化生成待填写材料，第一次检查失败是预期行为。填写 .sop/docs/ 的目标、边界与验收条件，再逐步推进。项目携带锁定版本的运行时、规则和模板，离开工具仓库及 Obsidian 后仍可工作。

已有项目也使用 init。目标 .sop 或 AGENTS.md 已存在时拒绝覆盖。已有 AGENTS.md 可用 `--agent-file SOP-AGENTS.md` 生成另一入口，再审阅合入原规则。初始化不安装全局工具，也不修改现有 hooks、业务代码或 CI。

## 项目日常使用

```sh
python .sop/runtime/sop.py check --stage L0
# 编辑 .sop/project.json 的 commands 后，显式执行：
python .sop/runtime/sop.py verify
python .sop/runtime/sop.py check --stage L4
python .sop/runtime/sop.py handover
```

命令使用参数数组，例如 `"test": ["python","-m","unittest","discover","-s","tests"]`。Windows 的 .cmd/.bat 可显式配置 `["cmd","/c","npm","test"]`。先审阅配置再执行，命令拥有当前用户权限。

check 只读；verify 执行门禁并保存日志，绑定源码和命令配置。源码或配置变化、缺少命令、失败或过期证据都会阻止 L4 通过。人工复核另行登记，自动检查通过不会代签验收。

| 档位 | 适用范围 | 必需文档 | 自动检查 | 人工复核 |
|---|---|---|---|---|
| S | 小工具、局部修改 | 宪法、需求、计划 | test | 验收 |
| M（默认） | 普通业务应用 | S + 技术设计 | test、build | 需求、设计、验收 |
| L | 跨模块、多人/Agent | M + 术语、任务、回归计划 | test、build、lint | 宪法、需求、设计、验收 |

`--risk high` 对任意档追加 risk 文档、security 命令和发布/回滚复核；`--module glossary`、`--module wireframe`、`--module regression` 按需补充材料。覆盖率与函数长度由项目自定，不用统一数字代替质量判断。

## Agent 的入口

生成的 AGENTS.md 很短，按任务指向工作流和对应阶段材料。给编码助手的启动提示：

> 阅读本项目 AGENTS.md 与 .sop/project.json，运行 check。结合现有代码确定本次变更需要补齐的决策，明确验收条件后实现一个可验证的纵向切片。按需加载文档，用实际测试结果交付，在已有授权范围内连续推进。

[可选 Skill](skills/vibe-coding-sop/SKILL.md) 提供相同执行入口。自动读取 AGENTS.md 和安装 Skill 的方式取决于助手配置，不支持时显式提供文件。本包不依赖其他 Skill 才能工作。

## 项目产物

```text
your-project/
├── AGENTS.md                 # 简短执行入口
└── .sop/
    ├── project.json          # 档位、风险、命令、版本
    ├── state.json            # 当前目标阶段和人工复核
    ├── core/workflow.md      # 按需读取
    ├── docs/                 # 已裁剪模板
    ├── runtime/              # 可独立运行的版本快照
    ├── evidence/             # verify 后生成
    └── handover/             # handover 后生成
```

[配置与证据协议](docs/protocol.md) 说明人工复核、源码指纹和退出码；[维护与迁移](docs/maintenance.md) 说明已有项目接入及显式升级。check 通过仅表示材料和登记证据符合协议，业务质量仍取决于测试断言和实际验收。

## 示例与测试

[行计数示例](examples/counter/README.md) 可以实际跑通自动验证，并演示人工验收仍待完成的状态。

```sh
python -m unittest discover -s tests -v
```

GitHub Actions 配置了 Windows/Linux、Python 3.10/3.14 测试矩阵。业务 CI 参考 [自动检查模板](templates/quality-gates.yml)，先补语言环境和依赖安装。工具 CI 与业务验收分开。

## 版本与来源

当前为 [0.1.0 试用版](CHANGELOG.md)，优先在两个真实项目测量交付耗时、返工、缺陷和人工介入，再扩展自动升级。没有自动修改源码、内置安全扫描器或审批身份认证；具体边界见协议。

从“一堂双三角”的 L0–L4 流程、质量门禁、测试验证和交接规范提炼。Obsidian 保存研究历史，本仓库维护可分发版本。未复制私人路径、服务器配置和未经核验的效果数字。沿用仓库既有 Apache-2.0 许可证。
