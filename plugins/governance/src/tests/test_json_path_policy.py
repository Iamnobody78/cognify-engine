"""TASK-REAL-010 — B 阶段 (json_path 工具治理) + 可解释主控 Step 1 (审计 Schema).

覆盖:
  1. json_path 解析器 (零依赖 JSONPath 子集: $ .key .. [N] [*])
  2. _json_extract 提取与安全回退 (非 JSON 体 → 空列表)
  3. Rule 条件规则匹配语义 (路径+方法+body 三重条件)
  4. 加载期 fail-closed 校验 (坏 json_path/json_pattern 拒绝载入)
  5. 工具杀伤半径权重表 (lethality_for_tool, 归一化+同形异义字)
  6. DecisionRecord 审计字段 + storage 持久化 + 旧库 ALTER 迁移
  7. e2e: /v1/intercept 体内工具治理 (DENY/ESCALATE/放行)
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import yaml
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src.policy import (
    Rule,
    PolicyEngine,
    _json_extract,
    _parse_json_path,
)
from src.models import DecisionRecord, InterceptRequest
from src.storage import Storage
from src.lethality import lethality_for_tool, TOOL_LETHALITY
from src.main import create_app, _audit_tool_fields

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICIES = REPO_ROOT / "config" / "policies.yaml"


# ── 1. json_path 解析器 ──────────────────────────────────────────────
class TestParseJsonPath(unittest.TestCase):
    def test_tokens_key_idx_wild_descend(self):
        toks = _parse_json_path("$.messages[0].tool_calls[*].function.name")
        assert toks == [
            ("key", "messages"),
            ("idx", 0),
            ("key", "tool_calls"),
            ("wild",),
            ("key", "function"),
            ("key", "name"),
        ]

    def test_tokens_recursive_descent(self):
        assert _parse_json_path("$..name") == [("descend",), ("key", "name")]

    def test_tokens_bare_root_and_leading_dot(self):
        assert _parse_json_path("tool_calls[1]") == [("key", "tool_calls"), ("idx", 1)]

    def test_invalid_syntax_raises(self):
        for bad in ("", "  ", "$.[", "$..[x]", "$.a[b"):
            with self.assertRaises(ValueError):
                _parse_json_path(bad)


# ── 2. _json_extract ─────────────────────────────────────────────────
class TestJsonExtract(unittest.TestCase):
    def test_absolute_path(self):
        body = {"messages": [{"tool_calls": [{"function": {"name": "write_file"}}]}]}
        assert _json_extract(body, "$.messages[0].tool_calls[0].function.name") == [
            "write_file"
        ]

    def test_recursive_descent(self):
        body = {"a": {"b": {"name": "execute_command"}}, "name": "plain"}
        found = _json_extract(body, "$..name")
        assert "execute_command" in found
        assert "plain" in found

    def test_wildcard_list(self):
        body = {"tool_calls": [{"name": "read"}, {"name": "write_file"}]}
        assert _json_extract(body, "$.tool_calls[*].name") == ["read", "write_file"]

    def test_double_encoded_str_body(self):
        inner = json.dumps({"tool_calls": [{"name": "rm_file"}]})
        assert _json_extract(inner, "$..name") == ["rm_file"]

    def test_safe_fallback_non_json(self):
        for body in (None, "", "not json", 42, True, [1, 2]):
            assert _json_extract(body, "$..name") == []


# ── 3. Rule 条件规则 ─────────────────────────────────────────────────
class TestJsonPathRule(unittest.TestCase):
    def _rule(self, **kw):
        defaults = dict(name="t", path_pattern="*", method="POST", action="DENY")
        defaults.update(kw)
        return Rule(**defaults)

    def test_match_when_body_satisfies(self):
        r = self._rule(json_path="$..name", json_pattern=r"^(execute_command)$")
        assert r.matches("/api/any", "POST", {"tool_calls": [{"name": "execute_command"}]})

    def test_no_match_when_pattern_differs(self):
        r = self._rule(json_path="$..name", json_pattern=r"^(execute_command)$")
        assert not r.matches("/api/any", "POST", {"tool_calls": [{"name": "get_weather"}]})

    def test_no_match_when_body_absent_safe_fallback(self):
        r = self._rule(json_path="$..name", json_pattern=r"^(execute_command)$")
        assert not r.matches("/api/any", "POST", None)
        assert not r.matches("/api/any", "POST", "unparseable")

    def test_presence_only_rule(self):
        r = self._rule(json_path="$..name")
        assert r.matches("/api/any", "POST", {"name": "x"})
        assert not r.matches("/api/any", "POST", {"other": 1})

    def test_backward_compat_rule_ignores_body(self):
        r = self._rule()
        assert r.matches("/api/any", "POST", None)
        assert r.matches("/api/any", "POST", {"name": "execute_command"})

    def test_invalid_fields_fail_closed(self):
        for kw in (
            {"json_path": "$.a["},
            {"json_pattern": r"(["},                       # bad regex
            {"json_path": None, "json_pattern": r"^x$"},   # pattern without path
        ):
            with self.assertRaises(ValueError):
                self._rule(**kw)


# ── 4. PolicyEngine 集成 ─────────────────────────────────────────────
class TestPolicyEngineJsonPath(unittest.TestCase):
    def test_yaml_json_rules_load(self):
        engine = PolicyEngine(str(POLICIES))
        rules = yaml.safe_load(POLICIES.read_text(encoding="utf-8"))["rules"]
        names = [r["name"] for r in rules if r.get("json_path") is not None]
        assert "block-shell-tool" in names
        assert "escalate-file-write-tool" in names
        loaded = [r for r in engine.rules if r.json_path is not None]
        assert len(loaded) == len(names)

    def test_evaluate_deny_on_matching_body(self):
        engine = PolicyEngine(str(POLICIES))
        body = {"tool_calls": [{"name": "execute_command"}]}
        result = engine.evaluate("/api/query", "POST", body)
        assert result is not None
        assert result.__dict__["name"] == "block-shell-tool"

    def test_evaluate_escalate_on_write_tool(self):
        engine = PolicyEngine(str(POLICIES))
        body = {"tool_calls": [{"name": "write_file"}]}
        result = engine.evaluate("/api/query", "POST", body)
        assert result.__dict__["name"] == "escalate-file-write-tool"

    def test_evaluate_benign_tool_no_rule(self):
        engine = PolicyEngine(str(POLICIES))
        body = {"tool_calls": [{"name": "get_weather"}]}
        assert engine.evaluate("/api/query", "POST", body) is None

    def test_evaluate_non_json_body_safe(self):
        engine = PolicyEngine(str(POLICIES))
        assert engine.evaluate("/api/query", "POST", "garbage") is None
        assert engine.evaluate("/api/query", "POST", None) is None

    def test_evaluate_backward_compat_no_body(self):
        engine = PolicyEngine(str(POLICIES))
        # 路径型规则不因 body 参数而改变行为
        assert engine.evaluate("/api/delete/user", "POST", None) is not None
        assert engine.evaluate("/api/unknown", "GET", None) is None


# ── 5. 工具杀伤半径权重表 ────────────────────────────────────────────
class TestLethality(unittest.TestCase):
    def test_read_write_exec_delete_buckets(self):
        assert lethality_for_tool("search") == 0.2
        assert lethality_for_tool("write_file") == 0.7
        assert lethality_for_tool("execute_command") == 0.95
        assert lethality_for_tool("delete_file") == 0.95
        assert lethality_for_tool("sudo_exec") == 0.95

    def test_unknown_and_empty_default(self):
        assert lethality_for_tool("unknown_tool_xyz") == 0.6
        assert lethality_for_tool("") == 0.6
        assert lethality_for_tool(None) == 0.6

    def test_normalization_case_and_confusable(self):
        assert lethality_for_tool("Execute_Command") == 0.95
        assert lethality_for_tool("delete_f\u03b9le") == 0.95  # U+03B9 iota
        assert lethality_for_tool("ｄｅｌｅｔｅ＿ｆｉｌｅ") == 0.95  # fullwidth NFKC

    def test_table_bounded(self):
        for v in TOOL_LETHALITY.values():
            assert 0.0 <= v <= 1.0


# ── 6. DecisionRecord + storage ──────────────────────────────────────
class TestAuditSchema(unittest.TestCase):
    def test_decision_record_audit_fields(self):
        rec = DecisionRecord(
            id="d1",
            verdict="ALLOW",
            reason="r",
            path="/api/query",
            method="POST",
            tool_name="write_file",
            tool_lethality=0.7,
        )
        data = rec.model_dump(mode="json")
        assert data["tool_name"] == "write_file"
        assert data["tool_lethality"] == 0.7

    def test_audit_fields_optional_none(self):
        rec = DecisionRecord(id="d2", verdict="ALLOW", reason="r", path="/x", method="GET")
        data = rec.model_dump(mode="json")
        assert data["tool_name"] is None
        assert data["tool_lethality"] is None

    def test_audit_helper_worst_tool(self):
        req = InterceptRequest(
            path="/api/query",
            method="POST",
            body={"tool_calls": [{"name": "read"}, {"name": "execute_command"}]},
        )
        tname, tleth = _audit_tool_fields(req)
        assert tname == "execute_command"
        assert tleth == 0.95

    def test_audit_helper_none_when_no_tools(self):
        req = InterceptRequest(path="/api/query", method="GET", body={"x": 1})
        tname, tleth = _audit_tool_fields(req)
        assert tname is None
        assert tleth is None


class TestStorageAuditColumns(unittest.TestCase):
    def test_persist_and_read_audit_fields(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "test.db")
            storage = Storage(db_path=db)
            storage.save(
                {
                    "id": "a1",
                    "verdict": "DENY",
                    "reason": "x",
                    "matched_rule": "block-shell-tool",
                    "timestamp": "2026-01-01T00:00:00+00:00",
                    "path": "/api/query",
                    "method": "POST",
                    "agent_id": "ag-1",
                    "tool_name": "execute_command",
                    "tool_lethality": 0.95,
                }
            )
            row = storage.get_by_id("a1")
            assert row["tool_name"] == "execute_command"
            assert row["tool_lethality"] == 0.95
            assert row["verdict"] == "DENY"
            storage.close()

    def test_migration_legacy_schema(self):
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "legacy.db")
            conn = sqlite3.connect(db)
            conn.execute(
                """CREATE TABLE decisions (
                    id TEXT PRIMARY KEY, verdict TEXT NOT NULL, reason TEXT NOT NULL,
                    matched_rule TEXT, timestamp TEXT NOT NULL, path TEXT NOT NULL,
                    method TEXT NOT NULL, agent_id TEXT)"""
            )
            conn.execute(
                "INSERT INTO decisions VALUES ('old1','ALLOW','r',NULL,"
                "'2026-01-01T00:00:00+00:00','/api/query','GET','ag-1')"
            )
            conn.commit()
            conn.close()
            storage = Storage(db_path=db)
            cols = {r[1] for r in storage.conn.execute("PRAGMA table_info(decisions)")}
            assert "tool_name" in cols
            assert "tool_lethality" in cols
            row = storage.get_by_id("old1")
            assert row["tool_name"] is None
            assert row["tool_lethality"] is None
            assert row["verdict"] == "ALLOW"  # 旧行无损
            storage.close()


# ── 7. e2e: /v1/intercept 体内工具治理 ───────────────────────────────
class TestInterceptJsonPathGovernance(AioHTTPTestCase):
    async def get_application(self):
        return create_app()

    @unittest_run_loop
    async def test_e2e_deny_shell_tool_in_body(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={
                "path": "/api/query",
                "method": "POST",
                "body": {"tool_calls": [{"name": "execute_command"}]},
            },
        )
        assert resp.status == 403
        data = await resp.json()
        assert data["verdict"] == "DENY"
        assert data["matched_rule"] == "block-shell-tool"

    @unittest_run_loop
    async def test_e2e_escalate_write_tool_in_body(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={
                "path": "/api/query",
                "method": "POST",
                "body": {"tool_calls": [{"name": "write_file"}]},
            },
        )
        assert resp.status == 202
        data = await resp.json()
        assert data["verdict"] == "ESCALATE"
        assert data["matched_rule"] == "escalate-file-write-tool"

    @unittest_run_loop
    async def test_e2e_benign_tool_allowed(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={
                "path": "/api/query",
                "method": "POST",
                "body": {"tool_calls": [{"name": "get_weather"}]},
            },
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["verdict"] == "ALLOW"

    @unittest_run_loop
    async def test_e2e_legacy_body_without_tools_unaffected(self):
        resp = await self.client.post(
            "/v1/intercept",
            json={"path": "/api/unknown", "method": "GET"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["verdict"] == "ALLOW"


if __name__ == "__main__":
    unittest.main()
