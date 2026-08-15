# 可观测性架构 (observability.md)

> 状态: v1.0 (ARCH T0.3 / GAP-1.1) | 2026-08-10
> 命名空间: `governance_*`（DUAL-ECO 双项目统一指标前缀，agent-governance-v2 侧同前缀）

## 1. 指标（Prometheus /metrics）

| 指标 | 类型 | 标签 | 含义 |
|------|------|------|------|
| `governance_requests_total` | Counter | endpoint, outcome(success/error/exception) | 治理 API 请求计数 |
| `governance_request_duration_seconds` | Histogram | endpoint | 请求时长直方图（P99 决策延迟的原始数据）|
| `governance_audit_writes_total` | Counter | status | 审计写入计数 |

设计要点:
- `/metrics` 端点由 `prometheus-client` 生成，Prometheus 文本格式
- `/metrics` 自身不计入请求计数（避免递归膨胀）
- `MetricsMiddleware` (Starlette BaseHTTPMiddleware) 统一采集，业务代码零埋点

## 2. 结构化日志

- `GOV_LOG_FORMAT=json` → JSON 结构化输出（时间戳/级别/logger/msg + 可选业务字段 endpoint/protocol/status）
- `GOV_LOG_FORMAT=plain`（默认）→ 人类可读
- 实现: `logging_setup.py`（标准库 logging + 自定义 JsonFormatter，零额外依赖）
- logger 命名: `governance.<module>`；业务调用 `get_logger("governance.api").info("deploy", protocol=..., status=...)`

## 3. 监控面板建议（Grafana）

- 面板 1: 请求量（RPS × outcome）— `sum(rate(governance_requests_total[5m])) by (endpoint, outcome)`
- 面板 2: P99 决策延迟 — `histogram_quantile(0.99, sum(rate(governance_request_duration_seconds_bucket[5m])) by (le))`
- 面板 3: 审计写入速率 — `sum(rate(governance_audit_writes_total[5m])) by (status)`
- 告警示例: P99 > 500ms 持续 5m → warning；audit_writes error 占比 > 5% → critical

## 4. 对接方式

```bash
export GOV_LOG_FORMAT=json
python dashboard/backend/main.py
# Prometheus scrape_config 增加:
#   - job_name: 'bottlesumo-dashboard'
#     metrics_path: '/metrics'
#     static_configs: [{'targets': ['localhost:8000']}]
```

## 5. 测试矩阵

- `tests/test_metrics.py` 4 例: 端点 200 / 命名空间 / 计数递增 / 自身排除
- E2E 不依赖 metrics；CI 全量回归含本模块
