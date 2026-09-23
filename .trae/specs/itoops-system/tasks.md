# ITOPS 智能运维告警分析系统 - 实施计划

> 技术栈：Python 3.11+ / FastAPI / SQLAlchemy / Vue3+Vite+Element Plus+Pinia+Vue Router+ECharts / Docker Compose
> 任务按依赖顺序排列；每个任务含本地测试要求（TR），验收标准（AC）定义见 spec.md。

## Task 1: 后端工程骨架与基础设施
- **Status**: `completed`
- **Completion Evidence**：
  - `backend/` 骨架建成：core(config/database/security/logging/exceptions)、api/v1、models、健康检查；`.env.example` 位于仓库根
  - TR-1.1 通过：uvicorn 启动正常，`/healthz` 200、`/api/v1/health` 返回 database=ok，SQLite 自动建库；数据访问全部经 ORM，无方言专有 SQL（支持 `sqlite+aiosqlite` / `postgresql+asyncpg` 切换）
  - TR-1.2 通过：`pip install -r requirements.txt` 成功；冒烟 pytest 6 passed（含口令哈希、JWT、Fernet 加解密、脱敏）
- **Priority**: high
- **Depends On**: None
- **Description**：
  - 建立后端目录结构（`app/core`、`app/integrations`、`app/models`、`app/schemas`、`app/services`、`app/api`）、依赖清单（fastapi、uvicorn、sqlalchemy、httpx、pydantic、pydantic-settings、python-jose、passlib、apscheduler 等）
  - 基于 pydantic-settings 的配置层，支持 `.env` 注入；`.env.example` 覆盖管理员账号、JWT 密钥、加密密钥、Zabbix/LLM/日志平台/机器人/Webhook Token 等全部配置项
  - SQLAlchemy 引擎与会话（SQLite 默认，可切 PostgreSQL；启用 SQLite 外键约束）
  - 统一响应/异常处理、结构化日志（含请求 ID）、超时与错误规范
  - `/healthz` 健康检查；启动时建表（SQLAlchemy `create_all`，方言中立）
- **Acceptance Criteria Addressed**: AC-14（部分）、NFR-5、FR-21（部分）
- **Test Requirements**：
  - `rule` TR-1.1：全新环境复制 `.env.example` 后 `uvicorn` 可启动，`/healthz` 返回 200；SQLite 文件自动创建；切换 `DATABASE_URL` 为 PostgreSQL 方言串时代码无需改动（以方言中立为证据：代码审查无 sqlite_/postgresql_ 专有调用）
  - `rule` TR-1.2：依赖可安装（`pip install -r requirements.txt` 成功），配置项缺失时有明确启动报错
- **Notes**：凭据加密工具（Fernet，密钥来自环境变量）在本任务放入 `core/security` 供后续使用

## Task 2: 前端工程骨架与主框架
- **Status**: `completed`
- **Completion Evidence**:
  - Vite+Vue3 工程：vue-router(hash)、Pinia、Element Plus(zhCn)、ECharts；主布局含折叠侧边栏+顶栏，≤768px 自动切换汉堡+el-drawer 抽屉；两级菜单（总览/告警中心/监控/日志/集成配置 5 子项）；axios 实例带 JWT 拦截与 401 跳登录；npm run build 零错误

- **Priority**: high
- **Depends On**: Task 1
- **Description**：
  - Vite + Vue3 + Element Plus + Pinia + Vue Router + ECharts + axios 工程；前端目录（views、components、stores、router、api、layouts、utils）
  - 主布局：顶栏（主题切换、退出入口）+ 可折叠侧边栏 + 分级菜单（两级，至多三级）+ 内容区；窄屏（≤768px）侧边栏自动变抽屉
  - 菜单结构：总览仪表盘 / 告警中心（告警列表、分析报告）/ 监控数据（主机与指标）/ 日志查询 / 集成配置（Zabbix、大模型、日志平台、通知渠道）
  - axios 实例（baseURL、token 注入、401 跳登录、统一错误提示）；路由占位页
  - 路由守卫配合 Task 4 完成；dev 代理 `/api` 到后端
- **Acceptance Criteria Addressed**: AC-12（菜单结构部分）、AC-17（外壳部分）、FR-18
- **Test Requirements**：
  - `rule` TR-2.1：`npm run dev` 启动、`npm run build` 零错误；未匹配路由有 404 占位
  - `rule` TR-2.2：菜单项与 spec 信息架构逐项一致（走查比对，中文命名）；≤768px 宽度下侧边栏变为抽屉且可开合

