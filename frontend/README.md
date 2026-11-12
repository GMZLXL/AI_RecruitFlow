# 前端工作台（开发 Mock）

当前S4：Dashboard/Candidates/ApplicationDetail/AIInbox/Tasks/SyncCenter/Settings均可运行，路由延迟加载，图表使用ECharts按需模块。1440/1024/390px已实际检查，移动端可人工审核及登记Offer；负责人只读、同步管理仅管理员，服务端同样校验。

Node要求22.13+（22.x）、24.x或26+；已实测24.14。`npm run test:web`运行Vitest/Testing Library的12项实际测试，根npm test同时运行后端。产品/界面事实见PRODUCT.md、DESIGN.md，其余命令见根README。

在仓库根运行 `npm ci`、`npm run dev:web`，需要后端已在8000端口启动。锁文件统一在根目录。

目录按app/pages/components/features/services/styles/types拆分，表单和读取状态按领域复用。同一消息重试复用事件ID，新业务显式新建事件；字段/版本/状态来自统一契约。页面已替换原占位组件，生产身份和真实第三方仍未联调。

API类型由后端OpenAPI生成到src/types/api.generated.ts；不要在页面重写领域类型。修改契约后在根目录运行npm run contracts:generate。npm run check聚合类型、lint、契约、后端和组件测试、构建。

同步中心包含真实任务统计、按状态分页、自动刷新、错误/下次重试与管理员人工重试表单。后台接受请求不等于远端成功；Mock/内部事件与腾讯凭证阻塞明确区分。标签与错误码展示位于features/sync，API方法只使用生成类型。
