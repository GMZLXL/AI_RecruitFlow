# Codex 总执行指令（复制本文件全部内容发给 Codex）

你现在是本仓库的全栈工程负责人，任务是把 AI RecruitFlow 实现为**可实际运行、可测试、可演示、并可按授权逐步接入第三方服务**的低成本招聘流程自动化系统。

## 一、必须先读取

- `AGENTS.md`
- `README.md`
- `docs/01-项目范围与业务方案.md` 到 `docs/12-里程碑与成本估算.md`
- `codex/PHASE_TASKS.md`
- `contracts/openapi.yaml`
- `starter/backend` 与 `starter/frontend` 当前内容

在修改代码前，向我简要说明你识别的业务边界、项目结构和实现顺序，不需重复文档原文。

## 二、不能更换的技术栈

Python 3.11+、FastAPI、SQLAlchemy2、Pydantic2、Alembic、Pytest；React、TypeScript、Vite、Ant Design、Axios、ECharts、React Router、npm；DeepSeek API；腾讯文档智能表格官方 MCP；企业微信自建应用。SQLite 作为本地默认，PostgreSQL 作为可选生产适配。允许使用满足小体量要求的最少辅助依赖。

## 三、工程目标

先实现无需任何 Key 的 Mock 全流程：
- 输入自然语言招聘消息；
- 根据 Mock 规则/预设测试案例解析字段；
- 依据申请编号匹配/新增记录，歧义进入待确认；
- 正确管理候选人、岗位、申请、面试、事件及操作审计；
- 在一个数据库事务内写业务数据和 outbox；
- 模拟智能表格新增/更新并保存 remote_id 映射；
- React 页面更新，图表读取真实数据库统计，提供清晰的模拟同步标签。

然后分别接入：DeepSeek live parser；腾讯文档 MCP（动态 tools/list 和授权测试）；企微签名验证/AES解密/去重与通知。若缺密钥，将该阶段标记为 `blocked_by_credentials`，不得用伪响应当作真实联调成功。

## 四、实施方式

严格根据 `codex/PHASE_TASKS.md` 按阶段执行。每一阶段：
1. 列出将修改的文件、影响范围、数据库迁移、测试计划；
2. 实现最小闭环，不进行与阶段无关的重构；
3. 编写单元测试/集成测试，运行命令并贴结果；
4. 更新 README、API 契约和 `.env.example`；
5. 给出本阶段“已完成/未完成/凭证阻塞项/下一阶段”报告；
6. 不要自行编造企业 API 凭证、腾讯文档字段 ID 或企业微信签名算法。

## 五、质量和安全红线

- 保证数据库是业务事实来源，腾讯文档是异步协作投影。同步失败可见、可重试、不丢业务数据。
- `candidate_id` 不等于 `application_id`。同一个候选人可应聘多个岗位。只凭姓名不得自动更新。
- 机器人群消息不可被默认主动监听。前期仅支持 HR 转发/主动投递消息。
- 关键业务操作（终态逆转、多个候选匹配、时间模糊）必经人工确认。
- 后端实施 RBAC，生产模式禁止以浏览器自报 role 进行身份认证。
- DeepSeek 输入使用必要字段与脱敏文本；Prompt 注入不得触发任意工具调用。
- 任何 `.env`、Token、真实候选人个人信息不得写入仓库、日志和自动测试样例。
- AI 只提出建议，不自动进行候选人淘汰或录用决定。

## 六、我需要你交付的最终结果

1. 前后端完整源代码 + package-lock.json + Python 锁定依赖 + Alembic migrations。
2. `.env.example`、Docker Compose、README（Windows/Unix启动命令）、日志与备份方案。
3. 测试：单元、接口、端到端 Mock、权限、幂等、版本冲突、外部同步故障。
4. 完整可演示页面：工作台、候选人、申请详情、AI录入与审核、待办、同步中心、系统设置。
5. 真实集成通过时给出授权测试结果；未授权时明确列出需要我提供的参数和管理员操作。
6. `docs/IMPLEMENTATION_REPORT.md`：功能清单、测试结果、风险、演示操作、尚未完成事项。

现在从 `PHASE_TASKS.md` 的 S0 开始，不要直接跳到最终部署。出现阻塞时优先完成不依赖外部凭证的代码和测试，不因缺密钥而停止整个项目。
