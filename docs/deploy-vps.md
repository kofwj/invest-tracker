# VPS 部署说明

本文档适用于 `deploy/vps` 分支。`main` 分支继续作为本地稳定版使用，VPS 相关配置优先放在本分支维护。

## 1. VPS 基础要求

建议配置：

- Ubuntu 22.04/24.04 或 Debian 12
- Docker Engine + Docker Compose Plugin
- Git
- 一个域名，解析到 VPS 公网 IP
- 防火墙只开放：22、80、443

## 2. 首次部署

```bash
git clone https://github.com/kofwj/invest-tracker.git
cd invest-tracker
git switch deploy/vps
cp .env.example .env
```

编辑 `.env`：

```env
APP_TIMEZONE=Asia/Shanghai
DB_PATH=/app/data/invest.db
FRONTEND_BIND=127.0.0.1
FRONTEND_PORT=8080
APP_DOMAIN=invest.example.com
GITHUB_OAUTH_CLIENT_ID=你的ClientID
GITHUB_OAUTH_CLIENT_SECRET=你的ClientSecret
GITHUB_OAUTH_ALLOWED_USER=你的GitHub用户名
OAUTH2_PROXY_COOKIE_SECRET=上一步生成的随机字符串
```

启动：

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

本机检查：

```bash
curl http://127.0.0.1:8080/api/health
```

## 3. 数据持久化

生产 Compose 会把数据保存到宿主机：

```text
./data      # SQLite 数据库
./backups   # 自动/手动备份
```

这两个目录不要提交到 Git，也不要在部署时删除。

## 4. GitHub 登录鉴权、反向代理与 HTTPS

`deploy/vps` 分支默认使用：

```text
Caddy HTTPS -> oauth2-proxy GitHub 登录 -> frontend -> backend
```

公网只需要开放 80/443，后端 `8000` 不暴露公网；前端 `8080` 默认只绑定 `127.0.0.1`，供 VPS 本机健康检查使用。

### 4.1 创建 GitHub OAuth App

进入 GitHub：

```text
Settings -> Developer settings -> OAuth Apps -> New OAuth App
```

填写示例：

```text
Application name: Invest Tracker
Homepage URL: https://invest.example.com
Authorization callback URL: https://invest.example.com/oauth2/callback
```

创建后得到：

- Client ID
- Client Secret

### 4.2 生成 Cookie Secret

`oauth2-proxy` 要求 `cookie_secret` **解码后** 正好是 16 / 24 / 32 字节。

推荐生成方式（32 字节原始密钥，再 base64url；结果通常 43 字符且无 `=` 填充）：

```bash
python3 -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
```

校验当前 `.env` 里 secret 是否合法（应打印 `decoded_bytes= 32 ok`）：

```bash
python3 - <<'PY'
import base64
from pathlib import Path
for line in Path('.env').read_text().splitlines():
    if line.startswith('OAUTH2_PROXY_COOKIE_SECRET='):
        s = line.split('=', 1)[1].strip().strip('"').strip("'")
        raw = base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))
        print('decoded_bytes=', len(raw), 'ok' if len(raw) in (16, 24, 32) else 'BAD')
        break
else:
    print('missing OAUTH2_PROXY_COOKIE_SECRET in .env')
PY
```

常见错误：

- 把 hex / 普通随机串直接当 secret（未按 base64 语义）→ 长度不对；
- secret 两侧加了引号、行尾有空格 → 日志常报 `but is 33/34 bytes`；
- 日志 `cookie_secret must be 16, 24, or 32 bytes ... but is 34 bytes`：请重新生成并整行替换。

改 secret 后执行：

```bash
docker compose -f docker-compose.prod.yml up -d oauth2-proxy
docker compose -f docker-compose.prod.yml ps oauth2-proxy
```

已登录用户需重新走 GitHub 授权。

### 4.3 配置 `.env`

```env
APP_DOMAIN=invest.example.com
GITHUB_OAUTH_CLIENT_ID=你的ClientID
GITHUB_OAUTH_CLIENT_SECRET=你的ClientSecret
GITHUB_OAUTH_ALLOWED_USER=你的GitHub用户名
OAUTH2_PROXY_COOKIE_SECRET=上一步生成的随机字符串
```

注意：真实 `.env` 不要提交到 Git。值两侧不要加引号，行尾不要留空格。

### 4.4 启动带鉴权的生产服务

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

启动后访问：

```text
https://invest.example.com
```

未登录时会跳转到 GitHub 授权；只有 `.env` 中 `GITHUB_OAUTH_ALLOWED_USER` 指定的 GitHub 用户可以访问。

### 4.5 当前鉴权边界

- Caddy 暴露公网 `80/443` 并自动申请 HTTPS 证书；
- oauth2-proxy 负责 GitHub OAuth 登录和会话 Cookie；
- frontend 仍通过内部 Docker 网络访问 backend；
- backend 只 `expose` 给 Docker 网络，不映射公网端口；
- 如果不想让 VPS 本机以外访问 `8080`，保持 `FRONTEND_BIND=127.0.0.1`。


### 4.6 家用 VPS + Cloudflare Tunnel（推荐读）

若域名经 **Cloudflare Tunnel（cloudflared）** 回源到家里/内网机器，**不要**让 Caddy 再申请公网 Let’s Encrypt：公网校验会打到 Cloudflare，拿到的是前端 HTML，证书会失败。

正确链路：

```text
浏览器 --HTTPS--> Cloudflare 边缘
                 --隧道--> 家里 cloudflared
                 --HTTP--> 本机 Caddy:80
                 --forward_auth--> oauth2-proxy
                 --proxy--> frontend → backend
```

