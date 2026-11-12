# 05｜REST API 接口契约（v1）

## S1 当前已实现契约

运行契约由Pydantic生成，共19个实际路径。以下内容优先于S0历史说明和后续目标示例。

- `/health`公开；`/ready`需开发身份并检查数据库；`/me`返回身份，`/dev/users`只列服务端虚构用户，均加`/api/v1`前缀。
- `GET/POST /positions`、`GET/PATCH/DELETE /positions/{id}`；新增/修改/删除仅管理员，查询按部门范围。
- `GET/POST /candidates`、`GET/PATCH/DELETE /candidates/{id}`；候选人独立于申请，不返回联系方式。创建可给owner_id，但HR只能指定自己。
- `GET/POST /applications`、`GET/PATCH/DELETE /applications/{id}`、`GET /applications/{id}/events`。
- `GET/POST /applications/{id}/interviews`、`GET/PATCH/DELETE /interviews/{id}`。创建面试If-Match是申请版本；修改/删除使用面试版本，父申请也递增版本。面试结果与阶段独立。
- `GET /confirmations`列出持久化任务；本阶段尚无resolve接口。
- 保留`POST /ingestions`、`GET /dashboard/overview`、`GET /sync/jobs`、`POST /sync/run`、`GET /integrations/status`；同步及集成状态仅管理员。当前仍是Mock，非真实外部写入。

所有列表page/page_size（默认20、最大100）。申请筛选keyword/candidate_id/position_id/owner_id/stage/source_channel/from/to，时间为带时区ISO8601且区间[from,to)；sort仅created_desc/updated_desc/code_asc。候选人支持keyword/owner_id；岗位支持keyword/active。

业务POST/PATCH/DELETE必须Idempotency-Key（1~150字符），缺失400；PATCH/DELETE必须If-Match正整数，缺失422、版本冲突409。同键同内容重放原响应，不同内容409；键按用户+操作隔离。ingestions按source+external_event_id去重，缺事件ID生成新事件；同ID不同消息409，不能重放其他用户事件。

申请创建每一类引用必须二选一：candidate_id或candidate_name、position_id或position_title。推荐ID关联同一候选人的多岗位申请；便捷姓名分支显式创建新候选人，不自动合并同名。HR仅可选择可见且部门匹配的现有岗位；管理员可在便捷分支创建岗位。同名岗位不唯一409要求使用ID。

```json
{"candidate_id":"已创建的候选人UUID","position_id":"已创建的岗位UUID","application_code":"A10001","source_channel":"referral","custom_fields":{"organization.referral_tag":"内推"}}
```

PATCH申请体为`stage?/source_channel?/custom_fields?/change_reason`，返回`data:{status,application,confirmation_id?,reason?}`。正常status=applied；终态逆转status=needs_confirmation且原状态/版本不变。普通跳阶段409。DELETE要求JSON体`{"change_reason":"..."}`并软删除；关联活跃申请的候选人/岗位不能删除。创建/修改任意未知字段422。

开发身份只在development+mock+DEV_AUTH_ENABLED=true生效，Header为X-Dev-User（UUID或服务端别名）。HR只操作本人；经理只读所属部门；管理员管理全局。生产入口拒绝启动，不采用浏览器自报role。未知/停用用户401，越权403。

错误码包括UNAUTHENTICATED/FORBIDDEN/NOT_FOUND/VERSION_CONFLICT/IDEMPOTENCY_CONFLICT/IDEMPOTENCY_KEY_REQUIRED/CONSTRAINT_CONFLICT/INVALID_STAGE_TRANSITION/INVALID_INPUT，保持统一error/request_id且不回显原始输入。

## S0 历史契约（已由S1更新）

`app/schemas.py -> contracts/openapi.yaml -> src/types/api.generated.ts`，通过根目录 `npm run contracts:generate` 生成，`npm run contracts:check` 检测漂移。详见 [统一数据契约与扩展规范](13-统一数据契约与扩展规范.md)。OpenAPI 仅导出当前实际路由；下方完整 API 列表为 S1~S7 目标，不代表已实现。

