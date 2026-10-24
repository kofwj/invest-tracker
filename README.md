# Invest Tracker · 真仓账本

个人真仓记账：持仓、交易、银证现金、存款、日快照、收益与纪律。  
**不模拟、不自动下单**。草稿确认后才入账。

变更按日见 [CHANGELOG.md](CHANGELOG.md)。VPS 步骤见 [docs/deploy-vps.md](docs/deploy-vps.md)。
桌面应用（Tauri 壳、打包与 dev 模式）见 [docs/desktop.md](docs/desktop.md)。
界面规范与 Figma 上手见 [docs/design/](docs/design/)（`figma-handoff.md` 规范与逐页清单、
`figma-basics.md` 操作速成、`page-performance-layers.md` 图层树）。

---

## 它做什么

本地或 VPS 上一份自己的账：

- **记清楚**：买了什么、证券现金多少、存款何时到期
- **对得上**：券商持仓 CSV/Excel 对账；银证流水 vs 组合投入/取出勾稽；总资产实测校准（差额单独立账）
- **看得懂**：今日贡献粗估、对大盘强弱、仓位是否偏离目标
- **管得住**：纪律破线、再平衡草稿、价格预警、短通知

**不是** 量化回测，也不是自动交易，更不会替你把银证转入写成组合投入。

---

## 页面

顶栏四组。默认进 **今日总览**。

| 组 | 页 | 路径 | 做什么 |
|----|----|------|--------|
| 总览 | 今日总览 | `/` | 今天赚了多少 / 本月 / 今年 + 待办；资产与仓位；曲线与持仓预览；距上次总资产校准几天 / 上次差额 |
| 日常 | 持仓明细 | `/holdings` | 当前仓、家底、近一年收益、持仓校正、手动改价；**点标的名看 K 线与基本面**；顶部「除权除息日历」列近 30 天已排期的除权除息 |
| | 交易录入/管理 | `/transactions` | 买卖/分红/草稿确认入账 |
| | 银行存款 | `/deposits` | 到期分布；年 / 到期前 / 整期利息 |
| | 券商对账 | `/broker` | 上传券商持仓表 → 差异 → 确认后写入持仓校正；预览/应用会留历史 |
| 分析 | 今天该看 | `/decision` | 市场结论、持仓今日贡献、破线条数（明细在结构与目标）、观察与预警 |
| | 收益与快照 | `/performance` | 逐日收益 + 快照明细 + 人工对账 + 风险 + 组合投入/取出（原「收益分析」与「资产快照」已合并到这一页） |
| | 结构与目标 | `/allocation` | 看现状 / 设目标 / 处理偏离（目标尺子、配置诊断、纪律与再平衡草稿） |
| 设置 | 消息推送 | `/ops/notify` | 通道密钥（库优先于 `.env`）、事件路由、试推 |
| | 证券账户 | `/cash` | 多账户费率、现金校准、银证流水、**银证勾稽** |
| | 数据备份 | `/ops/backup` | 备份 / 下载 / 恢复 / 上传；顶部流水线心跳（哪条多久没成功） |

旧地址仍跳转：`/market` → 今天该看；`/discipline` → 结构与目标；`/maintenance` → 消息推送；
`/snapshots` → 收益与快照（资产快照已并入）；`/klines` → 持仓明细（K 线已降级为点标的名打开的弹窗）。

金额打码：`?mask=1` 或 `?screenshot=1`。主题：白天 / 夜间 / 跟随系统。

---

## 核心口径

三套数字本来就不会相等。对华泰等「累计盈亏」，优先看全周期。

| 口径 | 算法 | 用在哪 |
|------|------|--------|
| 持仓浮盈 | `(现价 − 普通成本) × 数量 + 累计分红` | 当前仓 |
| 全周期盈亏 | `(现价 − 摊薄成本) × 数量` | 接近券商累计盈亏 |
| 整户总账 | `总资产 − 组合外部净投入` | 收益与快照；依赖组合资金流水 |
| 今日贡献 | `涨跌% × 市值` | 盘中参考，**不入账** |

### 日期与时区

- 全局只有一把"今天"：`APP_TIMEZONE`（默认 `Asia/Shanghai`）。后端与前端都按它算日期，
  交易时段（9:30 / 11:30 / 13:00 / 15:00）的判定同理 —— 换机器、换浏览器时区都不会改变
  "今天是哪天"（前端启动时从 `/api/health` 取该时区；取不到则用默认值）。
