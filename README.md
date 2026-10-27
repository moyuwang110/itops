# ITOPS 智能运维告警分析系统

> 将「**告警接收 → 指标与日志上下文聚合 → AI 根因分析 → 报告沉淀 → IM 通知**」链路自动化，缩短 MTTR，减少运维人员在多平台间切换排查的成本。

- **后端**：Python 3.11 + FastAPI（异步） + SQLAlchemy 2.0
- **前端**：Vue 3 + Vite + Element Plus + ECharts
- **存储**：SQLite 默认零配置，可一键切换 PostgreSQL
- **部署**：Docker Compose 一键启动
- **版本**：0.3.0

---

## 功能特性

| 模块 | 能力 |
| --- | --- |
| 告警接入 | Zabbix Webhook 接收（独立 Token 校验），按 `event_id` 幂等去重；恢复报文不覆盖 problem 原始报文；定时任务每 60 秒同步当前未恢复问题到本地库；告警列表含**主机 IP**列，Webhook 自动解析 IP 字段 |
| 仪表盘 | 24 小时告警统计 + 分析成功率 + 最新告警 + 集成状态；**CPU / 内存 / 磁盘使用率 TOP5 主机**横向柱状图；**24 小时告警趋势折线**（全部 / 未恢复 / 已恢复）；主机可用性统计卡片 |
| 监控数据 | Zabbix 主机/监控项/历史(`history`)/趋势(`trend`)/当前问题查询；**主机概览页**（主机组、Agent 可用性、CPU / 内存 / 磁盘使用率进度条） |
| 日志聚合 | Graylog / Loki / Elasticsearch 三平台统一查询，输出归一化结构（时间戳/主机/来源/级别/消息） |
| AI 根因分析 | MiniMax / DeepSeek / 豆包 / 通义千问 四供应商降级链；聚合告警+指标+日志上下文；结构化报告（根因/证据链/影响/处置/预防）；JSON 解析失败自动修复重试 |
| 分析触发 | 告警到达按开关自动入队；界面手动/重新触发；**后台异步执行**，界面轮询状态（pending/processing/success/failed） |
| 通知推送 | 飞书 interactive 卡片 + 企业微信 markdown，支持签名校验；自动或手动推送，超长自动截断并附报告链接 |
| VMware 集成 | vCenter 虚拟机清单（电源状态 / OS / CPU / 内存 / 资源池）；**告警工作台 VMware 虚拟机信息卡片**（按主机 IP / 主机名自动匹配）；虚拟机管理页支持**列宽可调 + 列拖拽排序**（Sortable.js，持久化 localStorage） |
| CMDB 集成 | OneOps CMDB 配置项查询代理，支持 CI 类型筛选、关键字搜索、详情查看 |
| IPAM 地址管理 | VLAN CRUD（ID 1–4094 校验）、网段 CRUD（CIDR / 网关 / 用途 / VLAN 关联 / 自动扫描开关）、IP 地址扫描入库 + 手工登记 / 释放、**冲突检测**（MAC 重复、已登记但扫描未在线）、**每日自动扫描**（北京时间 02:00）、变更记录时间线；冲突 IP 页面头部红色告警条 |
| Web 工作台 | 告警详情同屏集成 VMware 虚拟机信息、指标趋势图（ECharts + 告警时刻 markLine）、相关日志、AI 结论、通知时间线；亮/暗/跟随系统三态主题；响应式布局 |
| 安全 | 第三方凭据 Fernet 加密存储；接口脱敏；JWT 登出黑名单落库；默认密钥/口令**启动强校验**（生产模式未更换拒绝启动）；登录接口滑动窗口频率限制 |

---

## 技术栈

**后端**

| 类别 | 技术 |
| --- | --- |
| 框架 | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0（async） |
| 数据库 | SQLite（aiosqlite）/ PostgreSQL（asyncpg） |
| 鉴权 | python-jose（JWT）+ httpOnly Cookie |
| 加密 | cryptography（Fernet） |
| HTTP 客户端 | httpx（共享连接池，按 verify_ssl 分组） |
| Zabbix 适配器 | 原生 JSON-RPC |
| VMware 适配器 | pyvmomi |
| 测试 | pytest + pytest-asyncio + anyio |

