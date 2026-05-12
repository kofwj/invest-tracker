# 投资资产管理系统说明文档 / Investment Tracker Guide

> 更新时间 / Last updated：2026-05-12 07:40 CST  
> 本文档适用于本地运行的 `invest-tracker` 投资资产管理系统。  
> This guide describes the local `invest-tracker` investment portfolio web app.

---

## 1. 系统定位 / Purpose

### 中文

本系统用于管理个人投资组合与资产配置，覆盖：

- A股权益、A股ETF、港股ETF、债券基金、REITs、黄金、证券现金、银行存款；
- 持仓明细、资产配置、银行存款、交易录入/管理、现金设置、资产快照；
- 总资产、投资账户市值、证券现金、银行存款、投资账户盈亏、申购在途；
- 每个持仓标的可维护「预计年化收益」，用于计算组合预计年化；
- 支持场外基金「申购待确认」状态，解决只知道申购金额、份额/净值尚未确认的问题；
- 支持多证券账户交易费率设置，并按账户/分类/方向自动估算手续费，同时保留手动覆盖；
- 支持持仓强制校正/对账锚点，解决历史交易不完整或券商成本口径不一致的问题。

当前版本为本地 MVP：前端 Vue 3 + Element Plus + ECharts，后端 FastAPI + SQLite。

### English

This system manages a personal investment portfolio, including A-share equities, ETFs, bond funds, REITs, gold, brokerage cash, bank deposits, transaction records, asset snapshots, and portfolio allocation analysis. It is a local MVP built with Vue 3 + Element Plus + ECharts on the frontend and FastAPI + SQLite on the backend.

---

## 2. 今日更新摘要 / 2026-05-11 Update Summary

### 中文

本次主要更新：

1. **顶部资产总览重排**
   - 总资产卡片突出展示；
   - 投资账户市值、证券现金、银行存款、投资账户盈亏统一为更清晰的卡片布局；
   - 保持中国市场配色：盈利红色、亏损绿色。

2. **Tab 顺序调整**
   - 当前顺序：资产快照 → 资产配置 → 持仓明细 → 银行存款 → 交易录入/管理 → 现金设置；
   - 默认打开「资产快照」；
   - 原「交易录入」和「交易管理」已合并为「交易录入/管理」。

3. **资产快照优化**
   - 「记录/更新今日快照」改为同日更新，不再因当天已有快照而拒绝；
   - 新增总资产趋势图、当前资产结构图、区间变化明细；
   - 快照字段新增「申购在途」。

4. **资产配置页重做**
   - 顶部新增权益占比、防守资产占比、组合预计年化、申购在途指标；
   - 图表改为「权益/固收/存款」大类结构 + 细分类别占比；
   - 新增配置健康检查：权益波动暴露、防守缓冲、单类集中度、申购在途状态；
   - 银行存款、证券现金、基金申购在途均纳入资产配置，不再只看持仓市值。

5. **银行存款页优化**
   - 新增存款总额、加权平均利率、预计年利息、下一笔到期；
   - 新增银行集中度、到期分布；
   - 存款明细新增组合占比、预计年利息、剩余天数，并按到期时间排序。

6. **交易录入/管理增强**
   - 交易代码/名称支持自动匹配已有持仓；
   - 新标的也可直接录入，并按规则推断分类；
   - 分类可手动修改；
   - 交易价格不再自动填充，必须手动录入真实成交价；
   - 交易管理支持查询、编辑、删除。

7. **申购待确认 / 在途资产支持**
   - 新增交易方向：`申购待确认`；
   - 适用于场外基金申购当天只有金额、份额/净值未确认的场景；
   - 申购在途计入总资产和固收配置；
   - 不计入正式持仓数量、成本和盈亏；
   - 份额确认后，把同一笔交易从 `申购待确认` 改为 `买入`，补充实际份额和确认净值。

8. **证券现金自动联动**
   - 证券现金改为：`现金基准 + 资金流水净额 + 交易现金流`；
   - 买入 / 申购待确认自动扣减；
   - 卖出 / 分红自动增加；
   - 银证转入/转出和现金校准会写入「证券资金流水」，后续可查询。

9. **成本口径修正**
   - 持仓明细区分「普通成本」和「摊薄成本」；
   - 普通成本保留平均成本结转口径；
   - 摊薄成本改为贴近券商口径：累计买入现金 - 卖出回款 - 累计分红，可为负数。

