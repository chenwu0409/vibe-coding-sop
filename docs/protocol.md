# 配置与证据协议 v2

## 项目配置

`.sop/project.json` 使用 JSON（UTF-8），避免额外 YAML 解析依赖。

- `schema_version`：固定 1；`sop_version`：生成时锁定的工具版本。
- `profile`：S/M/L；`risk`：normal/high。项目类型与技术栈写入 constitution，命令从项目已有工具读取。
- `modules`：可选 glossary/wireframe/regression/research/development 文档。
- `commands`：门禁 ID 到命令参数数组的映射；不会经过隐式 shell。例如 `["python","-m","unittest","discover","-s","tests"]`。
- `timeout_seconds`：每条命令 1–3600 秒，默认 300。
- `platform`：可选对象；设置 `{"required": true, "name": "..."}` 后，L3/L4 的 `audit` 要求 `.sop/platform-verification.json` 记录真实平台编译和冒烟结果，并要求 `.sop/platform-flows.json` 登记页面清单和 required 关键用户流程。流程状态为 `passed` 时必须有真实平台证据；`blocked`/`unverified` 必须写原因、责任人和下一步，不能通过 L4。
- `environments`：全栈项目声明是否必需、交付环境和该环境的必需检查；各环境结果保存在 `.sop/environment-verification.json`，不得用 test 结果代替 local-dev/staging/production。
- `test_lifecycle.setup/cleanup`：可选参数数组。`verify` 为 setup、全部门禁和 cleanup 注入同一 `SOP_RUN_ID`；cleanup 在门禁失败或超时后仍会运行，cleanup 失败导致 verify 失败。
- `doctor_checks`：项目自己的只读诊断探针，例如测试数据库连通性、迁移权限和 API health。参数数组不经过 shell；探针必须只读，不把迁移或数据修复伪装成诊断。

`guard` 是只读导航入口：默认汇总当前阶段的发布阻塞；`guard --task <ID>` 只核对该任务的状态、AC、文件证据和 Git checkpoint。任务检查通过表示该任务已有可追溯记录，不表示当前源码或整版可发布。整版结论仍使用 `guard --stage L4`；详细诊断回到对应的单项命令。

初始化会在项目根目录创建自己的本地 Git 仓库。远端不是必需项，但 `.sop/git-baseline.json` 指向的命名提交是必需项；没有 Git 基线，`check` 不通过。已有干净 HEAD 时运行 `baseline` 只登记该提交；已有有效基线时再次运行只读取原记录。尚无 HEAD 时，先审阅文件并明确暂存，再运行 `baseline --commit-initial` 提交**已暂存**文件；命令不会自动 `git add`，会拒绝已暂存的 `.env`，也会拒绝仍有未暂存/未跟踪文件，保证基线对应完整工作区。已有提交但工作区不干净时必须先自行审阅并提交，`baseline` 不会代为提交。

Windows 下命令仍使用参数数组和 `shell=False`。需要运行 npm/npx/pnpm/yarn 时，应配置 `cmd /c` 包装，例如 `["cmd", "/c", "npm", "test"]`；doctor 会在 Windows 下报告未包装的命令并给出修复提示。

S 要求 test；M 加 build；L 加 lint；high 对任意档加 security。具体工具和覆盖率策略由项目决定。M 的 build 对解释型项目也应配置真实的包导入、编译或安装验证。没有对应检查时应重新评估档位，不使用空命令冒充通过。只执行档位要求的命令；额外检查可组合到项目已有测试脚本中。

若项目依赖独立目标平台/运行时（例如小程序、浏览器、移动端、桌面端、插件或游戏引擎），`build` 必须包含该平台可自动执行的编译/打包检查，或 validation.md 明确记录为何无法自动化、如何人工复跑及当前 ENV/未验证状态。Node/Python 语法检查、业务单测或 mock 不等价于目标平台编译。平台源码根目录、扫描/打包规则和保留目录必须在 design.md 记录，并在交付前核对。

