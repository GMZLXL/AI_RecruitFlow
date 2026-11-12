# 前端 Mock Starter

在仓库根运行 `npm ci`、`npm run dev:web`，需要后端已在8000端口启动。锁文件统一在根目录。

S1增加开发身份切换、权限显示、If-Match人工阶段推进；后端执行真正的数据范围与角色校验。已有工作台、申请列表/新增、有限Mock录入和模拟同步。完整详情/审核/成品看板在S4，生产身份和真实第三方尚未接入。

API类型由后端OpenAPI生成到src/types/api.generated.ts；不要在页面重写领域类型。修改契约后在根目录运行npm run contracts:generate。检查：npm run typecheck、npm run lint、npm run build。S4再引入组件测试。
