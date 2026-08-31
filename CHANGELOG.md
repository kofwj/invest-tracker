# 更新日志

格式大致遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。  
版本号单一来源 `backend/version.py`；发布流程：改那里 → 本文件记版本 → `git tag vX.Y.Z`。生产部署以分支 `deploy/vps` 为准。

---

## [1.0.1] — 2026-08-31 — oauth2 回跳域名修复 + 持仓操作列整理

- **登录回跳域名放行**（`docker-compose.prod.yml`）：oauth2-proxy 缺 `--whitelist-domain`，未带会话的 `/api` 请求被 302 到登录页但绝对 URL 回跳被拒 → 浏览器「Network Error」、页面像卡死；现在 `APP_DOMAIN` 放行，登录后能正确跳回
- **持仓明细操作列瘦身**（`HoldingsTab.vue`）：由年化/校正/记录/UZI/K线 5 钮减为只留「校正」；「年化」改点「预计年化」列数值即改；「记录」并入校正弹窗；行内 K线/UZI 下线（K线去「分析→K线查询」完整版，`modules/uziAnalysis.js` 删除）
- **年化/校正不再误弹交易记录**：瘦身时丢了原 `@click.stop` 包裹层，，点击会冒泡触发行点击再弹「交易记录」；补回 `.stop`

---

## [1.0.0] — 2026-08-31 — 首个带版本号的正式发布

首个正式版本，包含 `backend/version.py` 版本号体系（`/api/health` 与前端页头展示），并合并以下三次 2026-08-30 代码审查批次修复：

- 批次一（5 项：行情缓存 secid 隔离、闰年 2/29、交易 code trim、费率设置缺省 accounts、登录限速默认不信伪造 XFF)
- 批次二（中等优先级 11 项：分红未来日期、CSV Sniffer、日期参数 400、交易/存款导入校验、飞书 token 缓存按凭证、时区、防误清空等）
- 静态 lint 接入 `check.sh`（ruff F+E9）+ 存量清理 13 处

---

## [2026-08-30] — 代码审查批次修复（5 项）

### 修复
- **行情缓存按 secid 隔离**（`price_sync.py`）：原缓存 key 只是不带 `f` 的裸代码，上证指数 `000001`（secid `1.000001`）与平安银行 `000001`（secid `0.000001`）互相串价，且 `/sync-prices` 会把指数点位持久化写进 `holdings.last_price`。现改为按解析后的 secid 存取，并顺手清理过期缓存条目
- **闰年 2/29 近一年收益同步崩溃**（`return_sync.py`）：`end.replace(year=end.year - 1)` 在 2 月 29 日抛 `ValueError` → 接口 500。提取 `one_year_before()`，闰日回退到 2/28
- **交易 code 强制 trim + 非空**（`routers_transactions.py`）：带空白的 code 会导致"现金已扣、持仓不变"的账实分离（重算按 strip 后精确匹配）。`TransactionBase` 拒绝空白 code，`TransactionUpdate` 空白视为不改
- **费率设置缺省 accounts 不再静默重置**（`routers_fee_settings.py` + `fee_settings.py`）：PUT 不传 accounts 时从 settings keys 推导账户；顺带修复 `accounts: null` 时迭代 None 崩溃
- **登录限速默认不信任伪造 X-Forwarded-For**（`auth.py`）：原先客户端可换假 IP 无限获取新失败额度（密码爆破 + 内存无限增长）。现在默认用真实来源 IP；部署在可信反代后可设 `TRUST_PROXY_HEADERS=1` 恢复旧语义；限流状态加 `LOGIN_MAX_TRACKED_IPS`（默认 1000）容量上限

### 测试
- 新增 `tests/test_bugfix_regressions_20260830.py`（11 个回归测试），全套 174 个测试通过

---

## [2026-08-30] — 代码审查批次修复（第二批，中等优先级）

