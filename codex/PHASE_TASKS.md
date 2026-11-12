# Codex 分阶段可执行任务单

> 顺序执行 S0~S7。各阶段明确交付、依赖、验收；下一阶段以前一阶段验收通过为前提。注意 starter 是最小演示起点，不是完整实现。

## S0｜工程基线与Mock冒烟测试

**任务**：核查 `starter/backend` + `starter/frontend`，搭建工作区根README、.gitignore、API前缀、前端导航；新增全局类型检查、lint、最小pytest。执行无Key的启动验证。

**验收**：前端5173能打开、后端8000健康检查成功、Mock解析演示成功、基础 CRUD/看板可见。README说明怎样安装运行。`npm run build`、`npm run typecheck`、`pytest -q` 全绿。

**禁止**：引入真实Token；将 starter 当前简化代码宣称生产级完成。

## S1｜数据结构、迁移、身份与状态机

**任务**：建立 SQLAlchemy 模型与 Alembic 迁移：users/positions/candidates/applications/interviews/ingestion_jobs/confirmations/recruitment_events/sync_outbox/remote_record_links/reminders/audit_logs；使用业务状态机；设计 RBAC 和开发身份开关；完成CRUD、筛选、分页、版本冲突。

**验收**：同候选人可有2条岗位申请；重复 application_code 被拒绝；越权 403；stage 终态逆转进入确认；并发版本冲突 409；迁移可在空数据库执行。

**测试重点**：唯一约束、时间UTC、软删除、权限数据过滤、事务一致性。

## S2｜AI信息提取与确认闭环

**任务**：实现 `Parser` 协议（MockParser/DeepSeekParser）、DeepSeek API配置、JSON Output 与 Pydantic、超时/空响应/截断兜底；意图分类；申请编号提取和候选匹配；确认列表和操作；消息事件幂等。

**验收**：无Key Mock可演示三条业务（新增、一面通过、安排二面）；同名冲突不给自动提交；缺具体时点返回需确认；重复 event_id 不重复更新；包含恶意提示消息不会泄密。

**测试重点**：可重复的固定样本、LLM响应契约、时间歧义、负面用例。

## S3｜异步外部同步与腾讯文档MCP

**任务**：定义 `SmartSheetAdapter` 协议，Mock保存 `remote_id` 映射，事务性 outbox，单实例任务处理器、指数退避、死信、管理员重试接口，React 同步中心。

**真实联调**：使用用户提供的 `TENCENT_DOCS_TOKEN`，在独立测试表依次 `tools/list -> list_tables -> list_records -> add_records -> update_records -> list_records`；检查 token 权限及会员限制；以真实工具 JSON Schema 实现适配器。

**验收**：Mock 新增后更新同一远端记录，失败后重试；本地成功不被远端失败回滚；未提供Token显示未配置/凭证阻塞。无授权时不宣称真实成功。

## S4｜招聘看板、前端产品体验

**任务**：实现 Dashboard、Candidates、ApplicationDetail、AIInbox、Tasks、SyncCenter、Settings；统一 Axios 客户端、路由/权限、Loading/Empty/Error、日期范围、筛选、分页、Ant Design 风格、ECharts 图表。

**验收**：至少支持1440/1024/390px；空库不显示假数据；筛选会实时反映数据库；AI确认可在Web端完成；无权用户看不到敏感字段且后端确实拒绝对应访问。

**测试重点**：TypeScript、路由、组件状态、API错误回退、前后端联调。

## S5｜企业微信应用接入与提醒

**任务**：管理后台创建自建应用配置指南；实现企微 GET 回调 URL验证、POST 签名校验/AES解密、message id 防重、快速应答异步处理；应用消息发送；提醒逻辑/任务去重。

**验收**：Mock模拟消息能够进入同一 ingestion pipeline；真实企微应用管理员授权后通过官方URL校验；非法签名拒绝；重复消息一次处理；发送通知显示真实交付状态。无管理员权限可完成 Mock 与SDK测试，但标记未联调。

**边界**：普通企业微信群机器人不具备任意群消息监听能力。

## S6｜安全、部署与运维

**任务**：环境密钥保护、RBAC安全审计、速率限制、脱敏日志、SSO/企微OAuth生产方案、任务处理单实例锁、Docker Compose、备份与恢复手册、可观察性。

**验收**：生产不接受 dev header；日志无 Key；审计涵盖所有修改；`docker compose config` 通过；异常同步可重试；缺关键 live 配置直接拒绝使用 live 连接器；角色越权测试通过。

## S7｜端到端验收与交付

**任务**：完整跑 `docs/11-测试与验收标准.md` T01-T18；确保部署文档与命令真实可复现；修复高优先级 bug；输出 `docs/IMPLEMENTATION_REPORT.md`。

**验收**：说明哪些通过、哪些受外部 Token 阻塞；不得口头认定未执行的真实集成通过。以 Mock 模式录制可复现 Demo 操作。提交可回滚的清晰 Git commit。

---

## 每阶段汇报模板（必须使用）

```text
阶段：Sx
已完成：...
本阶段变更文件：...
数据库迁移：...
运行的命令：...
测试结果：通过 X，失败 Y，跳过 Z
未完成/阻塞：...
重要风险：...
下一阶段：Sy
```