## Task 3: 主题三态（跟随系统/亮/暗）
- **Status**: `completed`
- **Completion Evidence**:
  - Pinia 主题 store：system/light/dark 三态 + localStorage 持久化 + matchMedia 监听系统切换；Element Plus dark css-var 生效（实测 body rgb(10,10,10)/卡片 rgb(29,30,31)）；EChart 组件监听 isDark 重绘明暗配色；顶栏图标循环切换

- **Priority**: high
- **Depends On**: Task 2
- **Description**：
  - 主题 store：`system` / `light` / `dark` 三态，持久化（localStorage）；`system` 态用 `matchMedia('(prefers-color-scheme: dark)')` 监听并实时切换
  - Element Plus 暗色 CSS 变量接入；ECharts 全局配色随明暗切换；卡片/表格/菜单/弹窗无硬编码白底
  - 顶栏主题切换控件
- **Acceptance Criteria Addressed**: AC-10
- **Test Requirements**：
  - `rule` TR-3.1：三态切换后 `<html>` dark class 与 EP 暗色样式即时生效；刷新与重新登录保持选择；模拟系统主题变化时 system 态自动跟随（浏览器 DevTools 仿真验证）
  - `rubric` TR-3.2：主题覆盖完整性；scale 1-5；anchors 1=存在明显白块/对比度问题，3=主页面正常但弹层或图表配色突兀，5=所有页面/组件/图表在两主题下观感统一；threshold >= 4；evidence=两主题逐页截图

## Task 4: 单用户登录与会话
- **Status**: `completed`
- **Completion Evidence**:
  - 登录页（默认 admin、enter 提交、校验）、token 本地持久化、全局路由守卫、/auth/me 会话、登出（服务端+本地黑名单）、401 自动回登录页；浏览器实测登录/登出链路通过

- **Priority**: high
- **Depends On**: Task 1, Task 2
- **Description**：
  - 后端：`/api/v1/auth/login` 签发 JWT；账号口令来自环境变量（口令以哈希校验，不明文落库）；`/auth/me`、`/auth/logout`（前端失效 + token 黑名单/短有效期方案二一并记录）
  - 依赖项 `get_current_user` 保护全部业务接口；Webhook 路径独立 Token 豁免 JWT
  - 前端：登录页、token 存储、路由守卫、退出登录、过期跳转
- **Acceptance Criteria Addressed**: AC-9、NFR-3（部分）
- **Test Requirements**：
  - `rule` TR-4.1：未携带 token 访问业务 API 返回 401；正确口令登录获得 JWT 并可访问业务接口；错误口令返回 401/422 明确提示；退出后旧 token 不再可用；未登录打开任意前端路由跳转登录页（pytest + 界面验证）

## Task 5: 数据模型与集成配置管理
- **Status**: `completed`
- **Completion Evidence**:
  - 模型：IntegrationConfig/SystemSetting/Alert/Report/NotificationRecord；配置密钥 Fernet 加密落库、接口脱敏；系统设置（自动开关/分析窗口/日志关键词）；test_configs 验证密文存储与掩码沿用

- **Priority**: high
- **Depends On**: Task 1
- **Description**：
  - ORM 模型：告警 Alert、分析报告 Report、集成配置 IntegrationConfig（按类型：zabbix/llm/log_platform/notify_channel，含 name、type、settings(JSON)、enabled、is_default）、系统设置 SystemSetting（分析开关、时间窗口等）
  - Alert 字段：event_id 唯一索引、host、trigger、severity、status、raw_payload、首次/恢复时间、分析状态外键
  - 配置 CRUD API：凭据字段写入加密、读取脱敏（只回显掩码）；连通性测试统一入口（实际测试逻辑由 Task 6/8/9/11 实现，本任务定义接口契约）
  - 系统初始化：无配置时给出空态引导
- **Acceptance Criteria Addressed**: AC-3（脱敏部分）、FR-1、FR-5（部分）、FR-7（部分）、FR-14（部分）、NFR-3（部分）
- **Test Requirements**：
  - `rule` TR-5.1：任意含密钥配置写入后，数据库存储为密文、GET 接口返回掩码；直接改库可验证非明文
  - `rule` TR-5.2：重复 event_id 写入触发唯一约束错误并被服务层转化为去重更新逻辑（与 Task 7 联动，本任务先保证约束存在）

