# 后端 Mock Starter

S2本机开发：已实现领域模型、Alembic、CRUD/权限/状态机/版本、Parser协议、接入租约与人工审核。main仅装配应用，api/services/db/schemas/core/integrations分层；运行脚本位于scripts/contracts、migrations、smoke。生产认证与真实MCP/企微未接入；DeepSeek适配器已实现但无凭证联调。

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
`POST /api/v1/sync/run`：只模拟腾讯文档同步。

旧S0数据库须用-m scripts.migrations.upgrade_s0复制升级，不能直接stamp或覆盖原库。新数据库先Alembic upgrade，启动只校验版本。所有写接口要求Idempotency-Key，PATCH/DELETE另需If-Match；自然语言接入使用external_event_id。默认模拟管理员，X-Dev-User可切换服务端虚构用户。

Python3.11+，本次验证3.12；所有响应为data/request_id，列表带pagination。契约源app/schemas/，根目录npm run contracts:generate生成OpenAPI与TS。参见根README与实施报告。
