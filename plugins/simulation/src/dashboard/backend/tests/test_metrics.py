"""GAP-1.1 可观测性测试: /metrics 端点 + governance_* 指标存在性。"""
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_metrics_endpoint_ok():
    """/metrics 返回 200 + Prometheus 文本格式。"""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]


def test_metrics_namespace_governance():
    """指标统一 governance_* 命名空间（DUAL-ECO P0 一致）。"""
    resp = client.get("/metrics")
    body = resp.text
    # 先打一个请求确保 counter 存在
    client.get("/api/health")
    body = client.get("/metrics").text
    assert "governance_requests_total" in body
    assert "governance_request_duration_seconds" in body
    assert "governance_audit_writes_total" in body


def test_metrics_counts_requests():
    """请求后 counter 递增（endpoint/outcome 标签）。"""
    client.get("/api/health")
    body = client.get("/metrics").text
    assert 'governance_requests_total{endpoint="/api/health",outcome="success"}' in body


def test_metrics_excludes_itself():
    """/metrics 自身不计入计数（避免递归膨胀）。"""
    before = client.get("/metrics").text
    client.get("/metrics")
    after = client.get("/metrics").text
    # /metrics 不应出现在 endpoint 标签中
    assert 'endpoint="/metrics"' not in after
