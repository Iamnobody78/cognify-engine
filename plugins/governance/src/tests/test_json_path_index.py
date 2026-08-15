"""P3 (DEBT-0026): json_path 前缀索引树 — 剪枝正确性与语义等价性。

索引只跳过"提取必然为空"的规则 (首段具体键不在 body 顶层 / 首段 idx 而
body 非列表), 其余规则保持原优先级序 —— 因此 evaluate() 结果与线性扫描
逐位等价。本文件三组测试:
  1. _top_level_keys 归一化与 _json_extract 完全一致
  2. JsonPathIndex 剪枝正确性 (含 descend/wild/idx 不可剪枝的关键用例)
  3. engine 级语义等价性 (随机 body 电池 vs 线性参考实现) + 提取调用数
     证明 (剪枝真实生效, 而非仅正确)
"""

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from src.policy import (
    JsonPathIndex,
    PolicyEngine,
    Rule,
    _json_extract,
    _top_level_keys,
)


def _rule(name="r", path_pattern="*", method="POST", action="DENY", priority=100,
          json_path=None, json_pattern=None):
    return Rule(name=name, path_pattern=path_pattern, method=method,
                action=action, priority=priority, json_path=json_path,
                json_pattern=json_pattern)


def _write_policies(rules, tmp_path):
    """写临时 policies.yaml, 返回 PolicyEngine (规则按 priority 升序生效)。"""
    data = {"name": "test", "version": "0.0.0", "rules": rules}
    p = Path(tmp_path) / "policies.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return PolicyEngine(str(p))


# ── 1. _top_level_keys 与 _json_extract 归一化一致 ───────────────────
class TestTopLevelKeys(unittest.TestCase):
    def test_dict_keys(self):
        assert _top_level_keys({"a": 1, "b": 2}) == ({"a", "b"}, False)

    def test_list_body(self):
        assert _top_level_keys([1, 2, 3]) == (set(), True)

    def test_json_string_parity(self):
        assert _top_level_keys('{"a": 1}') == ({"a"}, False)

    def test_non_json_string(self):
        assert _top_level_keys("not json") == (set(), False)

    def test_none_and_scalar(self):
        assert _top_level_keys(None) == (set(), False)
        assert _top_level_keys(42) == (set(), False)
        assert _top_level_keys(True) == (set(), False)


