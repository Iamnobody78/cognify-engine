# -*- coding: utf-8 -*-
"""L2 (2026-08-04): tool_args 工具调用规则 — YAML 语法 + 匹配语义 + fail-closed 校验。

验收: tool_args 字段支持 name(工具名, glob) + 参数键值(相对参数的
json_path, glob 值); 与 json_path/json_pattern 互斥; 加载期校验 fail-closed。
"""
import pytest

from src.policy import PolicyEngine

RULE_YAML = """\
rules:
  - name: "block-delete-from-tool"
    path_pattern: "*"
    method: "POST"
    tool_args:
      name: "delete_file"
      path: "/etc/*"
    action: "DENY"
    priority: 10
    reason: "L2 demo: block delete_file on /etc/*"
"""


def make_engine(tmp_path, yaml_text, with_allow=True):
    cfg = tmp_path / "policies.yaml"
    text = yaml_text
    if with_allow:
        text = text + """\
  - name: "allow-chat"
    path_pattern: "/api/chat"
    action: "ALLOW"
    priority: 100
"""
    cfg.write_text(text, encoding="utf-8")
    return PolicyEngine(str(cfg))


def oai_body(name, arguments):
    """OpenAI 规范: messages[].tool_calls[].function.arguments 为 JSON 字符串。"""
    return {
        "messages": [
            {"role": "user", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": name, "arguments": arguments}}
            ]}
        ]
    }


# ── 加载与语法 ────────────────────────────────────────────────

def test_yaml_load_tool_args_rule(tmp_path):
    engine = make_engine(tmp_path, RULE_YAML)
    rule = next(r for r in engine.rules if r.name == "block-delete-from-tool")
    assert rule.tool_args == {"name": "delete_file", "path": "/etc/*"}
    assert rule.action == "DENY"
    assert rule.json_path is None  # 与 json_path 互斥

def test_fail_closed_non_dict_tool_args(tmp_path):
    yaml_text = RULE_YAML.replace("tool_args:\n      name: \"delete_file\"\n      path: \"/etc/*\"",
                                  "tool_args: \"delete_file\"")
    with pytest.raises(ValueError, match="tool_args"):
        make_engine(tmp_path, yaml_text)

def test_fail_closed_empty_value(tmp_path):
    yaml_text = RULE_YAML.replace("path: \"/etc/*\"", "path: \"\"")
    with pytest.raises(ValueError, match="non-empty string"):
        make_engine(tmp_path, yaml_text)

def test_fail_closed_mutual_exclusion(tmp_path):
    yaml_text = """\
rules:
  - name: "both"
    path_pattern: "*"
    json_path: "$..name"
    tool_args: {name: "delete_file"}
    action: "DENY"
"""
    with pytest.raises(ValueError, match="mutually exclusive"):
        make_engine(tmp_path, yaml_text, with_allow=False)

def test_fail_closed_bad_arg_key_jsonpath(tmp_path):
    yaml_text = """\
rules:
  - name: "bad-key"
    path_pattern: "*"
    tool_args: {name: "x", "a[": "y"}
    action: "DENY"
"""
    with pytest.raises(ValueError, match="not a valid json_path"):
        make_engine(tmp_path, yaml_text, with_allow=False)


# ── 匹配语义 ──────────────────────────────────────────────────

def test_match_exact_name_and_arg(tmp_path):
    engine = make_engine(tmp_path, RULE_YAML)
    body = oai_body("delete_file", '{"path": "/etc/hosts"}')
    assert engine.evaluate("/api/chat", "POST", body=body).action == "DENY"

def test_match_glob_arg(tmp_path):
    engine = make_engine(tmp_path, RULE_YAML)
    body = oai_body("delete_file", '{"path": "/etc/passwd"}')
    assert engine.evaluate("/api/chat", "POST", body=body).action == "DENY"

def test_no_match_wrong_tool_name(tmp_path):
    engine = make_engine(tmp_path, RULE_YAML)
    body = oai_body("get_weather", '{"path": "/etc/hosts"}')
    assert engine.evaluate("/api/chat", "POST", body=body).action == "ALLOW"

def test_no_match_wrong_arg_value(tmp_path):
    engine = make_engine(tmp_path, RULE_YAML)
    body = oai_body("delete_file", '{"path": "/tmp/scratch.txt"}')
    assert engine.evaluate("/api/chat", "POST", body=body).action == "ALLOW"