**前端**

| 类别 | 技术 |
| --- | --- |
| 框架 | Vue 3 + Vite |
| UI | Element Plus |
| 状态 | Pinia |
| 路由 | Vue Router 4 |
| 图表 | ECharts 5 |
| HTTP | axios |
| 拖拽 | Sortable.js |

---

## 项目结构

```
.
├── backend/
│   ├── app/
│   │   ├── api/v1/          # REST 接口（auth/configs/zabbix/ipam/webhooks/alerts/reports/logs/dashboard/vmware/cmdb）
│   │   ├── core/            # config / database / security(Fernet+JWT) / exceptions / timeutil / rate_limit
│   │   ├── integrations/    # 外部适配器：zabbix / llm(4家) / logs(3家) / notify(飞书+企微) / vmware / cmdb
│   │   ├── models/          # SQLAlchemy 模型（alert/report/config/revoked_token/agent/ipam 四张表）
│   │   ├── schemas/         # Pydantic 请求/响应
│   │   ├── services/        # 业务逻辑（alert/analysis/llm/log/metric/notify/report/config/prompt_builder/zabbix/ipam/network_tool）
│   │   └── main.py          # 应用入口（含启动回收 processing 任务、清理过期黑名单、Zabbix 告警同步后台循环、IPAM 每日扫描后台循环）
│   ├── tests/               # pytest 单元测试（61+ 个）
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── views/           # Login / Dashboard / AlertList / AlertDetail(工作台) / Monitoring / Hosts / Problems / Logs / Reports / Settings / Agents / VMs / CMDB / IPAM / DhcpInfo / AddressScan
│   │   ├── layouts/         # MainLayout（折叠侧栏 + 响应式抽屉）
│   │   ├── stores/          # auth / theme（三态）
│   │   ├── utils/           # api（axios 拦截器+401 处理+withCredentials）/ format
│   │   └── components/      # EChart（监听 isDark 重绘）
│   ├── nginx.conf           # SPA + /api 反代（proxy_read_timeout 120s）
│   └── Dockerfile           # node22 → nginx 多阶段
├── .env.example             # 环境变量模板（含默认密钥强校验说明）
├── docker-compose.yml       # 一键部署（含可选 postgres profile）
├── LICENSE                  # Mozilla Public License 2.0
└── DEPLOY.md                # 详细部署与运维指引
```

---

## 快速开始

### Docker Compose（推荐）

```bash
cd itops
cp .env.example .env
# 编辑 .env，必须修改以下三项（REQUIRE_SECURE_SECRETS=true 时未修改会拒绝启动）：
#   ADMIN_PASSWORD   管理员初始密码
#   JWT_SECRET_KEY   openssl rand -hex 32
#   FERNET_KEY       python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"
docker compose up -d --build
```

访问 `http://<服务器IP>:8080`，使用 `admin` 与 `.env` 中的密码登录。

> 完整配置顺序、PostgreSQL 切换、本地开发、运维说明见 [DEPLOY.md](./DEPLOY.md)。

### 本地开发

```bash
# 后端
cd backend
python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest                  # 61+ passed
.venv/bin/python -m uvicorn app.main:app --reload --port 8010

# 前端
cd frontend
npm install
npm run dev                                  # http://localhost:5173，自动代理 /api → 8010
npm run build
```

---

## API 一览