- 选历史区间看收益时，以**该区间末的最后一条快照**为期末（日期、资产、现金流同一口径）；
  `end_date` ≥ 今天按当前口径（实时总资产、含今日流水）；该日期之前没有任何快照时整体回退当前口径（不会拿今天的资产配历史现金流）。
- 月度收益已剔除区间内的外部投入/取出，转入不会被算成"当月收益"。
- 同一天的现金流水与快照以 `created_at` 判先后：快照之后转入的钱不算收益；老数据缺
  `created_at` 时按旧口径（同日流水都算作快照之后的现金流）处理。

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
| 组合流水 `portfolio_cash_flows` | 投入 / 取出（金额为正） | 收益与快照 |

银证转入 **不会** 自动生成组合投入。收益与快照有建议草稿；证券账户页会按 **同日、同额、同方向** 勾稽（容差 0.05），只标差、不入账。

### 券商对账

1. 券商 App 导出持仓 CSV / Excel（识别「证券代码 / 数量 / 成本价」等列）
2. 可选填券商证券现金
3. 上传预览差异；勾选后确认框会列出将改写的数量与成本
4. 写入「持仓校正」（先自动备份，再重扫）

每次预览和应用各留一条历史（schema v13 `broker_reconcile_runs`）。

### 总资产校准（净值对不对的最后一道）

持仓对账管「股数与成本」，现金校准管「证券现金」，两样都对了，合起来仍可能和券商 App 里的
**总资产**对不上：打新冻结、在途资金、跨境汇率、某笔漏记的流水，单看哪一条都查不出来。

- 总览「现在总资产」底下有一行小字：**距上次校准 N 天 · 上次差额 Y 元**，点它填券商 App 里的实测总资产；
- 差额记成一条**独立的平差余额**（`total_asset_calibrations`，schema v22），不摊回持仓、不摊回流水，
  所以「从哪天开始歪的」留在原地，一眼能看出来；
- 平差参与 `total_assets` 计算，看板与日终快照同时对齐实盘，不会出现「看板对了、净值曲线还差着」；
- 重新校准自动收敛：`新平差 = 旧平差 + (实测 − 显示)`，显示值已含旧平差，不会重复叠加。

超过 30 天没校准标黄、再久标红，但它只是提醒，不影响任何计算。

### 存款利息

单利、365 天。

| 字段 | 含义 |
|------|------|
| 预计年利息 | 本金 × 年利率 |
| 到期前利息 | 本金 × 利率 × 剩余天数 / 365；已到期为 0 |
| 整期利息 | 起存日 → 到期日；缺起存日显示 — |

---

## 快速启动

### 本地运行（单进程，最省事）

不需要 Docker：后端一个进程同时提供接口和页面，一个端口。

```bash
git clone https://github.com/kofwj/invest-tracker.git && cd invest-tracker
python3 -m venv venv && source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..
python backend/main.py
```

浏览器会自动打开 <http://127.0.0.1:8000>（`INVEST_TRACKER_NO_BROWSER=1` 可关掉自动打开）。

只想自己在本机用，上面就够了。要让同一局域网的手机 / 平板访问，
用 `HOST=0.0.0.0 PORT=8000 python backend/main.py`，并且**务必**同时设
`INVEST_TRACKER_PASSWORD`（开了鉴权后跨域默认关闭，同源直接用没问题）。

没有 `frontend/dist` 时后端只提供 API（改前端仍走下面的本机开发流程）。
数据库和备份**不在仓库目录里**，见「数据在主机的哪里」。

### Docker（VPS / 多机访问）

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

### 桌面应用（macOS）

打包成原生 `.app`（Tauri 2 外壳 + PyInstaller 侧车），双击即用，不用另起后端：

```bash
bash scripts/build-desktop.sh     # 产物在 src-tauri/target/release/bundle/
```

只想调壳本身就在仓库根跑 `./frontend/node_modules/.bin/tauri dev`：前端走 vite 热更新，
后端按上面的方式自己起在 8000。细节与已知限制见 [docs/desktop.md](docs/desktop.md)。

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

## 发版

