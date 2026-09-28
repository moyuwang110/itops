# ITOPS 代码审查与优化记录

> 日期：2026-09-23
> 范围：后端（FastAPI + SQLAlchemy + httpx）+ 前端（Vue 3 + Element Plus）+ 测试基础设施
> 目标：识别架构与代码不合理之处，完成修复并记录

---

## 一、审查发现的问题与修复

### 1. httpx 客户端未复用（性能 + 资源泄漏）

**问题**：
- `ZabbixClient` 每次实例化都创建 `httpx.AsyncClient`，每次 RPC 建连/TLS 握手，高频查询下浪费资源。
- `LLMClient.chat` 每次调用都 `async with httpx.AsyncClient(...)`，同样反复建连。

**修复**：
- 改为**模块级共享 httpx 客户端**，所有 RPC/LLM 请求复用同一连接池。
- `ZabbixClient._rpc` 使用 `_shared_http.post(...)`，不再持有实例级客户端。
- `LLMClient.chat` 使用 `_shared_http.post(...)`，移除 `async with`。
- `zabbix_service` / `analysis_service` 不再需要 `async with` 包装客户端。

**文件**：
- [client.py](file:///data/ops/backend/app/integrations/zabbix/client.py)
- [client.py](file:///data/ops/backend/app/integrations/llm/client.py)
- [zabbix_service.py](file:///data/ops/backend/app/services/zabbix_service.py)
- [analysis_service.py](file:///data/ops/backend/app/services/analysis_service.py)

**注意**：共享客户端默认 `verify=True`。Zabbix 配置项中的 `verify_ssl` 不再生效（httpx 不支持 per-request `verify`）。生产环境若 Zabbix 使用自签名证书，需将共享客户端改为 `verify=False` 或按 verify 分组维护多客户端。

---

### 2. SQLite 路径解析不健壮

**问题**：`database.py` 用 hacky 的 `://://` marker 检测来区分 `sqlite+aiosqlite:///./x.db`（相对路径）和 `sqlite+aiosqlite:////x.db`（绝对路径），逻辑脆弱。

**修复**：用 `urllib.parse.urlparse` 标准库解析，新增 `_sqlite_db_path()` 函数正确提取路径，支持相对路径、绝对路径、内存库三种形式。

**文件**：[database.py](file:///data/ops/backend/app/core/database.py)

---

### 3. SQLite 连接池导致事务可见性竞态（测试基础设施）

**问题**：测试使用 `sqlite+aiosqlite:///:memory:` + `StaticPool`，所有 session 共享同一 DBAPI 连接。后台分析任务与 HTTP 请求交替使用该连接时，SQLite 的事务隔离导致测试请求看不到后台任务刚提交的数据（报告列表返回空）。这是**预先存在的缺陷**，在特定时序下暴露。

**修复**：
- 测试改用**文件型 SQLite**（`tempfile` 生成临时 `.db` 文件），配合 `NullPool`，每个 session 获得独立连接，由 SQLite 文件锁处理并发。
- `database.py`：文件型 SQLite 使用 `NullPool`，内存型仍用 `StaticPool`（必须，否则各连接数据库不共享）。

**文件**：
- [conftest.py](file:///data/ops/backend/tests/conftest.py)
- [database.py](file:///data/ops/backend/app/core/database.py)

---

### 4. 测试数据时间硬编码导致时间窗口断言失效

**问题**：`PROBLEM` 的 `datetime` 硬编码为 `2026-09-22 10:05:00`。Dashboard 的 `total_24h` 按 `occurred_at >= now-24h` 过滤，当测试运行时间超过该时刻 24 小时后，断言 `total_24h == 1` 必然失败。这是**预先存在的时间相关测试缺陷**。

**修复**：
- `PROBLEM.datetime` 改为动态生成（当前时间前 2 小时），确保始终落在 24h 窗口内。
- `test_report_list_time_filter` 的时间参数改为基于 `_alert_dt` 动态计算，不再依赖硬编码日期。

**文件**：
- [test_analysis.py](file:///data/ops/backend/tests/test_analysis.py)
- [test_api_flows.py](file:///data/ops/backend/tests/test_api_flows.py)

---

### 5. 登录接口缺少频率限制（安全）

**问题**：登录接口无频率限制，可被暴力破解。

**修复**：
- 新增 [rate_limit.py](file:///data/ops/backend/app/core/rate_limit.py)：`SlidingWindowRateLimiter` 滑动窗口限流器。
- 登录接口接入限流：每 IP 每分钟最多 5 次登录尝试，支持 `X-Forwarded-For` 头部识别真实 IP。
- 超限返回 `429 Too Many Requests`。
- 测试 `conftest.py` 每个用例前 `login_limiter.reset()`，避免跨用例触发限流。

**文件**：
- [rate_limit.py](file:///data/ops/backend/app/core/rate_limit.py)（新建）
- [auth.py](file:///data/ops/backend/app/api/v1/auth.py)
- [conftest.py](file:///data/ops/backend/tests/conftest.py)

---

### 6. analysis_service 指标上下文默认值缺失

**问题**：Zabbix 不可用时，`metric_ctx` 未初始化即被引用，可能导致 `NameError`。

**修复**：在 try 块前初始化 `metric_ctx` 为包含空结构的默认 dict，确保 Zabbix 降级时不报错。

**文件**：[analysis_service.py](file:///data/ops/backend/app/services/analysis_service.py)

---

## 二、前端审查结论

前端代码结构清晰，无重大问题：

| 模块 | 评估 |
|------|------|
| `utils/api.js` | axios 实例 + 拦截器处理 401/错误，合理 |
| `stores/auth.js` | Pinia store + localStorage 持久化，标准做法 |
| `router/index.js` | 路由守卫正确处理未登录跳转 |
| `views/*` | 页面组件划分合理，按需加载 |

**已完成的优化**：
- token 由 `localStorage` 改为 `httpOnly Cookie`，前端不再持有令牌，防 XSS 窃取。
- 后端 `get_current_user` 优先读 Cookie，回退 Authorization 头（兼容旧客户端）。
- 路由守卫改用 `username` 作为已登录快速判断（真正鉴权由后端 Cookie 校验）。

---

## 三、测试验证

```
backend $ python -m pytest -q
61 passed
```

连续运行 5 次全部通过，无偶发失败。

---

## 四、已完成的第二轮修复（2026-09-24）

上一轮"未修复项"已全部实施：

1. **共享 httpx 客户端生命周期** ✅
   - Zabbix/LLM 客户端均新增 `close_shared_clients()` 函数。
   - `main.py` lifespan 在 `yield` 后关闭所有共享客户端，释放连接资源。

2. **Zabbix `verify_ssl` 支持** ✅
   - 改用按 `verify_ssl` 分组的共享客户端池（`_shared_clients: dict[bool, AsyncClient]`）。
   - `_get_http_client(verify_ssl)` 按需创建/复用，自签名证书环境正常工作。

3. **前端 token 改用 httpOnly Cookie** ✅
   - 登录接口设置 `httpOnly` + `samesite=lax` Cookie（`secure` 由 `COOKIE_SECURE` 配置控制）。
   - 前端 `api.js` 移除 Authorization 头注入，启用 `withCredentials`。
   - `auth.js` 不再读写 localStorage token，仅缓存用户名。
   - 登出清除 Cookie。
   - 新增 `cookie_secure` 配置项（默认 false，适配 nginx HTTP 反代）。

### 改动文件清单（第二轮）

| 文件 | 改动类型 |
|------|----------|
| `backend/app/main.py` | lifespan 关闭共享 httpx 客户端 |
| `backend/app/core/config.py` | 新增 `cookie_secure` 配置 |
| `backend/app/api/deps.py` | `get_current_user` 优先读 Cookie |
| `backend/app/api/v1/auth.py` | 登录设置 Cookie、登出清除 Cookie |
| `backend/app/integrations/zabbix/client.py` | 按 verify_ssl 分组共享客户端 + close 函数 |
| `backend/app/integrations/llm/client.py` | 新增 close 函数 |
| `frontend/src/utils/api.js` | 移除 token 注入，启用 withCredentials |
| `frontend/src/stores/auth.js` | 不再读写 localStorage token |
| `frontend/src/router/index.js` | 守卫改用 username 判断 |

---

## 五、后续建议（剩余）

1. **生产环境数据库**：SQLite + NullPool 适合开发/小规模部署，生产环境建议使用 PostgreSQL。
2. **请求重试与取消**：前端可增加请求重试与取消机制，提升弱网体验。
3. **COOKIE_SECURE**：若部署启用 HTTPS，建议设置 `COOKIE_SECURE=true`。
