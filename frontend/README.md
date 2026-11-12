# 前端 Mock Starter

在仓库根运行 `npm ci`、`npm run dev:web`，需要后端已在8000端口启动。锁文件统一在根目录。

目录按app/pages/components/features/services/styles/types拆分；S2提供人工审核队列、结构化修正、确认/驳回和结果联动。同一消息重试复用事件ID，新业务显式新建事件。完整详情/成品看板/多尺寸组件验收在S4，生产身份和真实第三方尚未联调。

API类型由后端OpenAPI生成到src/types/api.generated.ts；不要在页面重写领域类型。修改契约后在根目录运行npm run contracts:generate。检查：npm run typecheck、npm run lint、npm run build。S4再引入组件测试。

S3同步中心包含真实任务统计、按状态分页、自动刷新、错误/下次重试与管理员人工重试表单。后台接受请求不等于远端成功；Mock/内部事件与腾讯凭证阻塞明确区分。标签与错误码展示位于features/sync，API方法仍只使用生成类型。
