# 更新日志

格式大致遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。  
版本未打 tag 时按日期记录；生产部署以分支 `deploy/vps` 为准。

---

## [2026-07-19] — 界面轻美化（A+B）

### 视觉
- 背景微渐变；顶栏改为白卡片条 + 副标题
- 总资产主卡更突出；状态条 KPI 化
- 日常/分析/维护改为分段控件；内容区白底壳层 + tabs 层次

---

## [2026-07-19] — 结构审计 P0–P2 修复

### P0
- 备份下载改走带 Authorization 的 axios blob，避免开密码后 401

### P1
- `GET /evening-brief` 只读；推送改为 `POST /evening-brief/notify`
- `GET /dividends/scan` 标记 deprecated（请用 POST）
- 组合外部流水：类型仅「投入/取出」，金额存正数并校验
- 交易页申购在途横幅用 dashboard 全量笔数/金额
- `/health` 不再返回 `db_path`
- 新增交易默认安全备份（`?backup=false` 可关）

### P2
- 绩效页支持编辑组合外部流水（PUT）
- 资产配置「申购在途」笔数用 `pending_count`
- 生产 CORS=* 时告警；token TTL 可配 `TOKEN_TTL_DAYS`
- 纪律确认备份失败写 warning 日志

---

## [2026-07-19] — 多通道消息推送（A/B/C）

### 基建
- 新模块 `backend/notify.py`：飞书 / 钉钉 / 企微 / Telegram 统一 `dispatch`
- 兼容旧 `FEISHU_ALERT_WEBHOOK`；推荐 `NOTIFY_*` 环境变量
- 价格预警、晚间简报改走统一入口；`POST /notify/test` 试推
- schema **v9**：`notify_send_log` + 通知相关 settings

### 账本事件
- 价格预警（多通道）
- 晚间简报（页面/API `notify=true`）
- 存款到期（已到期 / 今天 / 7 天 / 30 天）
- 纪律破线摘要（只提示）
- cron：`cron_sync_prices.sh --notify-events` 或 `CRON_NOTIFY_EVENTS=1`

### 体验
- 维护页：通道状态、事件订阅、试推、最近 20 条日志、冷却与短/中模板

---

## [2026-07-19] — P1/P2 体验与可维护性

### P1
- 错误提示：存款/交易/资金/费率等失败时展示后端 detail
- 存款到期分布：单独「已到期」档；剩余天数标签区分已到期
- 缺起存日：顶部提示 + 表格「待填」高亮
- 模块内自 `import { computed } from 'vue'`，不再从 main 注入（防漏传白屏）

### P2
- `domainHelpers` 拆为 `feeHelpers` / `maintenanceHelpers` / `importExportHelpers`（barrel 兼容）
- Tab 导航抽到 `modules/tabNav.js`，main 略瘦
- 后端：晚间简报/快照异常/一年收益同步等静默 except 改为 warning/info 日志
- 工具：`apiErrorDetail`、`interestForDays`；利息纯函数单测

### 存款利息（schema v8，此前已上）
- 预计年利息 / 到期前利息 / 整期利息（单利 365 天）；可选起存日

---

## [2026-07-14] — 立刻/中等/技术债体验包

### 立刻
- 券商对账：支持 Excel；可填证券现金对比；应用校正后自动重扫
- 顶栏「更多」收纳：一年收益 / 分红 / 晚间简报
- Tab 分三组：日常 / 分析 / 维护
- 收益页：从银证流水生成「投入/取出」建议草稿（点记入才写）

### 中等
- A500 计划进度条 + 建议下次金额
- 绩效故事：大类贡献 + 近约 30 个快照变化
- 晚间简报 API + 页面预览/可选飞书推送（`GET /evening-brief`）

### 技术债
- 删除有副作用的 GET `/sync-prices`、`/sync-trailing-returns`（仅保留 POST）
- 首页最新价：超过约 20 小时标「已偏旧」
- 依赖补 `openpyxl`（Excel 对账）

---

## [2026-07-14] — 大功能 E：绩效故事 + 移动端 + 券商对账单

### 绩效故事
- `GET /performance/story`：人话 headline / 要点 / 赚钱靠前 / 拖累靠前
- 收益分析页顶部「绩效故事」卡片，随刷新更新

### 移动端
- 小屏：页边距、顶栏按钮换行、Tab 横向滑动、表格字号、弹窗宽度、绩效故事单列

### 券商对账单
- 新 Tab「券商对账」：上传 CSV 预览差异 → 勾选 → 写入持仓校正（先自动备份）
- 支持简化表头与华泰常见中文列名；utf-8 / gbk
- API：`POST /broker-reconcile/preview`、`POST /broker-reconcile/apply`

---

## [2026-07-14] — 立刻+中等功能包：草稿编辑/批量确认/计划/市场结论/快照异常/备份 UX

