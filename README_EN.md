# Investment Tracker Guide

> Last updated: 2026-05-19 06:45 CST  
> Project: local `invest-tracker` investment portfolio management app

---

## 1. Purpose

This app manages a personal investment portfolio and asset allocation, including:

- A-share equities, A-share ETFs, Hong Kong ETFs, bond funds, REITs, and gold;
- Brokerage cash, bank deposits, and pending fund subscriptions;
- Holdings, allocation analysis, asset snapshots, bank deposits, transaction entry/management, and cash settings;
- Transaction records, brokerage cash flows, holding corrections, cost-basis tracking, fee estimation, CSV import/export.

Current version: local single-user MVP.

- Frontend: Vue 3 + Element Plus + ECharts, single file `frontend/index.html`;
- Backend: FastAPI;
- Database: SQLite, default path `data/invest.db`;
- Deployment: both frontend and backend can be started with `docker compose`; nginx serves the frontend and forwards a unified `/api` reverse proxy to the backend;
- The backend database path now works in both host and container environments and defaults to the project-local `data/invest.db`.

---

## 2. How to Run

Project path:

```bash
/Users/jian/invest-tracker
```

Recommended startup:

```bash
cd /Users/jian/invest-tracker
docker compose up -d --build
```

If you only need to restart frontend or backend individually:

```bash
cd /Users/jian/invest-tracker
docker compose up -d --build frontend
docker compose up -d --build backend
```

URLs:

- Frontend: http://localhost:8080
- Proxied API via frontend: http://localhost:8080/api
- Backend API (direct host access): http://localhost:8000
- SQLite database: `/Users/jian/invest-tracker/data/invest.db`

Notes:

- The frontend now talks to the backend through `/api`, so the page no longer hardcodes `8000/8001` ports;
- `frontend/index.html` and `frontend/nginx.conf` are bind-mounted into the nginx container, so changes usually take effect after restarting the frontend container or doing a hard refresh;
- Backend code changes require rebuilding/restarting the backend container;
- The backend database path now works in both host and container environments and uses the project-local `data/invest.db` unless `DB_PATH` is explicitly set.

---

## 3. Main Features

### 3.1 Top Asset Overview

Displays:

- Total assets;
- Investment market value;
- Brokerage cash;
- Bank deposits;
- Investment profit/loss;
- Pending subscriptions.

The UI follows Chinese market color conventions: red for gains, green for losses.

### 3.2 Asset Snapshots

Default home page for recording and analyzing daily asset status.

Features:

- Record/update today's snapshot;
- Same-day snapshots are updated instead of duplicated;
- “Today” is calculated using the backend local timezone, defaulting to `Asia/Shanghai`;
- You can override the backend timezone with the `APP_TIMEZONE` environment variable;
- Total asset trend chart;
- Current asset structure chart;
- Period change details;
- Snapshot history table.

Snapshot fields include date, total assets, investment market value, bank balance, brokerage cash, pending purchase, total profit, investment ratio, cash + deposits + pending, and holdings count.

### 3.3 Asset Allocation

Used to analyze portfolio structure, risk exposure, and expected return.

Includes:

- Equity asset ratio;
- Fixed income + deposit ratio;
- Portfolio expected annual return;
- Pending purchase amount;
- Equity / fixed income / deposit macro allocation chart;
- Detailed category chart;
- Allocation health checks;
- Macro-category summary and detailed category table.

Current macro-category definition:

| Macro category | Included assets |
|---|---|
| Equity | A-share equities, A-share ETFs, Hong Kong ETFs, REITs, gold |
| Fixed income | Bond funds, brokerage cash, pending fund subscriptions |
| Deposits | Bank deposits |

Portfolio expected annual return:

```text
Portfolio expected annual return = Σ(asset amount × expected return) / Σ(asset amount)
```

### 3.4 Holdings

Shows all confirmed holdings.

Main fields:

- Name, category, code;
- Quantity;
- Ordinary cost;
- Diluted cost;
- Latest price;
- Market value;
- Cumulative profit/loss;
- Return rate;
- Expected annual return;
- One-year instrument trailing return.

Actions:

- Edit expected annual return;
- Create holding correction;
- View correction records;
- Click a holding row to view its transaction records;
- Click “sync latest prices” to update latest prices;
- Click “sync one-year returns” to update one-year instrument trailing returns.

Note: `pending purchase` transactions do not create confirmed holdings and do not affect holding-level profit/loss.

### 3.5 Performance Analysis

Used to evaluate the real investment return of the portfolio.

