# ITOPS 智能运维告警分析系统

> 将「**告警接收 → 指标与日志上下文聚合 → AI 根因分析 → 报告沉淀 → IM 通知**」链路自动化，缩短 MTTR，减少运维人员在多平台间切换排查的成本。

- **后端**：Python 3.11 + FastAPI（异步） + SQLAlchemy 2.0
- **前端**：Vue 3 + Vite + Element Plus + ECharts
- **存储**：SQLite 默认零配置，可一键切换 PostgreSQL
- **部署**：Docker Compose 一键启动
- **版本**：0.1.0

---

## 功能特性

| 模块 | 能力 |
| --- | --- |
| 告警接入 | Zabbix Webhook 接收（独立 Token 校验），按 `event_id` 幂等去重；恢复报文不覆盖 problem 原始报文 |
| 监控数据 | Zabbix 主机/监控项/历史(`history`)/趋势(`trend`)/当前问题查询 |
| 日志聚合 | Graylog / Loki / Elasticsearch 三平台统一查询，输出归一化结构（时间戳/主机/来源/级别/消息） |
| AI 根因分析 | MiniMax / DeepSeek / 豆包 / 通义千问 四供应商降级链；聚合告警+指标+日志上下文；结构化报告（根因/证据链/影响/处置/预防）；JSON 解析失败自动修复重试 |
| 分析触发 | 告警到达按开关自动入队；界面手动/重新触发；**后台异步执行**，界面轮询状态（pending/processing/success/failed） |
| 通知推送 | 飞书 interactive 卡片 + 企业微信 markdown，支持签名校验；自动或手动推送，超长自动截断并附报告链接 |
| Web 工作台 | 告警详情同屏集成指标趋势图（ECharts + 告警时刻 markLine）、相关日志、AI 结论、通知时间线；亮/暗/跟随系统三态主题；响应式布局 |
| 安全 | 第三方凭据 Fernet 加密存储；接口脱敏；JWT 登出黑名单落库；默认密钥/口令**启动强校验**（生产模式未更换拒绝启动） |

---

## 技术栈

**后端**

| 类别 | 技术 |
| --- | --- |
| 框架 | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0（async） |
| 数据库 | SQLite（aiosqlite）/ PostgreSQL（asyncpg） |
| 鉴权 | python-jose（JWT） |
| 加密 | cryptography（Fernet） |
| HTTP 客户端 | httpx |
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

---

## 项目结构

```
.
├── backend/
│   ├── app/
│   │   ├── api/v1/          # REST 接口（auth/configs/zabbix/webhooks/alerts/reports/logs/dashboard）
│   │   ├── core/            # config / database / security(Fernet+JWT) / exceptions / timeutil
│   │   ├── integrations/    # 外部适配器：zabbix / llm(4家) / logs(3家) / notify(飞书+企微)
│   │   ├── models/          # SQLAlchemy 模型（alert/report/config/revoked_token）
│   │   ├── schemas/         # Pydantic 请求/响应
│   │   ├── services/        # 业务逻辑（alert/analysis/llm/log/metric/notify/report/config/prompt_builder）
│   │   └── main.py          # 应用入口（含启动回收 processing 任务、清理过期黑名单）
│   ├── tests/               # pytest 单元测试（61 个）
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── views/           # Login / Dashboard / AlertList / AlertDetail(工作台) / Monitoring / Logs / Reports / Settings
│   │   ├── layouts/         # MainLayout（折叠侧栏 + 响应式抽屉）
│   │   ├── stores/          # auth / theme（三态）
│   │   ├── utils/           # api（axios 拦截器+401 处理）/ format
│   │   └── components/      # EChart（监听 isDark 重绘）
│   ├── nginx.conf           # SPA + /api 反代（proxy_read_timeout 120s）
│   └── Dockerfile           # node22 → nginx 多阶段
├── .env.example             # 环境变量模板（含默认密钥强校验说明）
├── docker-compose.yml       # 一键部署（含可选 postgres profile）
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
.venv/bin/python -m pytest                  # 61 passed
.venv/bin/python -m uvicorn app.main:app --reload --port 8010

# 前端
cd frontend
npm install
npm run dev                                  # http://localhost:5173，自动代理 /api → 8010
npm run build
```