required 平台故事进入实现前先预检真实工具/模拟器、账号与审批链路、Web/API 可达性及合成资料。未就绪时先登记 ENV 依赖并调整故事顺序或 release 范围，避免在故事末尾才发现无法执行关键路径。

更改配置后需要重新验证和复核。默认 profile 是初始裁剪，不是对项目风险的自动判断。工具不自动执行安装、联网下载、提交或发布。

## 阶段与材料

`.sop/state.json` 的 `target_stage` 默认为 L0。完成当前阶段后手动改为下一阶段，或用 `check --stage L3` 临时检查；阶段改变后必须运行 `sync --stage <阶段>`。检查累积前面阶段的要求。包含 TODO/TBD/NEEDS CLARIFICATION/双花括号占位符或缺少必需二级章节内容的文档不能通过。必需标题定义在 gates/document-sections.json，不随意改名；引用块中的说明、标题、空复选框不算项目内容。

`.sop/tasks.json` 是任务状态的机器可读权威文件。v2 的 `release.id`、`required_task_ids` 和 `required_ac_ids` 冻结当前拟发布版本；新版本先确定范围，再把历史任务留作已完成记录或明确的 backlog，不自动追加到当前 release。每项任务至少包含 `id`、`status`、`ac_ids`、`implementation`、`tests`、`evidence` 和 `verification`。L4 中所有 required task 必须 `done/passed`，required AC 必须真实存在并被覆盖。非 required 未完成任务需写延期原因、责任人和下一步。v1 兼容读取，但没有显式 backlog 语义，L4 将所有任务视为本次范围。

`audit` 是显式的语义一致性检查：它确认任务引用的 AC 在 requirements 中存在，implementation/tests 声明的路径在项目内存在，release AC 有任务覆盖；全栈项目核对交付环境的逐项状态；当 `platform.required=true` 时，L4 只接受 `attest-platform` 生成且证据哈希、源码指纹、流程清单哈希和 Git 历史仍有效的平台凭据。它不判断测试断言质量，也不替代真实用户验收。

平台凭据 v3 的源码指纹由 `platform.source_paths` 限定；流程定义指纹忽略状态与证据字段，仍对 required 路径和页面定义变化敏感。`release open` 默认仅预览；显式 `--apply` 将旧范围存入 `release_history`，选中任务 AC 自动组成新 required AC 集，移出范围的未完成任务须保留 backlog 理由。`verify` 的结构化 summary 与同次运行 artifact 哈希记录在各门禁结果中；声明了格式却无法解析时失败，不能只看进程退出码。

`release_gates` 是发布自动门禁的权威顺序表：无 `--gate` 的 `verify` 必须逐项执行，L4 必须逐项检查同一 run 的状态、日志与可配置数量。不得遗漏 profile/risk/stack 的基础门禁；目标平台配置了 E2E 时必须显式列入，否则配置检查报“发布验证不完整”。

任务状态由 `task` 命令提供受控转换：`start` 将 planned/blocked 转为 in_progress/pending；`verify` 仅在 AC、代码、测试路径真实存在且 evidence 文件真实存在、非空时转为 in_progress/passed；`done` 只接受已经 passed 的任务；`block` 要求填写 `defer_reason`、`owner` 和 `next_action`，并转为 blocked/blocked。直接编辑 JSON 仍可被读取以兼容旧项目，但 `check`/`audit`/checkpoint 会拒绝不一致状态。

检查不判断自然语言内容是否正确；随意填一句话仍可能通过结构检查。因此通过不等于内容审查通过，尤其不能代替独立业务预期和可失败的测试断言。具体内容审查见 core/stages。

S 的计划兼任开发落点记录；M/L 增加 development 文档。所有档在 L4 要求 validation，记录 AC→TC→测试位置/实际证据、失败及未验证项。脚本只保存命令退出码和日志，不自动解析用例数量、生成覆盖率或跨语言 TC 映射。

