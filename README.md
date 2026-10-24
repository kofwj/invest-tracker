<h1 align="center">Invest Tracker · 真仓账本</h1>

<p align="center">
  <strong>严肃的个人真仓记账：本地唯一账本，不给别人管，更不让数字变旧。</strong>
</p>

<p align="center">
  持仓对账 · 银证勾稽 · 总资产校准平差 · 收益日快照 · 纪律预警 · 双轨心跳监控<br />
  <strong>不模拟、不自动下单、不写双本账</strong>。草稿确认后入账，手机只做 PWA 终端。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Vue-3-4FC08D?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue 3" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/SQLite-WAL%20(v22)-003B57?style=for-the-badge&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/PWA-Ready-5A0FC8?style=for-the-badge&logo=pwa&logoColor=white" alt="PWA" />
  <img src="https://img.shields.io/badge/License-AGPL--3.0-1f6feb?style=for-the-badge" alt="AGPL-3.0" />
</p>

<p align="center">
  <img src="https://img.shields.io/github/stars/kofwj/invest-tracker?style=flat-square&color=ffd33d&logo=github" alt="Stars" />
  <img src="https://img.shields.io/github/forks/kofwj/invest-tracker?style=flat-square&color=8957e5&logo=github" alt="Forks" />
  <img src="https://img.shields.io/github/last-commit/kofwj/invest-tracker?style=flat-square&color=3fb950&logo=github" alt="Last commit" />
  <img src="https://img.shields.io/badge/Tests-636%20backend%20%7C%20249%20frontend-3fb950?style=flat-square" alt="Tests" />
</p>

<p align="center">
  <strong>简体中文</strong> · <a href="CHANGELOG.md">更新日志</a> · <a href="docs/deploy-vps.md">VPS 部署</a> · <a href="docs/desktop.md">桌面版指南</a> · <a href="docs/android-feasibility.md">手机端路线</a>
</p>

---

> [!NOTE]
> 这是个人严肃真仓记账工具。坚持**中心唯一账本原则**：数据落在本地 SQLite（或个人私有 VPS），手机端作为 PWA 客户端访问，不在端侧做双向写入与 CRDT 同步，确保资产数字永远对齐。

## 这是什么

不是那种把模拟盘当真仓的玩具，不是自动下单的黑盒量化软件，更不是多端各自存一份 SQLite 的同步噩梦。

它是属于你自己的**真仓财务底座**：

```
┌────────────────────────────────────────────────────────────────────────┐
│                        中心唯一账本 (VPS / 本地服务)                    │
│   SQLite (WAL, schema v22) ── 真实资产与历史快照的单一真相来源        │
└───────────┬────────────────────────────────────────────────┬───────────┘
            │                                                │
   ┌────────┴───────────────────────────┐           ┌────────┴──────────────┐
   │ 终端接入 (只读呈现 / 确认动账)     │           │ 定时流水线 (Cron / 监控)│
   ├────────────────────────────────────┤           ├───────────────────────┤
   │ • 桌面端 (Tauri 2 原生打包)        │           │ • 15:20 交易日行情同步│
   │ • 浏览器 (PC 宽屏三栏工作台)       │           │ • 16:40 净值快照+闸门 │
   │ • 手机端 (PWA 离线底座+网络优先)   │           │ • 02:15 账本自动备份  │
   └────────────────────────────────────┘           └───────────┬───────────┘
                                                                │
                                            ┌───────────────────┴───────────┐
                                            │ 双轨心跳 (失败自报警)         │
                                            │ • 对外: dead-man URL ping     │
                                            │ • 对内: 飞书/钉钉/企微/TG 逾期 │
                                            └───────────────────────────────┘
```

- **记清楚**：买了什么、证券现金多少、存款何时到期。
- **对得上**：
  - **券商对账**：导入券商 CSV / Excel 比对持仓股数与成本；
  - **银证勾稽**：银证转账流水 vs 组合外部资金投入同日同向同额自动勾稽；
  - **总资产校准平差**：实盘与账面总资产差额单独立账，看得见哪天开始歪的，不毁坏历史持仓。