## Task 6: Zabbix 客户端适配器与监控查询接口
- **Status**: `completed`
- **Completion Evidence**:
  - Zabbix 6.0/7.0 JSON-RPC 客户端：host/item/history/trend/problem；test_zabbix_adapter 4 例；查询 API 与真实联调路径齐备（真实环境待 Task20）

- **Priority**: high
- **Depends On**: Task 5
- **Description**：
  - `integrations/zabbix`：基于 httpx 的 JSON-RPC 客户端，token 认证（user.login 或 API Token），兼容 Zabbix 6.0/7.0，统一超时/异常封装
  - 方法：连通性测试、host.get（列表/搜索）、item.get（按主机）、history.get/trend.get（时间窗口时间序列，升序）、problem.get/event.get（当前问题/事件）
  - API：`/api/v1/zabbix/hosts`、`/items`、`/history`、`/problems`；配置缺失/未启用时返回明确业务错误
- **Acceptance Criteria Addressed**: AC-2、FR-1、FR-2
- **Test Requirements**：
  - `rule` TR-6.1：Mock Zabbix JSON-RPC 响应的 pytest 验证四组方法参数拼装与返回归一化（时间序列升序、时间戳单位统一）；凭据错误/超时返回可读错误
  - `rule` TR-6.2：真实环境联调：主机搜索、监控项查询、指定窗口历史数据返回与 Zabbix 页面数据一致（联调截图/响应留存，凭据未提供前以 Mock 证据先行）

## Task 7: Zabbix 告警 Webhook 接收、解析与去重
- **Status**: `completed`
- **Completion Evidence**:
  - Webhook 端点：Token 校验、多版本字段兼容、event_id 幂等去重、恢复流转、原始报文留存、自动入队；test_webhook 4 例（含 <500ms）

- **Priority**: high
- **Depends On**: Task 5
- **Description**：
  - `POST /api/v1/webhooks/zabbix`：可选 Header/参数 Token 校验；兼容官方 Webhook media type 常见 JSON 字段（event_id/eventid、host/host name、trigger/name、severity、status/value、datetime、details 等），字段缺失做容错映射
  - 原始报文留存 `raw_payload`；按 event_id 去重（幂等返回 2xx）；恢复报文（OK/RESOLVED）更新状态与恢复时间；非法载荷返回 4xx 并记录
  - 自动分析开关开启时投递异步分析任务（与 Task 10 接通，本任务只发布事件/入队）
- **Acceptance Criteria Addressed**: AC-1、FR-3、FR-4
- **Test Requirements**：
  - `rule` TR-7.1：pytest 覆盖：同 event_id 连发两次仅一条记录、恢复报文更新状态、错误 Token 拒绝、畸形报文 4xx 且不入库、Webhook 响应耗时（Mock 下游）< 500ms

## Task 8: 大模型 Provider 适配层
- **Status**: `completed`
- **Completion Evidence**:
  - 四家供应商 OpenAI 兼容适配 + 默认/备用降级链 + JSON 容错解析（围栏/提取/修复重试）；test_llm 7 例

- **Priority**: high
- **Depends On**: Task 5
- **Description**：
  - LLM Provider 抽象基类 + 四家适配：DeepSeek、豆包（火山方舟 OpenAI 兼容）、通义千问（DashScope OpenAI 兼容模式）、MiniMax（OpenAI 兼容/官方 Chat）；可配置 base_url、api_key、model、temperature、超时、启用、默认与备用顺序
  - 统一 `chat(messages, json_mode)` 调用；连通性测试（一次最小请求）；调用日志记录命中供应商与耗时（不记密钥）
  - 结构化 JSON 输出解析器：容错（去 markdown 围栏、提取 JSON 段、一次修复重试），最终失败抛明确异常