初始化复制完整阶段手册到 .sop/core，并将 README、实例、模板及规则放入 .sop/runtime。运行时可以脱离原工具库使用；不需要回到 Obsidian 读取原文。

## 任务生命周期与证据新鲜度

每个新故事、恢复中断故事或收到改变业务结果的新反馈时运行只读 `guard`；阶段切换或材料/范围异常时再运行 `check`。一个故事内可以有多个实现 checklist 项，不为每项重复阶段检查、全量 verify、Git checkpoint 和文档同步。起始状态是本次基线；旧口头结论和过期日志不能替代证据。

复核仅由其实际批准内容触发失效。需求复核绑定宪法/需求和项目风险档；设计复核绑定需求、设计、架构/契约和平台/环境边界；acceptance 复核绑定 AC 与 required AC 列表，不绑定普通源码、测试日志或进度文档；release 复核绑定最终源码、交付文档、required task/AC 和平台流程清单。源码实现变化刷新测试/平台证据并使最终 release/平台 attest 过期，但不要求重审已经批准的业务需求、设计决定或 AC。工具用 `scope_sha256` 判定这些边界；只有对应内容实质变化时才重新取得真实复核。

实现可以在需求/设计复核 pending 时继续的条件只有一个：工作是独立探索、原型或风险实验，且不把结果称为已交付；凡依赖变更后业务语义、共享契约或平台边界的实现，先完成对应复核再进入交付门。

L3 checkpoint 是实现阶段出口，不是文字记录。它要求至少一项任务已经 done/passed，当前源码和配置有新鲜且成功的 `verify` 报告，所有项目门禁通过，`audit --stage L3` 无问题，且本地 Git 工作区干净。未验证的平台或环境只能登记为 blocked/unverified，不能转换为完成证据。

UI、触摸/手势、平台导入、默认值和错误提示属于外部可观察行为。纯函数、Node/Python 测试只能证明其对应逻辑 seam；每个适用行为还要有真实界面人工步骤、端到端测试或目标平台编译/导入证据。平台工具不可用时，记录具体 ENV 阻塞、替代检查、责任人和未验证状态，L4 不能写成完整通过。

## 状态同步协议

每完成一个故事或阶段，更新任务清单和受影响文档，然后运行 `sync`。`sync` 将当前阶段、源码、配置、阶段文档和任务清单生成指纹写入 `.sop/sync.json`；`check` 对比该指纹。故事内部源码变更会让验证证据过期，但无需每个编辑都运行 sync；需求/设计/计划/共享契约变化后立即同步并复核，故事边界和阶段交付必须重新同步。

故事收尾顺序为：故事任务状态 → 实现/测试落点 → validation 证据 → 风险/未决事项 → `sync` → 当前阶段 `check` → 审阅并提交带故事 ID 的 Git commit → `checkpoint --task <ID>`。任务卡代表故事，因此每个 required 故事只登记一次 checkpoint；内部 checklist 不登记 checkpoint。全部故事完成后，检查最近一次成功 `verify` 是否仍匹配当前源码和配置；有效时复用，过期时重跑。最终治理记录提交并运行 `checkpoint --stage L4`。工具只验证和登记已审阅提交，不自动暂存业务文件。故事缺少测试/证据、工作区未提交或交付证据过期时，不得写“已完成”。

## 生产级证据链

“生产级”在本协议中不是保证业务没有缺陷，而是要求交付证据可追溯、可复跑、可恢复：

1. 阶段状态与材料一致：推进 `state.json.target_stage`，L4 交付不得仍停在 L0/L1/L2/L3；计划、开发、验证和交接不得保留与当前源码相矛盾的旧状态。
2. 风险档位有依据：敏感数据、权限、外部副作用、不可逆迁移和真实发布触发重新评估；适用时使用 high profile，并保留安全/发布复核。
3. 平台证据分三层：配置 schema/字段、源码边界/保留规则、真实编译/导入/冒烟。证据通过 `attest-platform` 绑定工具版本、证据哈希、源码指纹和 Git 提交；手工写 passed、仅 JSON 可解析、语法通过或 Node/Python 测试通过均不算目标平台通过。
4. 可恢复：保存本地 Git 基线、每个 required 故事的 checkpoint、当前 HEAD 的 L4 checkpoint、源码指纹、恢复步骤和数据限制。远端仓库不是必需项，本地 Git 是必需项。
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