版本号有**四处**必须一致：`backend/version.py` 是单一来源，`frontend/public/sw.js` 的
`CACHE_NAME`、`src-tauri/tauri.conf.json` 的 `version`、`src-tauri/Cargo.toml` 的 `version`
跟着它走。前两处被 `frontend/tests/pwa-static.test.js` 逐字比对，少改就红；Cargo 那行没有
测试盯着，但历史上每次发版都同步，漏了构建日志里还是旧号，翻日志时会以为打错了包。

| 位置 | 改什么 |
|------|--------|
| `backend/version.py` | `APP_VERSION = "1.7.3"` |
| `frontend/public/sw.js` | `const CACHE_NAME = 'invest-tracker-v1.7.3'` |
| `src-tauri/tauri.conf.json` | `"version": "1.7.3"`（桌面安装包版本） |
| `src-tauri/Cargo.toml` | `version = "1.7.3"`（crate 版本，构建日志里会打出来） |

功能提交**不**顺手 bump 版本：发版是单独一个 `chore(release)` 提交，否则「哪条改动属于哪个
版本」会跟着开发节奏漂。

```bash
# 1) 四处版本号 + CHANGELOG 的「未发布」段改成正式版本号，单独提交
git commit -am "chore(release): 1.7.3"
git tag -a v1.7.3 -m "v1.7.3"

# 2) 推源码与标签，再建 GitHub Release（正文直接取 CHANGELOG 里这一段）
git push origin main && git push origin v1.7.3
gh release create v1.7.3 --title "v1.7.3 — 一句话标题" --notes-file /tmp/notes.md

# 3) 生产分支快进，VPS 才跟得到
git push origin main:deploy/vps
```

桌面包：`bash scripts/build-desktop.sh`（产物在 `src-tauri/target/release/bundle/`）；要挂到
Release 上就 `gh release upload v1.7.3 <dmg 路径>`。DMG 是通用构建产物、不入库，所以每次发版
得重新打一个，否则附件永远停在旧版本。

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

#### 流水线心跳（别等周末才发现周三就没跑）

前三道防线都假设「任务跑了」：备份失败写 stderr、行情失败返回 500、快照被价格闸门拦下返回
`skipped`。可真实失效是**根本没跑**——cron 被删、脚本挂掉、容器起不来，日志里一片安静。

后端对每条流水线记一个「上次成功时间」，超过阈值没成功就走消息推送的**运维**通道喊人：

| job | 对应 | 默认阈值 |
|-----|------|----------|
| `backup` | `scripts/backup_daily.sh` | 30 小时（容一次失败重跑） |
| `sync_prices` | 行情同步（`/cron/sync-prices`、页面手动同步、docker 直调） | 96 小时（扛四天长假） |
| `snapshot` | 日终快照 | 96 小时 |

「从来没成功过」也算逾期——新服务器忘了配 crontab 正是最该被喊出来的情况。检查挂在
`/cron/notify-events` 上，所以**不用改 crontab**；运维页（`/ops/backup`）顶部也会列这三条的颜色。