### 纪律
- 草稿可编辑（数量/价格/金额/原因）；支持批量确认
- 确认入账后自动刷新首页持仓与交易列表
- 个人计划：A500 分批目标金额、格力软上限提醒
- 页面「怎么用」说明 + 参数说明

### 分红 / 市场 / 快照 / 维护
- 分红扫描提示不支持标的（债基等）并引导手工补录
- 市场「今天看点」加入持仓/自选大幅涨跌的人话结论
- 快照区间摘要：相邻两日总资产异常（≥2% 且 ≥1 万）告警
- 数据维护：备份时间/数量更显眼，恢复二次确认文案加强

---

## [2026-07-14] — 纪律模块审计修复（P0–P2）

### 修复
- 草稿同代码同方向去重（再生成更新已有草稿，避免双确认双记账）
- 确认卖出时再校验持仓；无现价/无数量直接拒绝
- 确认入账前安全备份
- 政策校验：权益上下限、目标合计≈100%、数字有效
- 纪律报告账户取最近成交账户；可配置防守额外品类
- 交易日历 / 一年收益 / CSV 文件名统一用 `APP_TIMEZONE`
- GET `/sync-prices`、`/sync-trailing-returns` 标记 deprecated
- 前端：生成草稿以服务端报告为准；参数 NaN 防护；格力上限/防守品类可调

---

## [2026-07-14] — 纪律 + 再平衡 + 交易草稿（真实仓位）

### 功能
- 新 Tab「纪律与再平衡」：基于真实持仓做纪律检查、目标比例差距、买卖建议
- 默认**不自动下单**；「建议→草稿」写入 `discipline_drafts`；用户确认后才进真实交易
- 默认纪律：权益 35–55%、防守≥40%、单票≤20%、格力≤15%；目标权益/固收/存款 45/30/25；优先加仓 A500
- 买入金额类确认默认记「申购待确认」（不虚增份额）

### 后端
- schema **v7**：`discipline_drafts` + settings `discipline_policy`
- `backend/discipline.py`、`routers_discipline.py`

### 前端
- `views/DisciplineTab.vue` + `modules/discipline.js`

---

## [2026-07-14] — 市场能力 1–5：VPS 清单 / 预警增强 / 交易日历 / 摘要 / 快照字段

### 1 VPS 收尾文档
- `docs/deploy-vps.md` 上线清单 + crontab（`--check-alerts` / 可选飞书）

### 2 预警增强
- 同规则冷却（默认 240 分钟，`ALERT_COOLDOWN_MINUTES` / settings）
- 历史：日期筛选、CSV 导出、清空
- 触发消息含涨跌% / 昨收

### 3 交易日历
- `backend/trading_calendar.py`；cron `--snapshot` 默认跳过周末/节假日（`--force-snapshot` 可强制）
- `GET /market/trading-day`

### 4 市场摘要增强
- 自选关注 CRUD（settings `market_watchlist`）
- 持仓 vs 沪深300/A500 对比；规则生成「今天看点」

### 5 快照 / 图表
- schema v6：`daily_snapshots.lifetime_profit`；快照表展示全周期盈亏
- 图表 `window.resize` 自动重算

---

## [2026-07-14] — 修复资产配置饼图不显示

### 修复
- tab 懒加载 + 异步 SFC 时，图表容器尚未挂载就 init echarts → 大类/细分类别饼图空白
- 等待 DOM 就绪后再画图；AllocationTab 挂载与数据变化时补绘；快照/收益图同样加固

---

## [2026-07-14] — 市场预警增强：定时检查 / 历史 / 缓存

### 功能
- cron：`cron_sync_prices.sh --check-alerts`（可选 `--notify-alerts` + `FEISHU_ALERT_WEBHOOK`）
- `GET /market/alert-events` 预警历史；市场页展示历史表 + 代码筛选
- 东财行情进程内缓存（`MARKET_QUOTE_CACHE_SECONDS`，默认 120s）；涨跌% 可从昨收推导

### 文档
- `docs/deploy-vps.md` crontab 示例；`.env.example` 新增相关变量

---

## [2026-07-14] — 市场摘要 + 简单价格预警（MVP）

### 功能
- 新 Tab「市场摘要」：关键指数（上证/深成/沪深300/创业板/A500）+ 持仓今日贡献粗估 + 与大盘对比一句话
- 价格预警规则 CRUD（持仓/指数，上穿/下穿阈值）；「立即检查」手动触发；触发写入 `alert_events`
- **不改真实账本**，不自动推送；行情复用东财延时接口

### 后端
- `schema` v5：`alert_rules` / `alert_events`
- 新增 `backend/market.py`、`backend/routers_market.py`
- `price_sync.fetch_eastmoney_quotes`（含涨跌%），`fetch_eastmoney_prices` 兼容旧调用

