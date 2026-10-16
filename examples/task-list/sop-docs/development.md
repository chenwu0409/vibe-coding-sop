# 开发落地说明

## 功能到代码
| 功能 | CLI 入口 | 业务/数据 | 测试 |
|---|---|---|---|
| 新增 | cli.py add | TaskStore.add | test_tc_task_001/002/003/007 |
| 列表 | cli.py list | TaskStore.list_tasks | test_tc_task_006、009 |
| 完成 | cli.py complete | TaskStore.complete | test_tc_task_004/005/006 |
| 用户闭环 | cli.main | 上述方法 | test_tc_task_008/009 |

源文件位于本示例根目录，测试在 tests/test_tasks.py。无 UI、路由或设计系统。

## 数据与接口落点
DDL 的唯一实现位于 TaskStore.__init__；没有另写迁移 SQL。方法契约见 design。CLI 把 ValueError/KeyError 转为退出码2，把 sqlite3.Error/OSError 转为1；成功 JSON 输出。没有对外服务契约、账号或外部 API。

## 关键实现约束
add 在执行 INSERT 前完成 trim 和长度校验；参数化查询；complete 先核对正整数和存在性，再更新 status。使用事务确保操作成功才提交；closing 负责释放连接。初始化只建不存在的表。列表查询 ORDER BY id，不能因完成操作改变顺序。

## 验证与未决事项
project.json 的 test 指向 unittest discover，build 指向 compileall；AC→完整函数名见 validation。适用完成定义是输入/持久化/状态/CLI 断言成立，旧行回归通过。无教学规格阻塞项；真实业务适用性、性能和磁盘故障验证未完成。
