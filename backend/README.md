# 后端服务（开发 Mock）

当前S6：新增0006_s6、RS256网关Cookie/DB授权/CSRF、请求限流/安全日志、AI配置加密、任务领导租约/健康、操作员与SQLite备份恢复脚本。真实SSO网关和外部连接器未联调，完整live拒绝。安装最新requirements.lock并备份后迁移；202项后端回归通过。API/TS契约已同步，实际运行与生产前置条件见根README及docs/15，以下保留阶段历史。

S5新增0005_s5、schemas/wecom、验签/AES适配器、持久接收与通知/提醒队列、配置与用户绑定API。SDK/密码库已锁定，安装requirements.lock后迁移；无Key保持Mock，真实企微未联调，生产身份仍待S6。`npm run smoke:wecom`验证后台闭环，不发送外部消息。

当前S4：新增独立offers、工作台聚合统计/安全历史/待办投影/岗位负责人选项与规则读取。0004_s4迁移已验证；前后端契约源不变。根npm run demo:seed生成24条明确标记的虚构申请；npm run smoke:workbench验证Offer与录用分离及权限。详情见根README和实施报告，下方保留基础运行方法。

S3本机开发：已实现领域模型、Alembic、CRUD/权限/状态机/版本、Parser与人工审核、异步outbox与持久Mock投影。main仅装配应用，api/services/db/schemas/core/integrations/jobs分层；脚本按contracts、migrations、smoke、integrations分目录。生产认证与真实MCP/企微未接入；腾讯适配器因凭证/实测Schema缺失而阻断写入。

```bash
python -m venv .venv
# 激活后
pip install --require-hashes -r requirements.lock
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m pytest -q
```

`POST /api/v1/applications`: `{"candidate_name":"虚构甲","position_title":"数据分析岗","application_code":"A10001"}`
`POST /api/v1/ingestions`: `{"text":"A10001 一面通过","external_event_id":"demo-001"}`
`POST /api/v1/sync/run`：202接受后台唤醒，实际结果见GET /sync/jobs；后台默认每2秒处理任务。POST /sync/jobs/{id}/retry仅管理员、要求任务revision的If-Match、Idempotency-Key和说明。默认只模拟智能表格同步。

旧S0数据库须用-m scripts.migrations.upgrade_s0复制升级，不能直接stamp或覆盖原库。新数据库先Alembic upgrade，启动只校验版本。所有写接口要求Idempotency-Key，PATCH/DELETE另需If-Match；自然语言接入使用external_event_id。默认模拟管理员，X-Dev-User可切换服务端虚构用户。

Python3.11+，本次验证3.12；所有响应为data/request_id，列表带pagination。契约源app/schemas/，根目录npm run contracts:generate生成OpenAPI与TS。参见根README与实施报告。