# ── 2. JsonPathIndex 剪枝正确性 ──────────────────────────────────────
class TestIndexPruning(unittest.TestCase):
    def test_key_hit_is_candidate(self):
        idx = JsonPathIndex([_rule(json_path="$.danger.level")])
        got = [r.name for r in idx.candidates({"danger": {"level": 3}})]
        assert got == ["r"]

    def test_key_miss_is_pruned(self):
        idx = JsonPathIndex([_rule(json_path="$.danger.level")])
        got = [r.name for r in idx.candidates({"other": 1})]
        assert got == []  # 首段 key 'danger' 不在顶层键 → 提取必空 → 剪枝

    def test_nested_path_requires_top_key(self):
        # $.a.b.c 命中需要顶层键 'a' 存在; 嵌套在 x 下时提取为空
        r = _rule(json_path="$.a.b.c")
        idx = JsonPathIndex([r])
        assert idx.candidates({"x": {"a": {"b": {"c": 1}}}}) == []
        assert [x.name for x in idx.candidates({"a": {"b": {"c": 1}}})] == ["r"]

    def test_descend_first_never_pruned(self):
        # 关键用例: $..name 可命中任意深度 —— 顶层无 'name' 也不能剪枝
        r = _rule(json_path="$..name")
        idx = JsonPathIndex([r])
        assert [x.name for x in idx.candidates({"tool_calls": [{"name": "x"}]})] == ["r"]
        assert [x.name for x in idx.candidates({"a": {"b": {"name": "x"}}})] == ["r"]

    def test_wild_first_segment_after_key_prunable(self):
        # $.tool_calls[*].name 首段是具体键 → 仍按 'tool_calls' 剪枝
        r = _rule(json_path="$.tool_calls[*].name")
        idx = JsonPathIndex([r])
        assert [x.name for x in idx.candidates({"tool_calls": [{"name": "x"}]})] == ["r"]
        assert idx.candidates({"other": [{"name": "x"}]}) == []

    def test_idx_first_only_list_body(self):
        r = _rule(json_path="$[0].name")
        idx = JsonPathIndex([r])
        assert [x.name for x in idx.candidates([{"name": "x"}])] == ["r"]
        assert idx.candidates({"0": {"name": "x"}}) == []

    def test_empty_root_path_is_any(self):
        r = _rule(json_path="$")
        idx = JsonPathIndex([r])
        assert [x.name for x in idx.candidates({"anything": 1})] == ["r"]

    def test_path_only_rule_always_candidate(self):
        r = _rule(json_path=None)
        idx = JsonPathIndex([r])
        assert [x.name for x in idx.candidates(None)] == ["r"]
        assert [x.name for x in idx.candidates("unparseable")] == ["r"]

    def test_candidates_preserve_priority_order(self):
        # 引擎在 _load 时按 priority 排序后才建索引; 索引保持输入序
        rules = [
            _rule(name="high", priority=10, json_path="$.k"),
            _rule(name="low", priority=200, json_path="$.k"),
            _rule(name="mid", priority=100, json_path="$.other"),
        ]
        idx = JsonPathIndex(rules)
        names = [r.name for r in idx.candidates({"k": 1})]
        assert names == ["high", "low"]  # mid 被剪枝, 其余保持原序


