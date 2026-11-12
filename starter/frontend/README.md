# 前端 Mock Starter

在仓库根运行 `npm ci`、`npm run dev:web`，需要后端已在8000端口启动。锁文件统一在根目录。

已演示：工作台、申请列表和新增、Mock AI 录入、Mock 同步中心。未实现：正式RBAC、招聘详情、审批队列、完整看板和真实第三方连接。这些必须由 Codex S1~S7 完成。

API类型由后端OpenAPI生成到src/types/api.generated.ts；不要在页面重写领域类型。修改契约后在根目录运行npm run contracts:generate。检查：npm run typecheck、npm run lint、npm run build。S4再引入组件测试。