- **看得懂**：今日贡献粗估、对大盘强弱、仓位是否偏离目标。
- **管得住**：纪律破线、再平衡草稿、价格预警、短通知推送。
- **静默失败克星**：流水线自带心跳；一旦没跑成，自动通过消息通知甚至外部 dead-man 开关（如 healthchecks.io）把人喊醒。

---

## 快速开始

### 推荐：Docker 部署（VPS / 局域网）

一行启动，开箱即用：

```bash
git clone https://github.com/kofwj/invest-tracker.git
cd invest-tracker
cp .env.example .env
docker compose up -d --build
# → 前端 http://localhost:8080 | 后端 API http://localhost:8000
```

<details>
<summary>本地单进程运行（最省事，不用 Docker）</summary>

不需要 Docker：后端一个进程同时提供接口和前端页面，占用一个端口：

```bash
git clone https://github.com/kofwj/invest-tracker.git && cd invest-tracker
python3 -m venv venv && source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..
python backend/main.py
```

浏览器会自动打开 <http://127.0.0.1:8000>（`INVEST_TRACKER_NO_BROWSER=1` 可关闭自动打开）。

同一局域网设备（如手机）访问：
```bash
HOST=0.0.0.0 PORT=8000 INVEST_TRACKER_PASSWORD=你的密码 python backend/main.py
```
</details>

<details>
<summary>本地全栈开发环境</summary>

前后端分离调试热更新：

```bash
# 后端
python3 -m venv venv && source venv/bin/activate
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python backend/main.py

# 前端 (开新终端)
cd frontend && npm install && npm run dev
# → 前端开发页 http://localhost:5173
```
</details>

<details>
<summary>macOS 原生桌面应用（Tauri 2 壳 + PyInstaller 侧车）</summary>

双击即用，内置 Python 独立后端，不污染系统环境：

```bash
bash scripts/build-desktop.sh     # 产物在 src-tauri/target/release/bundle/
```
细节与限制见 [docs/desktop.md](docs/desktop.md)。
</details>

<details>
<summary>手机端 PWA 终端使用</summary>

不推荐在手机跑后台服务或放 SQLite（见 [docs/android-feasibility.md](docs/android-feasibility.md)）。

手机浏览器打开你的部署地址（需 HTTPS），在菜单中选择 **「添加到主屏幕」**，即可像原生 App 一样全屏沉浸使用（网络优先，离线时保留安全底座）。
</details>

---

## 怎么用

顶栏分为四组，默认进入 **今日总览**。进系统后从上往下看：

| 组别 | 页面 | 路由 | 核心功能 |
|------|------|------|----------|
| **总览** | **今日总览** | `/` | 今天赚了多少 / 本月 / 今年 + 待办；资产分布与仓位比例；净值曲线；总资产校准状态提醒 |
| **日常** | **持仓明细** | `/holdings` | 当前持仓、成本与浮盈、持仓校正、手动改价；**点标的名看 K 线与基本面**；顶部「除权除息日历」列近 30 天排期 |
| | **交易录入** | `/transactions` | 买入 / 卖出 / 分红 / 草稿确认入账（草稿确认前绝自动动账） |
| | **银行存款** | `/deposits` | 存款明细、到期分布；预计年利息 / 到期前利息 / 整期利息 |
| | **券商对账** | `/broker` | 导入券商持仓表 → 差异对比 → 确认后写入持仓校正（留存历史记录） |
| **分析** | **今天该看** | `/decision` | 市场结论、持仓今日贡献、破线条数、自选观察与预警 |
| | **收益与快照** | `/performance` | 逐日收益率曲线 + 快照明细 + 风险指标 + 组合资金投入/取出记录 |
| | **结构与目标** | `/allocation` | 看现状 / 设目标 / 处理偏离（目标尺子、配置诊断、纪律与再平衡草稿） |
| **设置** | **消息推送** | `/ops/notify` | 通道密钥配置（飞书 / 钉钉 / 企微 / Telegram）、事件路由、一键测试 |
| | **证券账户** | `/cash` | 多账户费率、现金校准、银证流水、**银证流水与组合投入自动勾稽** |
| | **数据备份** | `/ops/backup` | 备份 / 下载 / 恢复 / 上传；**顶部 Q0 流水线心跳卡片（哪条多久没成功）** |

