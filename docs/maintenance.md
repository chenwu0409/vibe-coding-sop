# 维护与迁移

Obsidian 保存研究过程和复盘；本仓库维护分发版规则、模板、运行时。稳定规则先在这里修改、测试、提交，再记录到方法论资料。两边不做自动双向同步。

## 新项目与已有项目

将工具包克隆到独立位置，用 init 指向实际业务目录。不要把工具包自身当作业务仓库模板，否则会混入工具包测试、历史和 CI。

已有 AGENTS.md 时使用 --agent-file SOP-AGENTS.md，审阅并将入口链接合入原文件。原有 CI、测试命令、格式化配置优先复用。Skill 是可选入口，安装位置遵循所用助手的配置；本包不会修改机器全局设置。

## 版本与升级

项目 .sop/runtime 是可携带快照，project.json 锁定版本。本版不提供自动升级。需升级时：

1. 确保项目工作区已有可恢复备份，记录旧 SOP 版本。
2. 用新包在临时项目初始化相同 profile/risk/modules。
3. 比较 runtime、core、入口文件、project.json 协议差异。
4. 人工合并规则和运行时，保留已填写 docs 和真实复核记录。

0.2.1 增加目标平台/运行时边界检查。若项目使用小程序、浏览器、移动端、桌面端、插件或其他独立编译器，迁移时必须把平台配置、源码根目录、扫描/打包规则、真实编译入口和未验证状态补入 design/validation/handover；不能用 Node/Python 测试代替平台编译。迁移前后的版本变化都要重新运行 verify，并按实际范围重做受影响复核。
0.2.2 增加任务生命周期五道门、scope 新鲜度和 UI/手势真实操作检查。迁移时要更新 AGENTS、core、templates 和 runtime，并用新版本初始化临时项目验证这些规则确实随项目分发。
0.2.3 增加生产级证据链、敏感数据风险升级、平台配置 schema 检查、可恢复基线和完整交接要求。下一轮试跑应专门记录这些门是否真正阻止了过早交付，而不是只看自动测试是否通过。
0.2.4 将本地 Git、机器可读任务清单和状态同步指纹设为必需门。迁移时必须在项目根目录建立自己的 Git 仓库和命名基线，新增 `.sop/tasks.json`，检查任务状态与 plan/development/validation 的一致性，并先运行 `sync` 再进行阶段检查。旧项目没有基线时不能直接把工作区当作可恢复版本。

0.2.5 增加 `audit` 语义一致性检查和可选平台验证记录。迁移时更新锁定 runtime/core，若项目有微信小程序、Android、iOS 或其他独立平台，在 project.json 设置 `platform.required=true`，填写 `.sop/platform-verification.json`，并运行 `audit --stage L3` 与 `audit --stage L4`。L 档仍是单 Agent，不因有 tasks.json 就获得多 Agent 并行能力。
0.3.0 将 tasks 升级为显式 release scope，并新增分环境验证、run ID 数据生命周期、日志脱敏、平台凭据、doctor 和 Git checkpoint。旧项目迁移时不能只替换 `sop.py`：先把 tasks 转为 v2 并决定 required task/AC；在 project.json 补 environments/test_lifecycle/doctor_checks；全栈项目补 environment-verification；目标平台重新生成 attest；提交后分别登记任务和 L4 checkpoint。旧 v1 任务仍可读取，但没有 backlog 语义，不能作为完整 0.3 交付证据。
0.3.1 增加受控任务状态转换和 L3 checkpoint 硬门禁。迁移时更新 `sop.py`、AGENTS/Skill、protocol 和 README；让 Agent 通过 `task start/block/verify/done` 推进状态，不能直接把未验证任务写成 done/passed；使用 `checkpoint --stage L3` 前必须准备新鲜 verify 证据、通过 audit、至少一项已验证任务和干净 Git 工作区。旧项目仍可读取原 tasks.json，但建议逐项通过新命令重建当前任务状态。
0.3.2 增加只读 `guard` 导航入口，复用已有检查并输出当前阻塞和下一步；doctor 增加 Windows npm/npx/pnpm/yarn 命令包装诊断；handover 嵌入 checkpoints 记录和哈希。迁移时先运行 guard，保留已有项目材料和证据，不新增重复门禁。
5. 一起更新 sop_version，重新运行验证；内容变化导致的复核过期需重新确认。

不能只改版本号，也不要直接用新模板覆盖业务文档。首版保持 0.x，待两个真实项目验证后再评估 1.0。

### 0.1 → 0.2 的具体变化

在临时目录用 0.2 初始化同档位后，完整替换 runtime 和 core；合并入口，按新模板将已有正文整理到必需二级标题下。S/M/L 都新增 validation，M/L 新增 development，所有档新增 handover（交接时填写）。保留已有业务事实，不用空模板覆盖。新增 research/development 按需模块，原配置不需要强行启用。

结构检查比 0.1 更严格，旧的“标题 + 一句话”材料会被判缺章节。保留旧复核记录作为历史，不复制其 scope 来冒充新版范围已确认。补齐材料和版本后重新 verify，再根据 scope 变化确认需要重做的真实复核。详细采用/裁剪理由见 [来源表](source-map.md)。

## 实战检验

先用一个小功能和一个跨模块功能试跑。记录端到端交付耗时、返工、缺陷、人工介入，以及填写 SOP 所花时间。若文档没有影响任何决策或验证，合并或取消它；若缺陷未被测试发现，补充能复现问题的行为测试，再考虑增加规则。

模板和规则只承诺当前测试覆盖的行为。工具本身 CI 与业务项目 CI 分开；工具 CI 通过不代表业务项目通过。
