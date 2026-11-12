# 实施状态（2026-11-12，S1）

| 模块 | 状态 | 证据/备注 |
|---|---|---|
| 12份开发文档 | 已完成 | docs/01~12 |
| Codex 总任务书/分阶段计划 | 已完成 | codex/3份文件 + AGENTS.md |
| 统一数据契约 | 已实现S1 | Pydantic -> 19条实际路径OpenAPI -> 生成TS；自动漂移检查；扩展规范见docs/13 |
| FastAPI+SQLAlchemy Mock Starter | 已扩展基线 | 全量实际测试结果见docs/IMPLEMENTATION_REPORT.md |
| Mock AI 规则解析 | 基础可用 | 演示仅支持少量格式，不等于DeepSeek |
| Outbox模拟同步 | 基础可用 | 不调用腾讯文档，MOCK ID |
| React/TypeScript/npm代码 | 已安装构建 | 开发身份切换/版本化人工推进；S0浏览器主流程已补验；完整UI验收在S4 |
| 审计 | S0基础已实现 | 业务+事件+outbox+audit同事务，故障回滚测试 |
| Alembic迁移/业务CRUD/开发RBAC | 已实现S1 | UUID关系模型、空库迁移与旧库保留复制、角色数据范围、版本/软删除；生产身份未实现 |
| DeepSeek真实模型 | 未接入 | Codex S2，需Key |
| 腾讯文档MCP真实写入 | 未接入 | Codex S3，需授权/Token/VIP核查 |
| 企业微信回调/推送 | 未接入 | Codex S5，需企微管理员授权 |
| Docker Compose与生产安全 | 未实现 | Codex S6 |

强调：这是 **文档及开发起点**，不是一个可直接上线生产的系统。请按 Codex 阶段计划开发、测试和联调。

本轮补齐S0浏览器验收、初始化Git并保存基线，然后只实施S1。46项pytest、类型/lint/build/契约、迁移检查及HTTP冒烟通过。下一阶段S2，尚未开始。详细报告见`docs/IMPLEMENTATION_REPORT.md`。