# ── 3. engine 级语义等价 + 剪枝真实生效 ──────────────────────────────
class TestEngineEquivalence(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        rules = [
            {"name": "path-only", "path_pattern": "*", "method": "POST",
             "action": "ALLOW", "priority": 70},
            {"name": "jp-key-hit", "path_pattern": "*", "method": "POST",
             "action": "DENY", "priority": 20, "json_path": "$.danger.level",
             "json_pattern": r"^3$"},
            {"name": "jp-descend", "path_pattern": "*", "method": "POST",
             "action": "DENY", "priority": 30, "json_path": "$..name",
             "json_pattern": r"^execute_command$"},
            {"name": "jp-wild", "path_pattern": "*", "method": "POST",
             "action": "ESCALATE", "priority": 40,
             "json_path": "$.tool_calls[*].name",
             "json_pattern": r"^rm_file$"},
            {"name": "jp-idx", "path_pattern": "*", "method": "POST",
             "action": "SUSPEND", "priority": 50, "json_path": "$[0].name",
             "json_pattern": r"^forbidden$"},
            {"name": "jp-deep", "path_pattern": "*", "method": "POST",
             "action": "ALLOW_WITH_WARNING", "priority": 60,
             "json_path": "$.a.b.c", "json_pattern": r"^deep$"},
        ]
        self.engine = _write_policies(rules, self._tmp.name)

    def _linear(self, path, method, body):
        """无索引参考实现: 逐条规则线性扫描。"""
        for rule in self.engine.rules:
            if rule.matches(path, method, body):
                return rule
        return None

    def _bodies(self):
        return [
            None,
            "unparseable",
            "42",
            {},
            {"danger": {"level": 3}},
            {"danger": {"level": 1}},
            {"other": {"danger": {"level": 3}}},       # danger 非顶层 → 剪枝等价
            {"tool_calls": [{"name": "rm_file"}]},
            {"tool_calls": [{"name": "execute_command"}]},
            [{"name": "forbidden"}],
            [{"name": "allowed"}],
            {"0": {"name": "forbidden"}},               # dict 体对 idx 规则不可提取
            {"a": {"b": {"c": "deep"}}},
            {"x": {"a": {"b": {"c": "deep"}}}},         # a 非顶层 → 剪枝等价
            {"name": "execute_command"},                 # descend 顶层命中
            {"nested": {"deep": {"name": "execute_command"}}},
            {"tool_calls": [{"name": "rm_file"}], "danger": {"level": 3}},
            '{"danger": {"level": 3}}',                  # JSON 字符串体
            {"k": [1, 2], "danger": {"level": 3}},
        ]

    def test_evaluate_equals_linear_reference(self):
        for body in self._bodies():
            got = self.engine.evaluate("/api/x", "POST", body)
            want = self._linear("/api/x", "POST", body)
            got_name = got.name if got else None
            want_name = want.name if want else None
            assert got_name == want_name, (
                f"body={body!r}: indexed={got_name!r} linear={want_name!r}")

    def test_priority_winner_unchanged_by_index(self):
        # 同键多规则: 高层级键命中 + 低层级 wild 双中 → 仍按 priority 取先
        body = {"tool_calls": [{"name": "rm_file"}], "danger": {"level": 3}}
        r = self.engine.evaluate("/api/x", "POST", body)
        assert r.name == "jp-key-hit"  # priority 20 < 40, 且 danger 顶层命中

    def test_extraction_only_for_candidates(self):
        """剪枝真实生效: 仅顶层键命中的 json_path 规则触发 _json_extract。"""
        engine = PolicyEngine(str(Path(self._tmp.name) / "policies.yaml"))
        calls = {"n": 0}

        import src.policy as pol
        orig = pol._json_extract

        def spy(body, jp, segments=None):
            calls["n"] += 1
            return orig(body, jp, segments=segments)

        pol._json_extract = spy
        try:
            # body 顶层键: danger / tool_calls —— evaluate 首中即停, 让
            # jp-key-hit 不匹配 (level=1 ≠ ^3$) 才能观察到后续候选剪枝:
            # jp-key-hit($.danger) + jp-descend($..name, 不可剪枝) +
            # jp-wild($.tool_calls) 共 3 次提取; jp-idx 非列表体剪枝、
            # jp-deep(a 不在顶层) 剪枝、path-only 无 json_path 不提取
            r = engine.evaluate("/api/x", "POST", {"danger": {"level": 1},
                                                   "tool_calls": [{"name": "rm_file"}]})
        finally:
            pol._json_extract = orig
        assert r is not None and r.name == "jp-wild"
        assert calls["n"] == 3, f"expected 3 extractions (key-hit+wild+descend), got {calls['n']}"

    def test_descend_rule_still_extracts_nested(self):
        # 防退化: 剪枝后 descend 规则在嵌套 body 上仍能命中
        r = self.engine.evaluate("/api/x", "POST",
                                 {"outer": {"inner": {"name": "execute_command"}}})
        assert r is not None and r.name == "jp-descend"


# ── 4. 既有 json_path 语义不回归 ────────────────────────────────────
class TestRuleContract(unittest.TestCase):
    def test_rule_matches_uses_cached_segments(self):
        r = _rule(json_path="$..name", json_pattern=r"^execute_command$")
        assert r._segments == [("descend",), ("key", "name")]  # P3 缓存
        assert r.matches("/api/any", "POST",
                         {"tool_calls": [{"name": "execute_command"}]})
        assert not r.matches("/api/any", "POST", {"tool_calls": [{"name": "x"}]})

    def test_invalid_fields_still_fail_closed(self):
        for kw in ({"json_path": "$.a["}, {"json_pattern": r"(["},
                   {"json_path": None, "json_pattern": r"^x$"}):
            with self.assertRaises(ValueError):
                _rule(**kw)

    def test_json_extract_segments_param_parity(self):
        body = {"a": [{"b": 1}]}
        assert _json_extract(body, "$.a[*].b") == _json_extract(
            body, "$.a[*].b", segments=_parse_segments("$.a[*].b"))


def _parse_segments(path):
    from src.policy import _parse_json_path
    return _parse_json_path(path)


if __name__ == "__main__":
    unittest.main()