所有业务接口（除登录与 Zabbix Webhook 外）均需在请求头携带 `Authorization: Bearer <JWT>`；0.2.0 起也支持 httpOnly Cookie 鉴权。基础路径 `/api/v1`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/login` | 管理员登录，返回 JWT + 设置 httpOnly Cookie |
| GET | `/auth/me` | 当前登录用户 |
| POST | `/auth/logout` | 退出登录（令牌入黑名单 + 清除 Cookie） |
| PUT | `/auth/profile` | 修改管理员用户名与头像 |
| PUT | `/auth/password` | 修改管理员密码（需验证原密码） |
| GET/POST/PUT/DELETE | `/configs` | 集成配置 CRUD（密钥加密+脱敏） |
| GET/PUT | `/configs/system` | 系统设置（自动分析开关、取数窗口、日志关键词、自动推送渠道） |
| GET | `/zabbix/hosts` `/zabbix/hosts-overview` `/zabbix/items` `/zabbix/history` `/zabbix/trend` `/zabbix/problems` | Zabbix 监控数据查询；`hosts-overview` 含主机组、Agent 可用性、CPU / 内存 / 磁盘使用率 |
| POST | `/webhooks/zabbix` | 接收 Zabbix 告警报文（独立 Token，不走 JWT） |
| GET | `/alerts` `/alerts/{id}` | 告警列表（筛选/分页/按 IP 搜索）、详情（含报告/通知记录/VMware 联动） |
| POST | `/alerts/{id}/analyze` | 手动触发/重新分析（后台异步，返回 `queued`，可选 `agent_id`） |
| POST | `/alerts/{id}/acknowledge` | 确认（忽略）单条告警 |
| POST | `/alerts/acknowledge-batch` | 批量确认告警 |
| GET | `/alerts/{id}/vmware` | 告警关联 VMware 虚拟机信息（按 host_ip / host 匹配 vCenter VM） |
| GET | `/reports` `/reports/{id}` `/reports/{id}/export` | 报告列表（支持时间/级别/关键词筛选）、详情、Markdown 导出 |
| POST | `/reports/{id}/notify` | 手动推送报告到通知渠道 |
| GET | `/logs/platforms` `/logs/query` | 已启用日志平台列表、统一日志查询 |
| GET | `/dashboard/summary` | 24h 告警统计、分析成功率、集成状态、**24h 告警趋势**（每小时 total/problem/resolved） |
| GET | `/dashboard/host-usage` | **主机资源 TOP5**（CPU / 内存 / 磁盘使用率 + 主机可用性统计） |
| GET/POST/PUT/DELETE | `/ipam/vlans` | VLAN CRUD |
| GET/POST/PUT/DELETE | `/ipam/subnets` | 网段 CRUD；`POST /subnets/{id}/scan` 立即扫描 |
| GET | `/ipam/addresses` | 网段内 IP 地址列表（支持状态 / 关键词 / 仅冲突筛选） |
| POST | `/ipam/addresses/assign` | 手工登记 / 分配 IP |
| POST | `/ipam/addresses/{id}/release` | 释放手工登记 |
| GET | `/ipam/conflicts` | 冲突 IP 地址列表 |
| GET | `/ipam/changelogs` | IP 变更记录（分页） |
| GET | `/vmware/vms` | vCenter 虚拟机清单 |
| GET | `/cmdb/types` `/cmdb/list` `/cmdb/statistics` | OneOps CMDB 代理查询 |
| POST | `/network-tools/scan` | 地址扫描 |
| GET | `/health` `/healthz` | 健康检查 |

> 接口完整结构可在本地以 `ENABLE_DOCS=true` 启动后访问 `/docs`（Swagger UI）。生产模板默认 `ENABLE_DOCS=false`。

---

## 分析工作流

```
Zabbix 告警 Webhook
        │
        ▼
  幂等入库（按 event_id 去重，同时解析 host_ip）
        │
        ├── auto_analysis=true ──► 后台异步 submit_analysis
        └── auto_analysis=false ─► 等待界面手动触发
                                         │
                                         ▼
                          ┌───────────────────────────────┐
                          │  1. 指标上下文（Zabbix 历史/趋势）│
                          │  2. 日志上下文（多平台 OR 检索）  │
                          │  3. VMware 虚拟机信息（如已配置） │
                          │  4. LLM 根因分析（主供应商→降级） │
                          │  5. 结构化报告落库 + Markdown    │
                          └───────────────────────────────┘
                                         │
                        ┌────────────────┴────────────────┐
                        ▼                                 ▼
                  分析成功 (success)                 分析失败 (failed，可重试)
                        │
                        ▼
              auto_notify_channels 已配置 ──► 飞书/企微推送卡片
