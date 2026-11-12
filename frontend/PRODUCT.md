# AI RecruitFlow 产品事实

## Platform
Web：桌面HR工作台，兼容1024px与390px移动浏览器；不是原生App。

## Audience and job
HR录入招聘记录、安排与反馈面试、登记Offer、人工审核AI提议；负责人查看部门进展；管理员管理岗位与同步故障。数据写入受后端权限/版本/幂等控制。

## Mechanism
React输入→受校验的AI提议→人工确认/业务写入→事务性审计与outbox→异步协作表投影。数据库是事实源，外部失败不撤销本地记录。

## Stack
用户指定React/TypeScript/Vite/npm、Ant Design、Axios、ECharts；后端FastAPI/Pydantic/SQLAlchemy/Alembic。不可擅自更换。

## Confirmed constraints
用户指定按docs/01~12和PHASE_TASKS分阶段实施，采用浅色企业级Ant Design。S4补充：同时显示Offer发出/接受/拒绝与已录用，增加独立Offer事实记录；生成明确标记的虚构人名、岗位、面试数据。Offer接受不等于录用，不自动作招聘决定。

## Trust
默认Mock及开发模拟身份；第三方凭证缺失必须显示阻塞；不在浏览器保存Key/Token，不展示联系方式全文。图表使用实际数据库数值，演示数据不冒充真实招聘业绩。

## Success
1440/1024/390px均能查询、录入和审核；筛选口径清晰；空、加载、错误、冲突与权限状态可恢复。真实集成与生产身份尚未验证。
