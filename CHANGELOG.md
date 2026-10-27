# Changelog

所有值得关注的变更记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.3.0] - 2026-10-27

### 新增

- **告警列表主机 IP 列**：`alerts` 表新增 `host_ip` 字段；定时同步时通过 Zabbix `host.get + selectInterfaces` 批量查询填充；Webhook 报文兼容 `host_ip` / `ip` / `host_ipaddress` 三种字段名；告警详情与列表接口统一输出 `host_ip`；关键字搜索支持按 IP 匹配
- **VMware 告警联动分析**：新增 `GET /alerts/{event_id}/vmware` 接口，按告警的 `host_ip` 与 `host` 匹配 vCenter 虚拟机（优先 IP 精确匹配，其次主机名忽略大小写/去域名后缀匹配）；返回虚拟机详情（电源状态、OS、客户机 IP/主机名、CPU/内存、资源池、整体状态、Tools 状态）；告警工作台左侧新增「VMware 虚拟机信息」卡片并在页面加载时自动查询；vCenter 未配置或未匹配时返回友好提示
- **仪表盘 CPU / 内存 / 磁盘使用率 TOP5**：新增 `GET /dashboard/host-usage` 接口，返回三类资源使用率 TOP5 主机（百分比柱状图，≥85% 红色、≥70% 黄色）与主机可用性统计；前端三张横向 ECharts 柱状图；Zabbix 不可用时自动降级返回提示
- **仪表盘 24 小时告警趋势折线**：`GET /dashboard/summary` 新增 `alert_trend`（24 小时分桶，每小时 `total / problem / resolved` 三个计数）；前端 ECharts 多序列折线 + 面积填充，按小时展示告警到达与恢复节奏
- **监控数据 > 主机页面**：新增 `HostsView.vue`，列含主机名、IP（mono 字体）、主机组（标签）、Zabbix 可用性（带错误 tooltip）、CPU/内存/磁盘使用率进度条、监控状态；支持关键字与可用性筛选；后端新增 `GET /zabbix/hosts-overview` 接口（含 `keyword` / `limit` 参数，返回主机组、接口 IP、Agent 可用性、启用状态）
- **Zabbix 资源使用率采集**：`ZabbixClient` 新增 `list_hosts_overview()` 与 `host_usage_map()`；CPU 兼容 `system.cpu.util[,idle]` 做 100-value 转换；内存优先 `vm.memory.utilization` 兜底 `vm.memory.size[pused]`；磁盘兼容 `vfs.fs.size` 与 `vfs.fs.dependent.size` 取多文件系统最大值
- **虚拟机列宽可调 + 拖拽排序**：VMsView 改用动态列定义；拖动表头边框调整宽度、拖动表头移动列顺序（基于 Sortable.js）；列顺序与宽度持久化到 localStorage；提供「重置列设置」按钮；电源状态筛选；顶部统计卡片（总数 / 开机 / 关机 / 挂起）
- **IPAM 地址管理模块**：
  - `backend/app/models/ipam.py` 新增四张表：`vlans`（VLAN ID / 名称 / 备注 + 唯一约束）、`subnets`（网段 CIDR / 网关 / 用途 / VLAN 关联 / 自动扫描开关 / 扫描统计缓存）、`ip_addresses`（IP 状态 / MAC / 主机名 / 责任人 / 来源 / 冲突原因 / 变更计数 + subnet+ip 联合唯一）、`ip_change_logs`（IP 变更历史）
  - `backend/app/services/ipam_service.py`：VLAN CRUD、网段 CRUD（CIDR 严格校验、网关需在网段内）、扫描入库（调用已有 `network_tool_service.scan_addresses`）、手工登记/释放、冲突检测、变更日志、网段统计自动刷新
  - `backend/app/api/v1/ipam.py`：整套 `/ipam/*` REST 接口（VLAN CRUD、网段 CRUD + 立即扫描、地址列表 + 手工登记 + 释放、冲突列表、变更记录分页）
  - `frontend/src/views/ipam/IPAMView.vue`：网段管理（利用率进度条 + 立即扫描按钮 + 编辑/删除）、VLAN 管理（ID 1–4094 校验）、地址明细（状态筛选 / 关键词 / 仅看冲突）、变更记录三标签页；手工登记弹窗、网段 CIDR 输入时自动校验
  - **冲突检测**：MAC 重复（同一 MAC 出现在多个 IP）、已登记责任人但扫描未发现在线
  - **每日自动扫描**：`main.py` 新增 `_ipam_daily_scan_loop` 后台任务，北京时间 02:00 扫描所有 `subnets.auto_scan=true` 的网段，扫描失败不阻塞其他网段
  - **页面头部冲突告警条**：存在冲突 IP 时页面顶部自动出现红色 `el-alert`，显示冲突数量与原因，点击可定位到冲突地址

### 优化

