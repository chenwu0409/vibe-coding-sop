# 配置与证据协议 v1

## 项目配置

`.sop/project.json` 使用 JSON（UTF-8），避免额外 YAML 解析依赖。

- `schema_version`：固定 1；`sop_version`：生成时锁定的工具版本。
- `profile`：S/M/L；`risk`：normal/high。项目类型与技术栈写入 constitution，命令从项目已有工具读取。
- `modules`：可选 glossary/wireframe/regression 文档。
- `commands`：门禁 ID 到命令参数数组的映射；不会经过隐式 shell。例如 `["python","-m","unittest","discover","-s","tests"]`。
- `timeout_seconds`：每条命令 1–3600 秒，默认 300。

S 要求 test；M 加 build；L 加 lint；high 对任意档加 security。具体工具和覆盖率策略由项目决定。M 的 build 对解释型项目也应配置真实的包导入、编译或安装验证。没有对应检查时应重新评估档位，不使用空命令冒充通过。只执行档位要求的命令；额外检查可组合到项目已有测试脚本中。

更改配置后需要重新验证和复核。默认 profile 是初始裁剪，不是对项目风险的自动判断。工具不自动执行安装、联网下载、提交或发布。

## 阶段与材料

`.sop/state.json` 的 `target_stage` 默认为 L0。完成当前阶段后手动改为下一阶段，或用 `check --stage L3` 临时检查。检查累积前面阶段的要求。包含 TODO/TBD/双花括号占位符或仅有标题的文档不能通过；检查不判断自然语言内容是否正确。

原始模板为长篇资料，本包将开发文档合入 design/plan；测试用例以实际测试代码和验收编号为准，报告从执行生成，避免重复填写。

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

源码指纹读取整个项目（包括未跟踪文件），跳过以下名字的目录：

` .git .sop __pycache__ .venv venv node_modules target dist build .pytest_cache .mypy_cache .gradle coverage .next `

跳过 .pyc/.pyo 文件，拒绝源码中的符号链接。以上目录必须用于依赖或构建产物，业务源码不能放入其中。不要在根目录生成日志、报告或缓存；将报告放在 coverage/build 或 .sop/evidence。输入变化导致保守失效时，先定位生成文件，再重新执行。锁文件和构建配置仍会被纳入指纹。

输入扫描只做本地哈希，不把源码内容发送到网络。日志可能包含项目命令输出，发布前审阅。默认项目入口不会修改现有 .gitignore；建议加入 `.sop/evidence/`、`.sop/handover/`，需要审计时自行归档必要证据。

这些记录不是防篡改审计系统；能够改写配置、脚本和报告的主体也能伪造记录。门禁仍依赖实际测试的断言质量。安全扫描由项目自行配置，包中不把正则匹配或包名存在性当作安全保证。

超时限制直接启动的进程；使用可能派生长期后台进程的命令时，项目脚本负责清理进程树，或交给 CI 作业级超时管理。verify 默认不重试、不修改代码。

## 退出码

- 0：命令成功；check 表示所选阶段材料/证据符合协议，verify 表示本次自动检查通过。
- 1：检查未就绪或自动验证失败。
- 2：配置、路径、协议或使用错误。
- handover 成功生成快照时返回 0；查看其 ready/blockers，不能把生成快照等同于交付完成。
