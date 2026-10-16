# 技术设计

## 架构与模块
用户→cli.py（参数/JSON/错误映射）→TaskStore（业务校验/事务）→SQLite。单进程每次命令可重新打开同一数据库；无服务器和外部服务。存储模块隐藏 SQL 与事务，不让 CLI 管理连接。

## 契约与状态
| 接口 | 输入 | 输出/错误 | 副作用/AC |
|---|---|---|---|
| add | trim 后长度 1–120 的字符串 | id/title/pending；ValueError | 新增一行，失败不插入；AC-001/002/003/007 |
| list_tasks | 无 | ID 递增对象数组 | 只读；AC-006 |
| complete | 正整数 id（不接受 bool） | 同一 id/title/done；KeyError/ValueError | 更新状态，重复幂等；AC-004/005 |
| CLI | --db 路径 + 子命令 | 成功 JSON 退出0，输入错误退出2，存储错误退出1 | AC-008 |

状态只有 pending→done 和 done→done；不改变标题和 ID。

## 数据与迁移
tasks(id INTEGER PRIMARY KEY,title TEXT NOT NULL,status TEXT NOT NULL CHECK)。id 是稳定主键；没有标题唯一约束。新增/完成使用连接事务，异常退出回滚，连接显式关闭。按主键排序不需要额外索引。
首次运行 CREATE TABLE IF NOT EXISTS；没有变更旧表结构的迁移。初始化不得清空现有表。后续结构升级需单独迁移与备份设计。当前不承诺并发性能与异常断电恢复。

## 外部依赖
仅 Python 内置 sqlite3；无远程 API、网络凭证、重试或熔断。应用参数使用参数化 SQL；SQL 文本作为普通标题处理。

## 质量与验证
纯输入校验与持久化共同用临时 SQLite 集成测试；关键用户旅程通过 subprocess 启动 CLI。重开库证明持久化，不用 mock 冒充数据库。编译检查验证两个入口模块语法，不能代替功能测试。错误提示由 CLI 映射，未对文件权限/磁盘耗尽做故障注入，作为未验证项保留。

## 决策与宪法对照
C-001 选择标准库降低接入成本；C-002 JSON 方便用户脚本及测试读取；C-003 独立临时库；C-004 通过重开及旧行测试。
放弃 JSON 文件存储，因为示例需展示事务/状态更新边界；放弃 Web UI，集中验证业务闭环。无违反宪法项。上述是示例设计选择，真实接入需负责人复核。
