# Changelog

所有值得关注的变更记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.2.0] - 2026-09-28

### 新增

- **用户管理**：新增 `users` 表（用户名/密码哈希/头像），认证从配置文件硬编码改为数据库用户模式；启动时自动播种初始管理员（幂等）
- **个人设置**：点击右上角头像下拉菜单「个人设置」，可修改用户名、头像（URL 或本地上传转 base64）、密码（需验证原密码）
- **PostgreSQL 支持**：数据库切换为 PostgreSQL-18（`pgsql18.hdks.cn:5432`），驱动 `asyncpg`
- **未恢复问题独立菜单**：「监控数据」改为子菜单，新增「未恢复问题」页面
- **未恢复问题筛选**：支持按主机名关键字和告警级别筛选
- **日志查询筛选**：新增日志级别（fatal/error/warn/info/debug/trace）和来源筛选

### 修复

- **Zabbix `problem.get` 报错**：移除 `problem.get` 不支持的 `selectHosts` 参数，改用 `trigger.get` + `selectHosts` 关联主机
- **登录「请求校验参数失败」**：修复 `auth.js` 的 `login()` 函数参数解构问题，将 Vue 响应式 form 对象提取为纯对象再提交
- **大模型 401 鉴权失败**：MiniMax 密钥为国内区，将 `base_url` 从 `https://api.minimax.io/v1` 修正为 `https://api.minimax.cn/v1`

### 变更

- 默认管理员密码改为 `ITOPS@ecidh.com`
- 认证响应（`/auth/login`、`/auth/me`）增加 `avatar` 字段
- 新增接口：`GET /auth/me`、`PUT /auth/profile`、`PUT /auth/password`
- Zabbix `/problems` 接口新增 `host`、`severities` 查询参数
- 日志 `/query` 接口新增 `level`、`source` 查询参数

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
