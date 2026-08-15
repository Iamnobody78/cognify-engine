#!/usr/bin/env bash
# ===== bottlesumo-pi 自签证书生成 (S6 — TLS 终止前置) =====
# 用法: bash deployment/gen_self_signed_cert.sh
# 输出: deployment/certs/bottlesumo.crt + bottlesumo.key
#
# 适用场景: 内网/开发/演示环境。公网生产请改用 Let's Encrypt:
#   certbot certonly --standalone -d your.domain
#   cp /etc/letsencrypt/live/your.domain/fullchain.pem deployment/certs/bottlesumo.crt
#   cp /etc/letsencrypt/live/your.domain/privkey.pem   deployment/certs/bottlesumo.key
set -euo pipefail

CERT_DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$CERT_DIR"

DAYS="${CERT_DAYS:-825}"          # 默认 825 天 (~2.3年), 可 CERT_DAYS=30 覆盖
SUBJ="${CERT_SUBJ:-/CN=bottlesumo.local}"

if [ -f "$CERT_DIR/bottlesumo.crt" ] && [ -f "$CERT_DIR/bottlesumo.key" ]; then
  echo "[skip] 证书已存在: $CERT_DIR/bottlesumo.{crt,key} (如需重新生成请先删除)"
  exit 0
fi

openssl req -x509 -nodes -newkey rsa:2048 -sha256 \
  -keyout "$CERT_DIR/bottlesumo.key" \
  -out "$CERT_DIR/bottlesumo.crt" \
  -days "$DAYS" -subj "$SUBJ"

chmod 600 "$CERT_DIR/bottlesumo.key"
echo "[ok] 证书生成完成:"
echo "  CRT: $CERT_DIR/bottlesumo.crt"
echo "  KEY: $CERT_DIR/bottlesumo.key"
echo "部署: docker compose -f docker-compose.yml -f deployment/docker-compose.tls.yml up -d"