### 前端
- `views/MarketTab.vue` + `modules/market.js`；`App.vue` / `main.js` / `api/index.js` 接线

### 校验
- `pytest` 新增 `tests/test_market_alerts.py`；`scripts/check.sh` 增加结构检查

---

## [2026-07-11] — Phase3e 按 tab 拆分 SFC + 懒加载

### 前端结构
- `App.vue` 降为壳：header / 首页卡片 / tabs / dialogs / 登录
- 新增 `views/*Tab.vue`（快照/配置/收益/持仓/存款/交易/现金/维护）与 `components/{AppHeader,HomeDashboard,AppDialogs,LoginOverlay}.vue`
- `provide/inject`（`useAppCtx`）共享根 setup 状态，避免海量 props
- `el-tab-pane lazy` + `defineAsyncComponent`：进入 tab 再加载对应 chunk

### 体积
- 主 app chunk 约 **143KB → 83KB**；各 tab 独立 3–14KB 异步包

---

## [2026-07-11] — Phase3d Vue SFC + Element Plus 按需

### 前端
- 模板从 `index.html` 迁入 `App.vue`；`index.html` 仅保留挂载点与登录关键 CSS
- Vue 改为 **runtime-only**（不再使用 `vue.esm-bundler`）
- `@vitejs/plugin-vue` + `unplugin-vue-components` / `unplugin-auto-import` + ElementPlusResolver 按需组件
- 去掉全量 `element-plus/dist/index.css`；消息/确认框/Loading 仍显式导入样式
- 构建体积（约）：element-plus JS **1.0MB → 565KB**，CSS **356KB → 221KB**

### 校验
- `npm run build` 通过；`pytest` 后端不变

---

## [2026-07-11] — Phase3 前端分包与结构优化

### 构建 / 性能
- Vite `manualChunks`：拆出 `vue` / `element-plus` / `echarts` / `axios` 缓存友好 vendor chunk
- ECharts 改为 `echarts/core` + Line/Pie 按需注册；图表渲染 `import()` 懒加载（进入快照/配置/收益分析 tab 再拉）
- 业务 app chunk 约 **57KB**（gzip ~18KB）；ECharts 约 **528KB**（gzip ~177KB）

### 结构
- `modules/*` 改为正式 ESM（`import api` / `element-plus`），去掉对 `window.createXxx` 的依赖
- 抽出 `composables/authMask.js`、`composables/domainHelpers.js`（费率/分红/维护/导入导出/配置分析）
- `main.js` 约 1364 → **780** 行；模板字段名与业务行为保持不变

### 校验
- 前端 build 通过；`pytest` **38 passed**；`check.sh` 同步 composables 检查

---

## [2026-07-11] — Phase1/2 安全与增量重算

### 安全 / 性能
- 登录防爆破：按 IP 滑动窗口失败计数，超限 429；成功清零（`LOGIN_MAX_FAILURES` / `LOGIN_WINDOW_SECONDS` / `LOGIN_LOCK_SECONDS`）
- 分红扫描：`requests.Session` 复用 + 进程内 6h TTL 缓存（东财/新浪）

### 账本
- `recalc_holdings(conn, codes=None)` 支持按 code 增量重算；单笔增删改 / 确认分红 / 持仓校正走增量，CSV 导入仍全量

### 测试
- `test_login_rate_limit` / `test_dividend_cache` / `test_partial_recalc`；全量 **38 passed**

---

## [2026-07-11] — 代码层优化

### 优化

- 新增 `backend/portfolio_totals.py`：首页与收益分析共用市值/现金/待确认/浮盈/全周期汇总，避免双份公式漂移
- SQLite 连接统一 `WAL` + `busy_timeout` + `foreign_keys` + `synchronous=NORMAL`；`db_session` 异常时 rollback
- dashboard / performance / deposits / fee-settings 路由统一 `db_session`，减少连接泄漏
- 登录密码改为长度安全的 `hmac.compare_digest`
- 前端 `holdingLifetimeProfit`：摊薄成本缺省时回退普通成本，与后端一致

### 测试

- 新增 `tests/test_portfolio_totals.py`；全量 **33 passed**

---

## [2026-07-11]

### 新增

- **半自动分红**
  - A 股个股：东财分红源，扫描草稿 → 用户确认入账，自动去重已有流水
  - 场内 ETF / 港股 ETF / REIT（如 513530、508056）：新浪 `FundPageInfoService.tabfh`
  - 开放式债基等仍支持手工录分红
- **持仓盈亏双口径**
  - 持仓浮盈：`(现价 − 普通成本)×数量 + 累计分红`
  - 全周期盈亏：`(现价 − 摊薄成本)×数量`（接近券商累计盈亏）
  - 持仓表明细列、首页卡片、资产配置表、收益分析贡献表均可对照