Key metrics:

| Metric | Description |
|---|---|
| Current Total Assets | Market value + brokerage cash + bank deposits + pending purchase |
| Net Contribution | Sum of all "deposit" flows - sum of all "withdrawal" flows |
| Total Gain | Current total assets - net contribution |
| XIRR Annualized | Money-weighted annualized return from external cash flows + current total assets |
| Unrealized P/L + Dividends | Holding unrealized P/L + cumulative dividends |
| YTD Gain | Year-to-date gain, adjusted for period cash flows |

Charts:

- Assets vs. net contribution trend chart;
- Per-holding contribution table (sorted by contribution).

Portfolio cash flows:

- Records external capital entering/leaving the portfolio (new deposits, withdrawals);
- Different from brokerage transfers (which are internal);
- Buy/sell/dividend transactions are internal asset conversions and should NOT be recorded here.

First use: record your historical cumulative investment as an initial baseline.

### 3.6 Bank Deposits

Used to maintain and analyze bank deposits.

Features:

- Create, edit, and delete deposits;
- Total deposits;
- Deposit ratio in total assets;
- Weighted average interest rate;
- Estimated annual interest;
- Next maturity;
- Bank concentration;
- Maturity distribution;
- Download deposit CSV template;
- Export deposits to CSV;
- Import deposits from CSV.

Deposit import template columns:

```text
bank_name, amount, interest_rate, due_date, remark
```

Import notes:

- Current supported format: `.csv`;
- `due_date` uses `YYYY-MM-DD` and may be empty;
- Before import, the system automatically backs up `data/invest.db` to `backups/`;
- Successful rows are written to the real deposit table; failed rows are reported in the import result.

### 3.6 Transaction Entry & Management

Transaction entry and transaction management are combined into one page.

Supported directions:

- Buy;
- Sell;
- Dividend;
- Pending purchase.

Transaction fields:

```text
date, brokerage account, code, name, category, direction, quantity, price, amount, fee, remark
```

Auto-matching rules:

- Existing holding code is matched exactly to name and category;
- Existing holding name is matched exactly, or automatically if there is only one candidate;
- New instruments can be entered directly and will not be overwritten by stale holdings;
- New instruments are categorized by code/name rules;
- Category is manually editable;
- Transaction price is never auto-filled; it must be entered from the real trade confirmation;
- Fee is automatically estimated from brokerage account and asset category, but can be manually overridden.

Transaction management supports:

- Filtering by date range, code, name, and direction;
- Editing transactions;
- Deleting transactions;
- Viewing pending purchase records;
- Downloading the transaction CSV template;
- Exporting transactions to CSV;
- Importing transactions from CSV.

Transaction import template columns:

```text
date, account, code, name, category, direction, quantity, price, amount, fee, remark
```

Import notes:

- Current supported format: `.csv`;
- `date` uses `YYYY-MM-DD`;
- `direction` must be one of `买入`, `卖出`, `分红`, `申购待确认`;
- `amount` should be positive. Buy/sell direction is represented by `direction`;
- The database is automatically backed up before import;
- After successful import, holdings, ordinary cost, diluted cost, brokerage cash, and pending purchase are recalculated automatically.

### 3.7 Cash Settings

Used to calibrate brokerage cash balance, record brokerage cash movements, and maintain trading fee rules.

Includes:

- Current automatically calculated brokerage cash;
- Manual cash calibration;
- Brokerage cash-flow records;
- Cash-flow filters;
- Period inflow, outflow, net flow, and current brokerage cash summary;
- Multi-broker fee settings.

Brokerage cash formula:

```text
Brokerage cash = cash base + cash-flow adjustment + transaction cash flow
```

Transaction cash-flow rules:

| Direction | Cash flow |
|---|---|
| Buy | `-(amount + fee)` |
| Pending purchase | `-(amount + fee)` |
| Sell | `amount - fee` |
| Dividend | `amount - fee` |

Note: buys, sells, dividends, and pending purchases should be recorded in Transaction Entry & Management. Bank-securities transfers, cash calibration, and other adjustments should be recorded in Brokerage Cash Flows.

### 3.8 Brokerage Cash Flows

Non-trading cash changes are recorded in `cash_flows`.

Supported types:

| Type | Description | Impact on brokerage cash |
|---|---|---:|
| Bank-to-broker transfer | Bank account to brokerage account | Increase |
| Broker-to-bank transfer | Brokerage account to bank account | Decrease |
| Cash calibration | Adjust to actual brokerage cash balance | Signed adjustment |
| Other adjustment | Manual adjustment | Signed amount |