**禁止**把隧道 Service 指到 `http://127.0.0.1:8080`（frontend）——会完全绕过 GitHub 登录，表现就是：页面 200 能开、不跳 GitHub、ACME challenge 变成首页 HTML。

#### 配置步骤

1. `.env`：

```env
APP_DOMAIN=asset.anemy.org
CADDYFILE=./caddy/Caddyfile.tunnel
FRONTEND_BIND=127.0.0.1
FRONTEND_PORT=8080
GITHUB_OAUTH_CLIENT_ID=...
GITHUB_OAUTH_CLIENT_SECRET=...
GITHUB_OAUTH_ALLOWED_USER=...
OAUTH2_PROXY_COOKIE_SECRET=...
```

`APP_DOMAIN` **不要**写 `https://`。

2. 重建：

```bash
docker compose -f docker-compose.prod.yml up -d --force-recreate caddy oauth2-proxy frontend
```

3. Cloudflare Zero Trust → Tunnel → Public Hostname：

| 字段 | 值 |
|------|-----|
| Hostname | 你的域名（如 `asset.anemy.org`） |
| Path | （空） |
| Type | HTTP |
| URL | `127.0.0.1:80` 或 `localhost:80` |

若 cloudflared 与 compose 在同一 Docker 网络，也可 `http://caddy:80`。

4. GitHub OAuth App 回调：`https://你的域名/oauth2/callback`

5. 验证（应 302，而不是直接 200 整页 HTML）：

```bash
curl -sI 'https://你的域名/' | head -20
curl -sI 'http://127.0.0.1:80/oauth2/sign_in' | head -15
```

6. 无痕窗口打开域名 → GitHub →（若启用）应用密码。

#### 资金流水失败

与 GitHub 是两层。未过应用密码门时 `/api/cash-flows` 为 401，前端提示「获取资金流水失败」。GitHub 通过后输入 `INVEST_TRACKER_PASSWORD` 再强刷。


## 5. 更新部署

```bash
cd invest-tracker
git switch deploy/vps
./scripts/deploy_vps.sh
```

或者手动：

```bash
git pull --rebase origin deploy/vps
docker compose -f docker-compose.prod.yml up -d --build
```

## 6. 备份建议

应用内“数据维护”页面支持创建、下载、恢复和删除备份。

VPS 上还建议加 cron 定时备份。最简单方式是定时调用应用内备份接口：

```cron
15 2 * * * curl -fsS -X POST http://127.0.0.1:8080/api/maintenance/backups >/dev/null
```

如果使用 cron，请先在 VPS 上手动验证命令可执行。

## 7. 上线前检查清单

- [ ] `.env` 已创建且没有提交到 Git
- [ ] `data/`、`backups/` 没有提交到 Git
- [ ] 域名已解析到 VPS
- [ ] HTTPS 已启用
- [ ] GitHub OAuth 登录已配置，且只允许指定 GitHub 用户访问
- [ ] 防火墙只开放必要端口
- [ ] 已测试创建备份、下载备份、恢复前确认流程


## 8. 更新后核对清单（强烈建议）

部署完成后在 VPS 执行：

```bash
cd /home/kofwj/invest-tracker
python3 scripts/backup_db.py --label before_deploy || true
./scripts/deploy_vps.sh
chmod +x scripts/verify_vps_deploy.sh scripts/cron_sync_prices.sh
./scripts/verify_vps_deploy.sh
```

浏览器强刷（Ctrl/Cmd+Shift+R）后人工确认：

- [ ] 登录页中文正常
- [ ] 首页有「持仓浮盈」与「全周期盈亏」两张卡片
- [ ] 持仓明细两列金额显示正确（非百分比串位）
- [ ] 收益分析贡献表有「全周期盈亏」列
- [ ] 同步最新价 / 半自动分红可用
- [ ] `data/`、`backups/`、`.env` 未被删除

## 9. 定时同步最新价

仓库提供 `scripts/cron_sync_prices.sh`：优先 `docker compose exec` 调用后端同步（绕过密码门与 OAuth），失败再回退本机 curl。

交易日建议：

```cron
20 15 * * 1-5 /home/kofwj/invest-tracker/scripts/cron_sync_prices.sh >> /home/kofwj/invest-tracker/backups/cron_sync_prices.log 2>&1
40 16 * * 1-5 /home/kofwj/invest-tracker/scripts/cron_sync_prices.sh --snapshot >> /home/kofwj/invest-tracker/backups/cron_sync_prices.log 2>&1
```

`--snapshot` 会在同步价后记录/更新今日资产快照。先手动跑一次确认日志正常再写入 crontab。

备份 cron（示例）：

```cron
15 2 * * * curl -fsS -X POST http://127.0.0.1:8080/api/maintenance/backups >/dev/null
```

若开启了 `INVEST_TRACKER_PASSWORD`，curl 备份接口需带 Bearer token；更稳妥是：

```cron
15 2 * * * cd /home/kofwj/invest-tracker && python3 scripts/backup_db.py --label daily >/dev/null
```

## 10. Docker 构建缓存清理

多次 `docker compose … --build` 会在小盘上堆积 **Build Cache**（数 GB）。

- **部署脚本自动清**：`./scripts/deploy_vps.sh` 在 build + health 成功后会执行 `docker builder prune -f`（不影响运行中容器与 `data/`）。
- **可选月度定时**（双保险，即使手工 build 也会回收）：

```cron
30 3 1 * * docker builder prune -f >> /var/log/docker-builder-prune.log 2>&1
```

查看占用：`docker system df` / `docker builder du`。不要对在用镜像使用 `docker system prune -a`。
