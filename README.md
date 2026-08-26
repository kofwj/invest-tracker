# Invest Tracker · 真仓账本

个人真仓记账：持仓、交易、银证现金、存款、日快照、收益与纪律。  
**不模拟、不自动下单**。草稿确认后才入账。

变更按日见 [CHANGELOG.md](CHANGELOG.md)。VPS 步骤见 [docs/deploy-vps.md](docs/deploy-vps.md)。

---

## 它做什么

本地或 VPS 上一份自己的账：

- **记清楚**：买了什么、证券现金多少、存款何时到期
- **对得上**：券商持仓 CSV/Excel 对账；银证流水 vs 组合投入/取出勾稽
- **看得懂**：今日贡献粗估、对大盘强弱、仓位是否偏离目标
- **管得住**：纪律破线、再平衡草稿、价格预警、短通知

**不是** 量化回测，也不是自动交易，更不会替你把银证转入写成组合投入。

---

## 页面

顶栏四组。默认进 **今日总览**。

| 组 | 页 | 路径 | 做什么 |
|----|----|------|--------|
| 总览 | 今日总览 | `/` | 总资产、浮盈、现金存款、近一周曲线、持仓预览 |
| 日常 | 持仓明细 | `/holdings` | 当前仓、家底、近一年收益、持仓校正 |
| | 交易录入/管理 | `/transactions` | 买卖/分红/草稿确认入账 |
| | 银行存款 | `/deposits` | 到期分布；年 / 到期前 / 整期利息 |
| 分析 | 今天该看 | `/decision` | 关键指标、今日看点、指数、持仓贡献、预警 |
| | 收益分析 | `/performance` | 整户总账、贡献分桶、时间线、组合投入/取出 |
| | 结构与目标 | `/allocation` | 目标尺子、配置诊断、纪律与再平衡草稿 |
| | K 线查询 | `/klines` | 日 K、均线解读、基本面、股东/分红 |
| 设置 | 消息推送 | `/ops/notify` | 通道密钥（库优先于 `.env`）、事件路由、试推 |
| | 证券账户 | `/cash` | 多账户费率、现金校准、银证流水、**银证勾稽** |
| | 数据备份 | `/ops/backup` | 备份 / 下载 / 恢复 / 上传 |

书签可进、导航里不单独成组：

| 页 | 路径 | 说明 |
|----|------|------|
| 券商对账 | `/broker` | 上传券商持仓表 → 差异 → 确认后写入持仓校正；预览/应用会留历史 |
| 资产快照 | `/snapshots` | 日终总资产曲线；可手录实盘总资产做误差对账 |

旧地址仍跳转：`/market` → 今天该看；`/discipline` → 结构与目标；`/maintenance` → 消息推送。

金额打码：`?mask=1` 或 `?screenshot=1`。主题：白天 / 夜间 / 跟随系统。

---

## 核心口径

三套数字本来就不会相等。对华泰等「累计盈亏」，优先看全周期。

| 口径 | 算法 | 用在哪 |
|------|------|--------|
| 持仓浮盈 | `(现价 − 普通成本) × 数量 + 累计分红` | 当前仓 |
| 全周期盈亏 | `(现价 − 摊薄成本) × 数量` | 接近券商累计盈亏 |
| 整户总账 | `总资产 − 组合外部净投入` | 收益分析；依赖组合资金流水 |
| 今日贡献 | `涨跌% × 市值` | 盘中参考，**不入账** |

### 交易怎么动账

| 方向 | 持仓 | 证券现金 |
|------|------|----------|
| 买入 | +数量 | −金额 − 费 |
| 卖出 | −数量 | +金额 − 费 |
| 分红 | 不变 | +现金 |
| 分红再投资 | +份额 | 不变（金额记累计分红） |
| 申购待确认 | 不进正式持仓 | −现金 |

费率在「证券账户」按账户、按品种设；录入时只是估算，**以券商成交单为准**。

### 两套现金流水

| 流水 | 记什么 | 在哪维护 |
|------|--------|----------|
| 银证流水 `cash_flows` | 银证转入/转出、现金校准 | 证券账户 |
| 组合流水 `portfolio_cash_flows` | 投入 / 取出（金额为正） | 收益分析 |

银证转入 **不会** 自动生成组合投入。收益分析有建议草稿；证券账户页会按 **同日、同额、同方向** 勾稽（容差 0.05），只标差、不入账。

### 券商对账

1. 券商 App 导出持仓 CSV / Excel（识别「证券代码 / 数量 / 成本价」等列）
2. 可选填券商证券现金
3. 上传预览差异；勾选后确认框会列出将改写的数量与成本
4. 写入「持仓校正」（先自动备份，再重扫）

每次预览和应用各留一条历史（schema v13 `broker_reconcile_runs`）。

### 存款利息

单利、365 天。

| 字段 | 含义 |
|------|------|
| 预计年利息 | 本金 × 年利率 |
| 到期前利息 | 本金 × 利率 × 剩余天数 / 365；已到期为 0 |
| 整期利息 | 起存日 → 到期日；缺起存日显示 — |

---

## 快速启动

### Docker（推荐）

```bash
cp .env.example .env
docker compose up -d --build
```

| | 地址 |
|--|------|
| 前端 | http://localhost:8080 |
| API | http://localhost:8000 |
| 健康检查 | http://localhost:8000/api/health |

```bash
make up / make down / make logs / make test / make check
```