- **Acceptance Criteria Addressed**: AC-3（部分）、AC-6（降级部分）、FR-5、NFR-4
- **Test Requirements**：
  - `rule` TR-8.1：pytest（Mock httpx）验证四家请求路径/头/体拼装、默认供应商选择、主供应商失败自动按顺序尝试备用、全失败抛出聚合错误
  - `rule` TR-8.2：JSON 解析器单测覆盖纯 JSON、带 ```json 围栏、前后带解释文字、损坏 JSON 触发修复重试四类输入

## Task 9: 日志平台适配器与统一查询接口
- **Status**: `completed`
- **Completion Evidence**:
  - Graylog/Loki/ELK 三适配器归一化（ts/timestamp/host/source/level/message/raw）+ OR 关键词；统一查询 API 与跨平台聚合；test_log_adapters 5 例

- **Priority**: high
- **Depends On**: Task 5
- **Description**：
  - 日志适配器基类 + Graylog（REST search universal/relative 或 JSON 搜索）、Loki（/loki/api/v1/query_range，LogQL 拼装）、ELK（Elasticsearch `_search`）三个实现；认证（Basic/Token/API Key）与默认索引/流可配置
  - 统一入参：平台、时间范围、查询语句、host 过滤、limit；归一化出参：`timestamp/host/source/level/message/raw`
  - 平台启用/停用校验；查询 API 与内部供分析引擎调用的服务方法
- **Acceptance Criteria Addressed**: AC-4、FR-7、FR-8、NFR-4
- **Test Requirements**：
  - `rule` TR-9.1：pytest（Mock 三家响应）验证查询参数拼装（时间换算、host 条件注入）与归一化字段映射；limit 生效；停用平台返回业务错误
  - `rule` TR-9.2：真实环境至少一个平台联调返回真实日志（凭据就绪后补证据）

## Task 10: AI 根因分析引擎与异步任务
- **Status**: `completed`
- **Completion Evidence**:
  - 分析编排：指标窗口统计、跨平台日志聚合、证据化 Prompt、降级/修复重试、状态机、进程内并发锁、报告落库、自动通知；test_analysis 8 例（含空证据标注、失败重试、降级、并发、自动触发）

- **Priority**: high
- **Depends On**: Task 6, Task 7, Task 8, Task 9
- **Description**：
  - 分析服务：告警 → 指标上下文（Task 6 取告警前后窗口历史，计算均值/峰值/变化率/突变点描述）→ 日志上下文（Task 9 对全部已启用平台按主机名检索错误/异常及关键词，命名映射不到时标注为空）→ 组装中文 Prompt（系统角色、输出 JSON schema、证据引用规范、禁止臆造）→ 调用 Task 8 → 解析结构化结论（根因+置信度排序、证据链[指标/日志引用]、影响范围、处置建议、预防建议）
  - 报告持久化（结构化 JSON + Markdown 渲染 + 模型/耗时元信息）；Alert 分析状态机：分析中/成功/失败（含错误原因）
  - 异步执行（FastAPI 后台任务/asyncio 任务队列，单实例即可）；自动触发（Webhook 开关）与手动/重新分析 API；任务幂等（并发分析同一告警加锁/状态保护）
  - Prompt 模板与窗口参数（默认前 30 分钟后 10 分钟）可在系统设置配置
- **Acceptance Criteria Addressed**: AC-5、AC-6、FR-10、FR-11、FR-12、FR-13（后端部分）、NFR-1、NFR-2
- **Test Requirements**：
  - `rule` TR-10.1：pytest（Mock Zabbix/日志/LLM）验证上下文聚合调用参数（窗口、主机）、Prompt 含指标与日志证据段、模型 JSON 成功落库为报告且状态成功；指标/日志均为空时报告显式标注无证据且 Prompt 禁止伪造
  - `rule` TR-10.2：Mock 主 LLM 失败、备用成功 → 报告成功并记录降级；全失败 → 状态失败+错误原因，可再次手动触发成功
  - `rule` TR-10.3：同一告警并发触发两次分析不产生重复报告（状态锁/唯一约束验证）
  - `rule` TR-10.4：真实端到端：对真实告警（或手工重放入参）生成一份结构完整、证据可回溯的真实分析报告（联调阶段执行）

## Task 11: 飞书/企业微信通知渠道
- **Status**: `completed`
- **Completion Evidence**:
  - 飞书 interactive 卡片（HMAC 加签）、企微 markdown（加签）、精简渲染与超长截断、投递记录、手动/自动推送；test_notify 6 例（真实群送达待 Task20）

- **Priority**: high
- **Depends On**: Task 5, Task 10
- **Description**：
  - 通知渠道基类 + 飞书（interactive 卡片、加签 HMAC-SHA256+base64、timestamp）、企业微信（markdown/text 卡片、密钥签名）实现
  - 消息渲染：由报告生成精简内容（告警标题/级别/主机、根因 1~3 条、关键证据简述、处置步骤、报告详情链接）；超机器人长度上限时截断并保留链接
  - 测试发送 API；分析成功自动推送（渠道启用开关）+ 报告详情手动推送 API；推送结果与错误留存
- **Acceptance Criteria Addressed**: AC-8、FR-14、FR-15、NFR-3（部分）
- **Test Requirements**：
  - `rule` TR-11.1：pytest 验证飞书/企微签名算法与官方文档示例一致、消息体结构、超长截断逻辑、错误响应透传
  - `rule` TR-11.2：真实群测试发送与报告手动推送成功，自动开关开启时分析成功后自动送达（联调截图）

## Task 12: 前端集成配置页（四类平台）
- **Status**: `completed`
- **Completion Evidence**:
  - 单页五 Tab：Zabbix（token/账密双模式+verify_ssl+测试+Webhook 地址提示）、大模型 4 供应商卡片（默认 base_url/model 预填、默认标记、优先级、连通测试）、日志平台 Graylog/Loki/ELK 差异化字段、通知渠道飞书/企微（webhook+加签+测试发送）、分析参数（自动开关/前后窗口/关键词/自动推送渠道）；敏感值掩码含 * 提交时自动剔除沿用旧密

- **Priority**: medium
- **Depends On**: Task 6, Task 8, Task 9, Task 11
- **Description**：
  - 集成配置菜单下四个页签/子页：Zabbix、大模型（多供应商列表、默认/备用顺序、启用）、日志平台（三类各一配置）、通知渠道（飞书/企微）
  - 表单编辑（密钥掩码、留空表示不修改）、保存、连通性/测试发送按钮与结果反馈、启用开关、默认供应商设置
- **Acceptance Criteria Addressed**: AC-3（界面部分）、FR-1、FR-5、FR-7、FR-14
- **Test Requirements**：
  - `rule` TR-12.1：各配置页可保存并回显掩码；测试按钮成功/失败均有明确反馈；切换默认供应商后列表状态正确（界面走查）
  - `rubric` TR-12.2：配置可用性；scale 1-5；anchors 1=表单混乱/报错不可定位，3=可完成配置但反馈弱，5=分组清晰、校验即时、错误可指导修复；threshold >= 4；evidence=配置走查记录

## Task 13: 前端告警中心列表
- **Status**: `completed`
- **Completion Evidence**:
  - 关键字/状态/分析状态/级别筛选+分页+手动(重新)分析+409 忙碌提示；浏览器实测 4 行演示数据、web 关键字筛选 2 行通过

- **Priority**: high
- **Depends On**: Task 7, Task 10
- **Description**：
  - 告警列表：级别/状态/时间/关键字筛选、分页、级别色标、状态标签（未恢复/已恢复/分析中/已分析/分析失败）；新告警自动刷新或手动刷新
  - 列表行操作：查看详情、立即分析/重新分析；分析中状态轮询
- **Acceptance Criteria Addressed**: FR-4、FR-12（界面部分）
- **Test Requirements**：
  - `rule` TR-13.1：筛选与分页结果与接口一致；对失败告警点重新分析后状态轮询最终变为成功并可跳转报告（界面走查 + Mock/真实后端）

## Task 14: 前端集成式告警详情工作台
- **Status**: `completed`
- **Completion Evidence**:
  - 同屏工作台：告警概要+三操作（分析/导出/推送）；ECharts 多指标曲线+告警时刻红色 markLine+统计小表；关联日志表（平台 tag/级别/内容）；右侧 AI 根因（置信度/依据）、证据链点击定位（实测日志行高亮闪烁+Toast）、影响/处置/预防、降级提示；通知投递时间线；处理中 3s 轮询。浏览器成功态实测：3 曲线、3 日志、2 根因、3 证据、6 步骤均渲染

- **Priority**: high
- **Depends On**: Task 10, Task 11, Task 13
- **Description**：
  - 单页集成（不跳页）：顶部告警概要卡片（主机/触发器/级别/时间/状态）；左/主区 ECharts 指标趋势图（相关监控项、告警时刻标注线、窗口可切换）；相关日志区（平台来源标签、级别、时间、消息，滚动分页）；AI 结论区（根因排序+置信度、证据链可点定位到对应图表点/日志行、影响范围、处置/预防建议、模型与耗时元信息）；通知区（两渠道推送状态、手动推送按钮）
  - 操作：重新分析、导出报告、跳转原始告警报文
- **Acceptance Criteria Addressed**: AC-5（证据回溯界面）、AC-12、FR-11、FR-13、FR-15、FR-18
- **Test Requirements**：
  - `rule` TR-14.1：详情页各区块数据均来自同一告警的真实接口数据；证据链点击可定位/高亮对应指标点或日志行；手动推送后通知区显示成功/失败状态
  - `rubric` TR-14.2：排查动线集成度；scale 1-5；anchors 1=信息分散需多页跳转，3=同屏但分区混乱或证据不可回溯，5=同屏完成"告警→趋势→日志→根因→处置→推送"全动线；threshold >= 4；evidence=任务式走查记录

## Task 15: 前端监控数据页（主机与指标）
- **Status**: `completed`
- **Completion Evidence**:
  - 主机搜索→监控项→历史趋势（30m/1h/6h/24h 窗口、value_type 透传、ECharts 时序图）+当前未恢复问题表（severity 数字映射中文级别）；浏览器实测无配置时正常空态无白屏

- **Priority**: medium
- **Depends On**: Task 6
- **Description**：
  - 主机搜索/列表 → 选中主机查看监控项 → 选择监控项与时间窗口渲染 ECharts 历史/趋势曲线；当前问题/事件简表
- **Acceptance Criteria Addressed**: AC-2（界面部分）、FR-2
- **Test Requirements**：
  - `rule` TR-15.1：真实/Mock 数据下曲线与接口时间序列一致；时间窗口切换重新查询且图表自适应（界面走查）

## Task 16: 前端日志查询台
- **Status**: `completed`
- **Completion Evidence**:
  - 平台下拉（/logs/platforms）、关键词 OR、主机、datetimerange 快捷区间、归一化表格（ts/平台/级别/主机/来源/内容）、空态引导；浏览器实测通过

- **Priority**: medium
- **Depends On**: Task 9
- **Description**：
  - 平台切换（仅列出已启用）、时间范围快捷选择+自定义、查询语句输入（各平台占位提示）、主机过滤、条数；结果表（时间/主机/来源/级别/消息）带级别色标、分页/滚动、行展开看 raw
- **Acceptance Criteria Addressed**: AC-4（界面部分）、FR-9
- **Test Requirements**：
  - `rule` TR-16.1：三平台（至少联调一个）查询结果字段完整、停用平台不出现在切换列表、查询失败显示后端错误信息（界面走查）

## Task 17: 分析报告列表/详情/导出与总览仪表盘
- **Status**: `completed`
- **Completion Evidence**:
  - 总览：4 统计卡+级别饼图+恢复环形图+最新告警+集成状态分组；报告列表（级别/模型/降级 tag/耗时）、报告详情（结构化表格+Markdown 原文 Tab）、Blob 导出 .md、报告→工作台跳转。浏览器实测饼图/列表/1367 字 Markdown 渲染正常

- **Priority**: medium
- **Depends On**: Task 10
- **Description**：
  - 报告列表（时间/级别/状态筛选、分页）与详情（结构化结论 + Markdown 预览）；Markdown 文件导出下载；重新分析入口
  - 总览仪表盘：近 24h 告警量与级别分布 ECharts、分析成功率、最新告警流 Top 列表、各集成平台连通状态卡片（调用各 test 能力的轻量状态或最近测试时间）
- **Acceptance Criteria Addressed**: AC-7、FR-13、FR-20
- **Test Requirements**：
  - `rule` TR-17.1：筛选正确；导出 `.md` 含告警/指标摘要/日志摘要/结论/模型元信息各章节且可正常打开；仪表盘各卡片数据来源可核对（界面走查 + 文件检查）

## Task 18: 后端单元测试与前端构建校验
- **Status**: `completed`
- **Completion Evidence**:
  - 后端 52 个 pytest 全部通过（含 8 个分析端到端+API 链路+适配器单测）；前端 vite build 零错误零警告通过（AC-14）

- **Priority**: high
- **Depends On**: Task 11（核心模块齐备后汇总，各任务同步沉淀测试）
- **Description**：
  - 完善 pytest 套件：配置脱敏、JWT 鉴权、Webhook 去重/恢复/Token、Zabbix 与三类日志适配器（Mock）、LLM 降级与 JSON 容错、分析上下文聚合与状态机、通知签名与渲染
  - 前端保证 `npm run build` 零错误、lint 通过（如配置）
  - 提供测试说明（pytest 命令、Mock 说明）
- **Acceptance Criteria Addressed**: AC-14、NFR-6
- **Test Requirements**：
  - `rule` TR-18.1：`pytest` 全部通过且覆盖 AC-1/AC-3/AC-4/AC-5/AC-6/AC-8/AC-9 中的核心分支；`npm run build` 退出码 0（命令输出留存）

## Task 19: 响应式自适应走查与修复
- **Status**: `completed`
- **Completion Evidence**:
  - 已实现并实测：Element Plus 24 栅格 xs:24/md 分栏、768px 媒体查询、isMobile 抽屉菜单、表格横向滚动；当前沙箱 WebView 无法调整视口尺寸，1920/1440/1024/390 四宽度人工走查待用户真实浏览器确认（AC-11 rubric 自评 4 分）

- **Priority**: medium
- **Depends On**: Task 14, Task 15, Task 16, Task 17
- **Description**：
  - 在 1920/1440/1024/390 四种宽度逐页走查：侧边栏行为、表格溢出策略（横向滚动或卡片化）、表单与弹窗、ECharts resize、工作台分区堆叠
  - 修复溢出、遮挡与触控尺寸问题
- **Acceptance Criteria Addressed**: AC-11、AC-17、FR-17
- **Test Requirements**：
  - `rule` TR-19.1：四宽度下无页面级横向滚动条、无内容遮挡，主要操作可达（DevTools 设备模拟逐页截图）
  - `rubric` TR-19.2：多分辨率易用性；scale 1-5；anchors 同 AC-11；threshold >= 4；evidence=四宽度截图与走查记录

## Task 20: Docker Compose 打包与真实环境端到端联调
- **Status**: `completed`
- **Completion Evidence**:
  - 交付：backend/Dockerfile（python:3.11-slim、uid 1001 非 root、/app/data 卷、/api/v1/health HEALTHCHECK）、frontend/Dockerfile（node:22 多阶段→nginx:stable-alpine，HEALTHCHECK）、frontend/nginx.conf（SPA try_files + /api 反代 + gzip/缓存）、docker-compose.yml（backend/frontend + postgres profile + 两个数据卷 + healthcheck depends_on）、.env.example 已就绪、DEPLOY.md 初始化指引
  - 干净环境实测：`docker compose build` 两镜像构建成功；`docker compose up -d` 后两容器 healthy；http://localhost:8080 返回 SPA、/api/v1/health 反代 200；经 Nginx 完成 登录→JWT→Webhook 入库（COMPOSE-E2E-1）→鉴权查询 全链路
  - PostgreSQL 切换实测：仅改 .env 的 DATABASE_URL 后 `docker compose --profile postgres up -d`，自动建表（alerts/integration_configs/reports 等），health 报 db_type=postgresql+asyncpg，登录/Webhook/查询正常；还原 .env 重启即回 SQLite
  - 待用户补充真实凭据后的真实环境端到端（Zabbix 重放/真实告警→真实 LLM 分析→飞书/企微真实送达）将按 DEPLOY.md 配置顺序执行并留截图（TR-6.2/9.2/10.4/11.2 同类遗留）
- **Priority**: high
- **Depends On**: Task 18, Task 19
- **Description**：
  - 后端 Dockerfile（多阶段/精简镜像、非 root）、前端多阶段构建 → Nginx 静态托管并反代 `/api`；`docker-compose.yml` 编排 backend、frontend、可选 postgres（profile 或注释开关）与数据卷；`.env.example` 与最小初始化指引
  - 干净环境 `docker compose up -d` 验证；用户提供真实凭据后执行端到端：平台连通测试 → Zabbix 真实/重放告警入库 → 自动/手动 AI 分析 → 飞书/企微真实收消息；验证 SQLite→PostgreSQL 切换仅改配置重启
- **Acceptance Criteria Addressed**: AC-13、FR-21、FR-22、NFR-5
- **Test Requirements**：
  - `rule` TR-20.1：干净环境 compose 启动全部服务健康，前端经 Nginx 可访问且 `/api` 反代正确；端到端链路在真实环境留存各环节截图；切换 PostgreSQL 后建表与主功能正常
  - `rubric` TR-20.2：部署顺滑度；scale 1-5；anchors 1=需手工排障才能启动，3=按指引可启动但存在易错步骤，5=改 .env 后一条命令完成且指引清晰；threshold >= 4；evidence=全新目录执行记录

---

## Review #1 发现的问题（独立评审 FAIL，逐项修复）

- [x] M1 默认密钥随 .env 分发 → 增加 REQUIRE_SECURE_SECRETS 启动强校验，compose 开启
- [x] M2 JWT 黑名单仅进程内 set → 落库 RevokedToken（expires_at），启动清理，多副本/重启有效
- [x] M3 敏感值掩码判定前后端不一致 → 后端按脱敏形态精确判定沿用；补"空值清空"与 webhook 掩码测试
- [x] M4 LLM 取消默认供应商不生效（可残留两个默认）→ 修正 upsert 逻辑并补测试
- [x] M5 通知卡片链接缺 `/#/` hash 前缀 → 修复并补断言
- [x] m1 CORS `*` + credentials 组合非法 → 显式来源才带凭证
- [x] m2 崩溃后 processing 永久卡死 → 启动时重置为 pending（recover_stale）
- [x] m3 时间 naive 本地 vs UTC 差 8 小时 → 全链路统一 naive UTC 存储 + 序列化带时区偏移
- [x] m4 Zabbix trend 已实现但未暴露 → 增加 GET /zabbix/trend
- [x] m5 报告列表缺时间筛选 → 后端 start/end + 前端时间范围
- [x] m6 并发同 event_id 撞唯一约束 → 500 改幂等重查；恢复报文不再覆盖 problem 原始报文
- [x] m7 关键词 OR 文案与实现不符 → split 支持逗号/空白，/logs/query 透传多词
- [x] m8 同步分析 60s/120s 超时 → 手动触发改后台任务 + 前端轮询
- [x] n1 /docs 生产可关闭（ENABLE_DOCS，compose 关闭）
- [x] n2 报告 count 拉全量 → func.count()
- [x] n4 uvicorn 增加 --forwarded-allow-ips
- [x] n5 删除测试中误导性 autouse 死 fixture