### 修复
- **确认分红拒绝未来日期**（`dividend_sync.py`）：原先提前确认未来除息的分红会立即虚增现金和累计分红，与其它交易写入路径"日期不能晚于今天"的约束矛盾
- **CSV Sniffer 崩溃 → 400**（`csv_utils.py`）：单列/无分隔符 CSV 让 `Sniffer.sniff` 抛 `csv.Error` 导致导入接口 500，现在回退 excel 方言走行级报错
- **交易/流水日期参数校验**（`routers_transactions.py` + `routers_cash_flows.py`）：`2025/1/1` 这类非 ISO 日期原先静默给出错误过滤结果（含导出 CSV），现在返回 400
- **交易日接口非法日期 → 400**（`trading_calendar.py` + `routers_market.py` + `routers_cron.py`）：原先非法日期静默按"今天"计算，cron 传错日期会拿到错误结论；未传日期仍默认今天
- **存款导入校验补齐**（`routers_deposits.py`）：金额 `nan` 原先溜过校验被 sqlite 存成 NULL、这笔存款从总资产凭空消失，现在行级报错；缺"年利率"列时利率落 NULL（未填）而不是误写成 0.0
- **分红导入报错行号修正**（`routers_dividends.py`）：行号改为文件真实行号（含表头），与交易/存款导入一致；`GET /dividends/scan` 非法 `lookback_days` 返回 422 而不是 500
- **历史持仓口径统一**（`dividend_sync.py`）：删除本地 `holding_quantity_as_of` 副本，委托 `holding_calculator` 实现——多条持仓校正记录时两处不再算出不同的登记日份额（分红估算金额错）
- **飞书 token 缓存按凭证区分**（`notify.py`）：更换 app_id/app_secret 后不再最长 90 分钟沿用旧应用 token；缓存 key 含 secret 摘要，凭证一变即失效
- **组合流水 created_at 时区**（`snapshots.py` + `routers_performance.py`）：显式写入应用本地时间（`APP_TIMEZONE`），不再依赖容器 OS 时区（UTC 容器上原先慢 8 小时）
- **`clear_alert_events` 防误清空**（`market.py`）：无过滤条件时抛 ValueError 而不是清空全表；"清空全部"由路由层显式 `allow_all=True` 触发
- **前端两处小问题**（`utils/index.js` + `modules/holdingCorrections.js`）：`holdingLifetimeProfitRate` 在 `diluted_cost` 为空时回退 `avg_cost`（与 `holdingLifetimeProfit` 口径一致，不再导致收益率直接不显示）；删除持仓校正失败不再被静默吞掉

### 测试
- 回归测试增至 22 个（第二批追加 11 个），后端 185 个 + 前端 24 个测试全部通过

---

## [2026-08-30] — 静态 lint 接入 check.sh

### 内容
- `scripts/check.sh` 新增 ruff lint 步骤（`ruff check backend tests`，未安装则跳过），此前脚本只有结构/冒烟检查、无任何静态 lint
- 新增 `ruff.toml` 固定最小安全规则集 `F + E9`（未使用导入、未定义名、语法错误）。**刻意不开默认风格规则**：本地测试跑 Python 3.9，默认集里的 UP007（`Union` → `X | Y`）一旦被 `--fix` 应用会破坏 3.9 兼容
- 清理存量 lint 残留 13 处（12 个未使用导入 + 1 个未使用局部变量，均在既有测试文件；`ruff --fix` 自动修复 + 1 处手工删除），后端源码在 F/E9 下零告警
- 测试回归：修复+精简后全套 185 后端 + 24 前端测试通过

---

## [2026-08-13] — 飞书支持自建应用推送

### 内容
## [2026-08-13] — 飞书支持自建应用推送

### 内容
- 消息推送新增飞书自建应用模式（app_id + app_secret + 接收人 open_id），走 tenant_access_token + 消息 API
- 与 Webhook 二选一；配了自建应用就忽略 Webhook；页面/`.env` 均可配
- token 进程内缓存（90 分钟），多通道发送已存在

---

## [2026-08-13] — 重写 README

### 内容
- 按当前页面、口径、启动/部署、cron token、对账与勾稽重写 README，去掉过时测试数量和七月导航流水账

---

## [2026-07-26] — 券商对账历史 + 银证勾稽

