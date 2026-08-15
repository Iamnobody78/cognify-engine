"""Critic 裁决器 — 一票否决 / 多数通过 / 需修正。

协议 §第二层 协调员裁决规则:
  - 一票否决: 任一批判者发现 HIGH → 整体 REJECT
  - 多数通过: 无 HIGH 且 ≥4/5 批判者无 MEDIUM → PASS
  - 需修正:   无 HIGH 且 2-3 个批判者含 MEDIUM → REVISION
  - 全部通过: 全批判者无 MEDIUM+ → PASS
  - LOW 不阻断（但计入报告建议区）

自约束: 严重度由问题本身决定，不能协商降级；裁决仅按规则机械执行。
"""

from __future__ import annotations

SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}
CRITIC_COUNT = 5


def _max_severity(findings: list[dict]) -> str:
    if not findings:
        return "PASS"
    return max((f["severity"] for f in findings), key=lambda s: SEVERITY_RANK.get(s, 0))


def apply(reports: list[dict]) -> dict:
    """对批判者报告列表应用裁决规则。

    reports: [{"critic": str, "findings": [{"severity", "check", "evidence",
              "suggestion"}]}, ...]

    返回: {"verdict": PASS|REVISION|REJECT, "reason": str, "exit_code": int,
           "per_critic": {name: PASS|WARN|FAIL}, "high_count", "medium_critics"}
    """
    per_critic = {}
    high_count = 0
    medium_critics = []

    for rep in reports:
        name = rep.get("critic", "unknown")
        findings = rep.get("findings", [])
        worst = _max_severity(findings)
        if worst == "HIGH":
            per_critic[name] = "FAIL"
            high_count += len([f for f in findings if f["severity"] == "HIGH"])
        elif worst == "MEDIUM":
            per_critic[name] = "WARN"
            medium_critics.append(name)
        else:
            per_critic[name] = "PASS"

    if high_count > 0:
        return {
            "verdict": "REJECT",
            "reason": f"一票否决: {high_count} 个 HIGH 问题",
            "exit_code": 1,
            "per_critic": per_critic,
            "high_count": high_count,
            "medium_critics": medium_critics,
        }

    medium_count = len(medium_critics)
    if medium_count >= 2:
        return {
            "verdict": "REVISION",
            "reason": f"需修正: {medium_count}/5 批判者发现 MEDIUM（{', '.join(medium_critics)}）",
            "exit_code": 1,
            "per_critic": per_critic,
            "high_count": 0,
            "medium_critics": medium_critics,
        }

    passed = sum(1 for v in per_critic.values() if v == "PASS")
    return {
        "verdict": "PASS",
        "reason": f"多数通过: {passed}/5 批判者无 MEDIUM+ 问题"
                  + (f"（{medium_critics[0]} 含 MEDIUM，按多数通过规则放行）"
                     if medium_count == 1 else "（全部通过）"),
        "exit_code": 0,
        "per_critic": per_critic,
        "high_count": 0,
        "medium_critics": medium_critics,
    }
