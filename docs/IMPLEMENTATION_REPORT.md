# AI RecruitFlow 实施报告

## S0 补验（2026-11-12）

本轮已实际通过内置浏览器打开5173页面，验证看板真实数据、创建`AS0UI20261112`虚构申请、AI输入该编号一面通过、结果进入二面、执行模拟同步。两个申请版本复用`MOCK-18695a03`映射，页面明确标注模拟。此前浏览器工具阻塞本次已解除，S0基础浏览器验收已补齐；完整多尺寸产品验收仍属于S4。已初始化本地main分支，保存S0基线后进入S1。下文保留上一轮原始执行记录。

日期：2026-11-12（Asia/Shanghai）。本轮按 `CODEX_MASTER_PROMPT.md` 从S0开始，只实施一个阶段。修改前已阅读README、AGENTS、docs/01~12、主提示、阶段任务、原始契约及Starter。

```text
阶段：S0
已完成：工程基线代码及自动验收；统一Pydantic/OpenAPI/TS契约、工作区检查、Mock主链路、实际HTTP启动验证。
本阶段变更文件：见下方清单。
数据库迁移：无Alembic迁移；保留create_all，仅补充audit_logs表；未删除旧库。正式迁移属S1。
运行的命令：npm run contracts:generate；npm run check；npm run smoke:http；python -m compileall -q app；锁文件哈希安装核查。
测试结果：pytest通过20，失败0，跳过0；Python/TS类型检查、lint、契约检查、前端build均通过；HTTP冒烟通过。
未完成/阻塞：浏览器可视和点击交互验收未完成；完整CRUD/RBAC/Alembic等尚未进入S1；真实第三方未接入。
重要风险：S0不是生产系统；仅固定本机开发身份；旧演示事件键需要S1迁移评估；前端产物较大；跨平台尚未实机验证。
下一阶段：补齐S0浏览器可视验收，再实施S1数据/迁移/身份/状态机。S1~S7未标记完成。
```

## 统一结构与字段扩展

- 唯一契约源：`starter/backend/app/schemas.py`；通过FastAPI导出真实路由的OpenAPI，再生成TypeScript，前端不再手写一份Application/SyncJob类型。
- 核心约定：snake_case、字符串API ID、独立申请编号、UTC输出、正整数version、统一分页/请求编号/安全错误响应、请求拒绝未知字段。
- 新增字段流程：先确定实体归属，再修改schema与必要的数据库迁移，再生成类型；业务可检索字段保持列和强类型，自定义字段使用未来S1受控命名空间JSON方案。S0不接受任意扩展字典。
- `docs/13-统一数据契约与扩展规范.md`先定义十二类领域实体的边界和S0验收计划，再实施代码。S0不提前生成未实现实体的假接口。

## 已验证行为

20项pytest覆盖：

- 无凭证Mock健康检查、申请创建、规则更新、version递增、请求编号。
- 相同事件去重，source间独立去重；自动生成的申请编号可再次用于更新。
- 同名/模糊时间/复合消息/恶意提示文本不自动写入；终态及阶段逆转需确认。
- 创建幂等键复用、相同键不同内容冲突、重复编号不残留候选人/事件/审计/outbox。
- 业务/审计/outbox事务一致性；注入审计异常时全回滚；500错误不返回异常原文。
- 分页、边界校验、字符串ID、UTC时间、空数据库真实统计。
- 本机写入门槛与非development/非mock启动拒绝。此项不等同于完整角色权限测试。
- 模拟同步复用同一个MOCK远端ID，重复执行无新增任务。
- 运行OpenAPI与仓库契约一致，未实现接口不出现在运行契约。

实际运行结果：

```text
npm run check
  contracts:check   OpenAPI and TypeScript contracts match the backend
  lint             Ruff + ESLint passed
  typecheck        Pyright: 0 errors; TypeScript passed
  pytest           20 passed, 1 warning in 5.26s
  build            2123 modules transformed; built in 14.88s

npm run smoke:http
  PASS: web 5173 + Vite proxy + API 8000 + create/update/dedupe/dashboard/mock sync

python -m compileall -q app
  exit 0

uv pip install --offline --require-hashes -r starter/backend/requirements.lock ...
  Checked 32 packages; exit 0

npm install（锁文件更新后审计）
  found 0 vulnerabilities
```