### 内容
- 预览/应用券商对账各留一条历史（schema v13 `broker_reconcile_runs`），页面可回看上次差异代码
- 应用校正前确认框列出将改写的数量与成本
- 证券账户页新增银证转入/转出 vs 组合投入/取出勾稽（同日同额配对，容差 0.05）

---

## [2026-07-26] — 结构页预设改版：右栏分段选择

### 内容
- 去掉顶部三张营销大卡；目标尺子收到右栏分段按钮
- 目标数字与偏离进度合并，去掉重复展示
- 预设文案缩短

---

## [2026-07-26] — 结构与目标：一键三套预设 + 排版

### 内容
- 新增防守 / 均衡 / 加仓中三套目标尺子（`GET/POST /discipline/presets*`）
- 只改权益/固收/存款目标与安全带，保留优先加仓、禁开、格力上限
- 结构页顶部一键套用卡片；诊断块三列收紧；目标偏离挪到右栏

---

## [2026-07-26] — 资产配置分析 P0+P1

### 内容
- 新增 `GET /allocation/story`：配置主结论、健康检查、问题清单、集中度（与纪律政策同源）
- P1：同质化粗分、收益依赖、30 日流动性、权益跌 5/10/20% 情景粗估（标明假设）
- 「结构与目标」页：主结论卡、目标偏离条、问题清单与 P1 诊断块；健康阈值去掉前端硬编码
- 改纪律参数 / 入账后自动刷新配置诊断

---

## [2026-07-25] — 今天该看：看点右上 + 关键指标补强

### 内容
- 「今日看点」挪到右栏最上方，先看结论再下钻指数/贡献
- 左栏关键指标扩到 12 卡：贡献/涨跌、vs 沪深300/A500、总资产、权益仓位、纪律、到期存款、最强/最弱、预警、指数情绪
- 补 `cols-2` 指标网格；破线摘要列表

---

## [2026-07-25] — 总览右上：近一周资产曲线

### 内容
- 原「资产构成」静态条改为近一周总资产变动曲线
- 数据来自日快照；近 7 天不足时回退最近快照，今日无快照补实时点
- 展示期初/最新与区间涨跌幅，切主题自动重画

---

## [2026-07-25] — 总览跟主题 + 全局夜间字色扫尾

### 内容
- 总览默认走浅色 token，仅夜间加深；不再硬锁黑底
- 首屏 `index.html` 提前应用 localStorage 主题，减少闪色
- 弹窗/持仓/交易页残留 `#606266/#303133/#909399` 改 token
- 同步提示条浅底硬编码改 token

---

## [2026-07-25] — 结构与目标：夜间字色 + 扇形图不叠字

### 内容
- ECharts 标题/图例/轴线跟主题 token；切日夜自动重画
- 扇形图：扇内只标大块百分比，名称走底部图例，hover 看详情（防叠字）
- 结构页风险卡/目标卡/纪律卡去掉浅底硬编码

---

## [2026-07-25] — 设置组：推送页面配密钥 + 证券账户归位

### 内容
- 顶栏「维护」改为「设置」
- 设置组 pill：消息推送 / 证券账户 / 数据备份
- 消息推送可在页面填写飞书/钉钉/企微/Telegram 密钥（存库，优先于 `.env`；不回填明文）
- 原隐藏「现金设置」改为「证券账户」（费率 + 现金校准 + 银证流水）

---

## [2026-07-25] — 收益分析夜间字色修复

### 内容
- 收益分析硬编码浅底/深字改为 token
- 故事卡/贡献条/流水标题/表头在 dark 下可读
- 业务页 el-card / el-table 夜间文字跟主题

---

## [2026-07-25] — redesign P0+P1+P2 账本视觉统一

### 内容
- P0：主色改克制青绿；涨跌/警示/成功 token 化；去掉表内硬编码红绿；主金额可换行
- P1：收益/决策加载骨架；持仓/总览空状态；页签 active 底线；可点表 hover；focus-visible；手机顶栏收字
- P2：登录页与 title 对齐；Overview 白天跟 token；补 z-index 层级；暗色表格 token

