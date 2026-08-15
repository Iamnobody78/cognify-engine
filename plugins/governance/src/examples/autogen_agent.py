#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P9 B2: AutoGen Agent — zero-touch governance gateway integration.

Complements examples/autogen_groupchat.py (the B2 contract file): this is a
runnable CLI demo proving that AutoGen-style OpenAI-compatible traffic is
governed when routed through the gateway via base_url — passive sidecar:

  * base_url=f"{gateway}/v1" is the ONLY gateway reference in this file;
  * declaring write_file -> ESCALATE (202); delete_file -> DENY (403);
    plain chat -> ALLOW (200, forwarded to the stub LLM);
  * every call prints trace_id / decision_id (verifiable governance trail).

The AutoGen SDK is imported when available (real wiring proof). Whether or
not it is installed, deterministic HTTP-protocol evidence is always printed
with the same OpenAI-shaped bodies AutoGen's OpenAIChatCompletionClient
would emit (see tests/test_integration_autogen.py::_autogen_tools_body).

Usage: python examples/autogen_agent.py [--gateway http://127.0.0.1:9000]
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):  # Windows cp950 兼容
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── real AutoGen SDK (optional dependency) ──────────────────────────────────
try:  # noqa: E402 - SDK is optional; HTTP-protocol evidence always available
    import autogen_agentchat

    SDK_AVAILABLE = True
    SDK_LABEL = f"autogen {getattr(autogen_agentchat, '__version__', '?')}"
except ImportError:  # pragma: no cover - SDK absent
    SDK_AVAILABLE = False
    SDK_LABEL = "not installed (HTTP-protocol fallback)"

DEFAULT_GATEWAY = "http://127.0.0.1:9000"

# AutoGen OpenAIChatCompletionClient model config: base_url is the ONLY
# gateway reference (passive sidecar — same shape autogen_groupchat.py uses).
AUTOGEN_MODEL_CONFIG = {
    "model": "test-model",
    "api_key": "test-key",
    "base_url": "{gateway}/v1",  # placeholder resolved at runtime
}


def sdk_wiring_proof(gateway_url: str) -> None:
    """Show the AutoGen client config wired to the gateway (no internal imports)."""
    if not SDK_AVAILABLE:
        print(f"[SDK] autogen {SDK_LABEL} — real SDK wiring skipped; "
              "HTTP-protocol evidence below is complete")
        return
    cfg = dict(AUTOGEN_MODEL_CONFIG)
    cfg["base_url"] = cfg["base_url"].format(gateway=gateway_url)
    print(f"[SDK] autogen model client config (base_url={cfg['base_url']}): "
          f"{json.dumps(cfg)}")
    try:
        from autogen_agentchat.agents import AssistantAgent  # noqa: F401
        print("[SDK] autogen_agentchat.agents.AssistantAgent importable — "
              "real SDK path available (see autogen_groupchat.py for full agent)")
    except Exception as exc:  # noqa: BLE001
        print(f"[SDK] AssistantAgent import failed: {type(exc).__name__}: {exc}")


def _chat_completions(gateway_url: str, body: dict):
    """POST an AutoGen-shaped OpenAI body to the gateway."""
    req = urllib.request.Request(
        f"{gateway_url}/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as err:
        payload = {}
        try:
            payload = json.loads(err.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            pass
        return err.code, payload, dict(err.headers)


def _autogen_tool_body(name: str) -> dict:
    """Same tool schema shape AutoGen generates for FunctionTool objects."""
    return {
        "type": "function",
        "function": {"name": name, "description": "auto",
                     "parameters": {"type": "object", "properties": {}}},
    }


def run_scenarios(gateway_url: str) -> None:
    base = {"model": "test-model", "messages": [{"role": "user", "content": "go"}]}
    scenarios = [
        ("ALLOW", "group chat, no tools", {**base}),
        ("ESCALATE", "FunctionTool: write_file", {**base, "tools": [_autogen_tool_body("write_file")]}),
        ("DENY", "FunctionTool: delete_file", {**base, "tools": [_autogen_tool_body("delete_file")]}),
    ]

    for verdict, label, body in scenarios:
        status, payload, headers = _chat_completions(gateway_url, body)
        trace_id = headers.get("X-Trace-ID") or "?"
        span_id = headers.get("X-Span-ID") or "?"
        err = payload.get("error") or {}
        reason = (err.get("message") or "?").replace("\n", " ")[:64]
        if status == 200:
            print(f"[ALLOW]    {label:<30} status=200 trace_id={trace_id} decision_id={span_id}")
        elif status == 202:
            print(f"[ESCALATE] {label:<30} status=202 reason={reason} trace_id={trace_id}")
        elif status == 403:
            print(f"[DENY]     {label:<30} status=403 reason={reason} trace_id={trace_id}")
        else:
            print(f"[UNKNOWN]  {label:<30} status={status} payload={json.dumps(payload)[:120]}")
        time.sleep(0.2)


def main() -> int:
    ap = argparse.ArgumentParser(description="AutoGen zero-touch governance demo")
    ap.add_argument("--gateway", default=DEFAULT_GATEWAY, help="gateway base URL")
    args = ap.parse_args()
    print(f"=== AutoGen Agent -> governance gateway {args.gateway} ===")
    print(f"[info] SDK: {SDK_LABEL}")
    sdk_wiring_proof(args.gateway)
    run_scenarios(args.gateway)
    print("=== done ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