| 方法 | 已实现路径 | 结构/限制 |
|---|---|---|
| GET | `/api/v1/health` | `data: {status,mode,note}` |
| GET | `/api/v1/integrations/status` | `data: {mode,deepseek,tencent_docs,wecom}`，只返回模拟/未连接 |
| GET | `/api/v1/applications` | `data: ApplicationRead[]`，page/page_size，默认20，最大100，id降序 |
| POST | `/api/v1/applications` | `candidate_name,position_title,application_code?`；201；编号冲突409 |
| POST | `/api/v1/ingestions` | `text,source?,external_event_id?`；source仅manual/wecom_mock；返回applied/needs_confirmation/duplicate |
| GET | `/api/v1/dashboard/overview` | `new_applications,by_stage,pending_sync,mode`；S0为全库总量，尚无时间筛选 |
| GET | `/api/v1/sync/jobs` | 分页，状态pending/mock_synced，mode=mock |
| POST | `/api/v1/sync/run` | `data: {processed,mode,warning}`，仅本地模拟，无网络调用 |

所有成功响应均带 `data,request_id`，列表带 `pagination`；错误为 `error:{code,message,details},request_id`，Header `X-Request-ID` 与 body 一致。422 不回显输入原文。

`ApplicationRead`：`id:string, application_code:string, candidate_id:string, candidate_name:string, position_id:string|null, position_title:string, stage:Stage, version:int, created_at:UTC, updated_at:UTC`。`position_id` S0为null，S1迁移到岗位关联。请求拒绝未知字段与空白名称。

```json
{"candidate_name":"虚构候选甲","position_title":"数据分析岗","application_code":"A10001"}
```

S0申请创建可带 `Idempotency-Key`（1~120字符）；同键同内容复用当前申请投影，不同内容409。AI接入按source+external_event_id去重已执行事件；待确认队列及其幂等持久化在S2实现。前端每次提交生成新事件ID/幂等键，S1/S2再补断网重试时复用键的完整交互。模拟同步重复运行不重复创建映射。当前无完整CRUD/删除/If-Match接口；S1交付。

所有写操作限制本机固定开发身份 `local-mock`，不是正式RBAC；APP_ENV非development或APP_MODE非mock拒绝启动。业务写与audit_logs/outbox同事务。S0沿用演示“一面通过→二面阶段、二面通过→Offer阶段”的有限规则，复合消息、同名和逆转不自动写；独立面试结果及完整状态机待S1/S2。

## 1. 通用约定

- 前缀 `/api/v1`，FastAPI 自动生成 `/openapi.json` 与 `/docs`；正式环境关闭或限权 Swagger。
- 使用 JSON；统一 UTC ISO8601 时间，前端按企业时区显示。
- 生产使用公司 SSO/企业微信 OAuth 等安全登录机制；不得用随意填写的用户 ID 直接相信其身份。Mock 环境可使用显式 Dev-only Header。
- 成功响应：`{"data":...,"request_id":"..."}`；分页返回 `{"data":[...],"pagination":{"page":1,"page_size":20,"total":0},"request_id":"..."}`。
- 错误响应：`{"error":{"code":"APPLICATION_NOT_FOUND","message":"...","details":{}},"request_id":"..."}`。
- POST 业务变更接受 `Idempotency-Key` header；原始事件接入优先使用 `external_event_id`。