def test_no_match_no_tool_calls(tmp_path):
    engine = make_engine(tmp_path, RULE_YAML)
    body = {"messages": [{"role": "user", "content": "hello"}]}
    assert engine.evaluate("/api/chat", "POST", body=body).action == "ALLOW"

def test_no_match_unparseable_arguments(tmp_path):
    engine = make_engine(tmp_path, RULE_YAML)
    body = oai_body("delete_file", "not-json-{")
    assert engine.evaluate("/api/chat", "POST", body=body).action == "ALLOW"

def test_same_call_scoping(tmp_path):
    """name 与参数必须来自同一个 tool_calls 节点 — 跨调用拼接不得命中。"""
    engine = make_engine(tmp_path, RULE_YAML)
    body = {
        "messages": [
            {"role": "user", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "delete_file", "arguments": '{"path": "/tmp/a"}'}},
                {"id": "c2", "type": "function",
                 "function": {"name": "get_weather", "arguments": '{"path": "/etc/hosts"}'}},
            ]}
        ]
    }
    assert engine.evaluate("/api/chat", "POST", body=body).action == "ALLOW"

def test_arguments_as_dict(tmp_path):
    """部分网关直传 arguments 为 dict (非字符串)。"""
    engine = make_engine(tmp_path, RULE_YAML)
    body = {
        "messages": [
            {"role": "user", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "delete_file", "arguments": {"path": "/etc/hosts"}}}
            ]}
        ]
    }
    assert engine.evaluate("/api/chat", "POST", body=body).action == "DENY"

def test_nested_arg_jsonpath(tmp_path):
    yaml_text = """\
rules:
  - name: "block-delete-nested"
    path_pattern: "*"
    tool_args:
      name: "delete_file"
      "args.files[0]": "/etc/*"
    action: "DENY"
    priority: 10
"""
    engine = make_engine(tmp_path, yaml_text)
    body = oai_body("delete_file", '{"args": {"files": ["/etc/shadow"]}}')
    assert engine.evaluate("/api/chat", "POST", body=body).action == "DENY"
    body_ok = oai_body("delete_file", '{"args": {"files": ["/tmp/x"]}}')
    assert engine.evaluate("/api/chat", "POST", body=body_ok).action == "ALLOW"

def test_match_flat_tool_calls_shape(tmp_path):
    """扁平形状: body.tool_calls[].function (部分 SDK 直传)。"""
    engine = make_engine(tmp_path, RULE_YAML)
    body = {"tool_calls": [{"function": {"name": "delete_file",
                                         "arguments": '{"path": "/etc/hosts"}'}}]}
    assert engine.evaluate("/api/chat", "POST", body=body).action == "DENY"

def test_string_body_supported(tmp_path):
    engine = make_engine(tmp_path, RULE_YAML)
    body = '{"messages": [{"tool_calls": [{"function": {"name": "delete_file", "arguments": "{\\"path\\": \\"/etc/hosts\\"}"}}]}]}'
    assert engine.evaluate("/api/chat", "POST", body=body).action == "DENY"


# ── 优先级集成 ────────────────────────────────────────────────

def test_priority_deny_beats_allow(tmp_path):
    engine = make_engine(tmp_path, RULE_YAML)
    # 同路径同方法: DENY(10) < ALLOW(100) → DENY 先命中
    body = oai_body("delete_file", '{"path": "/etc/hosts"}')
    assert engine.evaluate("/api/chat", "POST", body=body).action == "DENY"
    # 非 /etc/* 的 delete_file → 不命中 tool_args 规则 → ALLOW
    body2 = oai_body("delete_file", '{"path": "/tmp/cleanup"}')
    assert engine.evaluate("/api/chat", "POST", body=body2).action == "ALLOW"

def test_method_mismatch_no_match(tmp_path):
    engine = make_engine(tmp_path, RULE_YAML)
    body = oai_body("delete_file", '{"path": "/etc/hosts"}')
    assert engine.evaluate("/api/chat", "GET", body=body).action == "ALLOW"

def test_tool_args_rule_without_name_key(tmp_path):
    """省略 name → 任意工具名, 仅参数键值命中即匹配。"""
    yaml_text = """\
rules:
  - name: "block-etc-path-any-tool"
    path_pattern: "*"
    tool_args:
      path: "/etc/*"
    action: "DENY"
    priority: 10
"""
    engine = make_engine(tmp_path, yaml_text)
    body = oai_body("read_file", '{"path": "/etc/shadow"}')
    assert engine.evaluate("/api/chat", "POST", body=body).action == "DENY"