10. **近一年标的收益率**
   - 持仓明细新增「近一年收益」列；
   - 口径为标的自身过去一年价格/净值回溯收益，不等于账户实际持有收益；
   - 支持手动点击「同步近一年收益率」批量更新，查不到数据时显示暂无数据。

11. **证券资金流水**
   - 现金设置页新增「证券资金流水」；
   - 支持银证转入、银证转出、现金校准、其他调整；
   - 支持按日期、证券账户、流水类型查询；
   - 手动校准证券现金时会自动生成一条现金校准流水，后续可追溯。

11. **同步最新价优化**
   - A股 / ETF / REIT 价格同步改为更快的东方财富批量行情；
   - 场外基金如 `f002864`、`f004388` 使用天天基金净值；
   - 前端增加同步 loading 和完成提示，即使价格无变化也会明确反馈。

13. **持仓强制校正 / 对账锚点**
   - 持仓明细每行新增「校正」和「记录」入口；
   - 可按券商实际持仓录入数量、成本价、累计分红；
   - 校正记录作为新的计算锚点：校正日及之前交易不再追溯，校正日之后交易继续滚动；
   - 历史交易不被修改，校正记录可查询和删除。

14. **多证券账户费率与手续费估算**
   - 现金设置页新增「交易费率设置」；
   - 支持多个证券账户分别保存费率，例如华泰证券、招商证券；
   - 每个账户按资产类别维护佣金率、印花税率、过户费率、最低佣金；
   - 交易录入新增「证券账户」字段；
   - 手续费按证券账户 + 资产分类 + 交易方向 + 成交金额自动估算；
   - 手续费输入框仍可手动覆盖，最终以券商实际成交单为准。

15. **安全垫 / 回退机制**
   - 项目已初始化 Git，代码和文档可按提交回退；
   - 真实数据库 `data/invest.db` 不进入 Git，避免泄露和误提交；
   - 新增 `scripts/backup_db.py`、`scripts/restore_db.py`、`scripts/safety_snapshot.py`；
   - 高风险修改前应先创建数据库备份和代码安全快照。

### English

Major updates include redesigned top summary cards, reordered tabs, enhanced asset snapshots, redesigned allocation analysis, richer bank deposit analytics, merged transaction entry/management, pending fund subscription support, brokerage cash auto-linking, brokerage cash-flow records, holding correction anchors, one-year instrument trailing return, improved latest-price synchronization, multi-broker fee settings with automatic fee estimation and manual override, plus Git/database safety-net scripts for rollback.

---

## 3. 运行方式 / How to Run

### 中文

项目路径：

```bash
/Users/jian/invest-tracker
```

后端直接在主机运行：

```bash
cd /Users/jian/invest-tracker
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

前端通过 Docker nginx 提供静态页面：

```bash
cd /Users/jian/invest-tracker
docker compose up -d frontend
```

访问地址：

- 前端页面：http://localhost:8080
- 后端 API：http://localhost:8000
- SQLite 数据库：`/Users/jian/invest-tracker/data/invest.db`

说明：前端 `frontend/index.html` 通过 nginx bind mount 挂载，通常修改后刷新浏览器即可生效；后端代码修改后需要重启 FastAPI。

### English

Run backend on host:

```bash
cd /Users/jian/invest-tracker
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Serve frontend with Docker nginx:

```bash
cd /Users/jian/invest-tracker
docker compose up -d frontend
```

URLs: frontend `http://localhost:8080`, backend API `http://localhost:8000`, database `data/invest.db`.

---

## 4. 页面说明 / Pages

### 4.1 资产快照 / Asset Snapshots

默认首页。用于记录和分析每日资产状态。

包含：

- 最新总资产；
- 区间总资产变化；
- 投资盈亏变化；
- 当前投资 / 流动占比；
- 总资产趋势图；
- 当前资产结构图；
- 区间变化明细；
- 快照历史列表。

快照字段包括：日期、总资产、投资账户市值、银行存款、证券现金、申购在途、投资账户盈亏、投资占比、现金+存款+在途、持仓数。

重要规则：重复点击「记录/更新今日快照」会更新当天快照，不再拒绝重复记录。

### 4.2 资产配置 / Asset Allocation

用于分析组合结构、风险暴露和预计收益。

包含：