---

## [2026-07-25] — 收益分析大类拆开：债基 / REITs / 权益

### 内容
- 大类贡献不再合并「固收相关」；按 **债基 / REITs / 权益** 分开显示
- 避免 REIT 浮亏被误读成整块固收在亏

---

## [2026-07-25] — 维护页统一总览语言

### 内容
- 消息推送：顶部 4 张状态卡 + 通道卡片 + 一键推送区 + 分块设置/日志
- 数据备份：顶部 4 张状态卡（库状态/份数/最近备份）+ 备份表收进卡片
- 操作按钮收进页头，少口号多结果

---

## [2026-07-25] — P2 真合并：决策+市场 / 配置+纪律

### 内容
- 「今天该看」双栏：左结论（贡献/纪律/存款到期/看点），右市场详情（指数/持仓贡献）
- 自选 + 价格预警 + 预警历史并入「今天该看」；旧 `/market` 跳转 decision
- 「结构与目标」双栏：左当前结构（图+健康检查+大类），右目标与纪律（破线/计划/再平衡）
- 纪律草稿与参数弹窗并入 allocation；旧 `/discipline` 跳转 allocation
- 分析二级页签：今天该看 / 收益分析 / 结构与目标（3 个）
- 存款总额全宽 hero；收益分析主结论卡加粗；MetricCard 支持 title hover 全值

---

## [2026-07-25] — A+B 页指标卡统一为总览语言

### 内容
- 新增 `MetricCard` + 全局 `.ledger-metric*` 样式（等宽数字、单行金额、红绿/警示）
- A：今天该看 / 收益分析 / 资产配置 顶部指标卡改新样式
- B：持仓家底卡、银行存款、资产快照 顶部指标卡改新样式
- 表格与录入区保持原样；不全页强制暗底

---

## [2026-07-25] — 总览指标顺序 + 数字同行

### 内容
- 指标顺序：总资产 → 当日参考 → 持仓浮盈 → 现金存款
- 盈亏数字强制单行，避免「+」与金额换行

---

## [2026-07-25] — 总览去重复页头

### 内容
- 去掉「家底一眼清」口号与说明小字
- 去掉页内刷新 / 持仓明细 / 今天该看 / 记交易（顶栏已有刷新与导航）
- 进入总览仍自动拉市场数据

---

## [2026-07-25] — 顶栏四大组 + 全站 PageShell

### 内容
- P0：总览 / 日常 / 分析 / 维护 放进标题栏；内容区只留二级页签
- P1：新增 `PageShell`，日常/分析/维护各页统一页头壳
- 旧页头类名兼容统一字号/颜色；今日总览保持独立风格

---

## [2026-07-25] — 顶栏统一 + 去轨道动效 + 日夜主题

### 内容
- 顶栏改为 Lucide 按钮条（刷新 / 同步价 / 退出 / 主题切换）
- 主题：跟随系统 / 白天 / 夜间，记忆到 localStorage
- 今日总览去掉资产轨道动效，改为静态「资产构成」条
- 全局 CSS token 支持 dark class；Element Plus dark css-vars

---

## [2026-07-25] — 今日总览 A 底 + B 曲线

### 内容
- 仅改 `OverviewTab`：暗色精密账本骨架 + 右侧资产轨道 canvas
- Lucide 图标，无表情
- 主指标压成总资产 / 浮盈 / 当日参考 / 现金存款
- 持仓速览 + 今天可做 + 组合脉搏；轨道节点按市值权重示意

---

## [2026-07-25] — 今日总览持仓列表收紧

### 内容
- 名称 / 代码 / 分类合并为「标的」
- 列顺序改为：标的 | 最新价 | 市值 | 持仓浮盈
- 数字右对齐 + 等宽，行高略紧

---

## [2026-07-25] — 修复弹窗无反应（年化/校正/分红/存款）

### 根因
- `appCtx` 漏暴露 `expectedReturnDialog` / `holdingCorrectionDialog` / `holdingCorrectionHistoryDialog`
- `AppDialogs` 解构失败后整组弹窗挂掉，表现为：持仓年化/校正/记录无反应、分红草稿不弹、存款编辑也打不开

