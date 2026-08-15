"""ML 集成 Phase 1' 测试 — 代码片段语义预筛 (Meta-Harness 裁决 2026-08-04).

依据 docs/ml_integration_verdict.md 裁决 1': 否决 SIREN 集成 (用途错配),
改为复用现有 judge/llm_judge.py 资产 — AST 放行的代码片段 (工具调用参数)
送 LLM-Judge 按红线 A(编码混淆)/C(工具滥用) 复查, 高风险撤销 trace。

核心命题:
1. extract_code_snippets: OpenAI 格式 tool_calls 参数提取 / 工具声明兜底 /
   有界输入 (DEBT-0018 原则延伸)。
2. semantic_code_audit_async: 与 semantic_audit_async 同构 —
   只升不降 / fail-soft / 高风险 revoke / 空输入跳过 / 永不抛异常。
3. main.py 拦截链: verdict != DENY 时并发调度代码审计 (不阻塞主链路)。
4. 零新增依赖: 复用 SEMANTIC_JUDGE_URL 端点, judge prompt 加代码审计标记。
"""

import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

import src.semantic_hook as sh
from src.semantic_hook import (extract_code_snippets, _code_judge_prompt,
                               semantic_code_audit_async)

# ── unit: extraction ────────────────────────────────────────────────────────

def test_extract_code_snippets_openai_tool_calls():
    body = {
        "messages": [{
            "role": "assistant",
            "tool_calls": [{
                "function": {"name": "shell", "arguments": "rm -rf /tmp/x"}
            }],
        }]
    }
    s = extract_code_snippets(body)
    assert "rm -rf /tmp/x" in s


def test_extract_code_snippets_args_dict_values():
    body = {
        "messages": [{
            "role": "assistant",
            "tool_calls": [{
                "function": {"name": "sql", "arguments": {"query": "DROP TABLE users"}}
            }],
        }]
    }
    s = extract_code_snippets(body)
    assert "DROP TABLE users" in s


def test_extract_code_snippets_tools_fallback():
    body = {"tools": [{"function": {"description": "执行任意 shell 命令"}}]}
    s = extract_code_snippets(body)
    assert "执行任意 shell 命令" in s


def test_extract_code_snippets_bounded():
    body = {"messages": [{"role": "assistant", "tool_calls": [
        {"function": {"arguments": "x" * 10000}}]}]}
    s = extract_code_snippets(body, max_total=200)
    assert len(s) <= 200
    assert "...[truncated]..." in s


def test_extract_code_snippets_none_and_empty():
    assert extract_code_snippets(None) == ""
    assert extract_code_snippets("not json") == ""
    assert extract_code_snippets({"messages": [{"role": "user", "content": "hi"}]}) == ""


def test_code_judge_prompt_marked():
    p = _code_judge_prompt("rm -rf /")
    assert "[代码片段语义审计]" in p
    assert "rm -rf /" in p


# ── async: audit hook (fail-soft + revoke) ──────────────────────────────────

async def _judge_server(handler):
    app = web.Application()
    app.router.add_post("/v1/judge", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    return runner, port


async def _run_code_audit(handler, code, enabled=True, threshold=0.85):
    runner, port = await _judge_server(handler)
    old_url, old_en, old_th = sh.SEMANTIC_JUDGE_URL, sh.SEMANTIC_HOOK_ENABLED, sh.SEMANTIC_HOOK_THRESHOLD
    old_to = sh.SEMANTIC_HOOK_TIMEOUT
    sh.SEMANTIC_JUDGE_URL = f"http://127.0.0.1:{port}/v1/judge"
    sh.SEMANTIC_HOOK_ENABLED = enabled
    sh.SEMANTIC_HOOK_THRESHOLD = threshold
    sh.SEMANTIC_HOOK_TIMEOUT = 2.0
    try:
        return await semantic_code_audit_async("trace-1", code)
    finally:
        sh.SEMANTIC_JUDGE_URL, sh.SEMANTIC_HOOK_ENABLED = old_url, old_en
        sh.SEMANTIC_HOOK_THRESHOLD, sh.SEMANTIC_HOOK_TIMEOUT = old_th, old_to
        await runner.cleanup()


def test_code_audit_high_risk_revokes(monkeypatch):
    async def handler(request):
        return web.json_response({"score": 0.95, "level": "CRITICAL", "flags": ["encoding-obfuscation"]})

    revoked = {}

    class _FakeRegistry:
        def revoke(self, trace_id, reason, score):
            revoked["trace"] = trace_id
            revoked["score"] = score

    monkeypatch.setattr("src.revoke.revoke_registry", _FakeRegistry())
    result = asyncio.run(_run_code_audit(handler, "ZWNobyBoYWNrZWQ="))
    assert result["override"] == "ESCALATE"
    assert result["score"] == 0.95
    assert revoked["trace"] == "trace-1"
    assert revoked["score"] == 0.95


def test_code_audit_low_risk_no_revoke(monkeypatch):
    async def handler(request):
        return web.json_response({"score": 0.1, "level": "NORMAL", "flags": []})

    revoked = []

    class _FakeRegistry:
        def revoke(self, trace_id, reason, score):
            revoked.append(trace_id)

    monkeypatch.setattr("src.revoke.revoke_registry", _FakeRegistry())
    result = asyncio.run(_run_code_audit(handler, "echo hello"))
    assert result["override"] is None
    assert revoked == []


def test_code_audit_disabled_skips():
    async def handler(request):
        return web.json_response({"score": 0.99, "flags": []})

    result = asyncio.run(_run_code_audit(handler, "rm -rf /", enabled=False))
    assert result is None


def test_code_audit_empty_snippet_skips():
    async def handler(request):
        return web.json_response({"score": 0.99, "flags": []})

    result = asyncio.run(_run_code_audit(handler, "   "))
    assert result is None


def test_code_audit_failsoft_on_timeout(monkeypatch):
    """judge 不可用 → None, 不抛异常 (fail-soft: 静态裁决不受影响)。"""

    async def handler(request):
        raise web.HTTPInternalServerError()

    result = asyncio.run(_run_code_audit(handler, "rm -rf /"))
    assert result is None


def test_code_audit_never_raises(monkeypatch):
    """judge 返回畸形 JSON → None (解析失败静默降级)。"""

    async def handler(request):
        return web.Response(text="not-json")

    result = asyncio.run(_run_code_audit(handler, "rm -rf /"))
    assert result is None