- 权益资产占比；
- 固收 + 存款占比；
- 组合预计年化；
- 当前申购在途；
- 大类资产结构图：权益 / 固收 / 存款；
- 细分类别占比图；
- 配置健康检查；
- 资产大类汇总表；
- 细分类别明细表。

当前大类口径：

| 大类 | 包含 |
|---|---|
| 权益 | A股权益、A股ETF、港股ETF、REITs、黄金 |
| 固收 | 债基、证券现金、基金申购在途 |
| 存款 | 银行存款 |

组合预计年化 = 各资产金额 × 预计年化收益率 的加权平均。

### 4.3 持仓明细 / Holdings

展示当前所有确认持仓，包括：名称、分类、代码、持仓数量、买入均价、最新价、市值、累计盈亏、收益率、预计年化收益。

规则：

- 盈利用红色，亏损用绿色；
- 点击持仓行可查看该标的交易记录；
- 「预计年化收益」可编辑，并参与组合预计年化计算；
- `申购待确认` 不会生成正式持仓，不参与持仓盈亏。

### 4.4 银行存款 / Bank Deposits

用于维护和分析银行存款。

包含：

- 存款总额；
- 存款占总资产比例；
- 加权平均利率；
- 预计年利息；
- 下一笔到期；
- 银行集中度；
- 到期分布：30天内、31-90天、91-180天、180天以上、未设置到期；
- 存款明细：银行、金额、组合占比、利率、预计年利息、到期时间、剩余天数、备注、操作。

支持新增、编辑、删除。

### 4.5 交易录入/管理 / Transaction Entry & Management

交易录入和交易管理已合并在同一页面。

支持方向：

- 买入；
- 卖出；
- 分红；
- 申购待确认。

交易字段：日期、证券账户、代码、名称、分类、方向、数量、单价、金额、手续费、备注。

自动匹配规则：

- 输入已有持仓代码时，精确匹配名称和分类；
- 输入已有持仓名称时，精确匹配或唯一候选时自动匹配；
- 新标的可直接录入，不会被旧持仓错误覆盖；
- 新标的按代码/名称推断分类；
- 分类可手动改；
- 不自动填交易价格，价格必须按真实成交价手动录入；
- 手续费按所选证券账户和资产分类自动估算，但可手动覆盖。

交易管理支持：

- 表格显示交易所属证券账户；
- 按日期范围、代码、名称、方向筛选；
- 编辑交易；
- 删除交易；
- 查看申购待确认记录。

### 4.6 现金设置 / Cash Settings

用于校准证券账户现金余额、记录银证资金进出、维护交易费率。

包含：

- 当前证券现金自动余额；
- 手动校准余额；
- 证券资金流水：银证转入、银证转出、现金校准、其他调整；
- 资金流水查询：日期范围、证券账户、流水类型；
- 区间转入、区间转出、区间净额、当前证券现金汇总；
- 多证券账户交易费率设置。

证券现金口径：

```text
证券现金 = 现金基准 + 资金流水净额 + 交易现金流
```

交易现金流规则：

| 方向 | 现金流 |
|---|---|
| 买入 | `-(金额 + 手续费)` |
| 申购待确认 | `-(金额 + 手续费)` |
| 卖出 | `金额 - 手续费` |
| 分红 | `金额 - 手续费` |

现金设置页只用于银证转账或券商余额校准，不建议用它逐笔手动调整交易现金影响。

#### 交易费率设置 / Trading Fee Settings

现金设置页同时提供「交易费率设置」。

支持多个证券账户，每个账户独立维护一套费率：

- 当前费率账户：选择正在编辑的券商账户；
- 新增账户：输入账户名称后新增，例如 `招商证券`；
- 删除当前账户：只删除该账户费率配置，不删除交易记录；
- 保存费率设置：保存当前所有账户费率；
- 恢复默认费率：重置为默认账户和默认费率。

每个账户按资产类别维护：

| 类别 | 佣金率 | 印花税 | 过户费 | 最低佣金 |
|---|---:|---:|---:|---:|
| A股权益 | 可编辑 | 可编辑 | 可编辑 | 可编辑 |
| A股ETF | 可编辑 | 可编辑 | 可编辑 | 可编辑 |
| 港股ETF | 可编辑 | 可编辑 | 可编辑 | 可编辑 |
| REITs | 可编辑 | 可编辑 | 可编辑 | 可编辑 |
| 黄金 | 可编辑 | 可编辑 | 可编辑 | 可编辑 |
| 债基 | 可编辑 | 可编辑 | 可编辑 | 可编辑 |
| 其他 | 可编辑 | 可编辑 | 可编辑 | 可编辑 |