环境：Windows、Python3.12.16、Node24.14.0、npm11.9.0。系统原有Python3.10未修改；本轮在`.tools/`准备Python并创建`starter/backend/.venv`。Python锁文件由universal解析生成，具有平台标记与哈希，但Linux/macOS、Python3.11和PostgreSQL未做实机验证。

沙箱曾阻断网络安装、临时目录SQLite、开发服务子进程与端口访问；依赖和最终全量检查通过授权常规进程执行。测试临时数据库改放工作区`.pytest_cache`，不会覆盖演示数据库。初始热重载进程在本运行环境退出，默认启动改为单进程后HTTP验证通过。

## 浏览器验收阻塞

内置浏览器打开`http://127.0.0.1:5173`返回`net::ERR_CONNECTION_TIMED_OUT`。随后尝试选择本机Chrome时，Computer Use工具因无法可靠识别Windows当前浏览器URL而停止本轮操作。已停止UI操作，未绕过工具安全检查。

因此**没有完成浏览器渲染/点击交互、移动端布局和截图验收**。HTTP返回HTML与自动构建通过不能证明浏览器交互已通过。S0自动验收已通过，完整阶段验收仍保留这一缺口。

可在本机手动打开5173，依README依次验证新增、AI更新、工作台刷新、模拟同步。当前HTTP冒烟已留下一条“虚构冒烟甲”的本地演示记录；未写任何真实外部系统。

## 变更文件清单

| 范围 | 文件 |
|---|---|
| 根工程 | `.gitignore`, `package.json`, `package-lock.json`, `pyrightconfig.json`, `scripts/python.mjs`, `scripts/check-contracts.mjs` |
| 后端 | `starter/backend/app/db.py`, `app/main.py`, `app/schemas.py`, `scripts/export_contract.py`, `scripts/smoke_http.py`, `tests/conftest.py`, `tests/test_smoke.py`, `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `requirements.lock`, `.env.example`, `README.md` |
| 前端 | `starter/frontend/package.json`, `eslint.config.js`, `vite.config.ts`, `src/api.ts`, `src/App.tsx`, `src/types/api.generated.ts`, `README.md`, `DEPENDENCY_NOTE.md` |
| 契约/文档 | `contracts/openapi.yaml`, 根`README.md`, `IMPLEMENTATION_STATUS.md`, `docs/04`, `docs/05`, `docs/09`, `docs/11`, `docs/13`, 本报告 |

没有Git元数据，未创建commit。`.env`、数据库、日志、工具和虚拟环境均被忽略；不得提交真实个人资料。

## 未完成与后续验收

- S0浏览器可视验收待补，阶段不能宣称全部验收通过。
- S1：独立岗位/用户/面试等全部模型、UUID迁移、SQLite外键与PostgreSQL、Alembic空库升级和旧Starter升级、完整CRUD/筛选/软删除、RBAC数据范围、If-Match并发冲突及完整状态机。
- S2：正式Parser协议、独立面试结果、待确认持久化/人工确认、失败事件幂等、DeepSeek JSON验证与脱敏。当前Mock仍是有限演示规则，不能视为招聘决策系统。
- S3：正式adapter、任务重试/退避/死信、版本快照和真实腾讯MCP动态tools/list。当前Mock无网络调用，不代表腾讯文档成功。
- S4：完整页面/日期筛选/组件测试/响应式、前端按路由及图表拆包。目前主JS约2.30MB、gzip753KB，构建有chunk体积警告，未调大警告阈值掩盖问题。
- S5~S7：企微验签/AES/通知、生产身份/部署/运维、完整验收。真实DeepSeek、腾讯文档及企微均为未接入/未来凭证阻塞，未做真实授权联调。
- pytest当前存在1条Starlette对httpx兼容测试客户端的弃用警告，未关闭或过滤；测试全部通过。开发依赖的minimatch安全覆盖理由见前端DEPENDENCY_NOTE，上游修复后应移除覆盖。

## 演示命令

两个终端在仓库根目录分别运行`npm run dev:api`和`npm run dev:web`。检查`http://127.0.0.1:8000/api/v1/health`，打开`http://127.0.0.1:5173`。第三个终端可运行`npm run smoke:http`（会新增1条虚构记录并处理待模拟同步任务）。安装、Windows/Unix命令与字段扩展流程详见README。
