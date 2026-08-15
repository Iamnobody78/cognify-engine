"""TASK-REAL-011 — C 阶段 Trace 因果追踪 (DEBT-0019).

覆盖:
  1. _trace_context 提取/生成语义 (X-Trace-ID / X-Parent-Span-ID)
  2. DecisionRecord / InterceptResponse trace 字段
  3. storage 12 列 schema + 旧库无损迁移
  4. get_trace 递归 CTE: 单根 / 链 / 环终止 / 未知 trace
  5. e2e: 响应头回传 / trace 端点 roundtrip / 链式两请求 / 404
"""

import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src.models import DecisionRecord, InterceptResponse, Verdict
from src.storage import Storage
from src.main import create_app, _trace_context


def _is_uuid(value) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError):
        return False


# ── 1. trace 上下文提取 ──────────────────────────────────────────────
class TestTraceContext(unittest.TestCase):
    def test_from_headers(self):
        t, p = _trace_context({"X-Trace-ID": "t1", "X-Parent-Span-ID": "s1"})
        assert t == "t1"
        assert p == "s1"

    def test_missing_headers_generates_new_root(self):
        t, p = _trace_context({})
        assert _is_uuid(t)
        assert p is None  # 根节点语义 (CTE 锚点)

    def test_parent_only_keeps_parent(self):
        t, p = _trace_context({"X-Parent-Span-ID": "s1"})
        assert _is_uuid(t)
        assert p == "s1"

    def test_trace_only_no_parent(self):
        t, p = _trace_context({"X-Trace-ID": "t1"})
        assert t == "t1"
        assert p is None


# ── 2. 模型字段 ──────────────────────────────────────────────────────
class TestTraceModels(unittest.TestCase):
    def test_decision_record_trace_fields(self):
        rec = DecisionRecord(
            id="d1", verdict="DENY", reason="r", path="/api/query", method="POST",
            trace_id="t1", parent_span_id="s0",
        )
        data = rec.model_dump(mode="json")
        assert data["trace_id"] == "t1"
        assert data["parent_span_id"] == "s0"

    def test_intercept_response_trace_id(self):
        resp = InterceptResponse(
            verdict=Verdict.DENY, reason="r", decision_id="d1", trace_id="t1",
        )
        data = resp.model_dump(mode="json")
        assert data["trace_id"] == "t1"


# ── 3. storage schema + 迁移 ─────────────────────────────────────────
class TestTraceStorageSchema(unittest.TestCase):
    def test_fresh_schema_has_12_cols(self):
        with tempfile.TemporaryDirectory() as td:
            storage = Storage(db_path=str(Path(td) / "t.db"))
            cols = {r[1] for r in storage.conn.execute("PRAGMA table_info(decisions)")}
            assert "tool_name" in cols
            assert "tool_lethality" in cols
            assert "trace_id" in cols
            assert "parent_span_id" in cols
            storage.close()

    def test_migration_legacy_10col_schema(self):
        # REAL-010 时代的 10 列 schema → REAL-011 无损迁移
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "legacy10.db")
            conn = sqlite3.connect(db)
            conn.execute(
                """CREATE TABLE decisions (
                    id TEXT PRIMARY KEY, verdict TEXT NOT NULL, reason TEXT NOT NULL,
                    matched_rule TEXT, timestamp TEXT NOT NULL, path TEXT NOT NULL,
                    method TEXT NOT NULL, agent_id TEXT, tool_name TEXT,
                    tool_lethality REAL)"""
            )
            conn.execute(
                "INSERT INTO decisions VALUES ('old1','ALLOW','r',NULL,"
                "'2026-01-01T00:00:00+00:00','/api/query','GET','ag-1','read',0.2)"
            )
            conn.commit()
            conn.close()
            storage = Storage(db_path=db)
            cols = {r[1] for r in storage.conn.execute("PRAGMA table_info(decisions)")}
            assert "trace_id" in cols
            assert "parent_span_id" in cols
            row = storage.get_by_id("old1")
            assert row["tool_name"] == "read"
            assert row["trace_id"] is None  # 旧行无损, trace 字段为 NULL
            storage.close()

    def test_save_read_trace_fields(self):
        with tempfile.TemporaryDirectory() as td:
            storage = Storage(db_path=str(Path(td) / "t.db"))
            storage.save(
                {
                    "id": "d1", "verdict": "DENY", "reason": "x",
                    "matched_rule": "block-shell-tool",
                    "timestamp": "2026-08-03T00:00:00+00:00",
                    "path": "/api/query", "method": "POST", "agent_id": "ag-1",
                    "tool_name": "execute_command", "tool_lethality": 0.95,
                    "trace_id": "trace-1", "parent_span_id": "root-1",
                }
            )
            row = storage.get_by_id("d1")
            assert row["trace_id"] == "trace-1"
            assert row["parent_span_id"] == "root-1"
            assert row["tool_lethality"] == 0.95
            storage.close()


