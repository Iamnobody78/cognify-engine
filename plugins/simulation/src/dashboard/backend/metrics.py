"""可观测性: Prometheus 指标（统一 governance_* 命名空间, DUAL-ECO P0 一致）。

指标:
- governance_requests_total{endpoint, outcome}    治理 API 请求计数
- governance_request_duration_seconds{endpoint}   请求时长直方图
- governance_audit_writes_total{status}           审计写入计数
"""
import time

from fastapi import Request
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware

REQUESTS = Counter(
    "governance_requests_total", "治理 API 请求计数", ["endpoint", "outcome"]
)
DURATION = Histogram(
    "governance_request_duration_seconds", "治理 API 请求时长（秒）", ["endpoint"]
)
AUDIT_WRITES = Counter(
    "governance_audit_writes_total", "审计写入计数", ["status"]
)


class MetricsMiddleware(BaseHTTPMiddleware):
    """请求计数 + 时长直方图（/metrics 自身不计入，避免递归）。"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/metrics":
            return await call_next(request)
        start = time.perf_counter()
        outcome = "success"
        try:
            response = await call_next(request)
            if response.status_code >= 400:
                outcome = "error"
        except Exception:
            outcome = "exception"
            raise
        finally:
            DURATION.labels(endpoint=request.url.path).observe(
                time.perf_counter() - start
            )
            REQUESTS.labels(endpoint=request.url.path, outcome=outcome).inc()
        return response


def metrics_response() -> Response:
    """/metrics 端点响应（Prometheus 文本格式）。"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
