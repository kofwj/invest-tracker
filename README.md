# Invest Tracker · 真仓账本

> 更新：2026-07-26  
> 个人真仓投资账本：持仓、交易、现金/存款、日快照、收益与纪律。  
> **不模拟、不自动下单**；草稿确认后才入账。  
> 变更明细见 [CHANGELOG.md](CHANGELOG.md)。

---

## 它是什么

本地 / VPS 可跑的 **真仓账本**，用来：

- 记清楚：买了什么、现金多少、存款何时到期
- 看清楚：今天赚亏粗估、对大盘强弱、仓位是否偏了
- 管得住：纪律破线、再平衡草稿、价格预警、多通道短通知

**不是** 量化回测平台，也不是自动交易。

---

## 页面结构（顶栏四大组）

| 组 | 页 | 做什么 |
|----|----|--------|
| **总览** | 今日总览 | 总资产 / 当日参考 / 浮盈 / 现金存款；**近一周资产曲线**；持仓预览与状态 |
| **日常** | 持仓明细 | 当前仓、家底卡、近一年收益、UZI 本地分析入口 |
| | 交易录入/管理 | 买卖/分红/草稿确认入账 |
| | 银行存款 | 到期分布、年/到期前/整期利息 |
| **分析** | 今天该看 | 左 12 项关键指标；右 **今日看点** + 指数 + 持仓贡献；自选与价格预警 |
| | 收益分析 | 主结论 + 贡献（**债基 / REITs / 权益** 分桶）+ 时间线 |
| | 结构与目标 | 右栏一键三套目标尺子；配置诊断主结论+偏离；同质化/流动性/情景；纪律与草稿 |
| **设置** | 消息推送 | 通道开关、事件路由、**页面可配密钥**（库优先于 `.env`）、试推与日志 |
| | 证券账户 | 费率 + 现金校准 + 银证流水 + 与组合投入勾稽 |
| | 数据备份 | 备份 / 恢复 / 上传 |

旧路由仍可跳转：`/market` → 今天该看；`/discipline` → 结构与目标；`/maintenance` → 消息推送。  
隐藏页（书签可进）：资产快照、券商对账（预览/应用会留历史，应用前确认数量与成本）。

金额打码仅 `?mask=1`（或 `?screenshot=1`）。

---

## 近期更新（2026-07）

| 方向 | 要点 |
|------|------|
| 导航 | 顶栏四组 + 二级 pill；默认进 **今日总览**；去掉侧栏与口号 |
| 总览 | 右上改为 **近一周资产曲线**；主题跟随系统/白天/夜间，不再硬锁黑底 |
| 今天该看 | 决策+市场合并；看点置右上；关键指标补到 12 卡（对大盘、仓位、最强最弱等） |
| 结构与目标 | 配置+纪律合并；`/allocation/story` 政策同源诊断；扇形图防叠字；夜间字色跟主题 |
| 收益 | 大类拆成 **债基 / REITs / 权益**；主结论加粗；夜间可读 |
| 设置 | 「维护」改名；推送密钥可在页面填（不回填明文）；证券账户归设置组 |
| 视觉 | 克制青绿主色；MetricCard 统一；日夜 token；表格只做对齐密度 |

完整按日记录见 [CHANGELOG.md](CHANGELOG.md)。

---

## 技术栈

- 后端：FastAPI + SQLite（`schema` 版本迁移）
- 前端：Vite + Vue 3 + Element Plus + ECharts + vue-router
- 部署：Docker Compose（前端 Nginx，后端 Uvicorn）

---

## 快速启动

### Docker（推荐）

```bash
cd invest-tracker
cp .env.example .env   # 按需改密码等
docker compose up -d --build
```

- 前端：http://localhost:8080  
- API：http://localhost:8000  
- 健康：http://localhost:8000/api/health  

```bash
make up / make down / make logs / make test / make check
```

### 本机开发

```bash
# 后端（含测试依赖）
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python backend/main.py

# 前端（另开终端）
cd frontend && npm install && npm run dev
```

后端测试：

```bash
PYTHONPATH=backend /usr/bin/python3 -m pytest tests/ -q
# 当前约 152 passed
```

前端单测：

```bash
cd frontend && npm test
# vitest（utils / K线均线解读等纯逻辑）
```

---

