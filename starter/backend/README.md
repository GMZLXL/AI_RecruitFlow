# 后端 Mock Starter

只适用于本地教学与Codex工程起点：**未实现**完整RBAC、Alembic迁移、真正DeepSeek/MCP/企微接入。生产运行被主动阻止。

```bash
python -m venv .venv
# 激活后
pip install --require-hashes -r requirements.lock
uvicorn app.main:app --reload --port 8000
python -m pytest -q
```

`POST /api/v1/applications`: `{"candidate_name":"虚构甲","position_title":"数据分析岗","application_code":"A10001"}`
`POST /api/v1/ingestions`: `{"text":"A10001 一面通过","external_event_id":"demo-001"}`
`POST /api/v1/sync/run`：只模拟腾讯文档同步。

Codex 在 S1 中必须把 `Base.metadata.create_all` 迁移为 Alembic；补充身份/事件状态/幂等约束等。

Python 3.11+，本次验证3.12。所有响应为data/request_id；列表带pagination；错误统一error/request_id。运行契约来源app/schemas.py，根目录npm run contracts:generate生成OpenAPI与前端类型。S0有事务性audit_logs与本机固定开发身份，但不是完整RBAC。
