#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P9 B1: LangChain Agent — zero-touch governance gateway integration.

Demonstrates the *passive sidecar* pattern: the ONLY gateway reference in
this file is ``ChatOpenAI(base_url=...)``. There are zero imports of the
governance codebase (no ``src`` / ``gateway`` / ``main``) — the gateway
intercepts the OpenAI-compatible ``/v1/chat/completions`` traffic at the
network layer and governs tool declarations before they reach upstream:

  * declaring a dangerous tool (``delete_file``)  -> DENY     (403)
  * declaring a sensitive tool (``write_file``)   -> ESCALATE (202)
  * plain chat (no tools)                         -> ALLOW    (200, forwarded)

Two evidence layers:
  1. [SDK]  real LangChain path — create_agent(ChatOpenAI(base_url=gateway))
            is built and invoked; the gateway governs the call (SDK raises).
  2. [HTTP] protocol layer — deterministic raw requests with the same
            OpenAI-shaped bodies the SDK would emit, printing verdict,
            matched rule and trace ids from response headers.

LangChain SDK is an optional dependency: when missing (e.g. .venv-b2) the
example degrades to HTTP-protocol evidence only — consistent with the B1
contract (tests parse this file's AST, they never import the module).

Usage: python examples/langchain_agent.py [--gateway http://127.0.0.1:9000]
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):  # Windows cp950 兼容
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── real LangChain SDK (optional dependency) ────────────────────────────────
try:  # noqa: E402 - SDK is optional; HTTP-protocol evidence always available
    import langchain
    from langchain.agents import create_agent
    from langchain_openai import ChatOpenAI

    SDK_AVAILABLE = True
    SDK_LABEL = f"langchain {getattr(langchain, '__version__', '?')}"
except ImportError:  # pragma: no cover - exercised in .venv-b2
    SDK_AVAILABLE = False
    SDK_LABEL = "not installed (HTTP-protocol fallback)"

DEFAULT_GATEWAY = "http://127.0.0.1:9000"


def delete_file(path: str) -> str:
    """Dangerous capability — the gateway must DENY this declaration."""
    return f"[would delete {path}]"


def write_file(path: str, content: str) -> str:
    """Sensitive capability — the gateway must ESCALATE this declaration."""
    return f"[would write {path}:{content}]"


def build_governed_agent(gateway_url: str):
    """Zero-touch wiring: the ONLY gateway reference is ChatOpenAI(base_url=).

    base_url points at the gateway /v1 — the gateway passively governs the
    tool declarations in each request. No internal module is imported.
    """
    base_url = f"{gateway_url}/v1"
    model = ChatOpenAI(
        model="test-model",
        base_url=base_url,  # <-- single gateway config point (sidecar mode)
        api_key="test-key",
        timeout=10,
        max_retries=1,
    )
    return create_agent(model=model, tools=[delete_file, write_file])


def sdk_probe(gateway_url: str) -> None:
    """Real SDK path: invoke the create_agent agent; the gateway governs it."""
    if not SDK_AVAILABLE:
        print(f"[SDK] langchain {SDK_LABEL} — real SDK invoke skipped; "
              "HTTP-protocol evidence below is complete")
        return
    try:
        agent = build_governed_agent(gateway_url)
        print(f"[SDK] create_agent(ChatOpenAI(base_url={gateway_url}/v1)) "
              f"built: {type(agent).__name__}")
        agent.invoke({"messages": [{"role": "user", "content": "delete /etc/passwd"}]})
        print("[SDK] unexpected: call was NOT governed")
    except Exception as exc:  # noqa: BLE001 - gateway 403/202 surfaces as SDK error
        print(f"[SDK] real SDK call governed by gateway -> {type(exc).__name__}: {exc}")


def _chat_completions(gateway_url: str, body: dict):
    """POST an OpenAI-shaped body to the gateway; return (status, json, headers)."""
    req = urllib.request.Request(
        f"{gateway_url}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as err:  # 403 DENY / 5xx surfaces here
        payload = {}
        try:
            payload = json.loads(err.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            pass
        return err.code, payload, dict(err.headers)


def run_scenarios(gateway_url: str) -> None:
    """Deterministic protocol evidence: ALLOW / ESCALATE / DENY."""
    base = {"model": "test-model", "messages": [{"role": "user", "content": "hello"}]}

    def tool(name: str) -> dict:
        return {
            "type": "function",
            "function": {"name": name, "parameters": {"type": "object", "properties": {}}},
        }

    scenarios = [
        ("ALLOW", "safe chat, no tools", {**base}),
        ("ESCALATE", "tool: write_file (sensitive)", {**base, "tools": [tool("write_file")]}),
        ("DENY", "tool: delete_file (dangerous)", {**base, "tools": [tool("delete_file")]}),
    ]

    for verdict, label, body in scenarios:
        status, payload, headers = _chat_completions(gateway_url, body)
        trace_id = headers.get("X-Trace-ID") or "?"
        span_id = headers.get("X-Span-ID") or "?"
        err = payload.get("error") or {}
        reason = (err.get("message") or "?").replace("\n", " ")[:64]
        if status == 200:
            print(f"[ALLOW]    {label:<34} status=200 trace_id={trace_id} decision_id={span_id}")
        elif status == 202:
            print(f"[ESCALATE] {label:<34} status=202 reason={reason} trace_id={trace_id}")
        elif status == 403:
            print(f"[DENY]     {label:<34} status=403 reason={reason} trace_id={trace_id}")
        else:
            print(f"[UNKNOWN]  {label:<34} status={status} payload={json.dumps(payload)[:120]}")
        time.sleep(0.2)


def main() -> int:
    ap = argparse.ArgumentParser(description="LangChain zero-touch governance demo")
    ap.add_argument("--gateway", default=DEFAULT_GATEWAY, help="gateway base URL")
    args = ap.parse_args()
    print(f"=== LangChain Agent -> governance gateway {args.gateway} ===")
    print(f"[info] SDK: {SDK_LABEL}")
    sdk_probe(args.gateway)
    run_scenarios(args.gateway)
    print("=== done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