开发 Compose 会给后端装测试依赖（`INSTALL_DEV=true`），所以 `make test` 能直接跑 pytest。

### 本机开发

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python backend/main.py
```

```bash
cd frontend && npm install && npm run dev
```

---

## 测试与 CI

```bash
# 后端
PYTHONPATH=backend python3 -m pytest tests/ -q

# 前端单测 + 生产构建
cd frontend && npm test && npm run build
```

GitHub Actions（`main` / `deploy/vps` / PR）：

- 后端：ruff `F,E9` + pytest
- 前端：vitest + `npm run build` + `npm audit --omit=dev`

---

## 生产部署

`main` 是源码真相；每次推 `main` 后 **fast-forward** `deploy/vps`。VPS 只跟 `deploy/vps`，不要在该分支上独自提交。

```bash
git pull origin deploy/vps
./scripts/deploy_vps.sh
# 或：docker compose -f docker-compose.prod.yml up -d --build
```

完整清单、HTTPS、GitHub OAuth、Cloudflare Tunnel： [docs/deploy-vps.md](docs/deploy-vps.md)。

公网至少做一件：

- 设 `INVEST_TRACKER_PASSWORD`（应用内门锁），和/或
- 走 Caddy → oauth2-proxy GitHub 登录（只放行一个 GitHub 用户）

生产建议再设：

```env
CRON_API_TOKEN=          # python3 -c 'import secrets; print(secrets.token_hex(24))'
CORS_ALLOW_ORIGINS=https://your-domain
```

未配 cron token 时，定时脚本仍会回退 `docker exec` / 登录 HTTP，旧部署不会立刻断。

### 定时任务

`scripts/cron_sync_prices.sh` 优先打 `POST /cron/*`（头 `X-Cron-Token`）。  
登录 Bearer **不能** 调 `/cron/*`；cron token **不能** 调用户接口。

```cron
20 15 * * 1-5 /path/to/invest-tracker/scripts/cron_sync_prices.sh >> /path/to/invest-tracker/backups/cron_sync_prices.log 2>&1
40 16 * * 1-5 /path/to/invest-tracker/scripts/cron_sync_prices.sh --snapshot --check-alerts >> /path/to/invest-tracker/backups/cron_sync_prices.log 2>&1
15 2  * * *   /path/to/invest-tracker/scripts/backup_daily.sh >> /path/to/invest-tracker/backups/backup_daily.log 2>&1
```

常用开关：`--snapshot`、`--check-alerts`、`--notify-alerts`、`--notify-events`、`--force-snapshot`。  
配好 token 后，手动试跑日志里应出现 `cron-http sync ok`。

---

## 消息推送

只发短通知（飞书 / 钉钉 / 企微 / Telegram），和 Hermes 长报告分开。

优先在 **设置 → 消息推送** 填密钥（存库，不回填明文；留空=不改，勾清除=删库值）。`.env` 的 `NOTIFY_*` 只作服务器兜底。

飞书支持两种：**Webhook**（机器人）或 **自建应用**（app_id + app_secret + 接收人 open_id，走消息 API）。配了自建应用就忽略 Webhook。

事件：价格预警、晚间简报、存款到期、纪律破线、运维、试推。

---

## 数据与安全

```bash
bash scripts/privacy_check.sh
python3 scripts/backup_db.py --label manual
python3 scripts/restore_db.py backups/你的备份.db
```

- `data/`、`backups/`、`.env` 不进 Git
- 可用 `DB_PATH`、`BACKUP_DIR`、`APP_TIMEZONE`、`CORS_ALLOW_ORIGINS` 覆盖
- 库 schema 版本见 `backend/schema.py`（当前 **v13**）；启动时自动迁移
- 上传上限：普通 CSV 20MB，券商 Excel 50MB；导出 CSV 会清洗公式注入前缀

---

## 仓库结构

```text
invest-tracker/
  backend/                 FastAPI + SQLite
    schema.py              版本迁移（当前 v13）
    routers_*.py           HTTP
    routers_cron.py        /cron/* ，独立 token
    broker_reconcile.py    券商对账 + 银证勾稽
  frontend/src/
    views/                 各页
    modules/               业务逻辑（非组件）
    components/            PageShell / MetricCard / 顶栏 / 弹窗
  tests/                   pytest
  frontend/tests/          vitest
  scripts/                 部署 / 备份 / cron / 隐私检查
  docs/deploy-vps.md
  docker-compose.yml       本地
  docker-compose.prod.yml  VPS
  .github/workflows/ci.yml
  data/  backups/          运行时，不入库
```

---

## 常见问题

**页面空白 / 弹窗没反应**  
硬刷新。确认前端已 rebuild。弹窗依赖 `appCtx` 里的 dialog state，不只是 open 函数。

**数字对不上券商**  
先看口径表。全周期 ≠ 持仓浮盈 ≠ 整户总账。持仓对不上就走 `/broker`；银证和组合投入对不上看证券账户页勾稽。

**backend unhealthy**

```bash
curl -fsS http://localhost:8000/api/health
```

**本地 pytest 环境不对**  
用装了依赖的解释器，或走 `make test`（容器内）。

**公网 CORS / 定时同步失败**  
生产把 `CORS_ALLOW_ORIGINS` 写成域名。cron 配 `CRON_API_TOKEN` 后看日志是否 `cron-http sync ok`。

---

## 许可证

个人真仓记账工具。公开仓库前请跑 `scripts/privacy_check.sh`，确认没有真实持仓、备份和密钥。
