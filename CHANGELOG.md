# 更新日志

格式大致遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。  
版本未打 tag 时按日期记录；生产部署以分支 `deploy/vps` 为准。

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