`verify` 保存 run ID、执行范围、每个门禁的退出码、脱敏日志哈希、源码指纹、配置哈希和时间。`verify --gate <名称>` 可重复指定已配置门禁，仅为本次影响面产生 `focused-latest.json`；无参数的全量 `verify` 才更新 `latest.json`，L4 只认可全量记录。每条子进程收到相同 `SOP_RUN_ID`；项目据此标记测试租户/数据，cleanup 必须只删除该 run ID 的数据。无命令、setup/cleanup 失败、非零退出、超时、启动失败、执行期间输入变化均失败；`check --stage L4` 再核对全量日志是否存在且未改动。测试数量和跳过项因框架不同由项目测试报告及 validation 明确登记，不能从退出码推断。

日志在写盘前遮蔽常见 Bearer/JWT、Cookie、数据库 URL 和 password/token/secret/API key；报告只保存脱敏配置副本及原配置哈希。该规则降低意外泄露，不替代项目的 secret scanner。`doctor` 会阻止 Git 已跟踪的 `.env`，并报告 `.env.example` 中疑似明文凭证的字段名而不打印值。

源码指纹读取整个项目（包括未跟踪文件），跳过以下名字的目录；这不等于目标平台会跳过它们，平台扫描边界必须单独核对：

` .git .sop __pycache__ .venv venv node_modules target dist build .pytest_cache .mypy_cache .gradle coverage .next `

跳过 .pyc/.pyo 文件，拒绝源码中的符号链接。以上目录必须用于依赖或构建产物，业务源码不能放入其中。不要在根目录生成日志、报告或缓存；将报告放在 coverage/build 或 .sop/evidence。输入变化导致保守失效时，先定位生成文件，再重新执行。锁文件和构建配置仍会被纳入指纹。`.sop/tasks.json`、`.sop/sync.json`、`.sop/git-baseline.json` 和 `.sop/checkpoints.json` 的职责分别是交付范围/任务状态、同步指纹、初始恢复指针和任务/阶段 Git 指针；后三者由 `.sop/.gitignore` 排除。

输入扫描只做本地哈希，不把源码内容发送到网络。日志可能包含项目命令输出，发布前审阅。默认项目入口不会修改现有 .gitignore；建议加入 `.sop/evidence/`、`.sop/handover/`，需要审计时自行归档必要证据。

这些记录不是防篡改审计系统；能够改写配置、脚本和报告的主体也能伪造记录。门禁仍依赖实际测试的断言质量。安全扫描由项目自行配置，包中不把正则匹配或包名存在性当作安全保证。

超时限制直接启动的进程；使用可能派生长期后台进程的命令时，项目脚本负责清理进程树，或交给 CI 作业级超时管理。verify 默认不重试、不修改代码。

## 退出码

handover 额外读取 .sop/docs/handover.md，将其路径和 SHA256 写入 narrative，并嵌入当前 checkpoints 记录及其哈希，方便跨 Agent 交接时核对本地 checkpoint。ready 表示 L4 材料/登记证据状态；handover_complete 表示交接正文结构已补齐，handover_issues 列出缺口，两者独立。接收方应检查正文和 checkpoints 哈希；快照引用正文而非嵌入全文，归档时必须一起保存。旧 design_decisions/next_actions 字段保留兼容，实际理由与下一步写正文。

- 0：命令成功；check 表示所选阶段材料/证据符合协议，verify 表示本次自动检查通过。
- 1：检查未就绪或自动验证失败。
- 2：配置、路径、协议或使用错误。
- handover 成功生成快照时返回 0；查看其 ready/blockers，不能把生成快照等同于交付完成。
