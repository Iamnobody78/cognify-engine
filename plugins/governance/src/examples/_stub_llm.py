#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P9 helper: minimal OpenAI-compatible stub LLM for the examples runner.

The governance gateway (src.main) forwards ALLOWed /v1/chat/completions
requests to AGENT_BACKEND_URL (default http://localhost:8000). This stub
mimics that upstream so the ALLOW path can be demonstrated end-to-end
without a real LLM provider.

It is a *test double*, NOT part of the governance product: it carries no
gateway imports, no policy logic and no persistence. It exists only so
examples/run_examples.sh can produce ALLOW evidence.

Usage: python examples/_stub_llm.py        # listens on 127.0.0.1:8000
"""

import json

from aiohttp import web


def _chat_response(body: dict) -> dict:
    model = body.get("model", "test-model")
    messages = body.get("messages") or []
    prompt = messages[-1].get("content", "") if messages else ""
    return {
        "id": "chatcmpl-stub-0001",
        "object": "chat.completion",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": f"stub echo: {prompt}"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12},
    }


async def handle_chat(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 - stub must never 500 the chain
        body = {}
    return web.json_response(_chat_response(body))


async def handle_health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/v1/chat/completions", handle_chat)
    app.router.add_get("/health", handle_health)
    return app


if __name__ == "__main__":
    web.run_app(make_app(), host="127.0.0.1", port=8000)