- **磁盘使用率采集兼容性**：`host_usage_map` 的磁盘搜索由 `vfs.fs.size` 改为 `vfs.fs.`，兼容 Zabbix 6.x 推荐的 `vfs.fs.dependent.size[/,pused]` 形式
- **Zabbix 主机可用性标签统一**：新增 `_AVAILABLE_LABEL` 映射表，`host_usage_map` / `list_hosts_overview` / 前端主机页均使用同一套"可用 / 不可用 / 未知"文案
- **告警详情 VMware 接口降级保护**：vCenter 未配置时返回 `{matched: false, reason}` 而非抛 500，前端展示"未配置 VMware vCenter"提示

### 修复

- **告警列表 host_ip Webhook 入库路径**：`parse_zabbix_payload` / `ingest_alert` / `_apply_update` 补齐 `host_ip` 字段的解析、写入与更新逻辑，与同步路径对齐
- **主机资源查询失败不影响仪表盘**：`GET /dashboard/host-usage` 捕获 Zabbix `BizError` 后返回 `{available: false, reason}`，前端展示友好提示而非整块卡片空白
- **虚拟机 Sortable.js 与 el-table 配合**：`initSortable` 在 `onMounted` 与每次 `onEnd` 后通过 `nextTick` 重新绑定表头，避免 ref 失效导致拖动排序无响应

## [0.2.0] - 2026-09-29

### 新增

- **用户管理**：新增 `users` 表（用户名/密码哈希/头像），认证从配置文件硬编码改为数据库用户模式；启动时自动播种初始管理员（幂等）
- **个人设置**：点击右上角头像下拉菜单「个人设置」，可修改用户名、头像（URL 或本地上传转 base64）、密码（需验证原密码）
- **PostgreSQL 支持**：数据库切换为 PostgreSQL-18（`pgsql18.hdks.cn:5432`），驱动 `asyncpg`
- **未恢复问题独立菜单**：「监控数据」改为子菜单，新增「未恢复问题」页面
- **未恢复问题筛选**：支持按主机名关键字和告警级别筛选
- **日志查询筛选**：新增日志级别（fatal/error/warn/info/debug/trace）和来源筛选
- **AI Agent**：用户可创建多个 Agent（人设/系统提示词 + 绑定大模型供应商与模型），作为告警根因分析时的可调用身份
- **告警调用 Agent**：告警详情页「立即分析」可选择已配置 Agent，自动结合告警主机 Zabbix 指标趋势 + 跨平台日志上下文，按 Agent 人设完成分析
- **左侧菜单「AI Agent」**：进入 `/agents` 管理个人 Agent 列表（新建/编辑/删除/设为默认）
- **告警/未恢复问题级别多选筛选**：告警列表与未恢复问题的级别筛选由单选改为多选（`el-select multiple`），后端 `/alerts` 与 `/zabbix/problems` 均支持 `severities` 数组参数
- **分析报告手动删除**：报告列表新增「删除」按钮（`el-popconfirm` 二次确认），后端新增 `DELETE /reports/{id}`，不存在返回 404
- **工作台独立菜单**：新增「工作台」页面（`/workbench`），聚合展示未恢复告警、最近报告、集成配置状态，统计卡片可点击跳转
- **日志平台连通性测试**：集成配置「日志平台」页签新增「连通性测试」按钮，复用已有 `POST /configs/{id}/test` 接口，测试最近 5 分钟日志查询并展示结果
- **Zabbix 告警定时同步**：后端启动后台任务每 60 秒拉取 Zabbix 当前未恢复问题同步到本地 `alerts` 表；已不在 Zabbix 问题列表中的本地告警自动标记为 `resolved`（含 `recovered_at`）
- **告警列表数据源切换**：`GET /alerts` 由实时拉取 Zabbix 改为读取本地同步数据，支持 `status`（problem/resolved）、`severities`（多选）、`sort=severity`（按严重级别倒序）参数
- **已恢复告警菜单**：「告警中心」新增「已恢复告警」子菜单（`/alerts/resolved`），展示 `status=resolved` 的告警及恢复时间
- **工作台未恢复告警 Top10**：工作台告警表改为按严重级别倒序取 Top10，统计卡片展示未恢复告警总数
- **告警确认（忽略）功能**：告警列表与工作台新增「确认」按钮，点击后将 `alerts.acknowledged` 置为 `True`，该告警从默认列表隐藏；后端新增 `POST /alerts/{event_id}/acknowledge`；定时同步不会重置已确认状态
- **修复告警级别筛选失效**：axios 默认数组序列化格式为 `severities[]=3`，FastAPI `Query(list[int])` 无法解析导致级别筛选被忽略、返回全部告警；修复方式为在 [api.js](frontend/src/utils/api.js) 中配置 `paramsSerializer: { indexes: null }`，使数组序列化为 `severities=3&severities=4`
- **告警批量确认**：告警列表与工作台告警表新增多选列，选中后可点击「批量确认」按钮一次性忽略多条告警；后端新增 `POST /alerts/acknowledge-batch`（接收 `event_ids` 数组，返回 `acknowledged` 数量与 `not_found` 列表）
- **VMware vCenter 集成**：集成配置新增「VMware vCenter」页签，支持配置 vCenter 地址/端口/用户名/密码/证书校验及连通性测试；后端基于 pyvmomi 实现 `VCenterClient`（含 10s 连接超时）
- **虚拟机管理菜单**：新增「虚拟机管理」页面（`/vms`），对接 vCenter 拉取虚拟机清单，展示名称、电源状态、主机名、IP、操作系统、CPU、内存、资源池、整体状态，支持按名称/主机名/IP 关键字和电源状态筛选，顶部展示开/关/挂起统计
- **OneOps CMDB 集成**：集成配置新增「CMDB」页签，支持配置 CMDB 地址、用户名、密码及连通性测试；后端基于 httpx 实现 `OneOpsClient`，通过 `/api/v1/acl/login` 登录获取 `Access-Token`，调用 `/api/v0.1/ci_types`、`/api/v0.1/ci`、`/api/v0.1/statistics`、`/api/v0.1/relation_types` 获取配置项数据
- **CMDB 配置项菜单**：新增「CMDB 配置项」页面（`/cmdb`），通过后端代理调用 OneOps API 拉取 CI 实例列表（名称、CI 类型、IP、操作系统、状态、位置），支持按 CI 类型筛选和关键字搜索，顶部展示实例总数/类型数/关系数统计，点击「详情」查看完整属性；另提供「打开 CMDB 系统」按钮在新窗口访问完整 CMDB 功能