The page supports filtering by date, brokerage account, and flow type. It also supports create, edit, and delete.

### 3.9 Multi-Broker Fee Settings and Fee Estimation

Cash Settings provides Trading Fee Settings.

Supported:

- Multiple brokerage accounts with independent fee matrices;
- Per-account fee rules by asset category: commission rate, stamp tax rate, transfer fee rate, and minimum commission;
- Transaction-entry fee estimation based on the selected brokerage account;
- Manual fee override;
- Once manually overridden, later changes to amount/category/direction/account do not overwrite the manual fee.

Default logic:

- A-share equities: commission, sell-side stamp tax, and transfer fee;
- ETFs / REITs / gold: commission only by default;
- Bond funds: 0 by default;
- Rate unit is `%`. For example, 2.5 bps should be entered as `0.025`.

Huatai ordinary account example:

| Category | Commission | Stamp tax | Transfer fee | Minimum commission |
|---|---:|---:|---:|---:|
| A-share equities | 0.013 | 0.05 | 0.001 | 5 |
| A-share ETFs / Hong Kong ETFs / REITs / gold | 0.01 | 0 | 0 | 5 |
| Bond funds | 0 | 0 | 0 | 0 |

### 3.10 Holding Corrections

Used when the brokerage app’s actual holding quantity/cost differs from the value recalculated from transaction history.

Rules:

- A correction is a calculation anchor; it does not modify historical transactions;
- Without corrections: all transactions are used for holding recalculation;
- With corrections: the latest correction anchor is used as the starting point, and only transactions after the correction date are applied;
- Correction records can be queried and deleted;
- After deletion, holdings are recalculated from the remaining records.

Typical use cases:

- Incomplete historical transaction records;
- Missing old fees, dividends, splits, or other events;
- Brokerage cost basis differs from the app’s ordinary cost basis;
- The current brokerage value should become the new calculation anchor.

### 3.11 Ordinary Cost and Diluted Cost

The system keeps two cost-basis metrics:

```text
Ordinary cost per share = remaining ordinary holding cost / remaining quantity
Broker-style diluted cost = (cumulative buy cash - cumulative sell proceeds - cumulative dividends) / remaining quantity
```

Notes:

- Ordinary cost is used to calculate floating profit/loss on the remaining confirmed holdings;
- Diluted cost tries to match the brokerage app’s displayed cost basis;
- Diluted cost can become negative if historical sell proceeds plus dividends exceed cumulative buy cash;
- Cumulative profit/loss still uses ordinary cost to avoid double-counting gains from negative cost.

Agricultural Bank example:

```text
(cumulative buys 288,018.19 - sell proceeds 330,137.19 - cumulative dividends 43,934.21) / 41,400 ≈ -2.0786
```

### 3.12 One-Year Instrument Trailing Return

The holdings table includes a one-year return column.

Definition:

```text
One-year instrument trailing return = one-year price/NAV change of the instrument itself
```

Notes:

- It is historical instrument performance, not the account’s actual holding return;
- It does not consider your buy/sell timing, position changes, cost basis, diluted cost, or cash flows;
- It can be compared with expected annual return: expected return is a future assumption, trailing return is past performance;
- A-shares / ETFs / REITs / gold use adjusted K-line data where possible;
- Open-end funds use Eastmoney/Tiantian Fund accumulated NAV, with unit NAV as fallback;
- If external data is missing or fails, the UI displays “no data”.

---

## 4. Core Data Definitions

### 4.1 Total Assets

```text
Total assets = investment market value + brokerage cash + bank deposits + pending purchase
```

### 4.2 Investment Market Value

```text
Investment market value = Σ(confirmed quantity × latest price)
```

### 4.3 Investment Profit/Loss

```text
Investment P/L = Σ[(latest price - ordinary cost per share) × quantity + cumulative dividends]
```

Pending purchases are not included in investment profit/loss.

### 4.4 Return Rate

```text
Return rate = cumulative P/L / ordinary holding cost
```

### 4.5 Portfolio Expected Annual Return

```text
Portfolio expected annual return = Σ(asset amount × expected return) / Σ(asset amount)
```

### 4.6 Pending Purchase

Use this state when an open-end fund subscription has reduced or frozen brokerage cash but shares/NAV are not confirmed yet.

```text
Pending purchase = Σ(amount + fee for transactions whose direction is pending purchase)
```

Rules:

