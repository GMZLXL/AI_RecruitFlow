# 实施状态（2026-11-12，S3）

| 模块 | 状态 | 证据/备注 |
|---|---|---|
| 12份开发文档 | 已完成 | docs/01~12 |
| Codex 总任务书/分阶段计划 | 已完成 | codex/3份文件 + AGENTS.md |
| 统一数据契约 | 已实现S3 | 按领域schemas包 -> 22条实际路径OpenAPI -> 生成TS；自动漂移检查 |
| FastAPI+SQLAlchemy Mock Starter | 已扩展基线 | 全量实际测试结果见docs/IMPLEMENTATION_REPORT.md |
| Mock AI 规则解析 | 基础可用 | 演示仅支持少量格式，不等于DeepSeek |
| Outbox异步模拟同步 | 已实现S3 | 持久Mock投影/映射、租约、指数退避、死信、幂等重试；不调用腾讯文档 |
| React/TypeScript/npm代码 | 已安装构建 | 开发身份切换/版本化人工推进；S0浏览器主流程已补验；完整UI验收在S4 |
| 审计 | S0基础已实现 | 业务+事件+outbox+audit同事务，故障回滚测试 |
| Alembic迁移/业务CRUD/开发RBAC | 已实现S1 | UUID关系模型、空库迁移与旧库保留复制、角色数据范围、版本/软删除；生产身份未实现 |
| S2解析/审核 | 已实现 | Mock/DeepSeek协议、事件租约/幂等、确认/修正/驳回、Web审核 |
| DeepSeek真实模型 | blocked_by_credentials | 适配器及模拟HTTP契约测试通过，未使用真实Key联调 |
| 腾讯文档MCP真实写入 | blocked_by_credentials | 只读initialize/tools/list发现器及失败关闭适配器；仍需授权/实测Schema/字段映射/VIP核查 |
| 企业微信回调/推送 | 未接入 | Codex S5，需企微管理员授权 |
| Docker Compose与生产安全 | 未实现 | Codex S6 |

强调：这是 **文档及开发起点**，不是一个可直接上线生产的系统。请按 Codex 阶段计划开发、测试和联调。

本轮已完成S3无需凭证部分及Web死信重试验证。真实授权边界、测试数量和HTTP结果见`docs/IMPLEMENTATION_REPORT.md`。下一阶段S4；腾讯授权联调仍待凭证，不能宣称真实写入通过。