默认口径：

- A股权益：佣金万2.5、卖出印花税万5、过户费万0.1；
- A股ETF / 港股ETF / REITs / 黄金：默认只按佣金估算；
- 债基：默认 0；
- 费率单位是 `%`，例如万2.5填写 `0.025`。

手续费估算规则：

```text
自动估算手续费 = 所选证券账户 + 资产分类 + 交易方向 + 成交金额
```

- 买入：佣金 + 过户费；
- 卖出：佣金 + 印花税 + 过户费；
- 分红 / 申购待确认：通常按 0，除非手动填写；
- 佣金低于最低佣金时，按最低佣金估算；
- 手续费一旦手动修改，后续改金额/分类/方向/账户时不会覆盖手动值，只会更新提示；
- 最终手续费仍以券商成交单为准。

---

## 5. 核心数据口径 / Data Definitions

### 5.1 总资产 / Total Assets

```text
总资产 = 投资账户市值 + 证券现金 + 银行存款 + 申购在途
Total assets = market value + brokerage cash + bank deposits + pending purchase
```

### 5.2 投资账户市值 / Investment Market Value

```text
投资账户市值 = Σ(确认持仓数量 × 最新价)
Investment market value = Σ(confirmed quantity × latest price)
```

### 5.3 投资账户盈亏 / Investment Profit/Loss

```text
投资账户盈亏 = Σ[(最新价 - 买入均价) × 持仓数量 + 累计分红]
Investment P/L = Σ[(latest price - average cost) × quantity + accumulated dividends]
```

说明：申购在途不计入投资账户盈亏。

### 5.4 成本价口径 / Cost Basis

系统保留两个成本口径：

```text
普通成本价 = 剩余持仓普通成本 / 剩余持仓数量
券商摊薄成本 = (累计买入现金 - 累计卖出回款 - 累计分红) / 剩余持仓数量
```

说明：

- 普通成本价用于计算剩余确认持仓的浮动盈亏；
- 券商摊薄成本尽量贴近券商 APP 的持仓成本口径；
- 当历史卖出回款 + 分红已经超过累计买入现金时，券商摊薄成本可能为负数；
- 例如农业银行在当前记录下：`(累计买入 288,018.19 - 卖出回款 330,137.19 - 累计分红 43,934.21) / 41,400 ≈ -2.0786`。

### 5.5 收益率 / Return Rate

```text
收益率 = 累计盈亏 / 普通持仓成本
Return rate = accumulated P/L / ordinary holding cost
```

### 5.6 组合预计年化收益 / Portfolio Expected Annual Return

```text
组合预计年化 = Σ(资产金额 × 预计年化收益率) / Σ资产金额
Portfolio expected annual return = Σ(asset amount × expected return) / Σ(asset amount)
```

### 5.7 近一年标的收益率 / One-Year Instrument Trailing Return

```text
近一年标的收益率 = 标的自身过去一年价格/净值变化率
One-year trailing return = one-year price/NAV change of the instrument itself
```

说明：

- 该指标用于和「预计年化收益」对比：预计年化是未来假设，近一年收益是过去表现；
- 不是账户实际持有收益，不考虑你的买入/卖出时点、仓位变化和资金流；
- A股/ETF/REIT/黄金优先使用前复权K线；场外基金使用净值走势；
- 外部行情源缺失或失败时显示暂无数据。

### 5.8 证券资金流水 / Brokerage Cash Flows

非交易类资金变化通过 `cash_flows` 记录，包括：

| 类型 | 说明 | 对证券现金影响 |
|---|---|---:|
| 银证转入 | 银行转入证券账户 | 增加 |
| 银证转出 | 证券账户转出到银行 | 减少 |
| 现金校准 | 按券商实际余额修正差额 | 按差额增减 |
| 其他调整 | 手工修正 | 按输入金额增减 |

买入、卖出、分红、申购待确认仍属于 `transactions` 交易记录，不放入资金流水。

### 5.9 申购待确认 / Pending Purchase

适用场景：场外基金申购后，券商现金已扣减/冻结，但份额和确认净值尚未给出。

口径：

