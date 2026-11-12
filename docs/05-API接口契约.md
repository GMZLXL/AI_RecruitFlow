# 05｜REST API 接口契约（v1）

## S6 当前增量（优先于历史契约）

当前OpenAPI **0.7.0 / 41路径**；新增schemas/ai_settings.py、operations.py并扩展identity，前端TS已生成。以下路径前缀均为`/api/v1`：

| 方法/路径 | 行为 |
|---|---|
| GET /auth/config | 公开；authentication=development_only/sso_cookie、mode=mock/hybrid、同源login_url/logout_url或null |
| GET /readyz | 公开；DB版本和已启用worker租约就绪返回Health信封，否则503 NOT_READY |
| GET /ops/status | 管理员；schema、worker_role/lease_healthy/heartbeat_at、各worker循环/成功/安全错误、实际队列计数及最老未完成申请同步时间、限流与日志格式；不返token |
| GET /settings/ai | 管理员；只读配置元数据，不返回Key/密文 |
| PATCH /settings/ai | 管理员；If-Match设置version + Idempotency-Key + Update；返回最新元数据 |

AISettingsRead字段为version/provider/model/has_api_key/key_source/secret_store_ready/real_calls_allowed/status；provider=mock/deepseek，key_source=managed/environment/none，status=mock_only/blocked_by_credentials/configured_not_verified/mode_mismatch。Update要求provider/model/change_reason；model最长120且只允许字母数字点/下划线/连字符。api_key为可选SecretStr（1~512字符、无首尾空白），clear_api_key默认false；新增/清除互斥。Key为空或省略保留，clear禁用环境Key回退。Key哈希摘要用于幂等比较，正文Key不入幂等表。首次读取虚拟version1、首次保存version2。

过期版本/同键不同内容409，Mock启用DeepSeek为409 REAL_AI_NOT_ALLOWED，无Key为400 API_KEY_REQUIRED，主密钥不可用503 SECRET_STORE_NOT_READY，越权403、结构422。Key只经安全表单提交后端加密，禁止URL参数、浏览器存储和日志；保存不代表联通验证。业务/audit/outbox同事务，网络在事务之外。

GET /me的authentication新增sso_cookie及可空csrf_token；SSO使用HttpOnly Secure `__Host-recruitflow_session`，RS256+issuer/audience/时间/claims与DB映射授权。写入须精确Origin和X-CSRF-Token；开发头生产403，未认证401，未授权/CSRF为403。开发目录生产关闭。请求体≤64KiB/10秒，限流429附Retry-After，默认600/IP/min与30/录入actor/min；生产关闭/docs、/openapi.json。网关Cookie/claim协议与全部运行限制见docs/15。以下保留阶段历史。

## S5 当前增量（优先于历史契约）

当前OpenAPI 0.6.0、37个路径；统一Pydantic在schemas/wecom.py，生成OpenAPI和前端TS。所有JSON接口沿用data/request_id与分页/错误信封；回调特例按平台协议使用纯文本响应。

