# 配置与证据协议 v1

## 项目配置

`.sop/project.json` 使用 JSON（UTF-8），避免额外 YAML 解析依赖。

- `schema_version`：固定 1；`sop_version`：生成时锁定的工具版本。
- `profile`：S/M/L；`risk`：normal/high。项目类型与技术栈写入 constitution，命令从项目已有工具读取。
- `modules`：可选 glossary/wireframe/regression/research/development 文档。
- `commands`：门禁 ID 到命令参数数组的映射；不会经过隐式 shell。例如 `["python","-m","unittest","discover","-s","tests"]`。
- `timeout_seconds`：每条命令 1–3600 秒，默认 300。
- `platform`：可选对象；设置 `{"required": true, "name": "..."}` 后，L3/L4 的 `audit` 要求 `.sop/platform-verification.json` 记录真实平台编译和冒烟结果。

初始化会在项目根目录创建自己的本地 Git 仓库。远端不是必需项，但 `.sop/git-baseline.json` 指向的命名提交是必需项；没有 Git 基线，`check` 不通过。使用 `python .sop/runtime/sop.py baseline --message "..."` 建立或更新基线，不由工具自动提交业务代码。

S 要求 test；M 加 build；L 加 lint；high 对任意档加 security。具体工具和覆盖率策略由项目决定。M 的 build 对解释型项目也应配置真实的包导入、编译或安装验证。没有对应检查时应重新评估档位，不使用空命令冒充通过。只执行档位要求的命令；额外检查可组合到项目已有测试脚本中。

若项目依赖独立目标平台/运行时（例如小程序、浏览器、移动端、桌面端、插件或游戏引擎），`build` 必须包含该平台可自动执行的编译/打包检查，或 validation.md 明确记录为何无法自动化、如何人工复跑及当前 ENV/未验证状态。Node/Python 语法检查、业务单测或 mock 不等价于目标平台编译。平台源码根目录、扫描/打包规则和保留目录必须在 design.md 记录，并在交付前核对。

更改配置后需要重新验证和复核。默认 profile 是初始裁剪，不是对项目风险的自动判断。工具不自动执行安装、联网下载、提交或发布。

## 阶段与材料

`.sop/state.json` 的 `target_stage` 默认为 L0。完成当前阶段后手动改为下一阶段，或用 `check --stage L3` 临时检查；阶段改变后必须运行 `sync --stage <阶段>`。检查累积前面阶段的要求。包含 TODO/TBD/NEEDS CLARIFICATION/双花括号占位符或缺少必需二级章节内容的文档不能通过。必需标题定义在 gates/document-sections.json，不随意改名；引用块中的说明、标题、空复选框不算项目内容。

`.sop/tasks.json` 是任务状态的机器可读权威文件，至少包含 `id`、`status`、`ac_ids`、`implementation`、`tests`、`evidence` 和 `verification`。L3/L4 必须有至少一项任务；`status=done` 时必须有非空测试/证据且 `verification=passed`。Markdown 任务表必须与它同步，不能只更新其中一处。

`audit` 是显式的语义一致性检查：它确认任务引用的 AC 在 requirements 中存在，implementation/tests 声明的路径在项目内存在；当 `platform.required=true` 时，还确认平台记录包含工具版本、源码根目录、真实编译和冒烟通过状态。它不判断测试断言质量，也不替代真实用户验收。

检查不判断自然语言内容是否正确；随意填一句话仍可能通过结构检查。因此通过不等于内容审查通过，尤其不能代替独立业务预期和可失败的测试断言。具体内容审查见 core/stages。

S 的计划兼任开发落点记录；M/L 增加 development 文档。所有档在 L4 要求 validation，记录 AC→TC→测试位置/实际证据、失败及未验证项。脚本只保存命令退出码和日志，不自动解析用例数量、生成覆盖率或跨语言 TC 映射。

初始化复制完整阶段手册到 .sop/core，并将 README、实例、模板及规则放入 .sop/runtime。运行时可以脱离原工具库使用；不需要回到 Obsidian 读取原文。

## 任务生命周期与证据新鲜度

每次新任务、继续中断任务或收到会改变结果的新反馈，都按以下顺序运行：起始 `check` → 读取当前阶段手册 → 实现切片 → `verify`/目标平台验证 → 最终 `check --stage L4`。起始 check 的输出是本次基线；旧 Agent 的口头“已通过”或旧日志不能替代它。

下列变化会使相应范围的人工复核失效：需求/AC、宪法、设计、计划、平台源码边界、项目配置、共享接口或源码变化。工具用 `scope_sha256` 判定范围是否仍一致；一旦输出“复核范围已变化”，Agent 必须说明受影响的复核名称和新的 scope，重新取得真实复核，或明确将任务保持为待复核/未交付。只改内部实现也会使 acceptance/release 范围变化，这是有意的；它确保验收针对当前源码。

实现可以在需求/设计复核 pending 时继续的条件只有一个：工作是独立探索、原型或风险实验，且不把结果称为已交付；凡依赖变更后业务语义、共享契约或平台边界的实现，先完成对应复核再进入交付门。

UI、触摸/手势、平台导入、默认值和错误提示属于外部可观察行为。纯函数、Node/Python 测试只能证明其对应逻辑 seam；每个适用行为还要有真实界面人工步骤、端到端测试或目标平台编译/导入证据。平台工具不可用时，记录具体 ENV 阻塞、替代检查、责任人和未验证状态，L4 不能写成完整通过。

## 状态同步协议