### 修复
- `main.js` appCtx 补回上述 3 个 dialog 状态

---

## [2026-07-25] — 表格样式克制重做

### 原则
- 不做列显隐、不做手机卡片、不改操作入口
- 只改对齐、密度、数字字体，让表格更清爽

### 内容
- 数字列右对齐 + 等宽数字
- 名称/代码合并成一列（持仓、交易）
- 表头弱化、行高略紧
- 交易/存款/快照/现金流水统一对齐

---

## [2026-07-24] — 维护组分页：消息推送 / 数据备份

### 导航
- 维护组拆成两个 pill：`消息推送`（`/ops/notify`）、`数据备份`（`/ops/backup`）
- 旧 `/maintenance`、`?tab=maintenance` 自动跳到消息推送
- 以后加「导入导出 / 系统信息」只加新 pill，不再往一页堆

### 页面
- `NotifyOpsTab`：通道开关、事件订阅、晚报、试推、日志
- `BackupOpsTab`：库状态、备份列表、创建/下载/恢复

---

## [2026-07-24] — 收益分析 P0+P1 瘦身

### 布局
- 默认折叠「怎么看 / 口径说明」；去掉重复 tip 墙
- 主卡 4 张（净投入 / 总收益 / 年化 / 全周期）+ 次卡 3 张
- 未录外部流水时顶部强提示，可跳转录入 / 银证建议

### P1
- 时间轴筛选：今年 / 近一年 / 全部
- 大类贡献条（权益 / 固收 / 存款）
- 贡献表精简列；点标的可看该标的交易

---

## [2026-07-24] — 顶栏瘦身：操作按页面分流

### 顶栏
- 仅保留：刷新数据、同步最新价、退出登录
- 去掉「隐藏数据」按钮；打码仅 `?mask=1` / `?screenshot=1` 时开启（默认不隐藏）

### 页面内
- 持仓明细：同步近一年收益率
- 交易录入：分红草稿
- 消息推送：生成晚间简报 / 生成并推送晚报

---

## [2026-07-24] — 今日总览 + 多页面路由

### 导航
- 启用 vue-router：`/` 今日总览，`/holdings`、`/transactions` 等独立路径
- 顶部分组：总览 / 日常 / 分析 / 维护；组内 pill 二级导航
- 兼容旧链接 `?tab=holdings` 自动跳转

### 今日总览
- 新首页：总资产、持仓数、市值、浮盈、当日收益参考（盘中粗估不入账）、现金+存款
- 状态条 + 申购在途提醒 + 持仓预览表（前 12 条）

---

## [2026-07-24] — 资产概览仅持仓页显示

### 布局
- 总资产等 6 张概览卡 + 状态条，从全站常驻改为仅「持仓明细」页顶部
- 去掉顶栏 slogan 文案
- 默认打开页改为持仓明细（`?tab=` 仍可指定）

### 修复
- 资产配置页补暴露 allocationSummary 等字段（避免空白）

---

## [2026-07-24] — P0 入口体验 + P1 决策信息

### P0
- UZI 弹窗只读声明；问题模板（综合/组合风险/今日归因/加减仓/数据对账）
- 分析备忘存浏览器 localStorage（不进真仓）
- 顶栏/首页定位文案：真仓账本 · 记清每一笔，再决定怎么调

### P1
- 分析分组新增「今天该看」：今日贡献、看点、预警、纪律破线、存款 30 天到期
- 复用 market/discipline/deposits 数据，只读不改仓

### 修复
- UZI 弹窗迁到持仓页本地，避免跨组件点击无反应

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

---

## [2026-07-23] — UZI-Skill 混合集成（第一步）

- 持仓明细新增「UZI 分析」按钮
- 自动生成带真实持仓（数量/普通成本/摊薄成本/浮盈/仓位占比）的提示词
- 支持 lite/medium/deep 切换 + 一键复制
- 提示词直接粘贴本机 Hermes 执行（UZI 仍在本地跑）