# ── 4. get_trace 递归 CTE ────────────────────────────────────────────
class TestGetTrace(unittest.TestCase):
    def _seed(self, db_path):
        storage = Storage(db_path=db_path)
        base = {
            "verdict": "ALLOW", "reason": "r", "path": "/api/query",
            "method": "POST", "timestamp": "2026-08-03T00:00:00+00:00",
        }
        storage.save({**base, "id": "A", "trace_id": "T1", "parent_span_id": None})
        storage.save({**base, "id": "B", "trace_id": "T1", "parent_span_id": "A"})
        storage.save({**base, "id": "C", "trace_id": "T1", "parent_span_id": "B"})
        return storage

    def test_unknown_trace_empty(self):
        with tempfile.TemporaryDirectory() as td:
            storage = self._seed(str(Path(td) / "t.db"))
            assert storage.get_trace("NO-SUCH-TRACE") == []
            storage.close()

    def test_single_root(self):
        with tempfile.TemporaryDirectory() as td:
            storage = Storage(db_path=str(Path(td) / "t.db"))
            storage.save(
                {
                    "id": "R", "verdict": "ALLOW", "reason": "r",
                    "path": "/api/query", "method": "GET",
                    "timestamp": "2026-08-03T00:00:00+00:00",
                    "trace_id": "T0", "parent_span_id": None,
                }
            )
            nodes = storage.get_trace("T0")
            assert len(nodes) == 1
            assert nodes[0]["id"] == "R"
            assert nodes[0]["depth"] == 0
            storage.close()

    def test_chain_three_nodes_ordered(self):
        with tempfile.TemporaryDirectory() as td:
            storage = self._seed(str(Path(td) / "t.db"))
            nodes = storage.get_trace("T1")
            ids = [n["id"] for n in nodes]
            assert ids == ["A", "B", "C"]
            assert nodes[0]["parent_span_id"] is None
            assert nodes[1]["parent_span_id"] == "A"
            assert nodes[2]["parent_span_id"] == "B"
            depths = [n["depth"] for n in nodes]
            assert depths == [0, 1, 2]
            storage.close()

    def test_self_loop_detaches_terminates(self):
        # 单亲链中"可达环"在结构上不可能 (改父必脱链); 真正的病态数据是
        # 自引用 (B.parent=B): CTE 沿 R→A 后从 B 扩展时遇到自身 → UNION
        # 去重天然终止, 不挂起、不无限循环。
        with tempfile.TemporaryDirectory() as td:
            storage = Storage(db_path=str(Path(td) / "t.db"))
            base = {
                "verdict": "ALLOW", "reason": "r", "path": "/api/query",
                "method": "POST", "timestamp": "2026-08-03T00:00:00+00:00",
            }
            storage.save({**base, "id": "R", "trace_id": "TC", "parent_span_id": None})
            storage.save({**base, "id": "A", "trace_id": "TC", "parent_span_id": "R"})
            storage.save({**base, "id": "B", "trace_id": "TC", "parent_span_id": "A"})
            # P2 契约: save() 走写缓冲, 未满批不落库; 直接 SQL 需先强制 flush
            # 否则 UPDATE 命中 0 行 (B 仍在缓冲中), 自环语义测试将失真。
            storage._flush_write_buffer()
            storage.conn.execute(
                "UPDATE decisions SET parent_span_id = 'B' WHERE id = 'B'"
            )
            storage.conn.commit()
            nodes = storage.get_trace("TC")
            assert sorted(n["id"] for n in nodes) == ["A", "R"]
            assert all(n["depth"] < 50 for n in nodes)
            storage.close()

    def test_deep_chain_depth_bound(self):
        # 60 层深链: max_depth=50 上限截断, 不挂起
        with tempfile.TemporaryDirectory() as td:
            storage = Storage(db_path=str(Path(td) / "t.db"))
            base = {
                "verdict": "ALLOW", "reason": "r", "path": "/api/query",
                "method": "POST", "timestamp": "2026-08-03T00:00:00+00:00",
            }
            prev = None
            for i in range(60):
                storage.save(
                    {**base, "id": f"N{i:02d}", "trace_id": "TD", "parent_span_id": prev}
                )
                prev = f"N{i:02d}"
            nodes = storage.get_trace("TD")
            assert len(nodes) == 51  # 根 + 50 层 (max_depth 默认值)
            assert nodes[0]["depth"] == 0
            assert nodes[-1]["depth"] == 50
            storage.close()

    def test_lethality_as_edge_weight(self):
        with tempfile.TemporaryDirectory() as td:
            storage = Storage(db_path=str(Path(td) / "t.db"))
            storage.save(
                {
                    "id": "X", "verdict": "DENY", "reason": "r",
                    "path": "/api/query", "method": "POST",
                    "timestamp": "2026-08-03T00:00:00+00:00",
                    "tool_name": "execute_command", "tool_lethality": 0.95,
                    "trace_id": "TW", "parent_span_id": None,
                }
            )
            nodes = storage.get_trace("TW")
            assert nodes[0]["tool_lethality"] == 0.95
            storage.close()


