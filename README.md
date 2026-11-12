# AI RecruitFlow

招聘记录自动化系统：React/TypeScript/Vite/Ant Design + FastAPI/Pydantic/SQLAlchemy。先运行不需要任何 Key 的 Mock，再按 S1~S7 完成业务和授权接入。

**当前为 S0 工程基线**：工作台、申请列表/新增、有限规则 Mock 录入、模拟同步。完整 CRUD、RBAC、Alembic、人工审核、真实 DeepSeek/腾讯文档/企业微信仍待后续阶段，不能用于生产或真实个人资料。S0 所有写操作只允许本机开发身份，生产/live 模式拒绝启动。

## 工作区

- `starter/backend/app/schemas.py`：前后端统一契约源。
- `contracts/openapi.yaml`：由实际 FastAPI 路由生成，只有已实现接口。
- `starter/frontend/src/types/api.generated.ts`：由 OpenAPI 自动生成，禁止手改。
- `docs/01~12`：产品与目标设计；`docs/13-统一数据契约与扩展规范.md`：字段/版本/扩展规范。
- `codex/PHASE_TASKS.md`：S0~S7 执行与验收顺序。
- `docs/IMPLEMENTATION_REPORT.md`：逐阶段实际结果与限制。

## 安装（仓库根目录）

需要 Python **3.11+**（本次验证 3.12）、Node.js **22.12+** 和 npm 10+。Python 3.10 不支持。已有 `.venv` 时可跳过环境创建。本工作区已准备独立 Python 3.12 和后端虚拟环境；这些本地工具不纳入 Git。

Windows PowerShell（已安装 Python 3.12 的新环境）：

```powershell
py -3.12 -m venv starter/backend/.venv
starter/backend/.venv/Scripts/python.exe -m pip install --require-hashes -r starter/backend/requirements.lock
Copy-Item starter/backend/.env.example starter/backend/.env
npm ci
```

Linux/macOS：

```bash
python3 -m venv starter/backend/.venv
starter/backend/.venv/bin/python -m pip install --require-hashes -r starter/backend/requirements.lock
cp starter/backend/.env.example starter/backend/.env
npm ci
```

`.env` 已存在时保留自己的文件，不覆盖。Mock 无需填写任何三方凭证。Python `requirements.lock` 包含开发依赖、精确版本、跨平台标记与哈希；Windows 已实测，Linux/macOS 尚未实机验收。npm 统一使用根目录 `package-lock.json`，不要在 frontend 另建锁文件。

## 启动

两个终端均位于根目录，无需激活虚拟环境：

```bash
# 终端1
npm run dev:api
# 终端2
npm run dev:web
```

打开 [Mock 页面](http://127.0.0.1:5173)、[后端文档](http://127.0.0.1:8000/docs)、[健康检查](http://127.0.0.1:8000/api/v1/health)。Vite 将 `/api` 转发给 8000。5173 被占用会明确失败，不自动换端口。数据库默认位于 `starter/backend/recruitflow.db`，不得提交。

## 演示与检查

1. 候选人记录：新增虚构姓名、岗位、编号 `A10001`。
2. AI消息录入：输入 `A10001 一面通过`，当前阶段进入二面、版本递增；或输入 `新增虚构乙应聘数据分析岗`。
3. 返回工作台刷新：阶段分布和数量来自数据库；空库显示空态。
4. 同步中心执行模拟同步：显示 `MOCK-` ID；同一申请更新复用映射，**不会写入腾讯文档**。
5. 同名、模糊时间和复合消息只提示需确认，尚无持久化审核队列（S2）。

```bash
npm run check             # 契约漂移 + lint + Python/TS类型 + pytest + build
npm run smoke:http        # 两个服务启动后执行；留下1条虚构申请，验证HTTP/代理/完整Mock链路
npm run contracts:generate # 修改schema/路由后重新生成OpenAPI和TS
npm run contracts:check
```

后端单独检查：进入 `starter/backend`，激活 `.venv` 后运行 `python -m pytest -q`、`python -m compileall -q app`。前端可单独运行 `npm run typecheck --workspace starter/frontend` 和 `npm run build --workspace starter/frontend`。S4 再补组件测试，不以空脚本冒充测试通过。

## 字段扩展

先改 Pydantic，再生成 OpenAPI/TS，契约检查会阻止手工类型漂移。核心字段强类型；API ID 始终为字符串、时间为 UTC、修改实体带 version。新业务字段需要数据库列时，从 S1 起必须带 Alembic 迁移；组织自定义字段按受控命名空间 JSON 设计，不混入权限/阶段等核心字段。详见 [扩展规范](docs/13-统一数据契约与扩展规范.md)。

S0仍使用 `create_all`，没有正式迁移；不会删除已有库。S1须补迁移及旧Starter升级策略。已有旧消息事件的幂等键格式与本次source分域格式不同，旧演示库不要重放历史消息；正式迁移前只使用虚构样本。

## 当前验证边界

自动化结果和浏览器可视验收分别记录在实施报告。当前 Windows 浏览器自动化受工具安全检查阻断，不能据 HTTP 冒烟声称已完成浏览器操作验收。所有真实连接均未接入；后续有凭证的阶段必须先验证权限及真实工具 schema。

已初始化本地Git仓库，使用main分支，尚未配置远程仓库。`.env`、数据库、日志、本地工具、个人资料不得纳入版本控制。
