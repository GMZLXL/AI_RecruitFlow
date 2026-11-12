# AI RecruitFlow 实施报告

## S7 实际交付（2026-11-12）

```text
阶段：S7
已完成：T01–T18逐项实际验收及JUnit矩阵；隔离无Key Mock演示；真实浏览器1440/1024/390完整录入/审核/同步/统计/越权链路；React19兼容缺陷修复；Windows/Linux CI全新安装与Linux Compose镜像构建/健康/Nginx代理HTTP；44秒关键帧录像及交付手册。
本阶段变更文件：backend/tests/integration/test_s7及多岗状态断言、scripts/acceptance/{release,demo}、可配置URL的smoke脚本；前端空态/成功提示断言、Vite本机代理、React19官方补丁与依赖锁；.github/workflows/acceptance.yaml；README/状态/docs03/06/09/11/12/14/15/16、S7计划及docs/demo/s7证据。
数据库迁移：无；业务契约保持OpenAPI0.7.0/41路径、DB head0006_s6；db:check无漂移。验收/演示均用新隔离SQLite，日常业务库与.env未被清空或覆盖。
运行的命令：npm run acceptance（契约/lint/类型/pytest/Vitest/build/隔离HTTP/合成SSO）；demo:isolated及--verify；db:check/deploy:config、compileall、FFmpeg录像编码/ffprobe；GitHub CI实际从锁文件安装、docker compose config/up --build --wait及HTTP；下载并核对两平台JUnit汇总产物。
测试结果：最终本机后端206通过（30.53s）、前端20通过/5文件（29.90s），失败0、跳过0；类型/lint/契约通过，build通过（12.29s）；T01–T18全部通过。最终Windows/Linux CI各226通过、0失败/跳过、18矩阵通过；Linux容器作业通过。结果限Mock/合成transport，非真实外部授权验收。
未完成/阻塞：真实DeepSeek与60条标注/人工复核准确率评测、腾讯MCP授权Schema和写入、企微租户、企业SSO网关/TLS与生产覆盖运行；PostgreSQL/macOS未实机；AI周报/导入导出/自动归档等P1未交付。没有把这些列为通过。
重要风险：单实例SQLite/单API进程内存限流，正式环境需匹配主密钥与恢复验收；保留Starlette测试客户端弃用、AntD静态消息不消费动态主题上下文和538.13KB主包提示。Mock通过不等于正式上线或95%模型准确率达标。
下一阶段：S0–S7 Mock范围结束；按有效授权开展真实连接器、模型评测和目标环境验收，不虚构新阶段或自动启用live。
```

### 最终交付范围与统一结构

候选人/多岗申请/面试/独立Offer、权限/版本/状态机/幂等、AI提议/人工审核、原子DB+审计+outbox、持久Mock映射/重试、数据库看板、企微Mock/SDK/提醒、管理员AI加密配置与安全运维均保留前阶段契约。S7没有新增业务字段或绕过后端规则，前后端继续使用同一生成数据结构。没有引入Redis/Celery或独立测试框架。

新增release脚本调用现有Pytest/Vitest和静态检查，读取实际JUnit，将T01–T18映射到真实用例；找不到、失败或跳过均不能给通过。T09验证空模型响应两次后完整管线入审核且业务未改；T10分别验证输入在外呼前拦截、恶意模型字段/SQL/合成Key被结构拒绝；T15独立SQL与Python日历核对多角色、岗位、上海日期边界、去重人数、Offer和未来/过去面试；T05补独立状态断言，T16补实际组件空态及浏览器空库。不是用相同实现函数给自己算期望值。

本轮新增4项后端、1项前端，最终206/20。首轮新增注入测试预期两次模型调用，实测为零次，原因是既有输入门禁提前拒绝；拆成输入注入与模型输出注入两种断言，保留安全检查并验证两条路径。未删除失败测试、隐藏警告或改成skip。

### 实际CI、失败修复与可复现运行