```text
申购在途 = Σ(方向为 申购待确认 的 金额 + 手续费)
```

规则：

- 计入总资产；
- 计入资产配置中的固收；
- 不计入正式持仓数量；
- 不计入持仓成本和盈亏；
- 份额确认后，编辑原交易为 `买入`，补充实际份额和确认净值。

示例：

```text
日期：2026-05-10
代码：f004388
名称：鹏华丰享
分类：债基
方向：申购待确认
数量：0
单价：0
金额：151000
手续费：0
```

---

## 6. 数据表 / Database Tables

| 表 / Table | 用途 / Purpose |
|---|---|
| `holdings` | 当前确认持仓，由交易记录和校正锚点重算 / Confirmed holdings derived from transactions and correction anchors |
| `transactions` | 交易记录，含证券账户字段 / Transactions with brokerage account |
| `holding_corrections` | 持仓强制校正/对账锚点 / Holding correction anchors |
| `cash_flows` | 证券资金流水：银证转入/转出/现金校准 / Brokerage cash flows |
| `deposits` | 银行存款 / Bank deposits |
| `settings` | 系统设置，如证券现金基准、交易费率配置 / Settings such as brokerage cash base and fee settings |
| `daily_snapshots` | 每日资产快照 / Daily asset snapshots |

### 6.1 `holdings`

主要字段：`code`, `name`, `category`, `quantity`, `avg_cost`, `diluted_cost`, `total_dividend`, `last_price`, `expected_return`, `trailing_return_1y`, `trailing_return_1y_source`, `trailing_return_1y_updated_at`, `updated_at`。

### 6.2 `transactions`

主要字段：`date`, `code`, `name`, `category`, `account`, `direction`, `quantity`, `price`, `amount`, `fee`, `remark`。

### 6.3 `holding_corrections`

主要字段：`date`, `code`, `name`, `category`, `actual_quantity`, `actual_avg_cost`, `actual_total_cost`, `actual_total_dividend`, `remark`, `created_at`。

### 6.4 `cash_flows`

主要字段：`date`, `account`, `flow_type`, `amount`, `balance_before`, `balance_after`, `remark`, `created_at`。

### 6.5 `daily_snapshots`

主要字段：`date`, `total_assets`, `total_market_value`, `bank_balance`, `securities_cash`, `pending_purchase`, `total_profit`, `holdings_count`, `created_at`。

---