| 方法/路径（前缀/api/v1） | 行为 |
|---|---|
| GET /webhooks/wecom | msg_signature/timestamp/nonce/echostr；SDK验签并解密，返回原样明文text/plain；无开发身份头 |
| POST /webhooks/wecom | 同签名参数（不含echostr），application/xml加密体≤64KiB；校验企业/AgentID与内部发送人，持久化后返回success；不等待AI |
| GET /wecom/status | 管理员；provider、callback/sending配置状态、worker_enabled、callback_path和边界说明，不回显密钥 |
| POST /wecom/mock/messages | 开发Mock、HR/管理员；body message_id(1~150)/text(1~2000)，Idempotency-Key；202 InboxRead，只代表已接收 |
| GET /wecom/inbox | page/page_size；管理员全局，其余仅本人；不返回文本、哈希、nonce或token |
| POST /wecom/inbox/{id}/retry | 管理员；If-Match接收任务version、Idempotency-Key、change_reason；仅failed且有脱敏工作文本，可恢复；先复核actor权限 |
| GET /notifications | page/page_size；管理员全局，其余仅本人且仍有业务访问权限；状态和最小通知内容，无外部UserID/Token |
| POST /notifications/{id}/retry | 管理员；If-Match通知version、Idempotency-Key、change_reason；仅failed/blocked；uncertain/accepted/mock_sent禁止重发 |
| GET/PATCH /settings/reminders | 管理员读取/更新单例；PATCH要If-Match+幂等键，body enabled/interview_hours(1~168)/feedback_hours(1~720)/stalled_days(1~365)/change_reason |
| GET /wecom/users | 管理员；分页读取内部用户及外部UserID映射，不包含凭证 |
| PATCH /wecom/users/{id} | 管理员；If-Match用户version+幂等键；external_userid或null解除绑定，change_reason必填；唯一约束，不允许@all |

回调验签/过期/企业/应用/未知发送人403，结构错误400，过大413，未启用或缺配置503；同MsgId不同正文409。认证后非文本事件仅ACK，不进入AI；不读取普通群聊。重复合法回调返回success且业务一次；nonce允许原密文重试，拒绝相同timestamp+nonce的不同密文。签名窗口±300秒。真实source=wecom只能经回调进入，手工ingestions拒绝伪装；wecom_mock保留兼容。

通知状态pending/processing/mock_sent/accepted/blocked/failed/uncertain/cancelled；API接受不代表设备收到/成员已读。平台msgid只保存实际响应；Mock前缀MOCK-NOTICE。失败只返回白名单安全码，网络异常不回传完整URL/响应。配置状态永远是mock_only/disabled/blocked_by_credentials/configured_not_verified，不凭配置显示connected。通用integrations/status的wecom同步更新为以上枚举。

所有配置/映射/任务重试同事务审计和outbox；无Key不调用网络。提醒规则更改不改变S4 Tasks实时事实分类和7天停滞阈值。

## S4 当前增量（优先于历史契约）

运行OpenAPI为0.5.0、27个实际路径。唯一Pydantic源仍位于schemas，所有前端领域类型继续生成，页面不复制业务协议。

| 方法/路径（统一前缀/api/v1） | 行为 |
|---|---|
| GET /dashboard/overview | 新增from/to（aware datetime、[from,to)）、position_id/owner_id/stage；与列表重用授权和筛选条件 |
| GET /recruitment/options | 读取授权岗位与可见负责人；keyword筛选，各最多100条，不返回密钥或联系方式 |
| GET /tasks | page/page_size、kind(interview/feedback/review/stalled/sync)、owner_id/position_id、from/to参考时间筛选 |
| GET /settings/policy | 当前业务时区、7天停滞阈值、阶段推进白名单、提醒尚未启用说明；不读密钥 |
| GET /applications/{id}/history | 先授权申请，再分页读取安全审计摘要：action、actor_name、reason、changes白名单、created_at |
| GET /applications/{id}/offer | data为OfferRead或null；null是没有登记事实，不推断已发出/接受 |
| POST /applications/{id}/offer | 201；Idempotency-Key、If-Match为申请version；body:sent_at/change_reason |
| PATCH /applications/{id}/offer | Idempotency-Key、If-Match为Offer version；body:status(accepted/declined)、responded_at/change_reason |

OfferRead包含id/application_id/status/sent_at/responded_at/version/created_at/updated_at。只登记事实，不发Offer、不改录用阶段。创建限制Offer阶段与正确发出时点；反馈限制sent状态及发出至当前之间的时点。越权403、过期版本/重复创建/逆转409、缺幂等键400、非法结构422、非法时点400；同键同内容重放原响应。业务、Offer、父申请版本、audit/outbox同事务，外部IO不进入事务。