*快捷功能*：
- **金额打码**：URL 追加 `?mask=1` 或 `?screenshot=1` 隐藏敏感金额。
- **界面主题**：白天 / 夜间 / 跟随系统。
- **路由重定向**：`/market` → `/decision`；`/discipline` → `/allocation`；`/maintenance` → `/ops/notify`；`/snapshots` → `/performance`；`/klines` → `/holdings`。

---

## 核心口径与对账设计

记账的底线是数字对得上。三套数字本来就不会相等：

### 1. 三套收益口径

| 口径 | 算法 | 用在哪 | 适用场景 |
|------|------|--------|----------|
| **持仓浮盈** | `(现价 − 普通成本) × 数量 + 累计分红` | 当前仓 | 看当前持仓赚钱还是亏钱 |
| **全周期盈亏** | `(现价 − 摊薄成本) × 数量` | 收益与明细 | 最接近华泰等券商的「累计盈亏」 |
| **整户总账** | `总资产 − 组合外部净投入` | 收益与快照 | 站在投资者口袋角度算真金白银绝对回报 |
| *今日贡献* | `涨跌% × 市值` | 盘中决策 | **仅供盘中参考，不入账** |

### 2. 日期与时区

- 全局只有一把"今天"：`APP_TIMEZONE`（默认 `Asia/Shanghai`）。换机器、换浏览器时区都不会漂移。
- 选历史区间看收益时，以**该区间末的最后一条快照**为期末（日期、资产、现金流同一口径）。
- 月度收益剔除区间内的外部投入/取出，转入的钱不会被算成"当月投资收益"。
- 同一天的现金流水与快照以 `created_at` 判定先后：快照之后转入的钱不计入当日收益。

### 3. 交易动账规则

| 方向 | 持仓变动 | 证券现金变动 | 备注 |
|------|----------|--------------|------|
| **买入** | +数量 | −金额 − 费用 | |
| **卖出** | −数量 | +金额 − 费用 | |
| **分红** | 不变 | +现金 | 增加可用现金 |
| **分红再投资** | +份额 | 不变 | 增加份额，金额计入累计分红 |
| **申购待确认** | 不进正式持仓 | −现金 | 确认份额后转为正式持仓 |

### 4. 两套现金流水与自动勾稽

| 流水类别 | 记录内容 | 维护页面 |
|----------|----------|----------|
| **银证流水** `cash_flows` | 银证转入/转出、现金校准 | 证券账户 (`/cash`) |
| **组合流水** `portfolio_cash_flows` | 外部真金白银投入 / 取出 | 收益与快照 (`/performance`) |

银证转入 **不会** 自动伪造为投资组合投入。证券账户页会按 **同日、同额、同方向（容差 0.05）** 自动勾稽，只标差、不入账，杜绝虚增收益。

### 5. 总资产校准平差（净值对齐的最后一道）

持仓管股数与成本，现金校准管证券现金，两样都对了，仍可能因打新冻结、在途资金、汇率折算与券商 App **总资产**有微小出入：

- 总览「现在总资产」下方展示：**距上次校准 N 天 · 上次差额 Y 元**。
- 差额记成一条**独立的平差余额**（表 `total_asset_calibrations`，schema **v22**），不摊回持仓、不摊回流水，「从哪天开始歪的」留在原地。
- 平差自动计入 `total_assets`，看板与日终快照同时对齐实盘，消除两本账。
- 重新校准自动收敛：`新平差 = 旧平差 + (实测 − 显示)`，显示值已含旧平差，不会重复叠加。

