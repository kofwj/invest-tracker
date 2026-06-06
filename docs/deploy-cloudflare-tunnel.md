# 接入已有 Cloudflare Tunnel 部署说明

本文档适用于 `deploy/cloudflare-tunnel` 分支，目标场景是：你已经在局域网中部署好了 Cloudflare Zero Trust / Tunnel / Access，本项目只负责在内网服务器上运行 `frontend + backend`。

## 1. 推荐架构

```text
外网用户
  -> Cloudflare DNS / HTTPS / Access
  -> 已有 Cloudflare Tunnel / cloudflared
  -> http://127.0.0.1:8080 或 http://内网服务器IP:8080
  -> frontend 容器
  -> backend 容器
  -> SQLite data/backups
```

本分支不会启动 `cloudflared` 容器，也不保存 Tunnel Token。

## 2. Cloudflare 侧配置

### 2.1 Public Hostname 指向

如果已有 `cloudflared` 和本项目在同一台机器，Public Hostname 建议指向：

```text
Type: HTTP
URL: http://127.0.0.1:8080
```

如果已有 `cloudflared` 在另一台局域网机器上，先把 `.env.cloudflare` 改成：

```env
FRONTEND_BIND=0.0.0.0
FRONTEND_PORT=8080
```

然后 Public Hostname 指向：

```text
Type: HTTP
URL: http://本项目服务器内网IP:8080
```

注意：这种情况下请用局域网防火墙限制 `8080` 只允许 cloudflared 所在机器访问。

### 2.2 Cloudflare Access 鉴权

在 Zero Trust 中确认 Access 应用保护整个域名：

```text
https://invest.example.com/*
```

不要只保护首页，避免 `/api/*` 被绕过。

策略建议：

```text
Allow: 你的邮箱 / GitHub 用户 / Google 用户
```

## 3. 本项目部署

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
- [ ] 如果 cloudflared 同机运行，`frontend` 保持绑定 `127.0.0.1:8080`
- [ ] 如果 cloudflared 不同机运行，局域网防火墙限制 `8080` 只允许 cloudflared 机器访问
- [ ] `backend` 只在 Docker 网络内 `expose 8000`
- [ ] Cloudflare Access 已保护整个域名，包括 `/api/*`
- [ ] `.env.cloudflare` 没有提交到 Git
- [ ] `data/`、`backups/` 没有提交到 Git
- [ ] 已测试备份下载和恢复流程
- [ ] 已配置备份保留天数和异地备份

## 6. 常用命令

```bash
# 查看服务状态
docker compose --env-file .env.cloudflare -f docker-compose.cloudflare.yml ps

# 查看日志
docker compose --env-file .env.cloudflare -f docker-compose.cloudflare.yml logs -f

# 重启前端/后端
docker compose --env-file .env.cloudflare -f docker-compose.cloudflare.yml restart frontend backend

# 健康检查
curl http://127.0.0.1:8080/api/health
```
