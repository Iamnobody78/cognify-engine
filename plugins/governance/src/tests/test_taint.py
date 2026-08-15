"""src/taint.py 数据流补强测试 (批判审计验收: 拼接形态闭合)。

验收标准 (用户裁决 2026-08-04):
  - getattr(__builtins__, 'ev' + 'al') → BLOCK (常量折叠识别 eval)
  - __builtins__['e' + 'val'] → BLOCK (同上)
  - 变量别名间接调用 fn = getattr(...); fn(x) → BLOCK (别名表)
  - 现有 760+ 测试零回归 (本文件不触碰其他模块行为)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ast_guard import ASTGuard  # noqa: E402
from src.taint import analyze_taint  # noqa: E402


@pytest.fixture(scope="module")
def guard() -> ASTGuard:
    return ASTGuard()


def kinds(frags):
    return [f.summary for f in frags]


# ── 单元: analyze_taint 直接检测 ───────────────────────────────────────

@pytest.mark.parametrize("code", [
    "getattr(__builtins__, 'ev' + 'al')('__import__(\"os\").system(\"id\")')",
    "fn = getattr(__builtins__, 'ev' + 'al')\nfn('payload')",
    "__builtins__['e' + 'val']('payload')",
    "x = 'eval'\ngetattr(__builtins__, x)('payload')",
])
def test_taint_detects_folded_builtins(code):
    findings = analyze_taint(code)
    assert findings, f"未检测到: {code!r}"
    for f in findings:
        assert f.kind.startswith("code-execution-")
        assert f.capture in ("alias_exec", "sub_exec")


def test_taint_variable_alias_chain():
    """fn = getattr(builtins, 'ev'+'al'); fn(x) → 别名表解析出 builtins.eval。"""
    findings = analyze_taint(
        "fn = getattr(builtins, 'ev' + 'al')\nfn('__import__(\"os\")')")
    assert findings
    assert any(f.capture == "alias_exec" for f in findings)


def test_taint_benign_no_false_positive():
    """良性: 普通 getattr / 非内建下标 / 字符串拼接。"""
    benign = [
        "name = getattr(user, 'display_name', '')",
        "x = 'ab' + 'c'\nprint(x)",
        "getattr(obj, 'ev' + 'al')('payload')",   # obj 非 builtins
        "mapping['ev' + 'al']('payload')",        # value 非 builtins
    ]
    for code in benign:
        assert not analyze_taint(code), f"误报: {code!r}"


# ── 集成: ASTGuard.analyze 端到端 ─────────────────────────────────────

def test_guard_blocks_folded_getattr(guard):
    code = "getattr(__builtins__, 'ev' + 'al')('os.system(1)')"
    frags = guard.analyze(code, "python")
    assert any("code-execution-alias" in s for s in kinds(frags)), kinds(frags)


def test_guard_blocks_folded_subscript(guard):
    code = "__builtins__['e' + 'val']('os.system(1)')"
    frags = guard.analyze(code, "python")
    assert any("code-execution-subscript" in s for s in kinds(frags)), kinds(frags)


def test_guard_blocks_variable_alias_call(guard):
    code = "fn = getattr(__builtins__, 'ev' + 'al')\nfn('os.system(1)')"
    frags = guard.analyze(code, "python")
    assert any("code-execution-alias" in s for s in kinds(frags)), kinds(frags)


def test_guard_blocks_check_request_tool_args_taint(guard):
    """工具参数盲区 + 拼接形态组合: function_call.arguments 内藏折叠别名。"""
    import json

    body = {
        "messages": [
            {"role": "assistant",
             "function_call": {
                 "name": "python_interpreter",
                 "arguments": json.dumps({
                     "code": "getattr(__builtins__, 'ev' + 'al')('x')",
                 }),
             }},
        ]
    }
    block = guard.check_request(body)
    assert block is not None and block.findings, "工具参数内折叠别名未阻断"


def test_guard_benign_taint_no_false_positive(guard):
    for code in [
        "name = getattr(user, 'display_name', '')",
        "x = 'ab' + 'c'\nprint(x)",
    ]:
        frags = guard.analyze(code, "python")
        assert not frags, f"误报: {code!r} -> {kinds(frags)}"
