# Deployment

生产部署指南（Docker / K8s）。

> 注：Docker 支持为 Good First Issue #1，容器镜像构建流程正在社区化中。以下为当前推荐路径。

## 直接运行（systemd / supervisor）

```bash
pip install -r requirements.txt
export CONTEXT_HMAC_KEY=<32字节随机密钥>   # 生产必设：治理头 HMAC
python -m src.main --port 9000
```

关键环境变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `AG_AST_DISABLE` | 未设 | 设为 `1` 关闭 AST 前门（不推荐） |
| `CONTEXT_HMAC_KEY` | 未设 | 未设 = 兼容模式（头防伪造降级，生产必设） |
| `AG_GOV_DB_PATH` | `data/gateway.db` | SQLite 路径 |

## Docker

```bash
# 构建
docker build -t agent-governance:v1.25.0 .

# 运行
docker run -d -p 9000:9000 \
  -e CONTEXT_HMAC_KEY=$(openssl rand -hex 32) \
  -v ./config:/app/config \
  -v ./data:/app/data \
  agent-governance:v1.25.0
```

## Docker Compose

```yaml
version: "3.8"
services:
  gateway:
    image: agent-governance:v1.25.0
    ports:
      - "9000:9000"
    environment:
      CONTEXT_HMAC_KEY: ${CONTEXT_HMAC_KEY}
    volumes:
      - ./config:/app/config
      - ./data:/app/data
    restart: unless-stopped
```

## Kubernetes（规划中，v2.0.0）

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-governance
spec:
  replicas: 2
  selector:
    matchLabels: {app: agent-governance}
  template:
    metadata:
      labels: {app: agent-governance}
    spec:
      containers:
        - name: gateway
          image: agent-governance:v1.25.0
          ports: [{containerPort: 9000}]
          env:
            - {name: CONTEXT_HMAC_KEY, valueFrom: {secretKeyRef: {name: ag-gov, key: hmac}}}
```

## 安全部署清单

- [ ] `CONTEXT_HMAC_KEY` 已设置（32+ 字节随机）
- [ ] 私有漏洞报告已启用（Settings → Security）
- [ ] Dependabot alerts 已启用
- [ ] CodeQL 扫描已配置（`.github/workflows/codeql.yml` 已含，需在 Settings 启用）
- [ ] API Key 经 `config/tenants.yaml` 管理，未入库
- [ ] `AG_AST_DISABLE` 未设置（AST 前门必须开启）

## 可观测性

- 决策审计：SQLite `DecisionRecord`（`/v1/decisions`）
- 因果链：`/v1/trace/{id}`
- 性能：`/v1/bench/intercept`（P14 locust 基准）
- Grafana Dashboard：规划中
