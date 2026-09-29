# Changelog

所有值得关注的变更记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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