```

- 主供应商超时/失败时按优先级自动降级到备用供应商；全部失败置 `failed` 并保留错误信息。
- LLM 返回的 JSON 解析失败时自动发起一次修复重试。
- 服务重启时会把上次崩溃停留在 `processing` 的告警重置为 `pending`，避免永久卡死。

---

## IPAM 工作流

```
创建 VLAN（可选）
        │
        ▼
创建网段（CIDR + 网关 + 自动扫描开关）
        │
        ├─► 立即扫描 ─► 调用 network_tool_service.scan_addresses
        │                  │
        │                  ▼
        │              IP 地址入库（自动状态：used/free/unknown）
        │                  │
        │                  ├─► _detect_conflicts（MAC 重复 / 已登记但未在线）
        │                  └─► refresh_subnet_stats（统计缓存更新）
        │
        └─► 每日 02:00 自动扫描（启用 auto_scan 的网段）

手工登记 IP
        │
        ▼
  addresses/assign（指定责任人/用途/备注）
        │
        ├─► source = manual
        ├─► 扫描若发现在线 → status = used（覆盖 reserved）
        └─► 扫描若未发现在线 → status = free，_detect_conflicts 标记冲突
```

---

## 安全说明

- **凭据加密**：所有第三方平台的 api_key/token/webhook_url/sign_secret 以 Fernet 对称加密存储（密文前缀 `enc:v1:`）；接口返回时统一脱敏（`******` 或 `scheme://host/******`），脱敏值回传视为"未修改"沿用旧密文。
- **默认密钥强校验**：`REQUIRE_SECURE_SECRETS=true`（`.env.example` 默认开启）时，若 `ADMIN_PASSWORD` / `JWT_SECRET_KEY` / `FERNET_KEY` 仍为内置默认值则**拒绝启动**。
- **登出黑名单落库**：JWT 登出后 jti 写入 `revoked_tokens` 表（带过期时间），重启/多副本均有效；过期记录服务启动时自动清理。
- **CORS**：`CORS_ORIGINS=*` 时自动关闭 `allow_credentials`，避免浏览器拒绝。
- **登录限流**：Sliding Window，每 IP 每分钟最多 5 次登录尝试，超限返回 429。
- **Webhook 独立鉴权**：Zabbix Webhook 走 `X-Webhook-Token` / `?token=` 鉴权，不走 JWT，与业务接口隔离。

---

## 验证

- 后端测试：`cd backend && .venv/bin/python -m pytest`（61+ passed，覆盖去重、脱敏、降级、JSON 解析容错、签名、JWT 黑名单、IPAM CRUD 等）
- 前端构建：`cd frontend && npm run build`（零错误）

---

## 配置项速查

见 [.env.example](./.env.example)。关键项：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `ADMIN_PASSWORD` | 管理员初始口令 | `ChangeMe_2026!`（强校验下必须改） |
| `JWT_SECRET_KEY` | JWT 签名密钥 | 内置默认（强校验下必须改） |
| `FERNET_KEY` | 第三方凭据加密密钥 | 内置默认（强校验下必须改） |
| `ZABBIX_WEBHOOK_TOKEN` | Webhook 校验 Token | 空（不校验） |
| `DATABASE_URL` | 数据库连接串 | SQLite |
| `REQUIRE_SECURE_SECRETS` | 启动强校验默认密钥 | `true` |
| `ENABLE_DOCS` | 是否开启 `/docs` | `false` |
| `CORS_ORIGINS` | 跨域来源 | `*` |
| `ANALYSIS_AUTO_ENABLED` | 告警到达自动分析 | `true` |
| `ANALYSIS_BEFORE_MINUTES` / `ANALYSIS_AFTER_MINUTES` | 指标/日志取数窗口 | 30 / 10 |
| `COOKIE_SECURE` | 登录 Cookie 是否加 Secure | `false`（HTTP 反代下保持 false） |
| `ALERT_SYNC_INTERVAL` | Zabbix 告警定时同步间隔（秒） | `60`（代码常量，非 env） |

---

## 许可

**Mozilla Public License 2.0（MPL-2.0）**。详见 [LICENSE](./LICENSE)。

本项目源代码在 MPL-2.0 条款下提供，可自由使用、修改与分发。若分发可执行形式，需同时提供对应源码形式。
