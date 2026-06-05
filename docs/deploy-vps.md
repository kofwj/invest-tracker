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

## 4. 反向代理与 HTTPS

推荐用 Caddy，配置简单且自动签发 HTTPS。

### Caddy 示例

安装 Caddy 后，编辑 `/etc/caddy/Caddyfile`：

```caddyfile
invest.example.com {
    encode gzip

    basicauth {
        your_user $2a$14$REPLACE_WITH_CADDY_HASHED_PASSWORD
    }

    reverse_proxy 127.0.0.1:8080
}
```

生成 Basic Auth 密码哈希：

```bash
caddy hash-password --plaintext 'your-strong-password'
```

重载：

```bash
sudo systemctl reload caddy
```

### Nginx 示例

如果使用 Nginx，建议配合 Certbot 签发 HTTPS，并加 Basic Auth。

```nginx
server {
    listen 80;
    server_name invest.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name invest.example.com;

    auth_basic "Invest Tracker";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

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
- [ ] Basic Auth / VPN / Cloudflare Access 至少启用一种
- [ ] 防火墙只开放必要端口
- [ ] 已测试创建备份、下载备份、恢复前确认流程