DashboardData保留new_applications/by_stage/pending_sync/mode，增加candidates去重人数、upcoming_interviews、pending_feedback、offers_sent/accepted/declined、offer_acceptance_rate、hired_applications、weekly_new、by_position、timezone/population。统计按申请创建时间形成的授权集合，再统计这些申请的面试/Offer事实；不是按Offer发出日期统计当期发送量。前端默认近30天，后端无日期参数仍返回全部授权申请以保持旧调用语义。from=to返回空集合，from>to为422。

接受率=accepted/(accepted+declined)，无明确反馈返回null，排除sent未回复；历史hired且没有独立Offer的申请不伪造为accepted。周趋势以Asia/Shanghai周一分组，岗位数量为过滤集合，编制为该岗位配置值。pending_sync从S4起只计申请投影的pending/processing/failed/dead，不把内部归档当成外部待同步。

ApplicationRead新增可空派生owner_name/next_interview_at/latest_result/sync_status。候选人列表支持现有keyword、岗位、负责人、阶段、来源渠道和创建时间；Dashboard仅提供日期/岗位/负责人/阶段，共同条件的口径一致。Tasks.at是参考时点：面试计划、审核/同步创建时间、停滞最后更新时间；对应业务处理后自动移出，没有任意“虚假完成”接口。AI审核API保持S2强类型与版本语义，表单按意图显示字段，高级ID匹配默认折叠。

## S3 历史增量（由S4增补）

运行OpenAPI为0.4.0、22个实际路径；Pydantic源、OpenAPI和前端生成类型已同步。

| 方法/路径（前缀/api/v1） | 当前行为 |
|---|---|
| GET /sync/jobs | 管理员；page/page_size、status枚举、application_id筛选；按创建时间/版本倒序 |
| GET /sync/summary | 管理员；实际counts、last_success_at（仅申请投影，含Mock）、worker_enabled、provider、tencent_docs、message |
| POST /sync/run | 管理员、Idempotency-Key；HTTP 202，data:{accepted:true,message}，只唤醒后台，不表示同步成功 |
| POST /sync/jobs/{id}/retry | 管理员；Idempotency-Key、If-Match任务revision、body:{reason:非空最多300字}；仅failed/dead→pending，返回SyncJob |

SyncJob：id/entity_type/entity_id/application_id、业务version、status、remote_record_id、attempts累计、cycle_attempts本轮、provider(mock/tencent_docs)、mode(mock/real)、revision、internal_only、last_error安全错误码、next_retry_at/completed_at/created_at UTC时间。不返回原始payload、处理token或凭证。状态包括pending/processing/mock_synced/synced/failed/dead/superseded；internal_only事件不代表外部写入。

空白说明422，无任务404，越权403，缺幂等键400，过期revision或状态不符409。同键同内容复用响应，不同说明/版本409；重试只重置本轮次数。仅failed且到期自动重试；dead等待管理员。已由更高版本同步的旧任务转superseded，不覆盖远端。

POST /sync/run相对S2从200及processed改为202及accepted，调用方必须轮询GET /sync/jobs；Web与冒烟脚本已迁移。看板pending_sync现在统计pending/processing/failed/dead，避免失败任务从待处理总量中消失。

GET /integrations/status新增sync_provider；tencent_docs由mock_only改为blocked_by_credentials/blocked_by_schema，分别表示缺Token/缺授权Schema与实测映射。配置Token不会返回connected。DeepSeek/企微字段保持S2语义。

内部ApplicationProjection为schema_version=1、application_id/code、candidate_name、position_title、stage/outcome、version、deleted、updated_at；只有适配器处理外部字段ID。新增outbox快照包含此投影；旧S1/S2快照在领取边界转换。

## S2 历史契约（由S3增补）

目录已工程化，统一契约源为backend/app/schemas/，路由在backend/app/api/v1/。运行OpenAPI为0.3.0、20个实际路径；以下S2内容优先于历史说明。