# ── 5. e2e ───────────────────────────────────────────────────────────
class TestTraceEndpoint(AioHTTPTestCase):
    async def get_application(self):
        return create_app()

    @unittest_run_loop
    async def test_e2e_intercept_returns_trace_headers(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/query", "method": "GET"},
        )
        assert resp.status == 200
        trace_id = resp.headers.get("X-Trace-ID")
        span_id = resp.headers.get("X-Span-ID")
        assert _is_uuid(trace_id)
        assert _is_uuid(span_id)
        data = await resp.json()
        assert data["trace_id"] == trace_id
        assert data["decision_id"] == span_id  # span_id == decision.id

    @unittest_run_loop
    async def test_e2e_respects_client_trace_header(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/query", "method": "GET"},
            headers={"X-Trace-ID": "client-trace-1"},
        )
        assert resp.headers.get("X-Trace-ID") == "client-trace-1"

    @unittest_run_loop
    async def test_e2e_trace_endpoint_roundtrip(self):
        first = await self.client.post(
            "/v1/intercept",
            json={
                "path": "/api/query", "method": "POST",
                "body": {"tool_calls": [{"name": "get_weather"}]},
            },
        )
        trace_id = first.headers.get("X-Trace-ID")
        resp = await self.client.get(f"/v1/trace/{trace_id}")
        assert resp.status == 200
        data = await resp.json()
        assert data["trace_id"] == trace_id
        assert data["node_count"] == 1
        assert data["nodes"][0]["trace_id"] == trace_id
        assert data["nodes"][0]["depth"] == 0

    @unittest_run_loop
    async def test_e2e_two_request_chain(self):
        # 第一跳: 新链根
        r1 = await self.client.post(
            "/v1/intercept",
            json={
                "path": "/api/query", "method": "POST",
                "body": {"tool_calls": [{"name": "get_weather"}]},
            },
        )
        trace_id = r1.headers.get("X-Trace-ID")
        span1 = r1.headers.get("X-Span-ID")
        # 第二跳: 携带 X-Parent-Span-ID 指向第一跳 → 形成链
        r2 = await self.client.post(
            "/v1/intercept",
            json={
                "path": "/api/query", "method": "POST",
                "body": {"tool_calls": [{"name": "search"}]},
            },
            headers={"X-Trace-ID": trace_id, "X-Parent-Span-ID": span1},
        )
        assert r2.status == 200
        tree = await self.client.get(f"/v1/trace/{trace_id}")
        data = await tree.json()
        assert data["node_count"] == 2
        assert data["nodes"][0]["parent_span_id"] is None
        assert data["nodes"][1]["parent_span_id"] == data["nodes"][0]["id"]

    @unittest_run_loop
    async def test_e2e_trace_not_found(self):
        resp = await self.client.get("/v1/trace/nonexistent-trace-123")
        assert resp.status == 404
        data = await resp.json()
        assert "error" in data

    # ── TASK-REAL-011.1 (Critic-Security / DEBT-0022) ──────────────────
    # chat/completions 路径全部决策分支必须携带 trace 上下文 — 修复前
    # _deny_decision 与 chat 主路径均无 trace 注入 (HIGH: 宣称-实现断层,
    # relay_state 曾宣称"两处构造点注入"但 chat 分支实际缺失)。

    @unittest_run_loop
    async def test_e2e_chat_malformed_deny_carries_trace(self):
        """chat 畸形工具声明 DENY — 决策落库必须携带生成的 trace_id。"""
        resp = await self.client.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "tools": {"bad": "not-a-list"}},
        )
        assert resp.status == 400
        assert resp.headers.get("X-Trace-ID")  # 新生成的链根 UUID
        span = resp.headers.get("X-Span-ID")
        assert span
        # 决策可在 trace 端点追到 (修复前: chat DENY 决策 trace_id=None → 不可追)
        tree = await self.client.get(f"/v1/trace/{resp.headers['X-Trace-ID']}")
        data = await tree.json()
        assert data["node_count"] == 1
        assert data["nodes"][0]["id"] == span
        assert data["nodes"][0]["verdict"] == "DENY"

    @unittest_run_loop
    async def test_e2e_chat_dangerous_deny_carries_trace(self):
        """chat 危险工具 DENY — 同样携带 trace 上下文 (403 分支)。"""
        resp = await self.client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [
                    {"role": "user", "content": "hi"},
                    {"role": "assistant", "tool_calls": [
                        {"function": {"name": "delete_file", "arguments": "{}"}},
                    ]},
                ],
            },
        )
        assert resp.status == 403
        assert resp.headers.get("X-Trace-ID")
        tree = await self.client.get(f"/v1/trace/{resp.headers['X-Trace-ID']}")
        data = await tree.json()
        assert data["node_count"] == 1
        assert data["nodes"][0]["id"] == resp.headers["X-Span-ID"]
        assert data["nodes"][0]["verdict"] == "DENY"

    @unittest_run_loop
    async def test_e2e_oversized_trace_header_treated_missing(self):
        """超长 X-Trace-ID (>128) — fail-safe 降级为缺失语义: 生成新链根。"""
        big = "x" * 200
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/query", "method": "POST", "body": {}},
            headers={"X-Trace-ID": big},
        )
        assert resp.status == 200
        emitted = resp.headers.get("X-Trace-ID")
        assert emitted and emitted != big  # 被替换为新 UUID
        assert len(emitted) == 36  # uuid4 规范长度

    @unittest_run_loop
    async def test_e2e_oversized_parent_header_treated_root(self):
        """超长 X-Parent-Span-ID (>128) — 降级为 None (链根), 不产生悬空引用。"""
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/query", "method": "POST", "body": {}},
            headers={"X-Trace-ID": "oversized-parent-root", "X-Parent-Span-ID": "y" * 200},
        )
        assert resp.status == 200
        tree = await self.client.get("/v1/trace/oversized-parent-root")
        data = await tree.json()
        assert data["node_count"] == 1
        assert data["nodes"][0]["parent_span_id"] is None


if __name__ == "__main__":
    unittest.main()
