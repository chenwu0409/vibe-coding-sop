# 验证计划与证据入口

## 需求到测试
全部用例位于 tests/test_tasks.py 的 TaskTests，使用独立临时 SQLite，无远程 mock。
| AC | TC/目的 | 前置/输入 | 可断言预期 | 函数 |
|---|---|---|---|---|
| AC-001 | TC-TASK-001 持久化 | 空库、带空白中文标题 | 重开仍同ID/trim标题/pending | test_tc_task_001_persists_after_reopen |
| AC-002 | TC-TASK-002 非法输入 | 空/空白/121字符/None | ValueError、零写入 | test_tc_task_002_invalid_title_never_inserts |
| AC-003 | TC-TASK-003 长度边界 | 1/120字符 | 返回完整标题 | test_tc_task_003_title_boundary |
| AC-004 | TC-TASK-004 完成幂等 | pending任务，调用两次 | done、内容一致、仍一行 | test_tc_task_004_complete_is_idempotent |
| AC-005 | TC-TASK-005 ID错误 | 0/-1/bool/字符串/不存在 | 指定异常、无新增 | test_tc_task_005_missing_and_invalid_ids |
| AC-006 | TC-TASK-006 旧行回归 | 两任务，完成第二条 | 重开顺序不变、第一条不变 | test_tc_task_006_regression_order_and_existing_rows |
| AC-007 | TC-TASK-007 SQL文字 | SQL文本标题 | 当作文字、表可读取 | test_tc_task_007_sql_text_is_data |
| AC-008 | TC-TASK-008 CLI闭环 | 独立进程创建/完成/列表 | JSON一致，退出0 | test_tc_task_008_cli_end_to_end |
| AC-008 | TC-TASK-009 CLI失败 | 空白标题/空库列表 | 退出2且stderr、列表[] | test_tc_task_009_cli_error_and_empty_list |

## 环境与执行结果
运行 python -m unittest discover -s tests -v，应收集9个测试；build 用 compileall。此文件是可复制的验证计划，未附使用者本次执行的时间/源码指纹/日志，不宣称这次已经跑过。verify 后在 .sop/evidence/latest.json 找实际日志，再补真实通过/失败/跳过数量。覆盖率、性能未测。

## 失败与修复
运行者若遇到失败，按日志记录 TC、期望/实际、CODE/BIZ/ENV/TEST 依据、最小修复和重跑路径。没有本次执行记录，不能写“零失败”。工具包的示例测试会故意把 complete 改成保留 pending，预期 TC-004/008 暴露错误；这是测试有效性实验，不是本例已知缺陷。

## 质量门结论
Q-01/02/03 由上述测试和实际验收验证，目前待运行者执行；Q-04 无外部依赖/凭证，参数化 SQL 由TC-007检查；Q-05 关键接口可从 design 解释，build 待执行；Q-06 需求/文件映射已给出，运行者核对实际差异；Q-07 仍待真实负责人复核。没有全绿声明或伪造签字。

## 验收与限制
真实使用者应在独立演示库完成新增→重启→完成，确认输出可接受；需求/设计/acceptance 记录保持 pending，按实际意见登记。未做压测、磁盘故障注入、多进程竞争、生产部署验证；不能用于宣称这些场景可靠。