### 6. 流水线心跳监控（失败会自己喊）

最危险的失效是**任务根本没跑**（crontab 丢失、服务器断电、容器挂掉）：

| 流水线任务 | 触发方式 | 默认超时阈值 |
|------------|----------|--------------|
| `backup` | `scripts/backup_daily.sh` 备份脚本 | 30 小时（容一次重跑） |
| `sync_prices` | `/cron/sync-prices`、手动同步、Docker 直调 | 96 小时（抗四天长假） |
| `snapshot` | `/cron/snapshot` 日终快照 | 96 小时 |

- **对内逾期检查**：挂在 `/cron/notify-events` 上，超时自动走消息推送的 `ops` 通道报警，**无需改动 crontab**。运维页顶部实时标色。
- **对外 dead-man 报警**：成功时 ping `HEARTBEAT_<JOB>_URL`（如 healthchecks.io），失败刻意不 ping，整机宕机外部监控也会超时自报警。

---

## 诚实的局限

- **绝不碰实盘自动交易**：不托管交易账号密码，不提供自动下单 API。所有交易录入均为草稿确认制，确保资金安全。
- **公共行情源有一定延迟**：行情抓取依赖公开接口（akshare 等），盘中分时估算仅作参考，日终快照以收盘清算价为准；节假日按内置与更新日历休市。
- **单账本原则拒绝端侧双向写入**：不在手机本地跑 Python 后端或 SQLite 数据库。手机只做 PWA 终端，服务器是唯一真理来源，避免两份数据库产生冲突（见 [docs/android-feasibility.md](docs/android-feasibility.md)）。
- **备份副本包含敏感配置**：备份文件受操作系统权限 `0600` 保护。若将 `.db.bak` 发送给他人或上传公共平台，必须先清除 `settings` 表中的推送 Token 与 AI Key。

---

## 生产部署与定时任务

生产环境以 `deploy/vps` 分支为准，`main` 是源码真相：

```bash
git pull origin deploy/vps
./scripts/deploy_vps.sh
```

公网建议安全配置：
1. 启用 `INVEST_TRACKER_PASSWORD` 页面门锁，或配置 Caddy + oauth2-proxy GitHub 单用户授权。
2. 配置 `CRON_API_TOKEN` 保护定时任务端点。
3. 限制 `CORS_ALLOW_ORIGINS=https://你的域名`。

### 推荐 Crontab 定时配置

```cron
# 交易日 15:20 同步行情
20 15 * * 1-5 /path/to/invest-tracker/scripts/cron_sync_prices.sh >> /path/to/invest-tracker/backups/cron_sync_prices.log 2>&1

# 交易日 16:40 生成日终资产快照并检查告警
40 16 * * 1-5 /path/to/invest-tracker/scripts/cron_sync_prices.sh --snapshot --check-alerts >> /path/to/invest-tracker/backups/cron_sync_prices.log 2>&1

# 每日 02:15 账本自动备份与心跳上报
15 2  * * *   /path/to/invest-tracker/scripts/backup_daily.sh >> /path/to/invest-tracker/backups/backup_daily.log 2>&1
```

---

## 数据与隐私安全

```bash
bash scripts/privacy_check.sh                     # 提交开源前隐私自检
python3 scripts/backup_db.py --label manual       # 手动备份账本
python3 scripts/restore_db.py backups/你的备份.db  # 恢复账本
```

### 1. 数据存放在哪

单进程本地运行时，账本存储在系统标准数据目录（**不在仓库代码目录，`git clean` 删不掉**）：
- **macOS**: `~/Library/Application Support/InvestTracker/data/invest.db`
- **Windows**: `%APPDATA%\InvestTracker\data\invest.db`
- **Linux**: `${XDG_DATA_HOME:-~/.local/share}/InvestTracker/data/invest.db`

优先级：`DB_PATH` > `INVEST_TRACKER_HOME` > 系统默认路径。

