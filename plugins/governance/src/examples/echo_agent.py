"""echo_agent.py — A minimal Agent that makes HTTP requests.

This simulates what LangChain, AutoGen, CrewAI etc. do: send HTTP requests
to an LLM backend. Critically, this Agent has ZERO knowledge of
governance-gateway — no import, no SDK, no interface implementation.

Run:
    python examples/echo_agent.py

The gateway sits between this agent and the upstream backend, transparently
intercepting, evaluating policies, and allowing/denying/escalating.
"""

import json
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# ── Configuration ────────────────────────────────────────────────
GATEWAY_URL = "http://localhost:19000"  # Sidecar proxy
UPSTREAM_URL = "http://localhost:18000"  # Direct backend (bypass gateway)


class EchoAgent:
    """A minimal Agent that makes HTTP API calls.

    In production, this would be LangChain's ChatOpenAI, AutoGen's
    AssistantAgent, or any LLM client. The key invariant: this class
    has zero imports from governance-gateway.
    """

    def __init__(self, use_gateway: bool = True):
        self.base_url = GATEWAY_URL if use_gateway else UPSTREAM_URL
        self.request_count = 0
        self.success_count = 0
        self.denied_count = 0
        self.escalated_count = 0

    def chat(self, message: str) -> dict | None:
        """Send a chat message to the API."""
        return self._request("POST", "/api/chat", {"message": message})

    def query(self, query: str) -> dict | None:
        """Send a data query."""
        return self._request("GET", "/api/query", {"q": query})

    def delete_resource(self, resource: str) -> dict | None:
        """Attempt to delete a resource (should be DENIED by gateway)."""
        return self._request("POST", f"/api/delete/{resource}", {"resource": resource})

    def update_config(self, key: str, value: str) -> dict | None:
        """Attempt to update config (should be ESCALATED by gateway)."""
        return self._request("POST", f"/api/config/{key}", {"key": key, "value": value})

    def execute_sudo(self, command: str) -> dict | None:
        """Attempt a sudo operation (should be DENIED by gateway)."""
        return self._request("POST", "/api/admin/sudo", {"command": command})

    def _request(self, method: str, path: str, body: dict | None = None) -> dict | None:
        self.request_count += 1
        url = f"{self.base_url}{path}"
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"}

        req = Request(url, data=data, headers=headers, method=method)

        try:
            with urlopen(req, timeout=5) as resp:
                self.success_count += 1
                raw = resp.read().decode()
                return json.loads(raw)
        except HTTPError as e:
            status = e.code
            if status == 403:
                self.denied_count += 1
                return {"verdict": "DENIED", "status": 403}
            elif status == 202:
                self.escalated_count += 1
                return {"verdict": "ESCALATED", "status": 202}
            else:
                return {"error": str(e), "status": status}
        except Exception as e:
            return {"error": str(e)}

    def report(self) -> dict:
        return {
            "total": self.request_count,
            "success": self.success_count,
            "denied": self.denied_count,
            "escalated": self.escalated_count,
        }


def main():
    agent = EchoAgent(use_gateway=True)

    print("=" * 60)
    print("EchoAgent — sending requests through governance-gateway")
    print(f"Gateway: {GATEWAY_URL}")
    print("=" * 60)

    scenarios = [
        ("allow: chat", lambda: agent.chat("Hello world")),
        ("allow: query", lambda: agent.query("status")),
        ("deny: delete", lambda: agent.delete_resource("user")),
        ("deny: sudo", lambda: agent.execute_sudo("rm -rf /")),
        ("escalate: config", lambda: agent.update_config("model", "v2")),
    ]

    for name, fn in scenarios:
        result = fn()
        verdict = result.get("verdict", result.get("error", "unknown"))
        print(f"  [{name}] → {verdict}")

    print("-" * 60)
    report = agent.report()
    print(f"Results: {report['success']} success, {report['denied']} denied, "
          f"{report['escalated']} escalated ({report['total']} total)")

    # Verify invariant
    if report["denied"] >= 2 and report["escalated"] >= 1:
        print("\n[PASS] Gateway correctly intercepted all requests.")
        print("[PASS] Agent code: zero gateway imports — ZERO-INVASION CONFIRMED.")
        return 0
    else:
        print(f"\n[WARN] Expected >=2 denied + >=1 escalated, got {report}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