最终成功[Release acceptance运行43206404969](https://github.com/GMZLXL/AI_RecruitFlow/actions/runs/43206404969)验证提交`244d1369a5b4c7196a9dc2f06f4f074afd052799`，三作业均success：

| 作业 | 实际结果 |
|---|---|
| Windows完整Mock验收 | 全新venv/哈希锁安装/npm ci；226通过、0失败、0跳过，矩阵18通过 |
| Linux完整Mock验收 | 同上；226通过、0失败、0跳过，矩阵18通过 |
| Linux Compose运行 | 两份配置解析；API/web镜像构建；服务健康；Nginx静态资源/安全header与代理业务链路；结束停止栈 |

已下载两平台artifact核对result.json，而非只读取绿灯。CI元数据、矩阵、测试函数对应关系见[16号手册](16-S7验收与演示.md)和docs/demo/s7/{acceptance,ci-result}.json。详细JUnit产物14天保留，源SQLite、secret、日志不进Git。后续纯文档与演示证据提交按workflow的paths-ignore跳过同一代码重跑，已测试源码提交保持清晰。

首轮CI两个平台完整验收均成功；容器已构建并健康，但HTTP步骤直接执行smoke/http.py遮蔽标准库http，导致httpx循环导入而失败，未将此算容器通过。修复为backend工作目录下`python -m scripts.smoke.http`，提交244d136后重新运行三作业全部成功。Docker运行并非在本机Windows假设完成，而是远端Linux真实执行；生产SSO覆盖仅config，不冒充真实TLS/租户验收。

前端原React19/AntD5缺官方兼容补丁，组件运行出现兼容提示且页面使用静态message。按[Ant Design官方用法](https://github.com/ant-design/v5-patch-for-react-19#usage)加入固定1.0.3及主入口/测试加载，实际断言审核成功消息可见，兼容提示消失。浏览器仍记录静态message上下文开发提示，不改主题/页面设计或掩盖它。生产手册role示例从hr修正HR，并修复README尚未配置远程的历史说法。

### 浏览器演示与录制

`demo:isolated`在新的忽略目录创建独立空库、显式Mock环境与API/Web进程，可指定本机端口，Ctrl+C停止本轮两服务。`--verify`生成虚构样本并执行原http/workbench/wecom链路后退出，不触碰日常数据库。端口占用明确失败，不擅自杀进程。Vite代理覆盖只接本机HTTP origin且只在服务端读取，不把密钥/地址注入前端业务契约。

本轮浏览器真实运行8037/5187，空库先显示0申请/0人/无反馈；从React输入“新增虚构S7演示甲应聘测试工程岗”，返回A75A93BFEF1F2。独立新事件推进筛选/一面、登记一面通过，再输入模糊二面时间进审核；390px补2026-11-13 15:00与虚构说明后执行。首次自动化日期填充未进入受控输入，页面正确阻断缺时点；改用原生日期输入后值保留且成功，未修改应用校验绕过。详情v5显示一面原计划未知/通过、二面未来计划/待反馈。同步中心显示同一MOCK远端映射，工作台实际变为1申请/1人/1待面试，Offer与录用0。HR乙直接访问该申请被后端拒绝，最后恢复管理员。

1024页面client/scroll均1024，390审核均390，无页面横溢。保存13张实际关键帧及时间/URL操作清单，选其中11张桌面帧各4秒编码[44秒MP4](demo/s7/demo.mp4)，298667字节，已ffprobe与中间帧目视验证。它是实际操作的关键帧录像，不是连续实时录屏，也不是AI生成画面；手机审核和1024详情另存截图。没有对外发消息、填写真实Key或采集真实候选资料。完整复演步骤、未来时点替换要求及截图见docs/16。

### 仍需授权的交付边界

T01–T18通过范围是无KeyMock、合成模型transport与合成签名会话；腾讯仍须真实tools/list Schema和独立授权表查询→新增→更新→复查，DeepSeek须真实模型和60条标注/复核评测，企微须企业管理员/HTTPS回调/成员测试，SSO须受信网关与实际TLS/映射撤销验收。没有达到或声称已达到95%准确率、业务ROI、P95或全部PRD增强功能。P1周报/导入导出/自动归档、PostgreSQL实例与macOS仍未验收，不以文档或离线DDL代替实测。

以下为S6及更早阶段历史记录。

## S6 实际交付（2026-11-12）

```text
阶段：S6
已完成：生产会话验证/DB角色/CSRF、失败关闭配置、环境与文件secret、AI前端配置及后端加密、限流/脱敏日志、领导租约/健康可观察性、Compose及备份恢复/用户授权工具与手册。
本阶段变更文件：schemas/ai_settings与operations/identity、OpenAPI0.7.0/41路径及TS；0006_s6/models；core安全模块、jobs/runtime、services/ai_settings、api/v1/operations及main；前端App/Settings/AISettingsPanel/client/api及组件测试；admin/operations/smoke脚本；部署/依赖锁与docs04~15、README/状态/设计事实。
数据库迁移：0006_s6新增auth_identities、ai_settings、worker_states；本机一致备份旧0005_s5库后升级，db:check无漂移；在线备份与新文件恢复演练通过，原库未覆盖。
运行的命令：contracts:generate/check、npm run check、db:upgrade/db:check、smoke:security/http/wecom、ops:backup/restore、deploy:config及生产覆盖config；Ruff/类型与compileall补检；1440/1024/390px浏览器验收及独立UI评审。
测试结果：后端202通过（36.84s）、前端19通过/5文件（41.26s）、失败0、跳过0；契约/lint/Python及TS类型通过，build通过（19.27s）。S6安全/运维targeted34项通过；新增安全HTTP冒烟通过；官方Compose两配置解析通过。
未完成/阻塞：无Docker Engine，未构建镜像/启动容器或运行Nginx；真实企业SSO网关/OAuth/TLS、DeepSeek Key、腾讯MCP工具Schema与写入、企微租户授权未联调；PostgreSQL与Linux/macOS未实机验收。
重要风险：单进程内存限流/单实例SQLite；备份必须同时保护匹配的加密主密钥；网关需正确签发应用Cookie并脱敏日志，JWT最长1小时且无逐jti撤销；保留测试客户端弃用及537.92KB主包警告。未宣称可直接上线。
下一阶段：S7（端到端验收与交付），本轮不提前实施。
```

### 用户要求：前端填写AI接入

管理员系统设置新增AI配置，沿用现有Ant Design纵向表单；provider/model与SecretStr输入先定义统一schema，再实现DB/服务/API/生成TS/前端。Key仅提交后端，AES-GCM密文存DB；主密钥由服务器提供，开发自动生成忽略文件，生产必须显式secret。GET、审计快照、outbox、错误及浏览器存储均不含Key/密文；幂等摘要区分同键不同Key。新Key空输入保留，清除禁用环境回退，Mock可预存但启用DeepSeek必须服务器hybrid。配置保存只标记未验证，未实际调用三方。

保存成功清空Key并显示保存版本；失败保留草稿，刷新只取最新版本供核对。后端管理员权限、If-Match、幂等、状态门禁、原子审计/outbox均测试。浏览器实际保存虚构Key到version2（已配置、输入清空），随后清除到version3（未配置、Mock），未保留测试Key。1440/1024/390px截图存于忽略的.tools/s6-ai-*.jpg，手机clientWidth/scrollWidth均375。静态detector只执行一次结果[]，独立review最终disposition **ship**，无material findings。

| 最终UI核验项 | Verdict |
|---|---|
| 入口、信息顺序、字体、材质 | match |
| 桌面/窄屏、密钥状态、保存反馈与恢复 | match |
| 认证展示 | match（源码；真实企业会话尚未联调） |

### 身份、日志与任务边界

生产拒绝dev/role头和开发目录，不加载开发.env；受信网关RSA>=2048公钥钉住，RS256 issuer/audience/iat/exp/sub/jti严格校验，JWT角色不赋权。实际授权依AuthIdentity与有效User，CLI显式配置/撤销并同事务审计；未对真实账号操作。SSO写入Origin+HMAC CSRF，浏览器仅内存令牌；登录/退出由同源外层网关提供。OAuth/企微OAuth为明确的目标方案与接口契约，未实现或伪造租户联调。

请求64KiB/10秒、Host、IP及actor限流、429 Retry-After；安全JSON日志事件白名单省略第三方任意消息/异常，应用日志用路由模板不带查询/正文，生产关闭文档并设安全header。根日志/uvicorn/httpx边界测试通过。全局45秒DB租约、5秒续租，仅leader启任务，standby不重复运行；原单任务token/幂等仍保留，最近循环/成功/错误与队列事实可从管理员ops读取。租约/心跳为协调元数据，不写业务审计以免放大。readyz只证明DB版本/租约，不能冒充所有任务成功。

### 部署和恢复证据

新增非root、只读根、tmpfs、drop capabilities、健康依赖与日志轮转的Compose；默认只绑定127.0.0.1:8080 Mock，生产覆盖要求外层HTTPS/SSO网关和受保护secret挂载。API单进程，启动先校验再迁移，不放开未验证live。后端runtime锁不包含测试依赖，前端npm ci。Nginx安全header遵循继承规则，不在子location覆盖；尚无运行时验收。

本机缺Engine，下载官方Compose standalone v5.7.1至忽略工具目录，官方SHA256 e4316597452650ae92fe9719a2a7c2fce8f56c5ceafed88d2aed6e39b2b2b2d0核对通过，实际执行Mock与生产示例config --quiet均退出0；没有将Python/YAML检查冒充Docker配置验证，也未宣称镜像运行成功。

SQLite在线快照备份、quick_check/FK/表计数与SHA256 manifest、新文件恢复通过；恢复只清协调租约，不覆盖活动库、不清业务状态或盲目重发通知。本机实际演练revision0006_s6、41申请、快照时1044审计一致。主密钥需另行安全备份；checksum不提供备份来源认证。完整切换/回退、secret ACL、网关与监控步骤见docs/15。

隔离smoke:security实际启动生产配置Mock HTTP进程，生成合成RSA/secret与独立库，验证签名会话→DB角色→CSRF拒绝/通过→dev头拒绝→Key加密/元数据→worker健康→生产docs404→日志无合成secret；进程结束后退出，不访问真实IdP/TLS/外部服务。现有smoke:http与smoke:wecom通过，后者本轮保留虚构申请A_S5_1A74F703。未删除失败测试、停用安全检查或把未执行项目报pass。

以下为S5及更早阶段历史记录。

## S5 实际交付（2026-11-12）

```text
阶段：S5
已完成：自建应用SDK验签/AES回调；快速持久ACK/异步同一ingestion/MsgId与nonce去重；用户映射及后台权限复核；持久通知、状态与管理员重试；四类事实提醒、阈值配置与去重；设置指引、模拟投稿及本人通知页面。
本阶段变更文件：schemas/wecom及生成OpenAPI 0.6.0/37路径/TS，0005_s5与models，integrations/wecom、services/wecom/notifications、jobs/wecom_worker、api/v1/wecom与main；前端features/wecom、Settings/Tasks、api及useResource；S5回归/HTTP脚本/依赖锁/文档，详见下方。
数据库迁移：0005_s5新增wecom_inbox/wecom_replays/notifications/reminder_policy，reminders增加源/接收人；本机停API、SQLite一致备份后升级，db:check无漂移；空库升降/重升、旧库复制兼容及PostgreSQL离线DDL回归通过。
运行的命令：requirements锁定安装；npm run contracts:generate/check、check、db:upgrade/db:check、smoke:wecom、smoke:http；compileall；真实浏览器1440/1024/390及界面评审。
测试结果：最终npm run check完整通过；后端168通过（27.66s，含36项S5新增），前端16通过/4文件（26.97s），失败0、跳过0；契约/lint/类型通过，build通过（13.61s）。无删除失败测试或关闭安全检查。
未完成/阻塞：真实企微管理员授权、凭证、限定HTTPS回调URL及平台投递尚未联调；DeepSeek/MCP真实联调依旧受凭证/Schema阻塞。当前默认Mock，不声称真实通知送达。
重要风险：单实例开发身份，生产认证/部署待S6；平台接受不是成员收到/已读；不明结果只能人工核实，当前不提供强制重发；已取消的同事实提醒不自动重开；保留测试客户端弃用及536.72KB主包警告；PostgreSQL和跨平台未实机验证。
下一阶段：S6（安全、部署与运维）。
```

### 数据、权限和任务边界

统一Pydantic先定义Inbox/Notification/Policy/Status/Binding，随后迁移、业务服务、API和前端消费。接收与投递状态独立于招聘stage；通知provider创建后固定，不把旧Mock队列迁往真实系统。映射只管理员修改，唯一外部UserID映射到既有内部用户；不会赋予新角色。后台再次查active/role/申请范围，模型不获得写权限，录用/淘汰规则不变。

回调默认禁用；真实provider需显式hybrid，回调和发送独立开关。SDK采用第三方wechatpy 1.8.18/cryptography，未自行编造AES算法。签名/时间窗、receiveId/企业/AgentID、UTF-8/XML/DTD/重复字段、大小、nonce摘要、MsgId均受控；只有主动发给自建应用的文本进入工作流，非文本验签后仅ACK，不接入普通群聊/会话存档。首次接收只保存哈希和脱敏工作文本，成功清理文本，API/audit/outbox不复制文本；失败暂保留供恢复。

POST事务提交接收任务即返回success；Mock为202已接收。后台以固定事件键调用同一S2 ingestion；保留原接收时点，跨日处理不移动相对日期。接收150秒租约，S2自身120秒租约仍生效；重复与旧token不重复写。配置/映射/接收/通知/提醒及其状态变化同事务audit/outbox；网络调用在事务之外。

通知状态为pending/processing/mock_sent/accepted/blocked/failed/uncertain/cancelled；每条单接收人、无广播，仅最小模板及申请编号，不发送候选姓名、联系方式、评价或聊天全文。发送采用官方固定HTTPS路径，token进程内缓存，无重定向/任意URL。获取token故障最多3次退避，通知POST不盲目重试；errcode或无效接收人不能记成功，缺msgid/超时/不明HTTP结果保持uncertain。真实120秒领取过期同样uncertain，Mock可重放。管理员重试限明确failed/blocked，必须理由、版本和幂等键。

提醒默认关闭，阈值24小时提前、24小时未反馈、7天停滞；另含最新申请投影故障。基于DB事实生成，类型/源ID/时点/负责人唯一键去重。发送前核对规则、事实、终态/删除、owner和可见范围，已完成/已恢复/权限变化的提醒cancelled。S4待办固定7天口径不变；规则单独控制通知。每2秒处理最多10项接收、20项通知，每30秒扫描提醒，无新增Redis/Celery服务。

### 界面与实测证据

设置保留现有Ant Design：接入/绑定、提醒规则、模拟投稿三标签；凭证只在服务端。通知记录在管理员设置及用户待办复用，文字区分模拟与平台接受；结果不明无重发按钮。配置保存可见确认；局部刷新保留草稿，显示服务器最新已保存数据/version供对照；连接刷新不卸载表单/改变标签。

真实HTTP `smoke:wecom`通过：持久ACK→同消息三次只更新一次→后台AI→一条MOCK-NOTICE模拟通知→RBAC→未配置回调拒绝。保留虚构申请A_S5_99DFB29F、A_S5_413775E9；原`smoke:http`全链路仍通过并保留其虚构记录。没有对外发送消息或访问真实企微数据。

浏览器1440/1024/390实测：390提交s5-ui-mobile-99DFB29F，将上述虚构申请从筛选推进一面，刷新显示已处理及模拟发送；1024文档宽1009、390文档宽375（滚动条宽）无页面横向溢出。管理员保存规则始终关闭且24/24/7；模拟另一个请求只递增配置版本，旧Web版本2真实提交409，刷新到3后草稿和提醒标签保留，再提交成功显示关闭/版本4。配置值未改变。

界面静态检测只运行一次为[]。独立评审首次要求M1保存确认、M2保留草稿的冲突恢复，已一批修复并复验；最终disposition **Ship**，无开放material findings。

| 评审项 | 最终结果 |
|---|---|
| M1 保存确认 | Resolved：binding和规则显示role=status及保存版本 |
| M2 版本恢复/草稿 | Resolved：局部版本刷新、最新值比较、连接刷新保持标签/表单 |

开发热更新修改hook依赖数量时出现旧HMR告警；最终完整重载后的新增console error=[]，不将旧开发日志伪报为生产缺陷或隐藏。多尺寸/成功/冲突截图保存于忽略的.tools/s5-*.jpg；最终截图s5-settings-final.jpg，不纳入Git。浏览器恢复默认视口，页面保留供查看。界面文档记录在frontend/DESIGN.md，产品记录旧schema提示未擅自迁移。

### 变更及验证限制

后端新增schemas/wecom、迁移0005_s5、integrations/wecom/{config,callback,sender}、services/wecom/notifications、jobs/wecom_worker、api/v1/wecom；调整main生命周期、模型/出口、integration状态、内部ingestion日期基准和隐私快照。新tests/integration/test_s5.py、unit/test_wecom_sender.py；scripts/smoke/wecom.py及根命令；requirements.txt/lock增加SDK和密码依赖。前端新增features/wecom及wecom.test，保留既有页面风格与目录结构；useResource可选保留旧值仅用于配置恢复。API/数据字典/接入与运行/测试/扩展/目录文档、README和状态同步。

回归包括异常签名、过期/未来/nonce、错企业/应用、未知发送人、DTD/重复字段/超大、并发去重、延迟基准、权限失效、审计故障回滚；token/发送响应、无网络Mock、失败/不明、四类提醒去重和过期取消、通知范围、事务外IO和token确认。前端新增完整投稿/绑定/规则/重试交互：虚拟Select测试需点击真实可见选项，不能点击仅供读屏的虚拟option节点；多步AntD流程给10秒测试时限，等待版本加载完成再保存，未修改业务安全检查。

最终串行check全通过：168后端、16前端，失败0/跳过0；类型与契约一致。组件回归保留原安全和业务断言，使用真实可见的虚拟Select选项修正测试交互，多步流程等待加载完成；未删除失败测试或关闭安全检查。真实管理员GET验证、成员投递/可见范围、生产认证、实际PostgreSQL和Linux/macOS未验收；官方页面本次无法直接抓取，SDK及官方入口依据见docs/08。S5不包括S6生产安全/部署，不宣称可上线。

以下为S4及更早阶段历史记录。

## S4 实际交付（2026-11-12）

```text
阶段：S4
已完成：七页工作台；授权数据库看板/阶段分布/周趋势/岗位进度；筛选/分页/详情历史/面试与待办；移动端AI审核；独立Offer发出/接受/拒绝与已录用统计；24条虚构申请的幂等样本；加载/空/错/冲突与路由权限；图表与路由分包。
本阶段变更文件：见下方分组；统一Pydantic→OpenAPI 0.5.0（27路径）→TypeScript已生成同步。
数据库迁移：0004_s4，仅新增offers表及约束；本机S3库已升级，空库升降/重升、S0复制/S2兼容、PostgreSQL离线DDL和Alembic check通过。
运行的命令：npm run check；npm run test:api/test:web；npm run typecheck/lint/build；npm run contracts:generate/check；npm run db:upgrade/db:check；npm run demo:seed；npm run smoke:workbench/smoke:http；compileall；生产构建preview；界面静态检测与浏览器验收。
测试结果：后端132通过，前端12通过，失败0，跳过0。完整聚合check通过；最后两项界面修复后，类型/12项组件/build/lint再次通过。HTTP全链路、Offer/权限联调、多尺寸浏览器及生产构建3个图表运行通过。
未完成/阻塞：真实DeepSeek/MCP/企微无凭证联调；自动通知/提醒留S5，生产身份及部署留S6。本轮未进入S5，不把Mock验收当真实集成通过。
重要风险：仅本机开发身份；MVP每申请一条Offer且反馈不可直接逆转，不含多轮谈判；保留1条上游测试客户端警告及535KB主分包警告；实际PostgreSQL和Linux/macOS未实机验证。
下一阶段：S5（企业微信应用接入与提醒）。
```

### 统一结构与变更文件

- backend/app/schemas/workbench.py：Offer、统计/周趋势/岗位进度、待办、审计历史、选项/规则读取；schemas/recruitment.py新增owner_name/next_interview_at/latest_result/sync_status派生字段；integration投影可空offer_status。
- backend/app/db/models.py、db出口、alembic/versions/0004_s4_offers.py：独立Offer实体、申请唯一外键、sent/accepted/declined状态与UTC发出/反馈时点、独立version。
- backend/app/services/workbench.py/offers.py、services/common.py：统一授权申请筛选、SQL聚合/分页待办、安全历史摘要、Offer业务事务及父申请投影。api/v1/workbench.py/dashboard.py/applications.py与路由装配，main版本0.5.0。
- frontend/src/app/App.tsx与pages/{Dashboard,Candidates,ApplicationDetail,AIInbox,Tasks,SyncCenter,Settings}.tsx：完整导航、路由保护和功能页面。features/recruitment分离创建/筛选/日期/状态/阶段/面试/Offer/历史，features/dashboard只注册所用ECharts模块，features/shared/useResource取消旧请求。
- frontend/src/components/RemoteState/AppErrorBoundary：加载、错误恢复、空态和异常边界；styles/global.css、main中文locale/主题、vite.config分包；services/api继续从生成operations/components提取领域类型。
- backend/scripts/demo/seed.py、scripts/smoke/workbench.py、根npm命令；后端S4/样本回归；frontend/src/test、vitest.config及npm测试依赖/统一锁文件。Node要求按实际Vitest/jsdom engines同步为22.13（22.x）或24.x/26+，本机24.14。
- README、backend/frontend README、.env.example、实施状态、docs/04/05/06/09/11/13/14、S4计划及frontend PRODUCT/DESIGN同步。未提交.env、数据库、Token、依赖目录或截图。

### 统计、Offer与权限口径

用户明确补充同时加入Offer反馈和虚构人名/岗位，因此先扩展契约及0004_s4，再写业务/页面。Offer发出只在Offer阶段登记已经发生的事实，不实际发送消息；接受不自动录用，拒绝不自动淘汰，录用仍需授权人员独立登记。旧hired没有Offer记录时不补造接受事实；接受率只统计接受/(接受+拒绝)，无反馈返回null。发出和反馈时点、阶段、权限、幂等、版本均在服务端校验，Offer/audit/outbox及父申请更新同事务。

Dashboard以授权申请创建日期的[from,to)形成集合，面试/Offer统计这个集合关联的实际事实；Web默认近30天。岗位/负责人/阶段/日期与列表重用过滤；列表另支持姓名编号/渠道。周一按上海日期聚合；阶段图明确是当前快照，不伪称历史转化率；岗位编制与已录用/申请量分别说明。无数据时三图显示明确空态，接受率不伪造0%。

待办为SQL分页事实投影：未来已安排面试、计划已过仍待反馈、待审核、7天未更新及最新申请投影故障；对应业务处理后自动移出，不新增任意“标记完成”捷径，不声称企微提醒已发送。History只返回白名单变化、操作人及脱敏依据，不回传原始消息或凭证。HR本人、经理部门只读、管理员全局；设置连接状态及同步任务继续管理员专用，前端隐藏不能代替后端403。

### 虚构数据与幂等

`npm run demo:seed`实际首次输出**added=24, kept_existing=0**，再运行输出**added=0, kept_existing=24**。24条申请使用DEMO_S4_01~24，23位候选人、4个演示岗位，来源“演示样本”、备注“S4虚构演示”。姓名如林沐、陈禾、周宁、宋言，含一人多岗与另一个同名人；岗位含前端、数据分析、Python、客户成功。历史日期/过去面试只在明确的演示初始化中生成并审计，公共API的未来面试限制保持有效。

脚本仅允许development+mock+Mock投影，不覆盖、删除或重置原有记录；已有样本人工修改保留，样本编号冲突会拒绝。全量回归验证原记录version/stage保持不变、一人多岗ID关联、二次运行数量不增。隔离测试初始样本有6条Offer、4接受/1拒绝/1未反馈、3已录用；这些是样本事实，不是产品硬编码指标，Web操作后会自然变化。

### 实际验证

聚合`npm run check`通过：**132 passed, 1 warning in 22.71s**；前端**3 files / 12 tests passed**，当次27.61s。最后界面两项修复后再次类型通过、组件**12 passed in 18.13s**、build **12.88s**、Ruff/ESLint通过。`db:check`为**No new upgrade operations detected**；compileall与契约漂移检查通过。最终阶段说明/契约更新后，OpenAPI及生产模式阻断3项再次通过（5.41s，属上述132项子集）。保留原失败测试意图，修正了日期[from,to)相等应为空集的兼容回归，没有删除失败用例或关闭检查；已删除被完整页面替代且无引用的FeaturePending占位组件。

新增回归覆盖Offer/录用独立、接受率排除未反馈、状态/时点/越权/版本/幂等、审计失败回滚、筛选SQL与列表一致、上海周边界、待办分页与范围、样本幂等。组件覆盖空数据/错误重试、上海日期半开区间/闰日、渠道与搜索、取消旧请求、阶段409保留输入、人工Offer反馈不调用录用、AI事件重试同ID、Web审核目标版本、认证/路由权限。图表空态测试不创建示例图形；实际浏览器和生产构建另验真实渲染，不拿jsdom当布局证据。

真实HTTP结果：**PASS: S4 filters + Offer sent/accepted/replay + independent manual hire + history + tasks + RBAC**，保留虚构WEB_S4_2BCF6BD7；原全链路脚本仍为**PASS: web 5173 + proxy + API 8000 + create/result/schedule/review/dedupe/dashboard/async mock sync**。

浏览器实测1440/1024/390px，移动显式导航、表格内横滚、详情与设置/同步均可用；稳定后viewport1024/document1009、viewport390/document375（滚动条宽度）无页面横向溢出。初次即时resize截图有异步图表尺寸瞬态，最终在布局稳定后重截；本机截图位于忽略的.tools/s4-*.jpg，不属于Git交付文件。

390px实际登记DEMO_S4_05宋言接受Offer，申请仍保持Offer阶段；对“陈禾进入一面”核对DEMO_S4_02并确认，结果面板更新为一面；复验“陈禾进入二面”并驳回，未继续推进。模拟HR乙跨部门直开详情返回403且不展示陈禾资料；模拟负责人可读但没有更新按钮；最后恢复模拟管理员。生产构建在4173临时预览，实际3个canvas图表、数据库指标可见，控制台error=[]，之后关闭预览服务并恢复默认浏览器视口。

界面评审disposition：**ship**，remaining：**clear**。

| 原问题 | 最终结果 | 证据 |
|---|---|---|
| F1 审核信息层级 | resolved | 按意图显示必要字段，高级匹配默认折叠；390px阶段审核三个按钮首屏可见 |
| F2 来源渠道筛选 | resolved | 来源“演示样本”实际返回25条（24样本+1联调），值保留并传递后端；组件回归覆盖 |

构建由S3约2.38MB单主包改为路由/表格/图表/框架等独立加载；最终主分包535.46KB、框架262.35KB、图表引擎367.17KB、渲染器186.51KB。仍有535KB阈值警告，未调高阈值隐藏；不以单个分包缩小冒充总流量或性能达标。未做真实PostgreSQL、跨平台、生产认证、三方授权或所有辅助技术/浏览器验收；下一阶段S5。

以下为S3/S2/S1/S0历史记录，当前状态以上述S4为准。

## S3 实际交付（2026-11-12）

```text
阶段：S3
已完成：SmartSheetAdapter协议、持久Mock模拟表与remote_id映射；事务性投影快照；后台扫描/领取租约/过期恢复；指数退避/死信；管理员幂等重试；React同步统计/筛选/自动刷新/重试表单；只读MCP工具发现及腾讯失败关闭边界。
本阶段变更文件：见下方分组清单；Pydantic→OpenAPI 0.4.0（22个路径）→前端生成类型已同步。
数据库迁移：0003_s3；本机现有S2库升级完成，旧Mock ID保留并回填模拟存储；空库升降/重升、S0复制、S2既有映射升级、PostgreSQL离线DDL、Alembic check通过。
运行的命令：npm run check；npm run db:upgrade；npm run db:check；npm run smoke:http；npm run smoke:sync-failure；npm run integrations:tencent:discover；compileall；S3专项pytest；git diff --check。
测试结果：完整pytest124通过、0失败、0跳过；最终任务重试时间清理后17项专项再通过。Python/TS类型、Ruff/ESLint、契约、build、迁移检查、HTTP异步Mock链路和浏览器死信重试通过。
未完成/阻塞：腾讯Token缺失，发现命令BLOCKED_BY_CREDENTIALS/退出2；真实工具Schema、字段映射、测试表查询/新增/修改/复查及会员权限均未联调。腾讯适配器不能真实写入，不宣称S3真实集成已完成。
重要风险：仅单实例本机开发身份，不可生产使用；Mock重放幂等不能证明腾讯真实建行幂等；真实PostgreSQL/跨平台部署未实测；保留测试客户端弃用和前端大包警告。
下一阶段：S4（招聘看板和前端产品体验）；真实腾讯授权联调独立待凭证补齐。本轮未进入S4。
```

### 文件与工程边界

- backend/app/schemas/integration.py及schemas出口：统一ApplicationProjection、SyncJob/SyncRun/SyncRetry/SyncSummary和连接状态；同步前端类型与contracts/openapi.yaml。
- backend/app/db/models.py、db出口、alembic/versions/0003_s3_async_sync.py：provider、revision、累计/本轮尝试、领取token/租约和完成时间；sync_worker_leases及mock_sheet_records；既有Mock映射回填。
- backend/app/integrations/smartsheet/{base,mock,tencent,factory,discovery}.py：协议、独立事务的持久Mock、未验证即阻断的腾讯适配器、provider工厂、只读Streamable HTTP工具发现。
- backend/app/services/sync.py、jobs/sync_worker.py、main.py：领取→提交→事务外IO→独立确认；后台周期和唤醒，20秒IO上限、120秒领取、5/10/20/40秒退避、第5次失败dead。
- backend/app/services/common.py、core/security.py、api/v1/{sync,identity,dashboard}.py：业务快照包含稳定投影，provider固定在任务创建时；不可登录系统账号审计；管理员任务API；看板积压包含失败与死信。
- frontend/src/pages/SyncCenter.tsx、features/sync/presentation.ts、services/api.ts：实际统计、状态分页、5秒刷新、错误与下次重试、审核说明表单；请求失败保留输入，任务revision冲突提示刷新；组件不持有外部Token。
- backend/scripts/integrations/tencent_discover.py、scripts/smoke/{http,sync_failure}.py、scripts/migrations/upgrade_s0.py、package.json：用途分目录，故障演示可复现，旧S0复制兼容新模拟存储。
- backend/tests/integration/test_s3.py、unit/test_mcp_discovery.py、migrations/test_migrations.py及原冒烟适配；README、环境示例、状态表、docs/03/04/05/08/09/13/14与阶段计划同步。

### 一致性、幂等与权限

数据库业务记录是事实来源，外部失败不回滚本地申请。业务写入与audit/outbox同事务；任务管理只更新任务元数据和审计，防止递归生成新outbox。同步IO时没有业务Session/已借出数据库连接，测试通过实际连接池计数确认。

Mock以本地申请ID形成稳定建行键，以业务version条件更新；处理后保存RemoteLink，后续更新复用同一ID。独立模拟写入成功但本地确认丢失，重试恢复同一行；旧version被更新版本覆盖后superseded，不回退远端；远端记录或已成功映射丢失直接dead，提示人工恢复而非盲目新建。实体provider一经持久化不会跟随环境切换，旧Mock任务不会意外发往腾讯。

单实例任务租约防止重复批处理，处理token对确认进行数据库条件更新，过期工作者不能覆盖新领取结果。周期错误只记录安全代码，不回显上游异常。永久权限/凭证/Schema错误直接dead；临时故障有限退避；管理员重试须权限、If-Match任务revision、幂等键和非空原因，保留累计尝试与审核记录。业务version不作为重试状态版本使用。终态及处理中不残留自动重试时间。

只有applications调用SmartSheet，其它outbox以internal_only归档；Mock标签不冒充腾讯成功。删除以deleted投影软删除事实，不执行真实远端硬删除。默认开发单API进程使用asyncio周期循环，无新增调度/队列依赖；租约不等于生产多节点验收。

### 实际验证证据

完整`npm run check`结果：**124 passed, 1 warning in 19.13s**，Pyright **0 errors**、TS/Ruff/ESLint/契约通过；Vite **built in 17.40s**，JS **2,385.37KB，gzip781.00KB**，保留大包警告。最后补充dead/processing不残留next_retry_at清理后，S3专项 **17 passed, 1 warning in 3.99s**，Ruff和diff检查通过。未删除失败用例或关闭检查。

新增回归覆盖稳定映射、持久Mock、本地成功远端超时、退避到期/5次死信、管理员重试/越权/冲突/幂等、写后超时恢复、映射/远端丢失、租约竞争/过期/旧token确认、实际连接池释放、旧版本防回退/软删除、provider固定、未知/历史错误脱敏、后台lifespan自动处理、非法投影和领取预算。MCP使用明确合成工具的HTTP响应测试JSON/SSE、初始化/分页、鉴权/会员错误和重定向阻断，没有把合成Schema冒充腾讯实际Schema。

本机现有S2库实际升到0003_s3，`npm run db:check`为**No new upgrade operations detected**。HTTP实际结果：**PASS: web 5173 + proxy + API 8000 + create/result/schedule/review/dedupe/dashboard/async mock sync**，后台自动处理、5个申请版本复用同一模拟ID；样本只保留本地虚构数据。原S0库/既有备份/.env未覆盖，不提交Git。

浏览器在同步中心查看真实统计，筛选死信任务`bf1af783-06fd-496c-ab4b-cd556f0338dd`（虚构申请A00EB2A34F328），空白说明被拦截；填写虚构恢复说明后确认重试，死信数从1变0。该申请已有2~5的新版本成功，旧version1按规则转superseded并复用同一MOCK ID，没有覆盖新状态。复验旧错误提示已清理。窄屏390px下检查了表单外的统计/筛选和横向表格；这不等于S4完整多页面响应式验收。

腾讯发现命令实际返回**BLOCKED_BY_CREDENTIALS**、退出2。只读发现器依据官方指南和MCP协议，提供initialize/tools/list通道；腾讯业务适配器保持失败关闭，无臆造字段或HTTP REST API。没有真实查询/新增/更新、无真实DeepSeek/MCP/企微验证；需授权的后续步骤见docs/08。

以下为S2/S1/S0历史记录，当前状态以上述S3为准。

## 工程化与 S2 实际交付（2026-11-12）

```text
阶段：S2
已完成：前后端与脚本目录工程化；Parser协议/Mock/DeepSeek适配器；强类型提取；匹配与确认/修正/驳回；事件幂等/租约恢复；Web审核与结果联动；事务审计/outbox。
本阶段变更文件：backend/app的api/core/db/schemas/services/integrations分层；frontend/src的app/pages/components/features/services/styles/types分层；脚本分类目录、测试分层、契约及文档。
数据库迁移：0002_s2；新增接入租约字段，允许无原计划的面试结果记录；实际S1库升级成功，Alembic check无漂移，空库/旧库/回滚与离线PostgreSQL DDL回归通过。
运行的命令：npm run check；npm run typecheck；python -m pytest -q；npm run contracts:check；npm run db:upgrade/db:check；npm run smoke:http；compileall；哈希锁离线安装核查。
测试结果：最终pytest96通过、0失败、0跳过；Python/TS类型、Ruff/ESLint、契约和构建通过；HTTP及浏览器Mock审核验证通过。
未完成/阻塞：真实DeepSeek为blocked_by_credentials，未使用真实Key联调；完整多尺寸产品验收在S4；腾讯文档/企微仍Mock，不属于本阶段真实接入。
重要风险：仍为本机开发身份，不可生产使用；复杂日期与未知语义需人工确认；存在无计划结果记录时迁移降级会拒绝；保留1条上游测试客户端弃用警告与前端包体积警告。
下一阶段：S3（异步外部同步与腾讯文档MCP）。本轮未进入S3。
```

目录整理先独立回归并保存`7f9e2cd`提交：46项S1测试、类型、lint、契约和构建全部通过。原starter前后端提升至根backend/frontend，.env/数据库/.venv随目录保留；npm workspace与锁文件、运行脚本、导入路径、Alembic、文档同步。根目录命令保持npm run dev:api/dev:web/check等，不需记内部脚本路径。工程规则见docs/14。

后端main只装配应用，路由按资源、服务按事务/招聘/面试/接入/确认/提议应用拆分；schemas按领域组织并统一导出。前端App只组织应用壳与路由，页面、共享组件、审核功能、Axios客户端分别独立。Python操作脚本按contracts/migrations/smoke归类，根JS脚本按workspace/contracts归类；测试helpers不再从测试模块互相导入。

S2解析：Mock/DeepSeek实现同一异步Parser协议。DeepSeek请求JSON Output、JSON Schema和示例，模型从环境读取，超时/空白/截断/非法字段最多重试一次；缺凭证、上游失败、引用不存在的标识/时点转审核。仅允许显式hybrid+deepseek使用官方HTTPS地址。输入脱敏，保存哈希与不超过300字的脱敏摘要，不保存独立原文或模型原始响应；用量缺失记unknown。官方依据见docs/07，未运行真实DeepSeek或声称95%字段准确率。

接入先持久化认领并提交，Parser阶段不持有DB事务，之后新事务重新核验用户/匹配/状态/版本。并发同事件不重复创建，处理中返回parsing，120秒租约可通过重放原消息恢复。多动作任意一步无法执行时整段业务回滚，单独生成待确认。姓名即使唯一也不能自动更新，同名/多岗必须显式选择；模糊日期/钟点、冲突结果和未知意图转人工。失败面试只记录结果，不自动淘汰候选人。

确认使用If-Match+Idempotency-Key，记录审核人、时间、理由、选中申请与修正提取内容；重复同请求复用结果，不同键处理已完成任务409；申请版本过期409并保留pending。审核业务、确认状态、接入结果、审计/outbox同事务。S1已有的人工终态逆转任务可继续确认；AI提议的录用/淘汰不能通过自动执行或AI审核捷径写入。

96项测试覆盖原46项意图，并增加固定Mock样本、明确/模糊时间及秒/时区、DeepSeek JSON/枚举/额外字段/空白/截断/超时/401/503、脱敏/注入、缺凭证、实际数据库连接释放断言、三条Mock业务、同名/唯一姓名确认、修正/驳回、过期版本/越权/一次执行、事件并发、租约恢复、复合操作回滚及面试结果独立。审核修正内容的持久化也已回归验证。多个申请编号/多个轮次冲突先经过确定性拦截，即使自定义Parser想给出可执行提议也不会调用或写业务。

实际最终后端结果为**96 passed, 1 warning in 12.33s**；此前聚合npm run check也已通过94项及前后端检查，增加两项确定性冲突回归后再次通过完整后端与类型/lint检查。前端最后构建**built in 13.01s**（主JS2,342.86KB、gzip767.76KB）。最终复核compileall、OpenAPI/TS漂移检查及Alembic check均通过；哈希锁离线检查38个包。未关闭警告或删除失败用例。

HTTP实际结果：**PASS: web 5173 + proxy + API 8000 + create/result/schedule/review/dedupe/dashboard/mock sync**，包括一面结果、二面安排、审核驳回及重复审核请求复用。运行会留下明确命名的虚构样本，所有同步均为MOCK。

浏览器实际打开AI录入页，创建`AA04DED41A1E3`（虚构UI审核甲），姓名消息进入审核，人工选择/核对并确认推进筛选、再推进一面；待确认列表清空，结果面板显示“人工审核已确认执行”和实际申请阶段。发现原结果面板未联动时已修复并复验。没有把浏览器操作等同于完整1440/1024/390多尺寸验收。

实际S1库已运行0002_s2升级；启动按Alembic head校验，无须新增迁移时手改版本常量。原S0库及先前备份保留，数据与.env均不提交。Linux/macOS启动、真实PostgreSQL连接和所有真实外部写入仍未执行；PostgreSQL仅离线DDL编译验证。

以下为S1/S0历史记录，当前状态以上述S2为准。

## S1 实际交付（2026-11-12）

```text
阶段：S1
已完成：十二类领域模型+幂等记录表；UUID/UTC/SQLite外键；Alembic；业务CRUD/筛选/分页/软删除；开发RBAC；状态机与版本冲突；事务审计/outbox；基础前端身份及阶段操作。
本阶段变更文件：见下方S1清单，契约和生成前端类型已同步。
数据库迁移：0001_s1；空库upgrade/check/downgrade/再upgrade通过；旧S0库已复制为recruitflow_s1.db并保留原库和备份；PostgreSQL迁移DDL离线编译通过。
运行的命令：npm run check；npm run db:check；npm run smoke:http；python -m compileall -q app alembic；-m scripts.migrations.upgrade_s0。
测试结果：46通过、0失败、0跳过；Pyright/TypeScript、Ruff/ESLint、契约漂移检查、Vite build及真实本机HTTP冒烟通过。
未完成/阻塞：无S1凭证阻塞；完整AI确认处理属S2；生产身份、真实PostgreSQL/外部系统尚未联调；成品界面与多尺寸验收属S4。
重要风险：仅本机模拟用户，禁止生产使用；旧记录归属模拟管理员；保留1条Starlette测试客户端兼容弃用警告；前端主包约2.30MB待S4拆包。
下一阶段：S2（Parser、DeepSeek配置/校验、匹配与人工确认闭环）。本轮未进入S2。
```

Git：已初始化本地main分支，S0基线提交`b137928`；本轮完成S1后保存独立提交。没有配置或推送远程。`.env`、数据库、备份、依赖/工具目录均已通过git check-ignore验证。

统一结构：Candidate与Position独立，ApplicationCreate支持ID引用/便捷名称互斥分支，一人可多岗位；读投影保持application_code/candidate_name/position_title，新增owner/source/outcome/custom_fields。扩展字段当前按白名单接受organization.referral_tag字符串，禁止任意JSON或权限字段注入。

权限：服务端固定虚构目录解析X-Dev-User；HR本人、经理本部门只读、管理员全局。未知/停用用户401；角色自报不提升权限；生产环境与live模式拒绝启动。联系方式没有采集或返回入口。

写入：Idempotency-Key按用户/操作隔离并保存请求哈希与响应；修改/删除要求If-Match；数据库条件更新使两次并发写入一成功一409。业务修改与审计/outbox同事务；注入审计或outbox失败均全回滚。候选人/岗位改名与面试修改递增相关申请投影版本。终态逆转只创建确认任务，原申请版本/状态保持，执行审核留S2。

迁移：启动不再create_all。迁移`0001_s1`包含全部目标表、约束和索引；空库测试通过Alembic check。S0升级命令只读原库、创建备份和新目标库；ID/关联/事件/审计/模拟映射保留，过期未同步历史版本标记superseded。实际原库recruitflow.db保留，备份recruitflow.db.backup-958f00df.db保留，当前本地.env指向recruitflow_s1.db。失败时不会覆盖原库；目标已有文件则拒绝。旧无source前缀事件按manual迁移，原数据没有实际负责人信息，统一归属模拟管理员。

本轮46项测试包含原S0全部测试意图（随严格状态机与接入记录更新断言），另验证一人多岗位、同名不合并、越权/经理范围、停用/关闭开发身份、幂等重放、并发409、确认持久化、关联删除限制、修改投影、扩展白名单、面试独立结果、时区/时间边界、SQLite外键、事务失败、空库/旧库迁移以及PostgreSQL离线DDL。期间发现新建面试首次响应未转UTC，已通过刷新持久化对象修复，回归通过。

实际结果：`npm run check`退出0；pytest **46 passed, 1 warning in 7.53s**；Vite **built in 15.39s**；`npm run db:check`为**No new upgrade operations detected**；`npm run smoke:http`为**PASS: web 5173 + Vite proxy + API 8000 + create/update/dedupe/dashboard/mock sync**。生成路径19个；主JS2,298KB、gzip754KB。未执行真实PostgreSQL连接、Linux/macOS启动或任何真实第三方写入，不将DDL编译视为真实数据库联调。

S1文件：`app/db.py`、`domain.py`、`schemas.py`、`security.py`、`errors.py`、`services.py`、`main.py`；`alembic.ini`及`alembic/`；`-m scripts.migrations.upgrade_s0`和HTTP冒烟；`tests/conftest.py`、保留的`test_smoke.py`、新增`test_s1.py`/`test_migrations.py`/`test_concurrency.py`；依赖源/哈希锁和.env示例；前端API/App/CSS/生成类型；根package/pyright配置；OpenAPI和README、docs/04/05/09/13、S1计划及状态报告。

以下为S0及补验历史记录，当前状态以上述S1交付为准。

## S0 补验（2026-11-12）

本轮已实际通过内置浏览器打开5173页面，验证看板真实数据、创建`AS0UI20261112`虚构申请、AI输入该编号一面通过、结果进入二面、执行模拟同步。两个申请版本复用`MOCK-18695a03`映射，页面明确标注模拟。此前浏览器工具阻塞本次已解除，S0基础浏览器验收已补齐；完整多尺寸产品验收仍属于S4。已初始化本地main分支，保存S0基线后进入S1。下文保留上一轮原始执行记录。

日期：2026-11-12（Asia/Shanghai）。本轮按 `CODEX_MASTER_PROMPT.md` 从S0开始，只实施一个阶段。修改前已阅读README、AGENTS、docs/01~12、主提示、阶段任务、原始契约及Starter。

```text
阶段：S0
已完成：工程基线代码及自动验收；统一Pydantic/OpenAPI/TS契约、工作区检查、Mock主链路、实际HTTP启动验证。
本阶段变更文件：见下方清单。
数据库迁移：无Alembic迁移；保留create_all，仅补充audit_logs表；未删除旧库。正式迁移属S1。
运行的命令：npm run contracts:generate；npm run check；npm run smoke:http；python -m compileall -q app；锁文件哈希安装核查。
测试结果：pytest通过20，失败0，跳过0；Python/TS类型检查、lint、契约检查、前端build均通过；HTTP冒烟通过。
未完成/阻塞：浏览器可视和点击交互验收未完成；完整CRUD/RBAC/Alembic等尚未进入S1；真实第三方未接入。
重要风险：S0不是生产系统；仅固定本机开发身份；旧演示事件键需要S1迁移评估；前端产物较大；跨平台尚未实机验证。
下一阶段：补齐S0浏览器可视验收，再实施S1数据/迁移/身份/状态机。S1~S7未标记完成。
```

## 统一结构与字段扩展

- 唯一契约源：`backend/app/schemas/`；通过FastAPI导出真实路由的OpenAPI，再生成TypeScript，前端不再手写一份Application/SyncJob类型。
- 核心约定：snake_case、字符串API ID、独立申请编号、UTC输出、正整数version、统一分页/请求编号/安全错误响应、请求拒绝未知字段。
- 新增字段流程：先确定实体归属，再修改schema与必要的数据库迁移，再生成类型；业务可检索字段保持列和强类型，自定义字段使用未来S1受控命名空间JSON方案。S0不接受任意扩展字典。
- `docs/13-统一数据契约与扩展规范.md`先定义十二类领域实体的边界和S0验收计划，再实施代码。S0不提前生成未实现实体的假接口。

## 已验证行为

20项pytest覆盖：

- 无凭证Mock健康检查、申请创建、规则更新、version递增、请求编号。
- 相同事件去重，source间独立去重；自动生成的申请编号可再次用于更新。
- 同名/模糊时间/复合消息/恶意提示文本不自动写入；终态及阶段逆转需确认。
- 创建幂等键复用、相同键不同内容冲突、重复编号不残留候选人/事件/审计/outbox。
- 业务/审计/outbox事务一致性；注入审计异常时全回滚；500错误不返回异常原文。
- 分页、边界校验、字符串ID、UTC时间、空数据库真实统计。
- 本机写入门槛与非development/非mock启动拒绝。此项不等同于完整角色权限测试。
- 模拟同步复用同一个MOCK远端ID，重复执行无新增任务。
- 运行OpenAPI与仓库契约一致，未实现接口不出现在运行契约。

实际运行结果：

```text
npm run check
  contracts:check   OpenAPI and TypeScript contracts match the backend
  lint             Ruff + ESLint passed
  typecheck        Pyright: 0 errors; TypeScript passed
  pytest           20 passed, 1 warning in 5.26s
  build            2123 modules transformed; built in 14.88s

npm run smoke:http
  PASS: web 5173 + Vite proxy + API 8000 + create/update/dedupe/dashboard/mock sync

python -m compileall -q app
  exit 0

uv pip install --offline --require-hashes -r backend/requirements.lock ...
  Checked 32 packages; exit 0

npm install（锁文件更新后审计）
  found 0 vulnerabilities
```

环境：Windows、Python3.12.16、Node24.14.0、npm11.9.0。系统原有Python3.10未修改；本轮在`.tools/`准备Python并创建`backend/.venv`。Python锁文件由universal解析生成，具有平台标记与哈希，但Linux/macOS、Python3.11和PostgreSQL未做实机验证。

沙箱曾阻断网络安装、临时目录SQLite、开发服务子进程与端口访问；依赖和最终全量检查通过授权常规进程执行。测试临时数据库改放工作区`.pytest_cache`，不会覆盖演示数据库。初始热重载进程在本运行环境退出，默认启动改为单进程后HTTP验证通过。

## 浏览器验收阻塞

内置浏览器打开`http://127.0.0.1:5173`返回`net::ERR_CONNECTION_TIMED_OUT`。随后尝试选择本机Chrome时，Computer Use工具因无法可靠识别Windows当前浏览器URL而停止本轮操作。已停止UI操作，未绕过工具安全检查。

因此**没有完成浏览器渲染/点击交互、移动端布局和截图验收**。HTTP返回HTML与自动构建通过不能证明浏览器交互已通过。S0自动验收已通过，完整阶段验收仍保留这一缺口。

可在本机手动打开5173，依README依次验证新增、AI更新、工作台刷新、模拟同步。当前HTTP冒烟已留下一条“虚构冒烟甲”的本地演示记录；未写任何真实外部系统。

## 变更文件清单

| 范围 | 文件 |
|---|---|
| 根工程 | `.gitignore`, `package.json`, `package-lock.json`, `pyrightconfig.json`, `scripts/python.mjs`, `scripts/check-contracts.mjs` |
| 后端 | `backend/app/db.py`, `app/main.py`, `app/schemas/`, `-m scripts.contracts.export`, `scripts/smoke_http.py`, `tests/conftest.py`, `tests/test_smoke.py`, `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`, `requirements.lock`, `.env.example`, `README.md` |
| 前端 | `frontend/package.json`, `eslint.config.js`, `vite.config.ts`, `src/api.ts`, `src/App.tsx`, `src/types/api.generated.ts`, `README.md`, `DEPENDENCY_NOTE.md` |
| 契约/文档 | `contracts/openapi.yaml`, 根`README.md`, `IMPLEMENTATION_STATUS.md`, `docs/04`, `docs/05`, `docs/09`, `docs/11`, `docs/13`, 本报告 |

没有Git元数据，未创建commit。`.env`、数据库、日志、工具和虚拟环境均被忽略；不得提交真实个人资料。

## 未完成与后续验收

- S0浏览器可视验收待补，阶段不能宣称全部验收通过。
- S1：独立岗位/用户/面试等全部模型、UUID迁移、SQLite外键与PostgreSQL、Alembic空库升级和旧Starter升级、完整CRUD/筛选/软删除、RBAC数据范围、If-Match并发冲突及完整状态机。
- S2：正式Parser协议、独立面试结果、待确认持久化/人工确认、失败事件幂等、DeepSeek JSON验证与脱敏。当前Mock仍是有限演示规则，不能视为招聘决策系统。
- S3：正式adapter、任务重试/退避/死信、版本快照和真实腾讯MCP动态tools/list。当前Mock无网络调用，不代表腾讯文档成功。
- S4：完整页面/日期筛选/组件测试/响应式、前端按路由及图表拆包。目前主JS约2.30MB、gzip753KB，构建有chunk体积警告，未调大警告阈值掩盖问题。
- S5~S7：企微验签/AES/通知、生产身份/部署/运维、完整验收。真实DeepSeek、腾讯文档及企微均为未接入/未来凭证阻塞，未做真实授权联调。
- pytest当前存在1条Starlette对httpx兼容测试客户端的弃用警告，未关闭或过滤；测试全部通过。开发依赖的minimatch安全覆盖理由见前端DEPENDENCY_NOTE，上游修复后应移除覆盖。

## 演示命令

两个终端在仓库根目录分别运行`npm run dev:api`和`npm run dev:web`。检查`http://127.0.0.1:8000/api/v1/health`，打开`http://127.0.0.1:5173`。第三个终端可运行`npm run smoke:http`（会新增1条虚构记录并处理待模拟同步任务）。安装、Windows/Unix命令与字段扩展流程详见README。