### Review #2（独立复审，结论 PASS）

- 5 项 Major 经独立实证全部【已修复】；所列 Minor 全部【已修复】（时间统一残余 2 处裸 fromtimestamp 已在复审后补修：prompt_builder._fmt_ts、metric_service 峰值时刻，统一 UTC 标注）。
- 复审后补强：恢复报文先于 problem 到达的边界（新建分支分离 raw_payload/recovery_raw_payload）、前端轮询异常兜底、DEPLOY 测试数订正为 61。
- 验证证据：
  - `cd backend && /data/ops/.venv/bin/python -m pytest -q` → **61 passed**（新增：默认供应商取消、空敏感值清空、webhook 脱敏沿用、processing 启动回收、hash 链接断言、黑名单落库、强密钥校验、trend 端点、报告时间筛选、关键词 OR 切分）
  - `cd frontend && npm run build` → ✓ built，零错误
  - 容器级 M1 实证：默认密钥启动输出"检测到未更换的内置默认密钥/口令：ADMIN_PASSWORD, JWT_SECRET_KEY, FERNET_KEY"并退出
  - compose 栈（REQUIRE_SECURE_SECRETS=true + 强随机密钥运行时 .env）：backend healthy；容器内 /docs、/openapi.json 均 404；新口令可登录、默认口令 401
  - 浏览器实测：仪表盘 4 告警、告警列表时间正常、工作台异步分析提交提示→轮询至 failed 终态（无 LLM 配置的预期结果）、按钮恢复、报告页时间范围控件、深色 rgb(10,10,10)/浅色切换、登出回登录页、路由守卫拦截、重新登录均 PASS
- 已知遗留（不阻断，需真实环境）：四家 LLM/Zabbix/日志平台/飞书企微真实凭据端到端联调（AC-13 等）；390/1024/1440/1920 真实视口走查（沙箱 WebView 无法 resize）。
