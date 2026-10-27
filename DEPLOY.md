# ITOPS 部署初始化指引

## 一、Docker Compose 一键部署（推荐）

前置：已安装 Docker 20.10+ 与 Compose v2。

```bash
cd /data/ops
cp .env.example .env
# 编辑 .env，至少修改以下三项（REQUIRE_SECURE_SECRETS=true 时未修改会拒绝启动）：
#   ADMIN_PASSWORD        管理员初始密码（首次启动生效）
#   JWT_SECRET_KEY        JWT 签名密钥（openssl rand -hex 32）
#   FERNET_KEY            凭据加密密钥（python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"）
#   ZABBIX_WEBHOOK_TOKEN  Zabbix Webhook 校验 Token
# 生产环境同时建议：CORS_ORIGINS 填具体前端地址、ENABLE_DOCS=false（模板默认已关闭）
docker compose up -d --build
```

> 注意：`.env` 含生产密钥，禁止提交版本库或随安装包分发；仓库仅提供 `.env.example` 模板。
> 登出令牌黑名单已落库，多副本/重启均有效；过期记录在服务启动时自动清理。

访问：`http://<服务器IP>:8080`（端口可用 `.env` 中 `WEB_PORT` 修改），使用 `admin` 与 `.env` 中的密码登录。

健康检查：`curl http://localhost:8080/api/v1/health`。

### 初始化后的配置顺序

1. 「集成配置 - Zabbix」：填写地址与 API Token（或账密），点「连通性测试」。
2. 「集成配置 - 大模型」：至少启用一家并设为默认，填写 API Key，点「连通测试」；可启用多家形成降级链。
3. 「集成配置 - 日志平台」：按需启用 Graylog / Loki / ELK。
4. 「集成配置 - 通知渠道」：配置飞书/企业微信群机器人 Webhook 与加签密钥，点「测试发送」。
5. 「集成配置 - 分析参数」：设置自动分析开关、取数窗口、日志关键词与自动推送渠道。
6. 「集成配置 - VMware vCenter」（可选）：填写 vCenter 地址/端口/用户名/密码/证书校验，点「连通性测试」。配置后告警工作台将自动关联虚拟机信息。
7. 「CMDB」（可选）：填写 OneOps CMDB 地址、用户名、密码，点「连通性测试」。
8. 「IPAM 地址管理」（可选）：
   - 进入 IPAM 页签先创建 VLAN（可选），再创建网段（填写 CIDR、网关、用途，勾选/取消"自动扫描"）。
   - 网段创建后可点「立即扫描」触发一次，也可等每日 02:00 自动扫描。
   - 对固定 IP（服务器 / 打印机 / 网络设备）可进入地址明细手工登记责任人与用途。
   - 扫描检测到冲突（MAC 重复 / 已登记但扫描未在线）时，页面头部红色告警条自动浮现。
9. 在 Zabbix 动作/媒介中配置 Webhook：
   - URL：`http://<服务器IP>:8080/api/v1/webhooks/zabbix`
   - 头：`X-Webhook-Token: <ZABBIX_WEBHOOK_TOKEN>`（或 URL 加 `?token=<TOKEN>`）

## 二、切换 PostgreSQL（可选）

```bash
# .env 中设置：
# DATABASE_URL=postgresql+asyncpg://itops:itops_pass_change_me@postgres:5432/itops
docker compose --profile postgres up -d --build
```

表结构在服务启动时自动创建（SQLAlchemy `Base.metadata.create_all`），支持以下四张业务表：
- `alerts` / `reports` / `agents` / `configs` 等告警分析核心表
- **IPAM 四张表**：`vlans`、`subnets`、`ip_addresses`、`ip_change_logs`

新增列时（如 `alerts.host_ip`）通过 `database.py` 中的 `_PG_COLUMN_DDL` 增量补齐（`ALTER TABLE ADD COLUMN IF NOT EXISTS`），无需手动迁移。

SQLite 与 PostgreSQL 之间切换仅需改 `DATABASE_URL` 并重启，无额外迁移步骤（新建库场景）。若从 SQLite 迁移已有数据到 PostgreSQL，可导出后导入。

## 三、本地开发

```bash
# 后端（Python 3.11）
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest                         # 运行测试（61+ 个）
.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 前端（Node 22）
cd frontend
npm install
npm run dev                                        # http://localhost:5173，自动代理 /api
npm run build
```

## 四、运维说明

### 常规运维

- SQLite 数据位于 `itops-data` 数据卷（容器内 `/app/data/itops.db`），备份该卷即可。
- PostgreSQL 数据在外部 `DATABASE_URL` 指向的实例上，遵循该实例的备份策略。
- 所有第三方凭据均以 Fernet 加密存储；更换 `FERNET_KEY` 后旧密文无法解密，请固定该密钥。
- 查看日志：`docker compose logs -f backend` / `docker compose logs -f frontend`。

### 后台定时任务

| 任务 | 间隔 / 时刻 | 说明 |
| --- | --- | --- |
| Zabbix 告警同步 | 每 60 秒 | 拉取当前未恢复问题到本地 `alerts` 表；已不在 Zabbix 问题列表中的告警自动标记 `resolved`（含 `recovered_at`）。 |
| IPAM 自动扫描 | 北京时间每日 02:00 | 扫描所有 `subnets.auto_scan=true` 的网段；单个网段失败不阻塞其他网段；扫描结果入库 + 冲突检测 + 变更日志。 |

两个后台循环均在 `app/main.py` lifespan 中注册，容器退出时自动取消。

### IPAM 手工登记与扫描的交互

- **手工登记优先保留**：手工登记的 IP（`source=manual`）在扫描后若仍在线，状态置为 `used`；若扫描未发现在线，状态置为 `free` 但责任人/用途/备注保留，并由冲突检测标记"已登记但扫描未在线"。
- **扫描不会覆盖登记信息**：扫描只更新 `status` / `last_seen_at` / `mac` / `hostname` / `open_ports` / `response_ms`，不触碰 `assigned_to` / `purpose` / `remark`。
- **冲突自动消解**：释放手工登记后，下次扫描会自动消除对应冲突标记。

### 虚拟机列宽与排序

虚拟机管理页的列宽与列顺序持久化在浏览器 localStorage 中（key：`itops.vms.columnOrder`、`itops.vms.columnWidth`）。如需重置，点页面顶部「重置列设置」按钮即可恢复默认布局。

### 前端 nginx 缓存

nginx 配置静态资源 `expires 7d`，源码改动后 chunk hash 变化时浏览器会自动拉新；若需强制刷新，按 `Ctrl+F5` 或 DevTools 勾选 "Disable cache"。