## 7. API 接口 / API Endpoints

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/dashboard` | 获取顶部总览数据 |
| GET | `/holdings` | 获取确认持仓 |
| PUT | `/holdings/{code}` | 更新持仓预计年化收益 |
| GET | `/holding-corrections` | 查询持仓校正记录，可按代码过滤 |
| POST | `/holding-corrections` | 新增持仓校正锚点并重算持仓 |
| DELETE | `/holding-corrections/{id}` | 删除持仓校正记录并重算持仓 |
| GET | `/sync-prices` | 同步最新价 |
| GET | `/sync-trailing-returns` | 同步近一年标的收益率 |
| GET | `/transactions` | 获取交易记录，可按 `code` 查询 |
| POST | `/transactions` | 新增交易 |
| PUT | `/transactions/{id}` | 更新交易 |
| DELETE | `/transactions/{id}` | 删除交易 |
| GET | `/deposits` | 获取银行存款 |
| POST | `/deposits` | 新增银行存款 |
| PUT | `/deposits/{id}` | 更新银行存款 |
| DELETE | `/deposits/{id}` | 删除银行存款 |
| GET | `/securities-cash` | 获取证券现金及现金流拆解 |
| PUT | `/securities-cash` | 校准证券现金当前余额，并自动写入现金校准流水 |
| GET | `/cash-flows` | 查询证券资金流水 |
| POST | `/cash-flows` | 新增证券资金流水 |
| PUT | `/cash-flows/{id}` | 编辑证券资金流水 |
| DELETE | `/cash-flows/{id}` | 删除证券资金流水 |
| GET | `/fee-settings` | 获取多账户交易费率配置 |
| PUT | `/fee-settings` | 保存多账户交易费率配置 |
| POST | `/fee-settings/reset` | 恢复默认交易费率配置 |
| POST | `/snapshots` | 记录或更新今日资产快照 |
| GET | `/snapshots` | 查询资产快照 |
| GET | `/snapshots/summary` | 查询快照区间变化汇总 |

---

## 8. 常见操作 / Common Operations

### 8.1 记录/更新今日资产快照

1. 打开「资产快照」。
2. 点击「记录/更新今日快照」。
3. 如果当天没有快照，系统新建；如果当天已有快照，系统更新当天数据。

### 8.2 录入普通买入交易

1. 打开「交易录入/管理」。
2. 选择方向 `买入`。
3. 选择证券账户。
4. 输入代码、名称、分类。
5. 手动输入数量、单价、金额。
6. 系统会自动估算手续费；如与券商成交单不一致，可手动覆盖。
7. 提交记录。

### 8.3 录入基金申购待确认

1. 打开「交易录入/管理」。
2. 方向选择 `申购待确认`。
3. 分类选择 `债基`。
4. 数量和单价可保持 `0`。
5. 金额填写实际申购金额。
6. 提交后，该金额进入「申购在途」，同时证券现金自动扣减。
7. 份额/净值确认后，编辑同一笔交易，方向改为 `买入`，补充确认份额和确认净值。

### 8.4 校准证券现金

1. 打开「现金设置」。
2. 查看当前自动余额。
3. 如发生银证转账或券商余额与系统不一致，输入券商显示的当前现金余额。
4. 点击「保存校准」。

### 8.5 记录银证转入/转出

1. 打开「现金设置」。
2. 在「证券资金流水」选择日期、证券账户、类型。
3. 类型选择 `银证转入` 或 `银证转出`。
4. 填写金额和备注。
5. 点击「新增流水」。
6. 系统会自动更新证券现金，并在流水表中保留记录。

说明：买入、卖出、分红、申购待确认不要在这里录入，应在「交易录入/管理」中记录。

### 8.6 持仓强制校正

适用于券商实际持仓数量/成本价与系统按交易记录重算结果不一致的情况：

1. 打开「持仓明细」；
2. 在对应标的右侧点击「校正」；
3. 选择校正日期，录入券商实际数量、成本价、累计分红；
4. 点击保存后，系统会以该记录作为新的持仓锚点，并重新计算持仓；
5. 点击「记录」可查看该标的历史校正记录，误录后可删除。

说明：强制校正不会修改历史交易；校正日之后新增/编辑/删除交易时，会继续从最新校正点向后滚动计算。

### 8.7 设置多证券账户费率

1. 打开「现金设置」。
2. 在「交易费率设置」中选择当前费率账户。
3. 如需新增券商，填写账户名称并点击「新增账户」。
4. 按类别修改佣金率、印花税、过户费和最低佣金。
5. 点击「保存费率设置」。
6. 后续交易录入选择对应证券账户后，手续费会按该账户费率自动估算。

注意：如果实际成交单手续费不同，直接在交易录入中手动改手续费即可，系统不会再次覆盖手动值。

### 8.7 修改持仓预计年化收益

1. 打开「持仓明细」。
2. 在目标持仓右侧点击「编辑」。
3. 输入新的预计年化收益。
4. 保存后，资产配置页的组合预计年化会重新计算。

---

## 9. 维护说明 / Maintenance Notes

### 9.1 主要文件

| 文件 | 说明 |
|---|---|
| `frontend/index.html` | 前端单文件页面 |
| `backend/main.py` | FastAPI 主逻辑 |
| `backend/models.py` | 模型定义/历史结构 |
| `data/invest.db` | SQLite 数据库 |
| `docker-compose.yml` | Docker 配置 |
| `README_BILINGUAL.md` | 当前说明文档 |

### 9.2 前端修改

前端通过 nginx 容器挂载本地文件，修改 `frontend/index.html` 后通常刷新浏览器即可看到效果，无需 rebuild。

### 9.3 后端修改

修改 `backend/main.py` 后需要重启后端：

```bash
cd /Users/jian/invest-tracker
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

建议修改后验证：

```bash
python3 -m py_compile backend/main.py
```

并检查：

- `GET /dashboard`
- `GET /holdings`
- `GET /transactions`
- `GET /snapshots`

---

## 10. 安全垫与回退 / Safety Net and Rollback

### 10.1 保护范围

本项目现在有两层安全垫：

| 层级 | 保护对象 | 方式 |
|---|---|---|
| 代码/文档 | `backend/`, `frontend/`, `README_BILINGUAL.md`, `scripts/` 等 | Git 提交与回退 |
| 真实数据 | `data/invest.db` | SQLite 时间戳备份文件 |