---

## API 一览

所有业务接口（除登录与 Zabbix Webhook 外）均需在请求头携带 `Authorization: Bearer <JWT>`。基础路径 `/api/v1`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/login` | 管理员登录，返回 JWT |
| GET | `/auth/me` | 当前登录用户 |
| POST | `/auth/logout` | 退出登录（令牌入黑名单） |
| GET/POST/PUT/DELETE | `/configs` | 集成配置 CRUD（密钥加密+脱敏） |
| GET/PUT | `/configs/system` | 系统设置（自动分析开关、取数窗口、日志关键词、自动推送渠道） |
| GET | `/zabbix/hosts` `/zabbix/items` `/zabbix/history` `/zabbix/trend` `/zabbix/problems` | Zabbix 监控数据查询 |
| POST | `/webhooks/zabbix` | 接收 Zabbix 告警报文（独立 Token，不走 JWT） |
| GET | `/alerts` `/alerts/{id}` | 告警列表（筛选/分页）、详情（含报告与通知记录） |
| POST | `/alerts/{id}/analyze` | 手动触发/重新分析（后台异步，返回 `queued`） |
| GET | `/reports` `/reports/{id}` `/reports/{id}/export` | 报告列表（支持时间/级别/关键词筛选）、详情、Markdown 导出 |
| POST | `/reports/{id}/notify` | 手动推送报告到通知渠道 |
| GET | `/logs/platforms` `/logs/query` | 已启用日志平台列表、统一日志查询 |
| GET | `/dashboard/summary` | 24h 告警统计、分析成功率、集成状态 |
| GET | `/health` `/healthz` | 健康检查 |

> 接口完整结构可在本地以 `ENABLE_DOCS=true` 启动后访问 `/docs`（Swagger UI）。生产模板默认 `ENABLE_DOCS=false`。

---

## 分析工作流

```
Zabbix 告警 Webhook
        │
        ▼
  幂等入库（按 event_id 去重）
        │
        ├── auto_analysis=true ──► 后台异步 submit_analysis
        └── auto_analysis=false ─► 等待界面手动触发
                                         │
                                         ▼
                          ┌───────────────────────────────┐
                          │  1. 指标上下文（Zabbix 历史/趋势）│
                          │  2. 日志上下文（多平台 OR 检索）  │
                          │  3. LLM 根因分析（主供应商→降级） │
                          │  4. 结构化报告落库 + Markdown    │
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

## 安全说明

- **凭据加密**：所有第三方平台的 api_key/token/webhook_url/sign_secret 以 Fernet 对称加密存储（密文前缀 `enc:v1:`）；接口返回时统一脱敏（`******` 或 `scheme://host/******`），脱敏值回传视为"未修改"沿用旧密文。
- **默认密钥强校验**：`REQUIRE_SECURE_SECRETS=true`（`.env.example` 默认开启）时，若 `ADMIN_PASSWORD` / `JWT_SECRET_KEY` / `FERNET_KEY` 仍为内置默认值则**拒绝启动**。
- **登出黑名单落库**：JWT 登出后 jti 写入 `revoked_tokens` 表（带过期时间），重启/多副本均有效；过期记录服务启动时自动清理。
- **CORS**：`CORS_ORIGINS=*` 时自动关闭 `allow_credentials`，避免浏览器拒绝。

---

## 验证

- 后端测试：`cd backend && .venv/bin/python -m pytest`（61 passed，覆盖去重、脱敏、降级、JSON 解析容错、签名、JWT 黑名单等）
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

---

## 许可

内部运维工具，未指定开源许可。