要连整机宕机也漏不掉，再配一条外部 dead-man（[healthchecks.io](https://healthchecks.io) 之类）：

```env
HEARTBEAT_BACKUP_URL=https://hc-ping.com/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
HEARTBEAT_SYNC_PRICES_URL=
HEARTBEAT_SNAPSHOT_URL=
```

**成功才 ping，失败刻意不 ping**——让外部服务的超时规则自己报警，比额外发一个「失败」信号更简单，
也不会漏（进程被杀时根本没机会发任何请求）。阈值可用 `HEARTBEAT_<JOB>_MAX_AGE_HOURS` 覆盖。
脚本上报走 `POST /cron/heartbeat`（复用 `CRON_API_TOKEN`），没有 token 时打一行 `heartbeat skip` 跳过，
不影响备份本身。

---

## 消息推送

只发短通知（飞书 / 钉钉 / 企微 / Telegram），和 Hermes 长报告分开。

优先在 **设置 → 消息推送** 填密钥（存库，不回填明文；留空=不改，勾清除=删库值）。`.env` 的 `NOTIFY_*` 只作服务器兜底。

飞书支持两种：**Webhook**（机器人）或 **自建应用**（app_id + app_secret + 接收人 open_id，走消息 API）。配了自建应用就忽略 Webhook。

事件：价格预警、晚间简报、存款到期、纪律破线、运维、试推。

除权除息提醒复用「存款到期」通道：定时任务先刷新本地日历（持仓 ∪ 自选）再推送，
除权除息前 7 天内与过期 7 天内每天最多一条；抓取失败只标记状态、不清空已存事件。

---

## 数据与安全

```bash
bash scripts/privacy_check.sh
python3 scripts/backup_db.py --label manual
python3 scripts/restore_db.py backups/你的备份.db
```

- `data/`、`backups/`、`.env` 不进 Git
- 可用 `DB_PATH`、`BACKUP_DIR`、`APP_TIMEZONE`（决定「今天」、交易时段判定与前端默认日期）、`CORS_ALLOW_ORIGINS` 覆盖
- 库 schema 版本见 `backend/schema.py`（当前 **v21**）；启动时自动迁移
- 上传上限：普通 CSV 20MB，券商 Excel 50MB；导出 CSV 会清洗公式注入前缀

### 数据在主机的哪里

单进程本地运行时，账本默认放在系统标准数据目录里（**不在仓库目录**，`git clean` 删不掉）：

| 系统 | 位置 |
|------|------|
| macOS | `~/Library/Application Support/InvestTracker/data/invest.db` |
| Windows | `%APPDATA%\InvestTracker\data\invest.db` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/InvestTracker/data/invest.db` |

备份在同根的 `backups/`。三条覆盖规则，优先级从高到低：

- `DB_PATH` / `BACKUP_DIR`：最高优先（Docker、VPS、测试都走这条，行为和以前完全一样）
- `INVEST_TRACKER_HOME=/some/dir`：换掉整个根目录（便携安装、一个目录一套账）
- 首次启动时，如果仓库里还留着旧的 `data/invest.db`，会复制一份到上面那个位置，
  旧文件改名成 `invest.db.migrated-<时间戳>` **留档不删**——迁错了改回名字就能退。

### 数据会去哪（联网行为）

离线也能记账。下面是仅有的三处主动出网：

| 出网 | 发什么 | 默认 |
|------|--------|------|
| 行情 / K 线 / 基本面（akshare 等） | 只发股票代码，不发持仓、不发金额 | 开（点开或定时同步时） |
| AI 简报 / 周报（`AI_ENABLED`） | **会把持仓明细和当日盈亏金额**发给所配的模型服务 | **关** |
| 消息推送（`/ops/notify`） | 推到你自己配的 webhook / 机器人 | 关 |

不想让持仓金额离开本机，就别开 `AI_ENABLED`；另外两处只发代码、或只发你自己配的目标地址。

### 备份里有明文凭据

`settings` 表里存着明文密钥：`ai_api_key`，以及 `notify_channel_credentials`
里的飞书 `app_secret`、钉钉加签 secret、Telegram bot token、各通道 webhook 地址。
**备份是整库副本，谁拿到 `.db.bak` 谁就拿到了这些密钥。**

程序落盘时会把账本库和备份收成 `0600`（仅属主可读写），但搬走之后管不到：

- 备份同步到网盘、塞进 Git、发给别人 = 交出凭据；要外传就先清空这几项
- 换机恢复备份后，去「设置 → 消息推送 / AI」核对密钥是否还有效
- 提 issue 想附样本库时，用 `sqlite3 库文件 "UPDATE settings SET value='' WHERE key IN ('ai_api_key','notify_channel_credentials')"` 再打包

---

## 仓库结构

```text
invest-tracker/
    app_paths.py           数据目录解析 / 首次启动迁移 / dist 定位
    schema.py              版本迁移（当前 v21）
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
  docs/desktop.md          桌面壳：结构 / 端口 / 打包 / dev 模式
  docker-compose.yml       本地
  docker-compose.prod.yml  VPS
  .github/workflows/ci.yml
  LICENSE                  AGPL-3.0
  # 运行时数据不在仓库里：默认落在系统数据目录，见「数据在主机的哪里」
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

[AGPL-3.0](LICENSE)（GNU Affero General Public License v3.0）。

简单说：你可以随便用、随便改、自己跑；但**改完要是给别人用（包括部署成网站给别人访问），就得把改后的源码一起开源**。AGPL 相比 GPL 多管住"软件即服务"这一层，正好对上一个能被公网访问的记账后端。

商用、闭源分发、或者想让改动的部分不开源，单独谈授权。

---

公开仓库前先跑 `scripts/privacy_check.sh`，确认没把真实持仓、备份和密钥传上去。`data/`、`backups/`、`.env` 已在 `.gitignore` 里，别用 `git add -f` 手动塞进去。
