"""Critic 协调器 — GATE 8 动态语义门控。

用法:
  python -m src.critic.runner                    # 全部 5 批判者 → .aionui/critic_report.md
  python -m src.critic.runner --critic security  # 单角色
  python -m src.critic.runner --output /tmp/report.md
  python -m src.critic.runner --json             # 机器可读输出

exit code: 0=PASS, 1=REJECT/REVISION（CI 失败 → 返回 Builder 修正）
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import audit_critic, arch_critic, docs_critic, security_critic, test_critic
from . import verdict as verdict_mod

CRITICS = {
    "audit": audit_critic.run,
    "security": security_critic.run,
    "arch": arch_critic.run,
    "test": test_critic.run,
    "docs": docs_critic.run,
}

DEFAULT_OUTPUT = ".aionui/critic_report.md"

SEVERITY_ICON = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
STATUS_ICON = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}
VERDICT_ICON = {"PASS": "✅ PASS", "REVISION": "⚠️ 需修正", "REJECT": "❌ REJECT"}


def _repo_root() -> Path:
    """定位仓库根（src/critic/runner.py → 上溯 3 层）。"""
    return Path(__file__).resolve().parent.parent.parent


def run_all_critics(repo_root: Path, critic_names: list[str] | None = None) -> dict:
    """并行运行 5 批判者（asyncio.gather + to_thread 真并行），返回聚合结果。"""
    names = critic_names or list(CRITICS.keys())

    async def _parallel():
        tasks = [asyncio.to_thread(CRITICS[n], repo_root) for n in names]
        results = await asyncio.gather(*tasks)
        return list(results)

    reports = asyncio.run(_parallel())
    decision = verdict_mod.apply(reports)
    return {
        "reports": reports,
        "decision": decision,
        "critic_version": "1.0.0",
    }


def render_markdown(aggregate: dict, repo_root: Path) -> str:
    """按协议输出模板渲染批判报告（含证据链，可复核）。"""
    decision = aggregate["decision"]
    lines = [
        "## 🧬 批判报告 — GATE 8（动态语义门控）",
        "",
        f"- 运行时间: {_now_iso()}"
        f" | 仓库: {repo_root}"
        f" | 批判者版本: {aggregate['critic_version']}",
        "",
        "### 批判者团队状态",
        "| 角色 | 状态 | 最高严重度 | 发现数 |",
        "|------|------|-----------|--------|",
    ]
    for rep in aggregate["reports"]:
        name = rep["critic"]
        status = decision["per_critic"].get(name, "PASS")
        worst = _max_sev(rep["findings"]) or "—"
        lines.append(f"| Critic-{name.capitalize()} | {STATUS_ICON.get(status, '✅')} {status} | {worst} | {len(rep['findings'])} |")

    lines += ["", "### 问题清单", "| 严重度 | 批判者 | 检查项 | 证据（文件:行号 或 可复现断言） | 建议修复 |", "|--------|--------|--------|------------------------------|----------|"]
    for rep in aggregate["reports"]:
        for f in rep["findings"]:
            icon = SEVERITY_ICON.get(f["severity"], "?")
            ev = f["evidence"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {icon} {f['severity']} | Critic-{rep['critic'].capitalize()} | {f['check']} | {ev} | {f['suggestion']} |")
    if not any(rep["findings"] for rep in aggregate["reports"]):
        lines.append("| — | — | 无 | 未发现不一致 | — |")

    lines += [
        "",
        "### 裁决",
        f"- 总体: {VERDICT_ICON.get(decision['verdict'], decision['verdict'])}",
        f"- 理由: {decision['reason']}",
        "- 证据链: 本报告所有断言均来自对仓库文件的直接解析（见证据列）；",
        "  测试证据见 `pytest tests/ -q` 与 GATE 1-7 结果。",
        "",
    ]
    return "\n".join(lines)


def _max_sev(findings: list[dict]) -> str:
    if not findings:
        return ""
    return max(f["severity"] for f in findings)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    # Windows 控制台（cp950/cp936）无法打印 emoji 图标 — UTF-8 输出 + 安全降级
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    parser = argparse.ArgumentParser(description="Critic Agent Team — GATE 8")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="报告输出路径")
    parser.add_argument("--critic", choices=list(CRITICS.keys()), help="仅运行单个批判者")
    parser.add_argument("--json", action="store_true", help="输出 JSON（stdout）")
    args = parser.parse_args(argv)

    repo_root = _repo_root()
    names = [args.critic] if args.critic else None
    aggregate = run_all_critics(repo_root, names)

    if args.json:
        print(json.dumps(aggregate, ensure_ascii=False, indent=2))
    else:
        markdown = render_markdown(aggregate, repo_root)
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")
        print(markdown)
        print(f"\n[critic] 报告已写入 {out}")

    return aggregate["decision"]["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
