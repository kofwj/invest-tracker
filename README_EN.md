# Investment Tracker Guide

> Last updated: 2026-05-13 08:45 CST  
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
- Database: SQLite, `data/invest.db`;
- Frontend is served by Docker nginx, backend runs directly on the host.

---

## 2. How to Run

Project path:

```bash
/Users/jian/invest-tracker
```

Start backend:

```bash
cd /Users/jian/invest-tracker
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Start frontend:

```bash
cd /Users/jian/invest-tracker
docker compose up -d frontend
```

URLs:

- Frontend: http://localhost:8080
- Backend API: http://localhost:8000
- SQLite database: `/Users/jian/invest-tracker/data/invest.db`

Note: `frontend/index.html` is mounted into the nginx container, so frontend changes usually take effect after a browser refresh. Backend changes in `backend/main.py` require restarting FastAPI.

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

### 3.5 Bank Deposits

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
| POST | `/cash-flows` | Create brokerage cash flow |
| PUT | `/cash-flows/{id}` | Update brokerage cash flow |
| DELETE | `/cash-flows/{id}` | Delete brokerage cash flow |
| GET | `/fee-settings` | Get multi-broker fee settings |
| PUT | `/fee-settings` | Save multi-broker fee settings |
| POST | `/fee-settings/reset` | Reset fee settings to defaults |
| POST | `/snapshots` | Record or update today’s asset snapshot |
| GET | `/snapshots` | Query asset snapshots |
| GET | `/snapshots/summary` | Query snapshot period summary |

---

## 7. Common Operations

### 7.1 Record or Update Today’s Asset Snapshot

1. Open Asset Snapshots.
2. Click “Record/Update Today’s Snapshot”.
3. If no snapshot exists today, the system creates one. If one already exists, the system updates it.

### 7.2 Enter a Normal Buy Transaction

1. Open Transaction Entry & Management.
2. Select direction `买入`.
3. Select brokerage account.
4. Enter code, name, and category.
5. Manually enter quantity, price, and amount.
6. The system estimates fee automatically. If it differs from the broker confirmation, override it manually.
7. Submit the transaction.

### 7.3 Enter a Pending Fund Subscription

1. Open Transaction Entry & Management.
2. Select direction `申购待确认`.
3. Select category `债基`.
4. Quantity and price may remain `0`.
5. Enter the actual subscription amount.
6. After submission, the amount becomes pending purchase and brokerage cash is reduced automatically.
7. After shares/NAV are confirmed, edit the same transaction, change direction to `买入`, and fill in actual shares and confirmed NAV.

### 7.4 Calibrate Brokerage Cash

1. Open Cash Settings.
2. Check the current automatically calculated balance.
3. If bank-securities transfers happened or the displayed balance differs from the brokerage app, enter the brokerage app’s current cash balance.
4. Click Save Calibration.
5. The system creates a cash calibration flow record automatically.

### 7.5 Record Bank-Securities Transfers

1. Open Cash Settings.
2. In Brokerage Cash Flows, select date, brokerage account, and type.
3. Choose `银证转入` or `银证转出`.
4. Enter amount and remark.
5. Click Add Flow.
6. The system updates brokerage cash and keeps the flow record.

### 7.6 Create Holding Correction

1. Open Holdings.
2. Click Correction on the target holding row.
3. Select correction date and enter the actual brokerage quantity, cost, and cumulative dividends.
4. Save it. The system uses this record as the new holding anchor and recalculates holdings.
5. Click Records to view historical corrections. Incorrect records can be deleted.

### 7.7 Configure Multi-Broker Fee Settings

1. Open Cash Settings.
2. Select the current fee account in Trading Fee Settings.
3. To add a broker, enter the account name and click Add Account.
4. Edit commission, stamp tax, transfer fee, and minimum commission by category.
5. Click Save Fee Settings.
6. Future transaction entry will estimate fees based on the selected account.

### 7.8 Import/Export Transactions

1. Open Transaction Entry & Management.
2. Click Download Transaction Template and fill in the CSV.
3. Click Export Transactions to back up all existing transactions.
4. Click Import Transactions and upload the CSV.
5. The system backs up the database before import and recalculates holdings and brokerage cash after successful import.

### 7.9 Import/Export Bank Deposits

1. Open Bank Deposits.
2. Click Download Deposit Template and fill in the CSV.
3. Click Export Deposits to back up current deposit records.
4. Click Import Deposits and upload the CSV.
5. The system backs up the database before import.

### 7.10 Edit Expected Annual Return

1. Open Holdings.
2. Click Annual Return or Edit on the target row.
3. Enter the new expected annual return.
4. After saving, the portfolio expected annual return in Asset Allocation is recalculated.

### 7.11 Sync One-Year Instrument Trailing Returns

1. Open Holdings.
2. Click Sync One-Year Returns.
3. The system fetches historical price/NAV data for each holding.
4. Successful rows show percentages. Failed or insufficient-data rows show no data.

---

## 8. Maintenance Notes

### 8.1 Main Files

| File | Description |
|---|---|
| `frontend/index.html` | Single-file frontend page |
| `backend/main.py` | Main FastAPI logic |
| `backend/models.py` | Model definitions / historical structure |
| `data/invest.db` | Real SQLite database |
| `docker-compose.yml` | Docker configuration |
| `README_CN.md` | Chinese guide |
| `README_EN.md` | English guide |
| `README_BILINGUAL.md` | Legacy bilingual guide |

### 8.2 Create a Safety Snapshot Before Risky Changes

Run before high-risk changes:

```bash
cd ~/invest-tracker
python3 scripts/safety_snapshot.py --label before_some_change
```

It will:

1. Create a timestamped database backup under `backups/`;
2. Create a Git commit if code/docs have changed.

### 8.3 Database-Only Backup

```bash
cd ~/invest-tracker
python3 scripts/backup_db.py --label manual
```

The backup script runs SQLite integrity check:

```sql
PRAGMA integrity_check
```

A backup is considered valid only if the integrity check passes.

### 8.4 Restore Database

```bash
cd ~/invest-tracker
python3 scripts/restore_db.py backups/invest_YYYYMMDD_HHMMSS_label.db.bak
```

Before restoring, the script backs up the current database as `before_restore` to avoid irreversible mistakes.

### 8.5 Verify Backend After Changes

```bash
cd /Users/jian/invest-tracker
python3 -m py_compile backend/main.py
```

Recommended checks:

- `GET /dashboard`
- `GET /holdings`
- `GET /transactions`
- `GET /snapshots`

---

## 9. Notes

1. This is a local single-user tool, not a production multi-user system.
2. `data/invest.db` is the core real data file. Back it up regularly.
3. Transaction price is never auto-filled and must be entered from the real trade confirmation.
4. Dividends, fees, and transaction amounts should follow brokerage records. System fee estimation is only a convenience.
5. Latest-price sync and one-year-return sync depend on external market data sources. Some instruments may fail.
6. Expected annual return is a personal assumption, not a return guarantee.
7. One-year instrument trailing return is a historical price/NAV metric, not account-specific return.
8. `申购待确认` should only be used before shares/NAV are confirmed. Once confirmed, edit it to `买入`.
9. Same-day asset snapshots are updated instead of duplicated.
10. Brokerage cash is derived from cash-flow records and transaction cash flows.
11. Bank-securities transfers should be recorded in Brokerage Cash Flows. Buys/sells/dividends/pending purchases should be recorded in Transaction Entry & Management.
12. Multi-broker accounts affect transaction ownership and fee estimation only. Deleting a fee account does not delete transactions.
13. CSV import writes real data. The system backs up automatically before import, but exporting current data first is still recommended.
14. Before high-risk changes, run `python3 scripts/safety_snapshot.py --label xxx`.

---

## 10. Current Feature Status

Implemented:

- Top asset overview cards;
- Asset Snapshots as default home page;
- Snapshot trend chart, structure chart, and period change details;
- Same-day snapshot update;
- Asset allocation analysis and health checks;
- Equity / fixed income / deposit macro allocation summaries;
- Bank deposit analysis, concentration, maturity distribution, and CRUD;
- Bank deposit CSV template, export, and import;
- Holdings, transaction detail view, expected annual return editing;
- One-year instrument trailing return sync and display;
- Combined transaction entry and management;
- New instrument entry, auto-category inference, manual category editing;
- Manual transaction price entry;
- Buy, sell, dividend, and pending purchase;
- Transaction CSV template, export, and import;
- Pending purchase included in total assets and fixed-income allocation;
- Pending purchase excluded from confirmed holding profit/loss;
- Brokerage cash automatically linked to transaction cash flows;
- Ordinary cost and broker-style diluted cost;
- Brokerage cash flows: transfer in/out, cash calibration, query, edit, delete;
- Holding corrections: anchors, record query, recalculation after deletion;
- Latest-price sync with frontend feedback;
- Multi-broker fee settings;
- Fee estimation by brokerage account / category / direction;
- Manual fee override protection;
- Git code baseline;
- Database backup, restore, and safety snapshot scripts.