## 2. API 列表

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| GET | `/health` | 存活检查 | public |
| GET | `/ready` | 数据库/任务检查，缺外部密钥不阻断 Mock | internal |
| GET | `/me` | 当前用户/角色及权限 | authenticated |
| GET | `/positions` | 岗位列表 | HR+ |
| POST | `/positions` | 新增岗位 | ADMIN |
| GET | `/candidates` | 候选人列表，筛选与分页 | HR+ |
| POST | `/candidates` | 新增候选人 | HR+ |
| GET | `/candidates/{id}` | 详情与其申请 | scope |
| GET | `/applications` | 申请列表 | scope |
| POST | `/applications` | 新增申请 | HR+ |
| GET | `/applications/{id}` | 申请详情 | scope |
| PATCH | `/applications/{id}` | 修改，乐观锁校验 | owner/ADMIN |
| GET | `/applications/{id}/events` | 事件历史 | scope |
| POST | `/applications/{id}/interviews` | 安排面试 | owner/ADMIN |
| PATCH | `/interviews/{id}` | 更新结果/时间 | owner/ADMIN |
| POST | `/ingestions` | 自然语言解析并提交（或进待确认） | HR+ |
| GET | `/ingestions` | AI 处理记录 | HR+ |
| GET | `/confirmations` | 待确认队列 | HR+ |
| POST | `/confirmations/{id}/resolve` | 确认/修正/驳回 | scope |
| GET | `/tasks` | 待办事项 | HR+ |
| GET | `/dashboard/overview` | 指标卡片 | scope |
| GET | `/dashboard/funnel` | 阶段漏斗 | scope |
| GET | `/dashboard/positions` | 岗位进度 | scope |
| POST | `/reports/weekly` | 本周摘要，优先确定性数据 | MANAGER+ |
| GET | `/sync/jobs` | 同步任务列表 | ADMIN |
| POST | `/sync/jobs/{id}/retry` | 重试同步 | ADMIN |
| GET | `/integrations/status` | 脱敏状态与模式 | ADMIN |
| GET/POST | `/webhooks/wecom` | 企业微信验证/接收（独立验签） | signed callback |

## 3. 请求与响应示例

### 3.1 AI 录入

`POST /api/v1/ingestions`

```json
{
  "text": "A10001 一面通过，下周二下午三点二面，王经理主持",
  "source": "manual",
  "external_event_id": "web-20261112-001",
  "execute_if_unambiguous": true
}
```

成功、待确认、失败三类互斥结果：

```json
{
  "data": {
    "ingestion_id": "evt_123",
    "status": "applied",
    "intent": "update_interview",
    "application_id": "app_123",
    "proposed_action": {"stage": "interview_2", "next_interview_at": "2026-11-17T07:00:00Z"},
    "sync_state": "pending"
  },
  "request_id": "req_001"
}
```

`needs_confirmation` 时返回 `confirmation_id` 与 `reason_code`，禁止在同一响应中宣称状态已修改。

### 3.2 应用阶段更新

`PATCH /api/v1/applications/app_123`（带 `If-Match: 3`，服务器内 version=3）

```json
{"stage":"offer","outcome":"pending","change_reason":"面试通过待发Offer"}
```

返回更新后的 `version=4`，并在同一数据库事务中写入 audit 和 outbox；版本不符返回 409。

### 3.3 看板

`GET /api/v1/dashboard/overview?from=2026-11-01&to=2026-11-30&position_id=all`

```json
{
  "data": {
    "new_applications": 120,
    "pending_interviews": 28,
    "pending_feedbacks": 7,
    "offers_sent": 15,
    "offers_accepted": 10,
    "period": {"from":"2026-11-01","to":"2026-11-30","timezone":"Asia/Shanghai"}
  },
  "request_id": "req_002"
}
```

## 4. 错误代码规范

| HTTP | code | 说明 |
|---|---|---|
| 400 | INVALID_INPUT | 字段非法/时间格式不合法 |
| 401 | UNAUTHENTICATED | 未登录 |
| 403 | FORBIDDEN | 无权限 |
| 404 | APPLICATION_NOT_FOUND | 不存在或不可见 |
| 409 | VERSION_CONFLICT | 乐观锁冲突 |
| 409 | DUPLICATE_EVENT | 重复事件（可返回原执行结果） |
| 422 | NEEDS_CONFIRMATION | 业务语义存在歧义，需人工确认（正常可用200状态表达） |
| 429 | RATE_LIMITED | 访问限流 |
| 502 | UPSTREAM_UNAVAILABLE | 外部服务不可达（仅在直接调用场景） |

## 5. 兼容性与接口设计纪律

- 前后端共享 OpenAPI 契约，可通过自动生成 TypeScript 类型，但不得假造后端无实现接口。
- 所有列表支持 page/page_size, keyword 及限定的 sort 字段；禁止将前端任意字段拼接 SQL ORDER BY。
- 日期筛选采用闭开区间 `[from,to)`，时区统一后计算。
- Webhook 不接受网页普通 Bearer 登录，独立实现签名与 AES 校验。
- 需要自动同步的接口在响应中返回实际 sync 状态：`pending/synced/failed`，而非单一成功标志。
