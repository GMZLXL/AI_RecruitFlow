# AGENTS.md — AI RecruitFlow 仓库执行约束

> 适用于整个项目及所有子目录。开发代理必须先阅读 README 和 docs/01~12。

## 使命

在低成本预算下实现 AI 驱动的招聘记录自动化：React/TypeScript/npm 前端、Python/FastAPI 后端、DeepSeek API、腾讯文档智能表格 MCP、企业微信自建应用；先 Mock 全流程可跑，再按有效授权接入真实系统。

## 技术栈不可擅自更改

- 前端 TypeScript、React、Vite、npm；组件 Ant Design；请求 Axios；图表 ECharts。
- 后端 Python 3.11+、FastAPI、Pydantic、SQLAlchemy 2、Alembic、Pytest；数据库开发SQLite，生产可配置PostgreSQL。
- AI 使用 DeepSeek API，模型名由 `DEEPSEEK_MODEL` 配置；JSON Output + Pydantic 强校验。
- 腾讯文档 `SmartSheetAdapter` + 官方 MCP，务必先 `tools/list`；不可臆造工具的参数与 REST API。
- 企业微信自建应用：验签、AES解密、去重及异步处理；群机器人不能直接读取群聊全量消息。

## 先完成最小垂直闭环

`React AI 输入 -> FastAPI ingestion -> Mock Parser -> 匹配/校验 -> DB+审计+outbox -> Mock SmartSheet -> 看板可见`，再扩展真实 DeepSeek/MCP/企微。

## 执行纪律

1. 实现前查看 `codex/PHASE_TASKS.md`；每阶段先列影响文件、验收条件，再实现。
2. 一次只完成一个阶段，跑测试后输出：完成/未完成、文件变更、测试结果、阻塞项与下一阶段。
3. 修改 API 要同步更新 `docs/05-API接口契约.md`、`contracts/openapi.yaml` 和前端类型。
4. 所有写操作必须检查后端权限、幂等、状态机和版本；不允许单纯依赖模型置信度。
5. 所有业务修改在一个事务中写入 `audit_logs` 与 `sync_outbox`；网络调用不得在数据库事务里。
6. 真实密钥只从 `.env`/secret store 读取；`.env`、数据库、Token、个人资料不得提交Git。
7. 无真实凭证时继续完成 Mock，而不是虚构真实同步已完成。
8. 不采集普通群机器人不可读取的消息，不擅自开放全量会话存档。
9. AI 不做录用/淘汰决定，不把候选人联系方式全文发送第三方模型。
10. 不为追求“功能丰富”提前引入 Redis/Kafka/Celery/微服务；单实例 SQLite+任务表足够MVP。升级必须说明依据。

## Definition of Done

- `python -m pytest -q`、`npm run typecheck`、`npm run build` 全通过。
- 无密钥 Mock 模式可完整演示；界面明确标记模拟接入。
- 同名冲突需确认；重复消息不重复写；状态逆转受控；同步故障可重试；权限阻断越权。
- README 开箱流程准确，迁移文件有效，API/数据字典同步更新。

## 禁止行为

- 在浏览器代码写入 DeepSeek Key / 腾讯文档 Token / 企业微信 Secret。
- 未验证接口却声称腾讯文档集成成功。
- 将普通微信群机器人作为群聊自动监听入口。
- 使用伪造指标或硬编码图表数据冒充实际业务数据。
- 跳过测试，删除失败测试或将安全检查临时关闭后宣称完成。
