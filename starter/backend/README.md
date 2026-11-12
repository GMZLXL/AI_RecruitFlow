# 后端 Mock Starter

S1本机Mock：已实现领域模型、Alembic、业务CRUD、开发RBAC、状态机/乐观锁、软删除和事务审计/outbox。生产认证、完整AI审核和真正DeepSeek/MCP/企微未接入，生产运行被主动阻止。

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

旧S0数据库须用scripts/upgrade_s0.py复制升级，不能直接stamp或覆盖原库。新数据库先Alembic upgrade，启动只校验版本。所有写接口要求Idempotency-Key，PATCH/DELETE另需If-Match；自然语言接入使用external_event_id。默认模拟管理员，X-Dev-User可切换服务端虚构用户。

Python3.11+，本次验证3.12；所有响应为data/request_id，列表带pagination。契约源app/schemas.py，根目录npm run contracts:generate生成OpenAPI与TS。参见根README与实施报告。