### 修复

- **Zabbix `problem.get` 报错**：移除 `problem.get` 不支持的 `selectHosts` 参数，改用 `trigger.get` + `selectHosts` 关联主机
- **登录「请求校验参数失败」**：修复 `auth.js` 的 `login()` 函数参数解构问题，将 Vue 响应式 form 对象提取为纯对象再提交
- **大模型 401 鉴权失败**：MiniMax 密钥为国内区，将 `base_url` 从 `https://api.minimax.io/v1` 修正为 `https://api.minimax.cn/v1`
- **`reports` 表缺 `agent_id` 列 500**：`create_all` 不会给已有表加列，新增 `_apply_pg_schema_diffs()` 自动 `ADD COLUMN IF NOT EXISTS`
- **Zabbix webhook 入库时区错误**：Zabbix 传来的 aware datetime 与 PG naive TIMESTAMP 相减报错，`_parse_time()` 统一转 naive UTC

### 变更

- 默认管理员密码改为 `ITOPS@ecidh.com`
- 认证响应（`/auth/login`、`/auth/me`）增加 `avatar` 字段
- 新增接口：`GET /auth/me`、`PUT /auth/profile`、`PUT /auth/password`
- 新增 Agent 接口：`GET /agents`、`GET /agents/providers`、`POST /agents`、`PUT /agents/{id}`、`DELETE /agents/{id}`、`POST /agents/{id}/default`
- 告警分析接口 `/alerts/{id}/analyze` 新增 `agent_id` 查询参数
- `reports` 表新增 `agent_id`、`agent_name` 字段，记录生成该报告的 Agent
- Zabbix `/problems` 接口新增 `host`、`severities` 查询参数
- 日志 `/query` 接口新增 `level`、`source` 查询参数
- **告警列表数据源改为实时拉取 Zabbix 当前未恢复问题**：`GET /alerts` 不再读本地 `alerts` 表，直接调 Zabbix `current_problems()`，支持 `host`/`severity` 筛选；`GET /alerts/{event_id}` 优先查本地记录（含报告/通知），无则从 Zabbix 回退；`POST /alerts/{event_id}/analyze` 首次分析时自动按 eventid 创建本地记录

## [0.1.0] - 2026-09-23

首个公开版本。

### 新增

- **告警接入**：Zabbix Webhook 接收端点，按 `event_id` 幂等去重，支持可选 Token 校验；恢复报文与 problem 原始报文分字段保存
- **监控数据**：Zabbix 主机/监控项/历史/趋势/当前问题查询接口
- **日志聚合**：Graylog / Loki / Elasticsearch 三平台统一查询适配器与归一化输出
- **AI 根因分析**：MiniMax / DeepSeek / 豆包 / 通义千问 四供应商降级链；告警+指标+日志上下文聚合；结构化根因报告；JSON 解析失败自动修复重试
- **分析触发**：自动入队 + 手动/重新触发；后台异步执行，pending/processing/success/failed 状态机；启动回收崩溃残留的 processing 任务
- **报告**：列表（时间/级别/关键词筛选）、详情、Markdown 导出、手动推送
- **通知**：飞书 interactive 卡片 + 企业微信 markdown，含签名校验；自动/手动推送，超长截断
- **前端工作台**：告警详情同屏集成指标趋势图、相关日志、AI 结论、通知时间线；亮/暗/跟随系统三态主题；响应式布局
- **安全**：Fernet 凭据加密、接口脱敏、JWT 登出黑名单落库、默认密钥启动强校验、CORS 凭证策略
- **部署**：Docker Compose 一键部署，SQLite/PostgreSQL 可切换，非 root 运行

### 已知限制

- 仅单管理员账号，不支持多租户/RBAC
- 真实 Zabbix / 日志平台 / 大模型 / 群机器人需用户提供凭据联调
- 响应式在 390/1024/1440/1920 真实视口下需最终人工走查