- **收益分析讲解向改版**
  - 三步导读、人话指标卡、三口径对照（整户总账 / 当前仓浮盈+分红 / 全周期）
  - 无组合外部流水时降级提示，避免误读 XIRR / 净投入
- **首页 / API 全周期汇总**
  - `dashboard.lifetime_profit`、`performance/summary.lifetime_profit`
  - 贡献行增加 `lifetime_profit`，可按全周期排序
- **VPS 运维**
  - `scripts/verify_vps_deploy.sh`：部署后核对分支、数据目录、容器、health、cookie_secret 长度、oauth2-proxy
  - `scripts/cron_sync_prices.sh`：交易日同步最新价；`--snapshot` 同步后写/更新今日快照
  - `docs/deploy-vps.md`：更新后核对清单、定时任务示例、cookie_secret 要求
- **Cloudflare Tunnel（家用回源）**
  - `caddy/Caddyfile.tunnel`：关闭 Caddy 自动 HTTPS，HTTP:80 做 oauth2-proxy 鉴权
  - compose 支持 `CADDYFILE=./caddy/Caddyfile.tunnel`
  - 文档明确：隧道必须指 `http://127.0.0.1:80`，禁止指 frontend `:8080`

### 修复

- 持仓表「持仓浮盈 / 全周期盈亏」显示成百分比、后列空白：Vue setup 未 `return` 计算 helper（`holdingLifetimeProfit` 等）
- VPS 登录页中文乱码 / 遮罩：字体与 charset、登录时关闭 screenshot-mask、native 密码框等加固
- `oauth2-proxy` 反复 Restarting：`OAUTH2_PROXY_COOKIE_SECRET` 缺失或长度非法（须 base64 解码后 16/24/32 字节；占位符 `replace-with-32-byte-base64-secret` 正好 34 字符）
- `APP_DOMAIN` 误写 `https://...` 导致回调与 Caddy 站点名异常
- 资产配置 `expected_return` 为合法 `0` 时被 `||` 盖成默认值 → 改用 `??`
- 前端 API 模块 axios / export 与 nginx 不缓存 `index.html` 等构建与登录链路问题（`deploy/vps` 历史提交一并纳入）

### 文档与部署说明

- README：功能概览补充半自动分红、双口径盈亏；盈亏口径对账表
- `docs/deploy-vps.md` §4.6 家用 VPS + Cloudflare Tunnel；§8 核对清单；§9 定时同步价
- `.env.example`：cookie_secret 生成与长度说明；隧道 `CADDYFILE` 注释

### 运维备忘（家用 + 隧道）

- `scripts/deploy_vps.sh` 部署成功后自动 `docker builder prune -f`，避免 Build Cache 占满小盘


```text
浏览器 --HTTPS--> Cloudflare
              --隧道--> 本机 cloudflared
              --HTTP--> Caddy:80（Caddyfile.tunnel）
              --forward_auth--> oauth2-proxy(GitHub)
              --> frontend → backend
```

- 应用密码门（`INVEST_TRACKER_PASSWORD`）与 GitHub OAuth 是两层
- 推荐 cron（机器时区 CST 时）：

```cron
20 15 * * 1-5 …/scripts/cron_sync_prices.sh >> …/backups/cron_sync_prices.log 2>&1
40 16 * * 1-5 …/scripts/cron_sync_prices.sh --snapshot >> …/backups/cron_sync_prices.log 2>&1
15 2 * * * cd …/invest-tracker && python3 scripts/backup_db.py --label daily >/dev/null
```

### 测试

- `PYTHONPATH=backend /usr/bin/python3 -m pytest tests/ -q` → **31 passed**（含 dashboard `lifetime_profit`、分红 ETF/REIT 等）

### 相关提交（`deploy/vps`，新→旧摘录）

- `a6e08b4` Cloudflare Tunnel 家用回源 Caddyfile.tunnel  
- `1c4effe` 文档与核对脚本检测 oauth2-proxy cookie_secret 长度  
- `83ce867` 首页/贡献表全周期汇总、VPS 核对与定时同步价  
- `8530d86` 半自动分红扩展支持港股 ETF 与 REIT  
- `b8d7767` 收益分析页讲解向改版  
- `4b6fcea` 暴露持仓浮盈/全周期盈亏计算函数到 Vue 模板  
- `0000afe` 加固 VPS 登录页中文显示  
- `63994bc` 持仓表区分持仓浮盈与全周期盈亏  
- `c598e0f` 半自动分红草稿 + 登录乱码初修  

---

## [2026-05 / 更早]

- P0–P2 持仓、校验与 dashboard 可靠性修复（见 `main` 历史 `e59deb2` 等）
- 密码门、GitHub OAuth、Caddy 生产 compose 等 VPS 部署能力（见 `deploy/vps` 早期提交）