- Included in total assets;
- Included in fixed-income allocation;
- Not included in confirmed holding quantity;
- Not included in holding cost or profit/loss;
- Once shares/NAV are confirmed, edit the original transaction to `买入` and fill in the actual shares and confirmed NAV.

---

## 5. Database Tables

| Table | Purpose |
|---|---|
| `holdings` | Current confirmed holdings, recalculated from transactions and correction anchors |
| `transactions` | Transaction records, including brokerage account |
| `holding_corrections` | Holding correction anchors |
| `cash_flows` | Brokerage cash flows: transfers, cash calibration, other adjustments |
| `deposits` | Bank deposits |
| `settings` | System settings, such as cash base and fee settings |
| `daily_snapshots` | Daily asset snapshots |
| `portfolio_cash_flows` | Portfolio external cash flows for XIRR analysis |

### 5.1 `holdings`

Main fields:

```text
code, name, category, quantity, avg_cost, diluted_cost, total_dividend,
last_price, expected_return, trailing_return_1y,
trailing_return_1y_source, trailing_return_1y_updated_at, updated_at
```

### 5.2 `transactions`

Main fields:

```text
date, code, name, category, account, direction, quantity, price, amount, fee, remark
```

### 5.3 `holding_corrections`

Main fields:

```text
date, code, name, category, actual_quantity, actual_avg_cost,
actual_total_cost, actual_total_dividend, remark, created_at
```

### 5.4 `cash_flows`

Main fields:

```text
date, account, flow_type, amount, balance_before, balance_after, remark, created_at
```

### 5.5 `daily_snapshots`

Main fields:

```text
date, total_assets, total_market_value, bank_balance, securities_cash,
pending_purchase, total_profit, holdings_count, created_at
```

### 5.6 `portfolio_cash_flows`

Main fields:

```text
date, flow_type (deposit/withdrawal), amount, source, remark, created_at
```

Purpose: Records portfolio-level external capital flows for XIRR annualized return calculation. Different from brokerage transfers (internal) and buy/sell/dividend transactions (asset conversion).

---

## 6. API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/dashboard` | Get top-level dashboard data |
| GET | `/holdings` | Get confirmed holdings |
| PUT | `/holdings/{code}` | Update expected annual return for a holding |
| GET | `/holding-corrections` | Query holding correction records, optionally by code |
| POST | `/holding-corrections` | Create a holding correction anchor and recalculate holdings |
| DELETE | `/holding-corrections/{id}` | Delete a holding correction and recalculate holdings |
| GET | `/sync-prices` | Sync latest prices |
| GET | `/sync-trailing-returns` | Sync one-year instrument trailing returns |
| GET | `/transactions` | Get transactions, optionally by `code` |
| GET | `/transactions/template` | Download transaction CSV import template |
| GET | `/transactions/export` | Export transactions to CSV |
| POST | `/transactions/import` | Import transactions from CSV, with automatic backup and recalculation |
| POST | `/transactions` | Create transaction |
| PUT | `/transactions/{id}` | Update transaction |
| DELETE | `/transactions/{id}` | Delete transaction |
| GET | `/deposits` | Get bank deposits |
| GET | `/deposits/template` | Download bank deposit CSV import template |
| GET | `/deposits/export` | Export bank deposits to CSV |
| POST | `/deposits/import` | Import bank deposits from CSV, with automatic backup |
| POST | `/deposits` | Create bank deposit |
| PUT | `/deposits/{id}` | Update bank deposit |
| DELETE | `/deposits/{id}` | Delete bank deposit |
| GET | `/securities-cash` | Get brokerage cash and cash-flow breakdown |
| PUT | `/securities-cash` | Calibrate current brokerage cash and create a cash calibration record |
| GET | `/cash-flows` | Query brokerage cash flows |
| POST | `/cash-flows` | Add brokerage cash flow |
| PUT | `/cash-flows/{id}` | Edit brokerage cash flow |
| DELETE | `/cash-flows/{id}` | Delete brokerage cash flow |
| GET | `/portfolio-cash-flows` | List portfolio external cash flows |
| POST | `/portfolio-cash-flows` | Add portfolio external cash flow |
| PUT | `/portfolio-cash-flows/{id}` | Edit portfolio external cash flow |
| DELETE | `/portfolio-cash-flows/{id}` | Delete portfolio external cash flow |
| GET | `/performance/summary` | Performance analysis summary (XIRR, net contribution, total gain) |
| GET | `/performance/timeline` | Performance timeline (assets vs net contribution) |
| GET | `/performance/contribution` | Per-holding contribution table |
