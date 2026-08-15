#!/bin/sh
# AFFiNE boot script (mounted into container)
set -e
cd /app
if [ ! -f /tmp/affine_key.pem ]; then
  openssl genrsa -out /tmp/affine_key.pem 2048 2>/dev/null
fi
export DATABASE_URL="postgres://affine:affine@affine-postgres:5432/affine"
export AFFINE_PRIVATE_KEY="$(cat /tmp/affine_key.pem)"
export AFFINE_SERVER_EXTERNAL_URL="http://localhost:3001"
export REDIS_SERVER_HOST="affine-redis"
export REDIS_SERVER_PORT="6379"
echo "[boot] starting AFFiNE backend with RSA key..."
exec node dist/main.js
