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

在本机或 VPS 执行：

```bash
python3 -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
```

### 4.3 配置 `.env`

```env
APP_DOMAIN=invest.example.com
GITHUB_OAUTH_CLIENT_ID=你的ClientID
GITHUB_OAUTH_CLIENT_SECRET=你的ClientSecret
GITHUB_OAUTH_ALLOWED_USER=你的GitHub用户名
OAUTH2_PROXY_COOKIE_SECRET=上一步生成的随机字符串
```

注意：真实 `.env` 不要提交到 Git。

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
