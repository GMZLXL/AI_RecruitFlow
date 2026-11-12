# AI RecruitFlow

招聘记录自动化系统：React/TypeScript/Vite/Ant Design + FastAPI/Pydantic/SQLAlchemy。先运行不需要任何 Key 的 Mock，再按 S1~S7 完成业务和授权接入。

**当前为 S3**：已完成工程分层、招聘CRUD与权限、AI提取/人工审核，以及异步投影、持久Mock智能表格、指数退避/死信/管理员重试。真实DeepSeek及腾讯文档没有凭证联调；腾讯写入适配器在缺凭证/缺实测Schema时明确阻断。仅用于虚构资料与本机演示，生产/live模式拒绝启动。

## 工作区

- `backend/app/schemas/`：前后端统一契约源。
- `backend/app/api/v1/`、`services/`、`integrations/parsers/`：路由、业务编排和解析器分离。
- `backend/app/integrations/smartsheet/`、`jobs/`：SmartSheet协议/适配器、只读MCP发现与后台任务。
- `frontend/src/app/`、`pages/`、`features/`、`services/`：应用装配、页面、审核交互和API客户端分离。
- `backend/scripts/contracts|migrations|smoke/`及根`scripts/workspace|contracts/`：运行脚本按用途归类，详见`docs/14-工程目录与开发约定.md`。
- `contracts/openapi.yaml`：由实际 FastAPI 路由生成，只有已实现接口。
- `frontend/src/types/api.generated.ts`：由 OpenAPI 自动生成，禁止手改。
- `docs/01~12`：产品与目标设计；`docs/13-统一数据契约与扩展规范.md`：字段/版本/扩展规范。
- `codex/PHASE_TASKS.md`：S0~S7 执行与验收顺序。
- `docs/IMPLEMENTATION_REPORT.md`：逐阶段实际结果与限制。

## 安装（仓库根目录）

需要 Python **3.11+**（本次验证 3.12）、Node.js **22.12+** 和 npm 10+。Python 3.10 不支持。已有 `.venv` 时可跳过环境创建。本工作区已准备独立 Python 3.12 和后端虚拟环境；这些本地工具不纳入 Git。

Windows PowerShell（已安装 Python 3.12 的新环境）：

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --require-hashes -r backend/requirements.lock
Copy-Item backend/.env.example backend/.env
npm ci
npm run db:upgrade
```

Linux/macOS：

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --require-hashes -r backend/requirements.lock
cp backend/.env.example backend/.env
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

打开 [Mock 页面](http://127.0.0.1:5173)、[后端文档](http://127.0.0.1:8000/docs)、[健康检查](http://127.0.0.1:8000/api/v1/health)。Vite 将 `/api` 转发给 8000。5173 被占用会明确失败，不自动换端口。数据库默认位于 `backend/recruitflow.db`，不得提交。

## 演示与检查

1. 顶部默认“模拟管理员”；候选人记录新增虚构姓名、岗位、编号 `A10001`。
2. 列表人工推进至“简历筛选”、再推进至“一面”。AI消息录入输入 `A10001 一面通过`，进入二面、版本递增。S1严格校验状态机，不能从新申请直接跳二面。
3. 返回工作台刷新：阶段分布和数量来自数据库；空库显示空态。
4. 后台每2秒扫描outbox；同步中心自动刷新实际状态，可请求立即处理：显示 `MOCK-` ID，同一申请更新复用映射，**不会写入腾讯文档**。只有申请投影到模拟表，其它事件标记“内部事件（不投影）”。
5. 顶部可切换模拟HR/负责人：HR仅查看本人，负责人只读所属部门，同步中心仅管理员可访问；后端同样执行限制。HR新增申请须使用已配置的岗位。
6. 输入姓名更新或模糊时间会进入“待人工确认”；点击审核，可选择申请、确认原提议、修正字段后执行或驳回。审核说明必填，过期申请版本409，任务只处理一次。
7. 在二面阶段输入`A10001 安排二面 明天15:00 面试官虚构王`，结果与计划分别记录；“一面通过”不代表“二面通过”。未提供原计划的结果记录不会补造时间/面试官。

```bash
npm run check             # 契约漂移 + lint + Python/TS类型 + pytest + build
npm run smoke:http        # 两个服务启动后执行；留下1条虚构申请，验证HTTP/代理/完整Mock链路
npm run contracts:generate # 修改schema/路由后重新生成OpenAPI和TS
npm run contracts:check
npm run db:check           # 模型与迁移漂移检查
npm run integrations:tencent:discover # 只读工具发现；缺Token退出2，不会调用业务工具
```

后端单独检查：进入 `backend`，激活 `.venv` 后运行 `python -m pytest -q`、`python -m compileall -q app`。前端可单独运行 `npm run typecheck --workspace frontend` 和 `npm run build --workspace frontend`。S4 再补组件测试，不以空脚本冒充测试通过。

## 字段扩展

先改 Pydantic，再生成 OpenAPI/TS，契约检查会阻止手工类型漂移。核心字段强类型；API ID 始终为字符串、时间为 UTC、修改实体带 version。新业务字段需要数据库列时，从 S1 起必须带 Alembic 迁移；组织自定义字段按受控命名空间 JSON 设计，不混入权限/阶段等核心字段。详见 [扩展规范](docs/13-统一数据契约与扩展规范.md)。

启动前必须执行Alembic，服务不再使用create_all。空库运行`npm run db:upgrade`；旧S0库不能直接upgrade或stamp，使用以下离线复制升级（后端服务先停止）：

```powershell
cd backend
.venv/Scripts/python.exe -m scripts.migrations.upgrade_s0 --source recruitflow.db --destination recruitflow_s1.db
```

Unix改用`.venv/bin/python`。命令保留原库和备份，目标文件必须不存在；验证后在后端`.env`设置`DATABASE_URL=sqlite:///./recruitflow_s1.db`再启动。当前工作区已完成此升级并使用新库；原库仍在，未加入Git。旧记录统一归属模拟管理员，需在正式迁移前核对真实负责人；S1不接收真实个人资料。

