# 本次交接说明

> 用法：先读 .sop/core/stages/06-delivery.md。填写后运行 handover。未完成也可交接，但要保留阻塞和未验证项。

## 用户意图与范围
TODO: 原始诉求、这次实现的 AC、未纳入范围的事项。

## 改动与设计理由
TODO: 直接文件、间接影响路径、关键选择/被拒方案和理由；引用权威设计，不复制整个文档。

## 任务与状态同步
TODO: 列出 `.sop/tasks.json` 中本次任务的 ID、AC、实现状态、测试、证据和验证状态；说明 plan/development/validation 是否已同步，最近 `sync` 指纹和当前阶段。

## 验证与本地复跑
TODO: 当前源码版本/指纹、环境、实际通过/失败的命令和日志；mock/真实边界；接手者必须复跑的测试或人工步骤。

## 恢复与下一步
TODO: Git 基线提交和本次变更提交；失败触发、恢复步骤与数据限制；阻塞/未验证项、下一步责任人和完成标准。没有远端时说明本地仓库位置和备份限制。

## 交付门核对
TODO: state.json.target_stage 是否为 L4；release required task/AC 是否全部闭合；风险档位及适用复核；verify run ID 与 cleanup；分环境状态；平台 attest 或 ENV 阻塞；每个 required task 和当前 HEAD 的 Git checkpoint；接手者已复跑的命令和必须人工复跑的步骤。逐项写已验证、未验证、阻塞和责任人。
