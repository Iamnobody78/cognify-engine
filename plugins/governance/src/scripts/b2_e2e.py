"""B2 e2e: real AutoGen GroupChat against the live gateway.

Runs examples/autogen_groupchat.py (pure AutoGen SDK, zero gateway imports)
against a live gateway + stub LLM. Proves end-to-end for MULTI-AGENT:
  AutoGen GroupChat (proposer↔executor, base_url=gateway/v1)
  → gateway /v1/chat/completions → policy check on EVERY agent's tool
  declarations → forward stub LLM (safe) or 403 (dangerous).

Diff vs B1 (LangChain single agent): AutoGen runs a multi-agent chat; the
gateway must intercept tool declarations from ANY participating agent.

Run with venv-b2 (has autogen-agentchat):
  .venv-b2/Scripts/python.exe scripts/b2_e2e.py
"""

import asyncio
import json
import logging
import sys
import warnings
from pathlib import Path

import aiohttp
import aiohttp.web  # explicit for aiohttp >= 3.9 lazy attribute loading

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "examples"))

# Windows consoles default to cp936/cp950 which cannot print some gateway
# error messages (Chinese reasons). Force UTF-8 to avoid crash on print.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# AutoGen logs a giant traceback to stderr on every denied publish message —
# that is EXPECTED here (the dangerous GroupChat must fail). Silence it so the
# e2e verdict is readable. Also suppress the model-mismatch UserWarning.
logging.getLogger("autogen_core").setLevel(logging.CRITICAL)
warnings.filterwarnings("ignore", message="Resolved model mismatch")

import src.main as main_module  # noqa: E402

STUB_PAYLOAD = {
    "choices": [{"message": {"role": "assistant", "content": "stub: 2026-08-03T12:00:00"}}]
}


async def run_groupchat(gateway_url: str, dangerous: bool, result_holder: list):
    """Run the REAL AutoGen GroupChat (async SDK) — safe or dangerous path."""
    from autogen_groupchat import build_groupchat

    team = build_groupchat(gateway_url, dangerous=dangerous)
    result = await team.run(task="What time is it?")
    texts = [m.content for m in result.messages if isinstance(m.content, str)]
    result_holder.append(texts[-1] if texts else "(no text)")


async def main():
    # 1. stub LLM upstream — records every request it receives
    seen_upstream = []

    async def upstream(request):
        body = await request.json()
        seen_upstream.append(body)
        return aiohttp.web.json_response(STUB_PAYLOAD)

    upstream_app = aiohttp.web.Application()
    upstream_app.router.add_post("/v1/chat/completions", upstream)
    u_runner = aiohttp.web.AppRunner(upstream_app)
    await u_runner.setup()
    u_site = aiohttp.web.TCPSite(u_runner, "127.0.0.1", 0)
    await u_site.start()
    u_port = u_site._server.sockets[0].getsockname()[1]

    # 2. real gateway in front of the stub
    old_url = main_module.AGENT_BACKEND_URL
    main_module.AGENT_BACKEND_URL = f"http://127.0.0.1:{u_port}"
    g_app = main_module.create_app()
    g_runner = aiohttp.web.AppRunner(g_app)
    await g_runner.setup()
    g_site = aiohttp.web.TCPSite(g_runner, "127.0.0.1", 0)
    await g_site.start()
    g_port = g_site._server.sockets[0].getsockname()[1]
    gateway_url = f"http://127.0.0.1:{g_port}"

    try:
        # 3a. SAFE GroupChat (executor tools=[get_time]) → ALLOW forward
        safe_result = []
        await run_groupchat(gateway_url, dangerous=False, result_holder=safe_result)
        assert safe_result, "safe GroupChat produced no output"
        print("SAFE GROUPCHAT FINAL:", safe_result[0])
        assert seen_upstream, "safe chat never reached upstream (should ALLOW)"
        print(f"  upstream saw {len(seen_upstream)} requests (multi-agent chat)")

        # 3b. DANGEROUS GroupChat (executor tools=[get_time, delete_file])
        #     NOTE: in a RoundRobinGroupChat the proposer's FIRST turn has no
        #     tools → it is legitimately ALLOWed and forwarded. The gateway
        #     DENYs the EXECUTOR's declaration request (403) → the groupchat
        #     raises PermissionDeniedError. So we assert:
        #       (i) the dangerous chat actually raised (403),
        #       (ii) NO request carrying a delete_file declaration ever
        #            reached upstream (zero dangerous declarations forwarded),
        #       (iii) a DENY decision is persisted mentioning delete_file.
        upstream_before_danger = len(seen_upstream)
        raised = False
        try:
            danger_result = []
            await run_groupchat(gateway_url, dangerous=True, result_holder=danger_result)
        except Exception as e:
            raised = True
            print(f"  dangerous chat raised (expected): {type(e).__name__}: {str(e)[:120]}")
        assert raised, (
            "dangerous GroupChat did NOT raise — governance failed to DENY "
            "the delete_file declaration"
        )
        danger_slice = seen_upstream[upstream_before_danger:]
        dangerous_forwarded = [
            b for b in danger_slice if "delete_file" in json.dumps(b)
        ]
        assert not dangerous_forwarded, (
            f"governance FAILED: {len(dangerous_forwarded)} request(s) with a "
            "delete_file declaration reached upstream"
        )
        print(f"  dangerous GroupChat: raised 403, "
              f"{len(danger_slice)} tool-free turn(s) forwarded (proposer), "
              f"0 dangerous declarations reached upstream")

        # 4. decisions persisted for both paths
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{gateway_url}/v1/decisions?limit=10") as r:
                data = await r.json()
        allows = [d for d in data["decisions"] if d["verdict"] == "ALLOW"]
        denies = [d for d in data["decisions"] if d["verdict"] == "DENY"]
        assert allows, "no ALLOW decision persisted for the safe GroupChat"
        assert denies, "no DENY decision persisted for the dangerous GroupChat"
        delete_denies = [d for d in denies if "delete_file" in d["reason"]]
        assert delete_denies, "DENY reason does not mention delete_file"
        print(f"PERSISTED: {data['total']} decisions "
              f"({len(allows)} ALLOW, {len(denies)} DENY; "
              f"{len(delete_denies)} delete_file DENY)")
        print("B2 E2E PASS: multi-agent safe→ALLOW, dangerous→DENY, both persisted")
    finally:
        main_module.AGENT_BACKEND_URL = old_url
        await g_runner.cleanup()
        await u_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
