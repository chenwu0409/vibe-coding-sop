# Vibe Coding SOP

可迁移、按项目复杂度裁剪的 AI 编程工作流。Python 3.10+，无第三方运行依赖。

## 五分钟开始

```sh
git clone https://github.com/chenwu0409/vibe-coding-sop.git
python vibe-coding-sop/sop.py init ../my-app --name my-app --profile M --risk normal
cd ../my-app
python .sop/runtime/sop.py check
```

初始化生成待填写材料，第一次检查失败是预期行为。让 Agent 先读生成的 AGENTS.md，结合现有代码和你的目标起草项目文档，只针对关键缺口提问。按阶段补齐，不要求先手工填完所有表格。项目携带锁定版本的运行时、阶段手册、模板和实例，离开工具仓库及 Obsidian 后仍可工作。

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
| S | 小工具、局部修改 | 宪法、需求、计划、验证摘要 | test | 验收 |
| M（默认） | 普通业务应用 | S + 技术设计、开发落点 | test、build | 需求、设计、验收 |
| L | 跨模块、多人/Agent | M + 术语、任务、回归计划 | test、build、lint | 宪法、需求、设计、验收 |

`--risk high` 对任意档追加 risk 文档、security 命令和发布/回滚复核；`--module` 可按需增加 glossary、wireframe、regression、research、development。所有档生成交接模板，但不要求启动时填写。覆盖率与函数长度由项目自定，不用统一数字代替质量判断。

## 具体如何做

入口保持短，实质内容在按需加载的手册中；每册给出输入、步骤、例子、内容审查及完成条件。

| 当前问题 | 操作手册 | 必须留下的结果 |
|---|---|---|
| 目标/底线是什么 | [项目宪法](core/stages/00-constitution.md) | 目标、非目标、带理由和检查方法的约束 |
| 到底做什么、怎样算对 | [需求与探索](core/stages/01-discovery.md) | 故事、可观察 AC、业务流程、澄清项；按需原型/术语/研究 |
| 怎样设计才能实现 | [技术设计](core/stages/02-design.md) | 模块契约、状态/数据、异常策略、质量验证、方案取舍 |
| 第一刀从哪里切 | [计划与开发落点](core/stages/03-planning.md) | 可复跑 Quickstart、宪法对照、代码/测试位置、任务依赖 |
| 怎样持续实现且不改坏 | [实现与反馈](core/stages/04-implementation.md) | 行为测试、最小修改、直接与间接影响回归 |
| 凭什么说完成 | [验证与质量门](core/stages/05-validation.md) | AC→TC→实际测试映射、原始证据、失败分类和人工验收 |
| 如何交给下个 Agent/上线 | [交付与交接](core/stages/06-delivery.md) | 真实限制、复跑命令、恢复边界、下一步和快照 |

小改动只更新受影响材料，不重走整套立项。模板里的示例是写法参考，不是项目决定；初始化后保留占位，避免“生成了文件就算完成”。

## Agent 的入口

生成的 AGENTS.md 很短，按任务指向工作流和对应阶段材料。给编码助手的启动提示：

> 阅读本项目 AGENTS.md 与 .sop/project.json，运行 check。先探索现有代码，按 .sop/core/workflow.md 路由加载当前阶段手册。根据我给出的目标起草本阶段文档，标明事实、假设及需要我决定的事项。明确验收条件后实现一个可验证的纵向切片，检查旧行为回归，用实际测试结果交付，在已有授权范围内连续推进。不要把模板示例当成我的决定，也不要代签审批。

[可选 Skill](skills/vibe-coding-sop/SKILL.md) 提供相同执行入口。自动读取 AGENTS.md 和安装 Skill 的方式取决于助手配置，不支持时显式提供文件。本包不依赖其他 Skill 才能工作。

## 项目产物

```text
your-project/
├── AGENTS.md                 # 简短执行入口
└── .sop/
    ├── project.json          # 档位、风险、命令、版本
    ├── state.json            # 当前目标阶段和人工复核
    ├── core/                # 总流程 + 7 个阶段操作手册
    ├── docs/                 # 已裁剪模板
    ├── runtime/              # 可独立运行的版本快照
    ├── evidence/             # verify 后生成
    └── handover/             # handover 后生成
```

[配置与证据协议](docs/protocol.md) 说明人工复核、源码指纹和退出码；[维护与迁移](docs/maintenance.md) 说明已有项目接入及显式升级。check 通过仅表示材料和登记证据符合协议，业务质量仍取决于测试断言和实际验收。

## 示例与测试

优先看 [任务清单完整实例](examples/task-list/README.md)：已填写的宪法、需求、设计、计划、开发落点、验证和交接材料，配套真实 SQLite/CLI 代码和 9 个测试。工具测试还会故意改坏完成任务的实现，确认门禁失败。实例展示材料如何指导实现，审批保持 pending。

[行计数小例](examples/counter/README.md) 用于快速体验 S 档命令，不是完整文档范本。

```sh
python -m unittest discover -s tests -v
```

GitHub Actions 配置了 Windows/Linux、Python 3.10/3.14 测试矩阵。业务 CI 参考 [自动检查模板](templates/quality-gates.yml)，先补语言环境和依赖安装。工具 CI 与业务验收分开。

## 版本与来源

当前为 [0.2.0 试用版](CHANGELOG.md)，优先在两个真实项目测量交付耗时、返工、缺陷和人工介入，再扩展自动升级。没有自动修改源码、内置安全扫描器或审批身份认证；具体边界见协议。0.1 项目需要显式迁移，不能只改版本号。

从“一堂双三角”的 L0–L4 流程、质量门禁、测试验证和交接规范提炼。[来源与取舍表](docs/source-map.md) 逐项说明采用了什么、放在哪里、哪些规则未机械照搬。Obsidian 保存研究历史，本仓库维护可分发版本。未复制私人路径、服务器配置和未经核验的效果数字。沿用仓库既有 Apache-2.0 许可证。