注意：`data/invest.db` 是真实投资数据，已被 `.gitignore` 排除，不会提交进 Git。

### 10.2 修改前创建安全快照

高风险修改前执行：

```bash
cd ~/invest-tracker
python3 scripts/safety_snapshot.py --label before_some_change
```

它会做两件事：

1. 在 `backups/` 下创建数据库备份，例如：

```text
backups/invest_20260512_090000_before_some_change.db.bak
```

2. 如果代码/文档有变化，会自动创建一条 Git 提交：

```text
safety snapshot: before_some_change
```

### 10.3 只备份数据库

```bash
cd ~/invest-tracker
python3 scripts/backup_db.py --label manual
```

备份脚本使用 SQLite backup API，并会对备份文件执行：

```sql
PRAGMA integrity_check
```

只有完整性检查通过才算备份成功。

### 10.4 恢复数据库

```bash
cd ~/invest-tracker
python3 scripts/restore_db.py backups/invest_YYYYMMDD_HHMMSS_label.db.bak
```

恢复前，脚本会先自动备份当前数据库，生成 `before_restore` 备份，避免二次误操作。

### 10.5 代码回退

查看提交：

```bash
git log --oneline -5
```

回退单个文件：

```bash
git restore frontend/index.html
git restore backend/main.py
```

整仓回到最近一次提交：

```bash
git reset --hard HEAD
```

如果要回到更早提交，先用 `git log --oneline` 找到提交号，再执行：

```bash
git reset --hard <commit_id>
```

### 10.6 操作原则

凡是涉及以下动作，必须先做安全快照：

- 修改总资产、证券现金、成本、收益率等核心公式；
- 批量导入、批量删除、批量重算交易或持仓；
- 修改数据库结构；
- 删除证券账户、交易记录、资金流水、持仓校正；
- 大幅调整前端/后端核心页面。

---

## 11. 注意事项 / Notes

1. 本系统是本地单用户工具，不是生产级多用户系统。
2. `data/invest.db` 是核心数据文件，建议定期备份。
3. 交易价格不会自动填充，必须按真实成交价手动录入。
4. 分红、手续费、交易金额应以券商记录为准；系统手续费只是自动估算。
5. 最新价同步依赖外部行情源，特殊标的可能同步失败。
6. 预计年化收益是个人假设，不代表收益承诺；近一年标的收益率是历史价格/净值回溯指标，不代表账户实际收益。
7. `申购待确认` 只用于尚未确认份额/净值的申购；确认后应改为 `买入`。
8. 同日资产快照会被更新，不会新增多条同日记录。
9. 证券现金由资金流水和交易现金流共同自动联动；现金设置页的校准会生成可追溯流水。
10. 银证转入/转出应记录在「证券资金流水」；买入/卖出/分红/申购待确认应记录在「交易录入/管理」。
11. 多证券账户只影响交易归属和手续费估算；交易记录不会因为删除某个费率账户而自动删除。
12. 高风险修改前必须先执行 `python3 scripts/safety_snapshot.py --label xxx`，确保数据库和代码都有回退点。

---

## 12. 当前功能状态 / Current Feature Status

已实现：

- 顶部资产总览卡片；
- 资产快照默认首页；
- 资产快照趋势图、结构图、区间变化明细；
- 同日快照更新；
- 资产配置分析与健康检查；
- 权益 / 固收 / 存款大类汇总；
- 细分类别明细；
- 银行存款分析、集中度、到期分布、CRUD；
- 持仓明细、交易记录查看、预计年化编辑、近一年标的收益率；
- 交易录入/管理合并；
- 新标的录入、自动分类、分类手动修改；
- 交易价格手动录入；
- 买入、卖出、分红、申购待确认；
- 申购在途计入总资产和固收配置；
- 申购在途不计入正式持仓盈亏；
- 证券现金自动联动交易现金流；
- 持仓明细区分普通成本和券商摊薄成本；
- 证券资金流水：银证转入、银证转出、现金校准、查询、编辑、删除；
- 持仓强制校正：校正锚点、记录查询、删除后重算；
- 最新价同步与前端反馈；
- 多证券账户费率设置；
- 按证券账户/分类/方向自动估算手续费；
- 手续费手动覆盖保护；
- Git 代码版本基线；
- 数据库备份、恢复、安全快照脚本。
