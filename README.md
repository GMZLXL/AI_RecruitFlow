# AI RecruitFlow

招聘记录自动化系统：React/TypeScript/Vite/Ant Design + FastAPI/Pydantic/SQLAlchemy。先运行不需要任何 Key 的 Mock，再按 S1~S7 完成业务和授权接入。

**当前完成 S1 数据与业务基础**：十二类领域模型、Alembic迁移、UUID关联、候选人/岗位/申请/面试CRUD、分页筛选、开发RBAC、版本冲突、软删除、事务审计/outbox，以及有限Mock录入和模拟同步。完整AI审核在S2；真实DeepSeek/腾讯文档/企业微信尚未连接。仅用于虚构资料与本机演示，生产/live模式拒绝启动。

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
npm run db:upgrade
```

Linux/macOS：

```bash
python3 -m venv starter/backend/.venv
starter/backend/.venv/bin/python -m pip install --require-hashes -r starter/backend/requirements.lock
cp starter/backend/.env.example starter/backend/.env
npm ci
npm run db:upgrade
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

1. 顶部默认“模拟管理员”；候选人记录新增虚构姓名、岗位、编号 `A10001`。
2. 列表人工推进至“简历筛选”、再推进至“一面”。AI消息录入输入 `A10001 一面通过`，进入二面、版本递增。S1严格校验状态机，不能从新申请直接跳二面。
3. 返回工作台刷新：阶段分布和数量来自数据库；空库显示空态。
4. 同步中心执行模拟同步：显示 `MOCK-` ID；同一申请更新复用映射，**不会写入腾讯文档**。
5. 顶部可切换模拟HR/负责人：HR仅查看本人，负责人只读所属部门，同步中心仅管理员可访问；后端同样执行限制。HR新增申请须使用已配置的岗位。
6. 终态逆转通过PATCH接口创建持久化确认任务，暂不执行逆转；完整审核执行/驳回在S2。Mock同名或时间歧义保存接入记录并返回需确认。

```bash
npm run check             # 契约漂移 + lint + Python/TS类型 + pytest + build
npm run smoke:http        # 两个服务启动后执行；留下1条虚构申请，验证HTTP/代理/完整Mock链路
npm run contracts:generate # 修改schema/路由后重新生成OpenAPI和TS
npm run contracts:check
npm run db:check           # 模型与迁移漂移检查
```

后端单独检查：进入 `starter/backend`，激活 `.venv` 后运行 `python -m pytest -q`、`python -m compileall -q app`。前端可单独运行 `npm run typecheck --workspace starter/frontend` 和 `npm run build --workspace starter/frontend`。S4 再补组件测试，不以空脚本冒充测试通过。

## 字段扩展

先改 Pydantic，再生成 OpenAPI/TS，契约检查会阻止手工类型漂移。核心字段强类型；API ID 始终为字符串、时间为 UTC、修改实体带 version。新业务字段需要数据库列时，从 S1 起必须带 Alembic 迁移；组织自定义字段按受控命名空间 JSON 设计，不混入权限/阶段等核心字段。详见 [扩展规范](docs/13-统一数据契约与扩展规范.md)。

启动前必须执行Alembic，服务不再使用create_all。空库运行`npm run db:upgrade`；旧S0库不能直接upgrade或stamp，使用以下离线复制升级（后端服务先停止）：

```powershell
cd starter/backend
.venv/Scripts/python.exe scripts/upgrade_s0.py --source recruitflow.db --destination recruitflow_s1.db
```

Unix改用`.venv/bin/python`。命令保留原库和备份，目标文件必须不存在；验证后在后端`.env`设置`DATABASE_URL=sqlite:///./recruitflow_s1.db`再启动。当前工作区已完成此升级并使用新库；原库仍在，未加入Git。旧记录统一归属模拟管理员，需在正式迁移前核对真实负责人；S1不接收真实个人资料。

## 当前验证边界

S0浏览器新增/Mock更新/模拟同步本次已补验。S1通过46项pytest、前后端检查、构建、空库升级/回滚/再升级、旧库复制和HTTP冒烟；完整多尺寸UI与组件验收在S4。PostgreSQL仅验证迁移DDL离线编译，尚无真实服务联调。测试有1条上游兼容弃用警告，前端约2.30MB产物体积警告留待S4拆包。

业务写入必需`Idempotency-Key`，修改/删除另需`If-Match`；AI接入使用外部事件ID。开发身份由服务端目录解析`X-Dev-User`，可用别名admin/hr-a/hr-b/manager-a；`DEV_AUTH_ENABLED=false`拒绝开发身份。浏览器只保存模拟用户ID，不保存Token，也不能自报role提升权限。

已初始化本地Git仓库，使用main分支，尚未配置远程仓库。`.env`、数据库、日志、本地工具、个人资料不得纳入版本控制。
