# Cloudflare Tunnel 部署说明

本文档适用于 `deploy/cloudflare-tunnel` 分支，目标场景是：项目跑在本地内网服务器，通过 Cloudflare Tunnel 暴露到公网，并使用 Cloudflare Access 做鉴权。

## 1. 推荐架构

```text
外网用户
  -> Cloudflare DNS / HTTPS / Access
  -> Cloudflare Tunnel
  -> 内网服务器 cloudflared 容器
  -> http://127.0.0.1:8080
  -> frontend 容器
  -> backend 容器
  -> SQLite data/backups
```

重点：不需要在路由器开放入站端口，也不要把后端 `8000` 暴露到公网。

## 2. Cloudflare Zero Trust 配置

### 2.1 创建 Tunnel

在 Cloudflare Zero Trust 控制台：

```text
Networks -> Tunnels -> Create a tunnel
```

选择 Docker 方式，复制 Tunnel Token，填入本机 `.env.cloudflare`：

```env
CLOUDFLARE_TUNNEL_TOKEN=你的TunnelToken
```

### 2.2 Public Hostname

给 Tunnel 添加 Public Hostname：

```text
Subdomain: invest
Domain: example.com
Type: HTTP
URL: http://frontend:80
```

如果你选择让 cloudflared 指向宿主机端口，也可以配置：

```text
URL: http://127.0.0.1:8080
```

本分支 Compose 推荐 cloudflared 与 frontend 同在 Docker 网络内，因此优先使用 `http://frontend:80`。

### 2.3 Cloudflare Access 鉴权

在 Zero Trust：

```text
Access -> Applications -> Add an application -> Self-hosted
```

应用域名：

```text
https://invest.example.com
```

策略建议：

```text
Allow: 你的邮箱 / GitHub 用户 / Google 用户
```

注意要保护整个域名，不要只保护首页，确保 `/api/*` 也被 Access 保护。

## 3. 本地服务器部署

```bash
git clone https://github.com/kofwj/invest-tracker.git
cd invest-tracker
git switch deploy/cloudflare-tunnel
cp .env.cloudflare.example .env.cloudflare
```

编辑 `.env.cloudflare`：

```env
APP_TIMEZONE=Asia/Shanghai
DB_PATH=/app/data/invest.db
FRONTEND_BIND=127.0.0.1
FRONTEND_PORT=8080
CLOUDFLARE_TUNNEL_TOKEN=你的TunnelToken
BACKUP_RETENTION_DAYS=60
```

启动：

```bash
docker compose --env-file .env.cloudflare -f docker-compose.cloudflare.yml up -d --build
```

本地健康检查：

```bash
curl http://127.0.0.1:8080/api/health
```

更新部署：

```bash
./scripts/deploy_cloudflare.sh
```

## 4. 备份策略

应用内“数据维护”页面支持手动备份、下载、恢复、删除备份。

建议再加 cron：每天自动备份 + 清理旧备份。

```cron
15 2 * * * cd /opt/invest-tracker && curl -fsS -X POST http://127.0.0.1:8080/api/maintenance/backups >/dev/null
30 2 * * * cd /opt/invest-tracker && BACKUP_RETENTION_DAYS=60 ./scripts/cleanup_backups.sh >> /var/log/invest-tracker-backup-cleanup.log 2>&1
```

如果内网服务器有 NAS/移动硬盘/对象存储，建议定期把 `backups/` 再同步一份出去。

## 5. 安全检查清单

- [ ] 路由器没有转发 `8000` / `8080` 到公网
- [ ] `frontend` 只绑定 `127.0.0.1:8080`
- [ ] `backend` 只在 Docker 网络内 `expose 8000`
- [ ] Cloudflare Access 已保护整个域名，包括 `/api/*`
- [ ] `.env.cloudflare` 没有提交到 Git
- [ ] Tunnel Token 没有出现在 GitHub
- [ ] 不要把包含真实 Token 的 `docker compose config` 输出贴到公开场所
- [ ] `data/`、`backups/` 没有提交到 Git
- [ ] 已测试备份下载和恢复流程
- [ ] 已配置备份保留天数和异地备份

## 6. 常用命令

```bash
# 查看服务状态
docker compose --env-file .env.cloudflare -f docker-compose.cloudflare.yml ps

# 查看日志
docker compose --env-file .env.cloudflare -f docker-compose.cloudflare.yml logs -f

# 重启 tunnel
docker compose --env-file .env.cloudflare -f docker-compose.cloudflare.yml restart cloudflared

# 健康检查
curl http://127.0.0.1:8080/api/health
```