## 当前验证边界

S3回归覆盖异步领取、退避/死信、远端成功但本地确认丢失、版本防回退、权限与幂等重试，数量见实施报告。HTTP冒烟包含新增/结果/安排/驳回/自动后台同步；浏览器验证了审核和同步中心重试。完整页面、多尺寸UI与组件验收在S4。PostgreSQL仅DDL离线编译；保留上游测试客户端兼容警告及前端大包警告，拆包在S4。

S2迁移为0002_s2，现有S1库运行`npm run db:upgrade`即可；启动自动读取Alembic当前head，新增迁移不需手改版本常量。结果记录允许没有原始面试计划；降级时若存在这些记录会明确拒绝，不删除记录或编造时间。

## DeepSeek 配置与边界

默认`APP_MODE=mock`、`AI_PROVIDER=mock`，无任何外部调用。若要测试真实模型，只在后端`.env`设置`APP_MODE=hybrid`、`AI_PROVIDER=deepseek`、`DEEPSEEK_API_KEY`及`DEEPSEEK_MODEL`；模型名不在代码写死，连接仅允许官方HTTPS地址。企业微信/腾讯文档仍模拟，生产认证尚未实现。

DeepSeek使用JSON Output与Pydantic，最多2次尝试；空白、截断、非法字段、超时、缺凭证转人工确认。手机号/邮箱/身份证/常见联系信息先脱敏；只保留哈希和不超过300字的脱敏摘要，不保存独立原文或模型原始响应。解析在数据库事务之外，落地前重新校验权限、状态和版本。未提供Key时显示blocked_by_credentials，不用Mock响应冒充真实调用。

Mock支持明确新增、唯一编号的阶段/面试结果、ISO时间及“明天/后天+钟点”的面试安排；不明确的星期/钟点、同名、多岗、冲突及未知意图都需审核。复杂自然语言效果和真实DeepSeek准确率尚未评测。AI提取的录用/淘汰不会自动执行，须使用人工申请管理操作。

业务写入必需`Idempotency-Key`，修改/删除另需`If-Match`；AI接入使用外部事件ID。开发身份由服务端目录解析`X-Dev-User`，可用别名admin/hr-a/hr-b/manager-a；`DEV_AUTH_ENABLED=false`拒绝开发身份。浏览器只保存模拟用户ID，不保存Token，也不能自报role提升权限。

已初始化本地Git仓库，使用main分支，尚未配置远程仓库。`.env`、数据库、日志、本地工具、个人资料不得纳入版本控制。

## S3 同步配置与故障演示

已有S2库先停止后端，运行`npm run db:upgrade`升级到`0003_s3`，再启动。迁移保留旧Mock远端ID，补建本机模拟存储，不会连接腾讯文档；原S0复制命令也已兼容当前head。迁移前自行保留数据库备份，已有原库和备份不覆盖。

默认`SMARTSHEET_PROVIDER=mock`、`SYNC_WORKER_ENABLED=true`、`MOCK_SHEET_FAILURE=none`，不需要新填.env，旧文件使用相同默认值。API默认一个进程，任务处理器随lifespan运行；数据库租约防止同时处理，120秒后可恢复过期领取。外部调用最长20秒；临时错误按5/10/20/40秒退避，第5次失败进入dead；权限、凭证、映射/结构问题直接dead，等待管理员修正。管理员重试重置本轮次数、保留累计次数。任务一旦存在，provider不随配置变更，避免把旧Mock任务发送给真实系统。

复现死信与人工重试（仅虚构Mock，**先停止API**）：

```bash
npm run smoke:sync-failure
npm run dev:api
```

打开同步中心，筛选“死信”，点击“人工重试”，填写说明并确认；后台恢复后查看“模拟已同步”。如果申请已有更新版本，旧任务显示“已由新版本覆盖”。此命令会保留1条虚构申请及审计，不删除数据；若旧库有其它待同步申请，同一批次也会受故障注入影响。恢复演示使用默认`MOCK_SHEET_FAILURE=none`。

`POST /sync/run`现返回202及accepted，只代表后台请求已接受；实际结果查询任务列表。重试须`If-Match`任务revision（区别于业务version）与`Idempotency-Key`，由后端检查管理员权限。远端故障不会撤销本地申请。Mock用申请ID稳定建行键及版本条件写入，重放不会重复建行；远端记录/已成功映射丢失转人工排查，不盲目重建。

腾讯只读发现命令读取服务端`TENCENT_DOCS_TOKEN`，仅允许官方HTTPS端点，不跟随重定向，先initialize再分页tools/list；Schema只保存在忽略的`.tools/`。当前缺Token实测返回BLOCKED_BY_CREDENTIALS；即使配置Token也只是blocked_by_schema，尚未实现通过真实Schema验证的业务参数映射。获得独立测试表授权后，仍需按docs/08完成查询→新增→更新→复查，不能以发现成功代替真实写入验收。
