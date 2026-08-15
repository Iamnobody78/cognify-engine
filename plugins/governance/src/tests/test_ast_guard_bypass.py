"""批判审计回归测试 (2026-08-04)。

外部批判 + 确认审计验证的 3 个 HIGH 漏洞:
  1. AST 只看函数名不看别名/数据流 → getattr(__builtins__, 'eval') 绕过
  2. __builtins__['eval'](...) 下标形态绕过
  3. function_call.arguments / tool_calls[].function.arguments 治理盲区
     (工具参数中的恶意代码静默放行)
  + SQL WHERE 1=1 恒真条件等效全表更新 (原逻辑只看 WHERE 存在性)

这些用例先于修复以失败形态出现 (探针 scripts/probe_base64_bypass.py 实证),
修复后全部转绿。拼接形态 (getattr(__builtins__, 'ev'+'al')) 为静态不可判定
边界, 不在本测试内 —— 见 docs/critique_audit.md 诚实边界。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ast_guard import ASTGuard  # noqa: E402

PAYLOAD_B64 = "X19pbXBvcnRfXygnb3MnKS5zeXN0ZW0oJ3JtIC1yZiAvJyk="


@pytest.fixture(scope="module")
def guard() -> ASTGuard:
    return ASTGuard()


def kinds(fragments):
    return [f.summary for f in fragments]


# ── HIGH-2: 别名/下标绕过 (实证 3/4 的直接形态) ──────────────────────────

def test_getattr_builtins_alias_blocked(guard):
    code = "fn = getattr(__builtins__, 'eval'); fn('os.system(1)')"
    frags = guard.analyze(code, "python")
    assert any("code-execution-alias" in s for s in kinds(frags)), kinds(frags)


def test_getattr_builtin_module_alias_blocked(guard):
    code = "getattr(builtins, 'exec')('x=1')"
    frags = guard.analyze(code, "python")
    assert any("code-execution-alias" in s for s in kinds(frags)), kinds(frags)


def test_builtins_subscript_eval_blocked(guard):
    code = "__builtins__['eval']('os.system(1)')"
    frags = guard.analyze(code, "python")
    assert any("code-execution-subscript" in s for s in kinds(frags)), kinds(frags)


def test_builtin_singular_subscript_compile_blocked(guard):
    code = "__builtin__['compile']('x=1','','exec')"
    frags = guard.analyze(code, "python")
    assert any("code-execution-subscript" in s for s in kinds(frags)), kinds(frags)


# ── HIGH-3: 工具参数盲区 (实证 5/6) ─────────────────────────────────────

def test_function_call_arguments_code_blocked(guard):
    body = {
        "messages": [
            {
                "role": "assistant",
                "function_call": {
                    "name": "python_interpreter",
                    "arguments": json.dumps({
                        "code": (
                            "user_input = base64.b64decode('%s')\n"
                            "eval(user_input)" % PAYLOAD_B64
                        ),
                    }),
                },
            }
        ]
    }
    block = guard.check_request(body)
    assert block is not None and block.findings, "工具参数中的代码未阻断"
    assert any("code-execution" in f.summary for f in block.findings)


def test_tool_calls_arguments_command_blocked(guard):
    body = {
        "messages": [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "run_shell",
                            "arguments": '{"command": "rm -rf /"}',
                        },
                    }
                ],
            }
        ]
    }
    block = guard.check_request(body)
    assert block is not None and block.findings, "工具参数中的命令未阻断"
    assert any("destructive" in f.summary for f in block.findings)


def test_tool_calls_arguments_dict_direct(guard):
    """arguments 直接为 dict (非 JSON 串) 也应被扫描。"""
    body = {
        "tool_calls": [
            {"function": {"name": "shell", "arguments": {"command": "rm -rf /"}}}
        ]
    }
    block = guard.check_request(body)
    assert block is not None and block.findings, "dict 形态工具参数未阻断"


# ── SQL WHERE 恒真 (审计附带的语义漏洞) ────────────────────────────────

@pytest.mark.parametrize("sql", [
    "UPDATE users SET active=0 WHERE 1=1;",
    "UPDATE users SET active=0 WHERE 1 = 1;",
    "DELETE FROM logs WHERE TRUE;",
    "DELETE FROM logs WHERE true;",
])
def test_trivial_where_blocked(guard, sql):
    frags = guard.analyze(sql, "sql")
    assert any("trivial-where-condition" in s for s in kinds(frags)), kinds(frags)


# ── 良性对照 (零误报) ──────────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    "name = getattr(user, 'display_name', '')",
    "x = getattr(obj, 'eval_method')",
    "print(__builtins__['__doc__'])",
])
def test_benign_getattr_not_blocked(guard, code):
    frags = guard.analyze(code, "python")
    assert not frags, kinds(frags)


@pytest.mark.parametrize("sql", [
    "UPDATE users SET active = 0 WHERE active = 1;",
    "UPDATE users SET active=0 WHERE id = 5;",
    "UPDATE users SET active=0 WHERE flag = 1;",
])
def test_benign_where_not_blocked(guard, sql):
    frags = guard.analyze(sql, "sql")
    assert not frags, kinds(frags)


def test_benign_tool_arguments_code_not_blocked(guard):
    body = {
        "messages": [
            {
                "role": "assistant",
                "function_call": {
                    "name": "python_interpreter",
                    "arguments": json.dumps({"code": "def add(a, b): return a + b"}),
                },
            }
        ]
    }
    block = guard.check_request(body)
    assert block is None or not block.findings, (
        [f.summary for f in block.findings] if block else []
    )