### 2. 联网行为透明说明

| 出网请求 | 携带内容 | 默认状态 |
|----------|----------|----------|
| **行情 / K 线 / 基本面** | 仅发送股票/基金代码，**不发持仓与金额** | 开启 |
| **消息推送** (`/ops/notify`) | 仅推送到你自己配置的 Webhook 或机器人 | 需手动配置 |
| **AI 投资简报** (`AI_ENABLED`) | **会把持仓明细和盈亏金额发送给所配的大模型服务** | **默认关闭** |

---

## 测试与发版

严谨的质量自检体系保证每次重构与迁移万无一失：

```bash
# 后端单测
PYTHONPATH=backend pytest -q tests/               # 636 passed

# 前端单测与编译
cd frontend && npm test && npm run build          # 249 passed, 31 文件全绿

# 全仓库健康与路由拓扑自检
bash scripts/check.sh                             # All checks passed
```

### 发版同步核对表

版本号单一来源为 `backend/version.py`，发布时以下位置需保持对齐：

| 文件 | 键值 | 说明 |
|------|------|------|
| [backend/version.py](backend/version.py) | `APP_VERSION = "1.7.3"` | 单一真相来源 |
| [frontend/public/sw.js](frontend/public/sw.js) | `const CACHE_NAME = 'invest-tracker-v1.7.3'` | PWA 缓存控制 |
| [src-tauri/tauri.conf.json](src-tauri/tauri.conf.json) | `"version": "1.7.3"` | 桌面安装包版本 |
| [src-tauri/Cargo.toml](src-tauri/Cargo.toml) | `version = "1.7.3"` | Rust crate 版本 |
| [src-tauri/Cargo.lock](src-tauri/Cargo.lock) | `version = "1.7.3"` (`invest-tracker`) | 保证 `cargo check --locked` 通过 |

---

## 仓库结构

```text
invest-tracker/
├── backend/
│   ├── app_paths.py           # 数据目录解析 / 迁移逻辑
│   ├── schema.py              # SQLite 数据库版本迁移 (v22)
│   ├── heartbeat.py           # 流水线心跳与 dead-man 机制
│   ├── total_asset_calibration.py # 总资产校准与平差立账
│   ├── broker_reconcile.py    # 券商持仓对账与银证勾稽
│   ├── routers_*.py           # FastAPI 业务路由
│   └── routers_cron.py        # /cron/* 独立 Token 鉴权接口
├── frontend/
│   ├── src/views/             # 业务页面 (总览 / 持仓 / 收益等)
│   ├── src/components/        # PageShell、CalibrationHint、MetricCard 等
│   └── tests/                 # Vitest 前端单元测试 (249 项)
├── tests/                     # Pytest 后端测试套件 (636 项)
├── scripts/                   # 部署 / 备份 / 心跳 / 自检脚本
├── src-tauri/                 # Tauri 2 原生桌面壳
└── docs/                      # 架构决策与运维文档
```

---

## 常见问题

**Q: 页面显示空白或弹窗无反应？**  
A: 执行强力刷新（Ctrl+F5 / Cmd+Shift+R），确认前端已完成构建。

**Q: 记账数字与券商 App 对不上？**  
A: 请核对「核心口径」部分，券商常见的“累计盈亏”通常对应本系统的“全周期盈亏”。持仓股数与成本有出入请使用 `/broker` 对账，整户总资产微小出入使用「总资产校准」平差。

**Q: 怎么进行数据迁移或还原？**  
A: 只要将备份的 `.db` 文件放入对应数据目录并命名为 `invest.db`，重启服务即可自动完成迁移。

---

## 许可证

本项目基于 [AGPL-3.0 License](LICENSE)（GNU Affero General Public License v3.0）开源。

你可以自由使用、修改与部署。若将修改后的版本作为网络服务提供给他人访问，必须同样开源其修改后的全部源代码。商业闭源使用请单独洽谈授权。