`POST /api/v1/ingestions`：text（1~2000，去除首尾空白）、source(manual/wecom_mock)、external_event_id?、execute_if_unambiguous（默认true）。同source+事件ID唯一，同ID不同文本或执行选项409；不提供ID表示新的事件。响应统一data/request_id，data包含ingestion_id、status(applied/needs_confirmation/duplicate/parsing/failed)、intent、application?/application_id?、confirmation_id?、reason/reason_code、sync_state、mode(mock/hybrid)、parser_provider(mock/deepseek)。缺凭证不是成功或Mock假响应，返回需确认并带BLOCKED_BY_CREDENTIALS。

处理分三段：持久化认领→无数据库事务的Parser调用→新事务复核后应用/生成确认。处理中重复消息返回parsing；120秒租约过期可携原始同消息重放恢复，处理token/版本阻断旧处理者提交。已应用事件重放duplicate，已驳回事件保持failed。S1未生成审核任务的历史needs_confirmation记录，可重放原消息升级到新审核流程，不猜测已丢弃的原文。

`GET /api/v1/ingestions?page=1&page_size=20`：按权限列出接入状态、错误码、时间、脱敏摘要、结构化extraction和result，不返回原文或模型原始响应。

`GET /api/v1/confirmations?status=pending&page=1&page_size=20`：返回id/version、application_id、reason/status、强类型proposal、可见申请候选列表、message_excerpt，以及S1终态任务的target_stage/expected_application_version。

`POST /api/v1/confirmations/{id}/resolve`：必须If-Match审核版本和Idempotency-Key。body为decision(confirm/modify/reject)、change_reason（必填），可选application_id、expected_application_version、candidate_id、position_id、interview_id、create_new_candidate（默认false）、correction（仅modify，且必填）。correction为完整强类型Extraction，拒绝未知字段/任意工具JSON。

```json
{"decision":"confirm","change_reason":"人工核对申请编号后确认","application_id":"目标UUID","expected_application_version":3}
```

确认重新检查权限、审核pending状态和目标版本；变更后409仍保留pending。同一幂等请求复用原响应；不同键重复处理已完成任务409。响应为data:{confirmation_id,status(confirmed/rejected),version,application?}。驳回不改变申请；修改内容、审核人/时间、理由及业务变更同事务审计/outbox。创建新同名候选人需显式create_new_candidate=true，或选择已有candidate_id，不能自动合并。

Extraction包括intent(create_application/update_stage/record_result/schedule_interview/query/unknown)、申请编号/姓名/岗位、stage、interview_round/result、scheduled_at、interviewer、next_interview、missing_fields/ambiguities/source_spans/should_confirm。时间带时区，缺具体时点不能猜测。来源片段及原因列表有条数/长度限制。姓名即使唯一也需人工选择申请；多个编号/多个轮次冲突不自动执行。AI提议的hired/rejected不会自动执行或通过AI审核捷径执行，应走人工申请管理。

“一面通过”记录第一轮passed并进入下一阶段；“安排二面”创建独立的第二轮scheduled/pending。结果-only记录可缺scheduled_at/interviewer（返回null），不编造历史计划；安排接口仍要求时间和面试官。多个动作必须全部校验成功，任何一步需确认都回滚本次业务修改。

`GET /integrations/status`（管理员）：增加parser_provider/model，deepseek为not_connected/blocked_by_credentials/configured_not_verified/mode_mismatch。configured_not_verified只代表存在配置，不代表真实联调成功。腾讯文档仍mock_only、企微仍not_connected。

## S1 历史契约（由S2增补/更新）

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

`app/schemas/ -> contracts/openapi.yaml -> src/types/api.generated.ts`，通过根目录 `npm run contracts:generate` 生成，`npm run contracts:check` 检测漂移。详见 [统一数据契约与扩展规范](13-统一数据契约与扩展规范.md)。OpenAPI 仅导出当前实际路由；下方完整 API 列表为 S1~S7 目标，不代表已实现。

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
