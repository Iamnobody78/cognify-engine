# ===== bottlesumo-pi 治理中心 — 生产 TLS 部署指南 (S6) =====

> 审计缺陷 S6: 部署容器缺少 HTTPS/TLS 生产配置 (TLS 终止缺失)。
> 本目录提供生产级 TLS 终止层, 与基础 `docker-compose.yml` 叠加使用。

## 架构

```
                        ┌─────────────────────────────────┐
  客户端 ──HTTPS 443──▶ │  nginx (frontend 容器, TLS 终止)  │
                        │  ├─ /api/*  ──▶ backend:8000     │
                        │  ├─ /v1/*   ──▶ backend:8000     │  (A4 版本化 API)
                        │  └─ /metrics──▶ backend:8000     │
                        └─────────────────────────────────┘
```

TLS 在 nginx 终止, backend 保持容器内明文 HTTP — 标准反向代理模式,
证书私钥不出容器网络, 后端无需感知 TLS。

## 快速开始

```bash
# 1. 生成证书 (自签/内部环境)
bash deployment/gen_self_signed_cert.sh

# 2. 设置生产密钥 (必填, 否则 compose 拒绝启动)
export GOV_AUTH_SECRET=$(openssl rand -hex 32)

# 3. 启动 (基础 + TLS 叠加层)
docker compose -f docker-compose.yml -f deployment/docker-compose.tls.yml up --build -d
```

验证:

```bash
curl -k https://localhost/api/health          # 应返回 200
curl -s http://localhost/api/health -o /dev/null -w "%{http_code}\n"   # 301 → HTTPS
```

## 文件清单

| 文件 | 作用 |
|------|------|
| `nginx-tls.conf` | TLS 终止 nginx 配置 (TLS1.2/1.3, HSTS, 安全头, HTTP→HTTPS 跳转) |
| `docker-compose.tls.yml` | 生产叠加层: 挂载 TLS 配置/证书, 强制 GOV_AUTH_SECRET |
| `gen_self_signed_cert.sh` | 自签证书生成脚本 (openssl, 输出到 `certs/`) |
| `prometheus.yml` | 可观测配置 (基础 compose 的 observability profile 使用) |

## 公网部署 (Let's Encrypt)

```bash
# 1. 申请证书 (需域名 DNS 已指向服务器)
sudo apt install certbot
sudo certbot certonly --standalone -d gov.your-domain.com

# 2. 复制到部署目录
sudo cp /etc/letsencrypt/live/gov.your-domain.com/fullchain.pem deployment/certs/bottlesumo.crt
sudo cp /etc/letsencrypt/live/gov.your-domain.com/privkey.pem   deployment/certs/bottlesumo.key
sudo chown $USER deployment/certs/bottlesumo.*

# 3. 启动 (同上)
```

证书续期: `certbot renew` (每 90 天), 续期后需重启 frontend 容器加载新证书。

## 安全基线对照 (S6)

- [x] TLS 1.2/1.3 仅启用 (禁用 SSLv3/TLS 1.0/1.1)
- [x] HSTS: `max-age=31536000; includeSubDomains`
- [x] HTTP → HTTPS 301 跳转
- [x] 安全响应头: `X-Content-Type-Options: nosniff` / `X-Frame-Options: DENY` / CSP
- [x] 生产密钥强制: `GOV_AUTH_SECRET` 未设置则 compose 拒绝启动 (fail-closed 配置)
- [x] backend 不直接暴露公网 (生产端口 8000 不映射宿主机)

## 注意

- 自签证书浏览器会告警 — 仅用于内网/演示; 公网必须使用 Let's Encrypt 或商业 CA。
- `.gitignore` 建议忽略 `deployment/certs/` (私钥不得入库)。
- TLS 层只负责传输加密; 应用层治理裁决 (ALLOW/DENY/ESCALATE) 语义不变。
