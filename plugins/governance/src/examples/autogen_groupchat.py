"""B2: Real AutoGen GroupChat — zero-touch multi-agent integration via gateway.

This example imports ONLY the AutoGen SDK — zero knowledge of the gateway.
It talks normal OpenAI protocol; the gateway intercepts /v1/chat/completions
transparently (sidecar mode). Governance is invisible to this code.

The key difference vs B1 (LangChain single-agent): AutoGen runs a GroupChat
with MULTIPLE agents talking to each other. Every LLM call from every agent
flows through the gateway, and every agent's tool declarations are inspected
at declaration time — so a dangerous tool declared by ANY agent is DENIED
before any request reaches the upstream LLM.

Run (against the stub LLM):
    python examples/autogen_groupchat.py --gateway http://127.0.0.1:9000

Topology:
    proposer (planner, no tools)
    executor (worker, declares get_time + delete_file)
Both agents share ONE model client pointed at the gateway via base_url.
"""

import argparse
import asyncio
import os

# ── zero gateway imports: only AutoGen SDK ─────────────────────────────
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient

# AutoGen infers the tool JSON schema from the Python signature + docstring.
def get_time() -> str:
    """Return the current wall-clock time as a string."""
    import datetime

    return datetime.datetime.now().isoformat()

def delete_file(path: str) -> str:
    """Delete the file at the given path. DANGEROUS — should be governed."""
    import os

    os.remove(path)
    return f"deleted {path}"

# ALLOW path: propose -> execute with safe tool only
_SAFE_TOOLS = [get_time]
# DENY path: same chat, but the executor also declares the dangerous tool
_DANGEROUS_TOOLS = [get_time, delete_file]


def build_model_client(gateway_url: str):
    """One model client shared by all agents, pointed at the gateway.

    base_url is the ONLY gateway reference — same zero-touch contract as
    B1. The gateway sees ordinary OpenAI-compatible traffic from AutoGen.
    """
    return OpenAIChatCompletionClient(
        model="test-model",
        base_url=f"{gateway_url}/v1",  # ← the ONLY gateway reference: base_url
        api_key="test-key",             # gateway does not validate keys (sidecar)
        model_info={
            "vision": False,
            "function_calling": True,
            "json_output": False,
            "structured_output": False,
            "family": "unknown",
        },
    )


def build_groupchat(gateway_url: str, dangerous: bool = False):
    """Build a multi-agent GroupChat whose every LLM call goes via gateway.

    dangerous=True gives the executor the delete_file tool — governance must
    DENY the executor's requests at declaration time.
    """
    model_client = build_model_client(gateway_url)
    tools = _DANGEROUS_TOOLS if dangerous else _SAFE_TOOLS

    proposer = AssistantAgent(
        name="proposer",
        model_client=model_client,
        system_message=(
            "You are the planner. Propose a step, then hand off to executor. "
            "Reply TERMINATE when the task is done."
        ),
        reflect_on_tool_use=False,
    )
    executor = AssistantAgent(
        name="executor",
        model_client=model_client,
        tools=tools,
        system_message=(
            "You are the worker. Use your tools to fulfil the proposer's step, "
            "then report back concisely."
        ),
        reflect_on_tool_use=False,
    )
    # RoundRobin: proposer -> executor -> proposer -> ... deterministic,
    # max_turns keeps the chat short for tests/e2e.
    return RoundRobinGroupChat(participants=[proposer, executor], max_turns=4)


async def run_async(gateway_url: str, dangerous: bool, task: str) -> str:
    team = build_groupchat(gateway_url, dangerous)
    result = await team.run(task=task)
    # last agent message content (or the last text in the transcript)
    texts = [m.content for m in result.messages if isinstance(m.content, str)]
    return texts[-1] if texts else "(no text messages)"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default=os.environ.get("GATEWAY_URL", "http://127.0.0.1:9000"))
    parser.add_argument("--task", default="What time is it?")
    parser.add_argument("--dangerous", action="store_true", help="give executor delete_file (DENY path)")
    args = parser.parse_args()

    final = asyncio.run(run_async(args.gateway, args.dangerous, args.task))
    print("GROUPCHAT FINAL:", final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
