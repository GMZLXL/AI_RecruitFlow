# 分段粘贴给 Codex 的短提示词

## 第一次（初始化和建立 Mock 闭环）

请阅读 `AGENTS.md`、`README.md`、`docs/01~12`、`codex/CODEX_MASTER_PROMPT.md`、`codex/PHASE_TASKS.md`，先执行 S0-S1，不接入真实第三方。优先让 FastAPI + React + npm 本地完整运行：候选人/岗位申请/状态修改、AI Mock 录入、SQLite 持久化、看板、最基本测试；SQLAlchemy模型与Alembic迁移必须到位。每个阶段结束运行 `pytest -q`、`npm run typecheck`、`npm run build`，输出真实结果并更新文档。不要更换技术栈。

## 第二次（AI 工作流）

基于已通过S0-S1的仓库执行S2，新增 DeepSeekParser/MockParser 和完整审核闭环，遵循 `docs/07-AI能力与提示词规范.md`，JSON Output + Pydantic 强校验、幂等、双重候选匹配、时间歧义、终态逆转等全部加测试。无真实Key时 mock 应继续正常运行。完成后报告测试结果。

## 第三次（腾讯文档与任务队列）

执行S3。先实现SmartSheetAdapter、SQLite持久化outbox、Mock同步成功/失败重试和remote id映射；再根据实际授权通过腾讯文档MCP的tools/list发现真实工具Schema，严禁猜测参数。缺TENCENT_DOCS_TOKEN则停止真实联调但不停止Mock开发。同步中心必须明确显示真实/模拟/未配置状态。

## 第四次（完整页面与企微）

执行S4-S5，按 docs/06 制作Ant Design React页面、ECharts统计、响应式和错误态；实现企微回调验签/AES、事件去重与异步处理，推送提醒。普通群机器人不能主动获取群聊所有消息，保留HR主动转发路径。运行全部测试。

## 第五次（安全部署验收）

执行S6-S7，完成权限、安全、脱敏、Docker Compose、备份、CI及T01~T18验收。提交 IMPLEMENTATION_REPORT 说明已通过功能、未联调的外部集成、真实测试结果。不要把空白第三方凭证表示成“接入成功”。
