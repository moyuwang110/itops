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
6. 在 Zabbix 动作/媒介中配置 Webhook：
   - URL：`http://<服务器IP>:8080/api/v1/webhooks/zabbix`
   - 头：`X-Webhook-Token: <ZABBIX_WEBHOOK_TOKEN>`（或 URL 加 `?token=<TOKEN>`）

## 二、切换 PostgreSQL（可选）

```bash
# .env 中设置：
# DATABASE_URL=postgresql+asyncpg://itops:itops_pass_change_me@postgres:5432/itops
docker compose --profile postgres up -d --build
```

表结构在服务启动时自动创建。SQLite 与 PostgreSQL 之间切换仅需改 `DATABASE_URL` 并重启，无额外迁移步骤（新建库场景）。

## 三、本地开发

```bash
# 后端（Python 3.11）
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest                         # 运行测试（61 个）
.venv/bin/python -m uvicorn app.main:app --reload --port 8000

# 前端（Node 22）
cd frontend
npm install
npm run dev                                        # http://localhost:5173，自动代理 /api
npm run build
```

## 四、运维说明

- SQLite 数据位于 `itops-data` 数据卷（容器内 `/app/data/itops.db`），备份该卷即可。
- 所有第三方凭据均以 Fernet 加密存储；更换 `FERNET_KEY` 后旧密文无法解密，请固定该密钥。
- 查看日志：`docker compose logs -f backend` / `docker compose logs -f frontend`。