每完成一个任务或阶段，必须更新任务清单和受影响文档，然后运行 `sync`。`sync` 将当前阶段、源码、配置、阶段文档和任务清单生成指纹写入 `.sop/sync.json`；`check` 对比该指纹。需求、设计、计划、验证、任务状态、源码或配置任一变化后，旧同步记录立即失效，必须重新同步。

同步顺序固定为：任务状态 → 代码/测试落点 → validation 证据 → 风险/未决事项 → 阶段状态 → `sync` → 当前阶段 `check` → Git 提交。同步提交信息应包含任务 ID 或阶段 ID。未同步、同步过期或任务完成状态缺乏测试/证据时，不得进入下一阶段或写“已完成”。

## 生产级证据链

“生产级”在本协议中不是保证业务没有缺陷，而是要求交付证据可追溯、可复跑、可恢复：

1. 阶段状态与材料一致：推进 `state.json.target_stage`，L4 交付不得仍停在 L0/L1/L2/L3；计划、开发、验证和交接不得保留与当前源码相矛盾的旧状态。
2. 风险档位有依据：敏感数据、权限、外部副作用、不可逆迁移和真实发布触发重新评估；适用时使用 high profile，并保留安全/发布复核。
3. 平台证据分三层：配置 schema/字段、源码边界/保留规则、真实编译/导入/冒烟。仅 JSON 可解析、语法通过或 Node/Python 测试通过不算目标平台通过。
4. 可恢复：保存本地 Git 基线或命名快照、源码指纹、恢复步骤和数据限制。0.2.4 起本地 Git 是必需项，不再把“没有版本控制”视为正常交付路径。
5. 可交接：handover.md 结构和内容完成，接手者能按命令和人工步骤复跑；快照中的 `handover_complete`、blockers 和 narrative 哈希必须审阅。

## 人工复核

复核由真实项目负责人作出；AI 可记录用户已明确给出的意见及出处。登记不是身份认证，也不是自动请求用户重复审批。

先完成相应阶段文档，运行 check，输出待复核项的 `scope_sha256`。把真实复核意见保存为 `.sop/reviews/requirements.md` 等项目内文件，然后修改 state.json 的对应项：

```json
{
  "status": "approved",
  "reviewer": "真实复核人",
  "decision": "需求与验收条件已确认；来源：会议日期或用户消息",
  "evidence": ".sop/reviews/requirements.md",
  "sha256": "证据文件的SHA256",
  "scope_sha256": "check输出的对应scope_sha256"
}
```

PowerShell 可用 `Get-FileHash .sop/reviews/requirements.md -Algorithm SHA256` 获取哈希，记录为小写。Python 通用方式：

```sh
python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('.sop/reviews/requirements.md').read_bytes()).hexdigest())"
```

scope 绑定对应阶段及之前的文档、配置；acceptance/release 还绑定源码。证据应放在 .sop 下，避免源码指纹包含审批文件导致循环变化。需求变化会使后续复核过期。初始化只创建 pending 记录。

## 自动证据与范围

`verify` 保存每个门禁的参数对应配置、退出码、日志哈希、源码指纹和时间。无命令、非零退出、超时、启动失败、执行期间输入变化均失败；`check --stage L4` 再核对日志是否存在且未改动。交接文件会保留尚未完成项。

源码指纹读取整个项目（包括未跟踪文件），跳过以下名字的目录；这不等于目标平台会跳过它们，平台扫描边界必须单独核对：

` .git .sop __pycache__ .venv venv node_modules target dist build .pytest_cache .mypy_cache .gradle coverage .next `

跳过 .pyc/.pyo 文件，拒绝源码中的符号链接。以上目录必须用于依赖或构建产物，业务源码不能放入其中。不要在根目录生成日志、报告或缓存；将报告放在 coverage/build 或 .sop/evidence。输入变化导致保守失效时，先定位生成文件，再重新执行。锁文件和构建配置仍会被纳入指纹。`.sop/tasks.json`、`.sop/sync.json` 和 `.sop/git-baseline.json` 的职责分别是任务状态、同步指纹和本地恢复指针；其中后两者由 `.sop/.gitignore` 排除，避免状态记录反复污染业务提交。

输入扫描只做本地哈希，不把源码内容发送到网络。日志可能包含项目命令输出，发布前审阅。默认项目入口不会修改现有 .gitignore；建议加入 `.sop/evidence/`、`.sop/handover/`，需要审计时自行归档必要证据。

这些记录不是防篡改审计系统；能够改写配置、脚本和报告的主体也能伪造记录。门禁仍依赖实际测试的断言质量。安全扫描由项目自行配置，包中不把正则匹配或包名存在性当作安全保证。

超时限制直接启动的进程；使用可能派生长期后台进程的命令时，项目脚本负责清理进程树，或交给 CI 作业级超时管理。verify 默认不重试、不修改代码。

## 退出码

handover 额外读取 .sop/docs/handover.md，将其路径和 SHA256 写入 narrative。ready 表示 L4 材料/登记证据状态；handover_complete 表示交接正文结构已补齐，handover_issues 列出缺口，两者独立。接收方应检查正文哈希；快照引用正文而非嵌入全文，归档时必须一起保存。旧 design_decisions/next_actions 字段保留兼容，实际理由与下一步写正文。

- 0：命令成功；check 表示所选阶段材料/证据符合协议，verify 表示本次自动检查通过。
- 1：检查未就绪或自动验证失败。
- 2：配置、路径、协议或使用错误。
- handover 成功生成快照时返回 0；查看其 ready/blockers，不能把生成快照等同于交付完成。