## VPS 生产

生产配置在分支 **`deploy/vps`**，步骤见 [docs/deploy-vps.md](docs/deploy-vps.md)。

更新常见流程：

```bash
git pull origin deploy/vps
docker compose -f docker-compose.prod.yml up -d --build
```

浏览器硬刷新。公网务必设 `INVEST_TRACKER_PASSWORD` 和/或 GitHub OAuth（见 `.env.example`）。

---

## 核心口径（对账用）

| 口径 | 含义 |
|------|------|
| 持仓浮盈 | (现价 − 普通成本) × 数量 + 累计分红 → **当前仓** |
| 全周期盈亏 | (现价 − 摊薄成本) × 数量 → 接近券商「累计盈亏」 |
| 整户总账 | 总资产 − 组合外部净投入 → 收益分析页，依赖组合资金流水 |
| 今日贡献粗估 | 涨跌% × 市值 → **不入账**，只作盘中参考 |

三套数字本来就不会相等；对华泰等累计，优先看全周期。

### 存款利息

| 字段 | 含义 |
|------|------|
| 预计年利息 | 本金 × 年利率（再放满一年） |
| 到期前利息 | 本金 × 利率 × 剩余天数 / 365；已到期为 0 |
| 整期利息 | 起存日→到期日；缺起存日显示 — |

单利、365 天。

### 常用交易方向

| 方向 | 持仓 | 证券现金 |
|------|------|----------|
| 买入 | +数量 | −金额−费 |
| 卖出 | −数量 | +金额−费 |
| 分红 | 不变 | +现金 |
| 分红再投资 | +份额 | 不变（金额记累计分红） |
| 申购待确认 | 不进正式持仓 | −现金 |

**银证转账不会自动生成「组合投入」流水**；需要时在收益分析用建议草稿。证券账户页会按同日同额勾稽银证转入/转出与组合投入/取出，标出未配对差额。

---

## 消息推送

与 Hermes 长报告分开：本系统只发 **短通知**（飞书 / 钉钉 / 企微 / Telegram）。

- **优先**在网页「设置 → 消息推送」填密钥（存库，不回填明文；留空=不改，勾清除=删库值）
- `.env` 仍可作服务器兜底（见 `.env.example`）
- 事件：价格预警、晚间简报、存款到期、纪律破线、运维、试推

---

## 项目结构（精简）

```text
invest-tracker/
  backend/           # FastAPI：schema / dashboard / market / performance / notify / routers_*
  frontend/src/
    views/           # Overview / Decision / Performance / Allocation / Holdings …
    modules/         # tabNav / market / discipline / snapshots …
    components/      # PageShell / MetricCard / AppHeader / AppDialogs
    charts/          # ECharts（跟主题 token）
  tests/             # pytest
  scripts/           # check / backup / restore / cron 价同步
  docs/deploy-vps.md
  docker-compose.yml
  docker-compose.prod.yml
  data/              # SQLite，不入库
  backups/           # 备份，不入库
```

---

## 数据与安全

```bash
bash scripts/privacy_check.sh
python3 scripts/backup_db.py
python3 scripts/restore_db.py backups/你的备份.db
```

- `data/`、`backups/`、`.env` 不进 Git  
- 可用 `DB_PATH`、`BACKUP_DIR`、`APP_TIMEZONE`、`CORS_ALLOW_ORIGINS` 覆盖  
- 公网：设密码门锁和/或 OAuth；生产 CORS 写死域名  

隐藏界面金额：`?mask=1`。

---

## 常见问题

**页面空白 / 弹窗无反应**  
硬刷新；确认前端已 rebuild。弹窗依赖 `appCtx` 提供的 **dialog state**（不只 open 函数）。

**总览一直黑**  
顶栏主题切「白天 / 跟随系统」；新版本默认跟 token，仅夜间加深。

**数字对不上券商**  
先看口径表；全周期 ≠ 持仓浮盈 ≠ 整户总账。

**backend unhealthy**  

```bash
curl http://localhost:8000/api/health
```

**本地 pytest** 请用系统 Python：

```bash
PYTHONPATH=backend /usr/bin/python3 -m pytest tests/ -q
```

---

## 许可证与用途

个人真仓记账工具。公开仓库前请跑隐私检查，并确认无真实持仓/密钥。
