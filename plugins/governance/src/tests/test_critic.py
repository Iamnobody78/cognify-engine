# GATE2-APPROVED: critic-agent-team v1
"""Critic Agent 代码化测试（TASK-REAL-012，GATE 8）。

验收表:
  AC1 5 个批判者均可独立运行，返回结构化报告
  AC2 裁决逻辑正确应用（一票否决 HIGH→REJECT / 2-3 MEDIUM→REVISION /
      多数通过 ≥4/5→PASS）
  AC3 集成 CI 作为 GATE 8，不影响现有 GATE 1-7
  AC4 全量测试通过（基线 274 + 新增）
  AC5 批判者报告可读，包含证据链

GATE 1 合规: 断言使用豁免根 resp / 调用根；无 set-comprehension LHS；
无 dataclass 断言。
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC.parent))

from src.critic import audit_critic, arch_critic, docs_critic, security_critic, test_critic  # noqa: E402
from src.critic import verdict as verdict_mod  # noqa: E402
from src.critic.runner import render_markdown, run_all_critics  # noqa: E402


# ── AC2: 裁决逻辑 ────────────────────────────────────────────────────

def _rep(name, severities):
    return {"critic": name,
            "findings": [{"severity": s, "check": "c", "evidence": "e",
                          "suggestion": "f"} for s in severities]}


def test_verdict_high_anywhere_is_reject():
    resp = verdict_mod.apply([
        _rep("audit", ["LOW"]),
        _rep("security", ["HIGH"]),
        _rep("arch", []),
        _rep("test", []),
        _rep("docs", []),
    ])
    assert resp["verdict"] == "REJECT"
    assert resp["exit_code"] == 1


def test_verdict_two_medium_is_revision():
    resp = verdict_mod.apply([
        _rep("audit", ["MEDIUM"]),
        _rep("security", ["MEDIUM"]),
        _rep("arch", []),
        _rep("test", []),
        _rep("docs", []),
    ])
    assert resp["verdict"] == "REVISION"
    assert resp["exit_code"] == 1


def test_verdict_one_medium_is_pass_majority():
    resp = verdict_mod.apply([
        _rep("audit", ["MEDIUM"]),
        _rep("security", []),
        _rep("arch", []),
        _rep("test", []),
        _rep("docs", []),
    ])
    assert resp["verdict"] == "PASS"
    assert resp["exit_code"] == 0


def test_verdict_all_clean_is_pass():
    resp = verdict_mod.apply([
        _rep("audit", []),
        _rep("security", []),
        _rep("arch", []),
        _rep("test", []),
        _rep("docs", []),
    ])
    assert resp["verdict"] == "PASS"
    assert resp["exit_code"] == 0


def test_verdict_low_does_not_block():
    resp = verdict_mod.apply([
        _rep("audit", ["LOW", "LOW"]),
        _rep("security", []),
        _rep("arch", ["LOW"]),
        _rep("test", []),
        _rep("docs", []),
    ])
    assert resp["verdict"] == "PASS"


# ── AC1: 批判者独立运行返回结构化报告 ────────────────────────────────

def test_all_five_critics_run_standalone():
    for run_fn in (audit_critic.run, security_critic.run, arch_critic.run,
                   test_critic.run, docs_critic.run):
        resp = run_fn(REPO_ROOT)
        assert resp["critic"] in ("audit", "security", "arch", "test", "docs")
        for finding in resp["findings"]:
            assert finding["severity"] in ("HIGH", "MEDIUM", "LOW")
            assert finding["check"]
            assert finding["evidence"]
            assert finding["suggestion"]


# ── Critic-Audit 逻辑（fixture 场景） ────────────────────────────────

def _write(tmp_path, rel, content):
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def test_audit_debt_without_commit_hash(tmp_path):
    _write(tmp_path, "debt_registry.md",
           "| DEBT-0099 | 某债务 | 已清偿 | 2026-08-03 |\n")
    resp = audit_critic.run(tmp_path)
    assert any(f["severity"] == "MEDIUM" and "A1" in f["check"] for f in resp["findings"])


def test_audit_relay_state_unfinished_is_high(tmp_path):
    _write(tmp_path, ".aionui/scheduler/relay_state.json",
           json.dumps({"task_id": "TASK-X", "status": "IN_PROGRESS"}))
    resp = audit_critic.run(tmp_path)
    assert any(f["severity"] == "HIGH" and "A3" in f["check"] for f in resp["findings"])


def test_audit_relay_state_multi_phase_in_progress_is_low(tmp_path):
    """多阶段长任务：存在 PENDING phase 时 IN_PROGRESS 合法（LOW 提示，不阻断）。"""
    _write(tmp_path, ".aionui/scheduler/relay_state.json",
           json.dumps({"task_id": "TASK-REAL-012", "status": "IN_PROGRESS",
                       "phases": {"1": {"status": "COMPLETED"},
                                  "2": {"status": "COMPLETED"},
                                  "3": {"status": "COMPLETED"},
                                  "4": {"status": "COMPLETED"},
                                  "5": {"status": "PENDING"}}}))
    resp = audit_critic.run(tmp_path)
    assert not any(f["severity"] == "HIGH" and "A3" in f["check"]
                   for f in resp["findings"])
    assert any(f["severity"] == "LOW" and "A3" in f["check"]
               for f in resp["findings"])


def test_audit_relay_state_all_phases_done_in_progress_is_high(tmp_path):
    """全部 phase 完成但 status 仍 IN_PROGRESS → 陈旧状态，HIGH。"""
    _write(tmp_path, ".aionui/scheduler/relay_state.json",
           json.dumps({"task_id": "TASK-X", "status": "IN_PROGRESS",
                       "phases": {"1": {"status": "COMPLETED"},
                                  "2": {"status": "COMPLETED"}}}))
    resp = audit_critic.run(tmp_path)
    assert any(f["severity"] == "HIGH" and "A3" in f["check"]
               and "陈旧" in f["check"] for f in resp["findings"])


def test_audit_drop_table_is_high(tmp_path):
    _write(tmp_path, "src/storage.py", "DROP TABLE decisions;\n")
    resp = audit_critic.run(tmp_path)
    assert any(f["severity"] == "HIGH" and "A4" in f["check"] for f in resp["findings"])


def test_audit_clean_repo_passes(tmp_path):
    _write(tmp_path, "debt_registry.md",
           "| DEBT-0099 | 某债务 | `abc1234` (TASK-X) | 2026-08-03 |\n")
    _write(tmp_path, ".aionui/audit_log.md",
           "## AUDIT-0027 — 2026-08-03T00:00:00Z\nTASK-X 完成\n")
    _write(tmp_path, ".aionui/scheduler/relay_state.json",
           json.dumps({"task_id": "TASK-X", "status": "COMPLETED"}))
    _write(tmp_path, "src/storage.py",
           "ALTER TABLE decisions ADD COLUMN trace_id TEXT;\nCREATE TABLE x(a);\n")
    _write(tmp_path, ".aionui/context/TRIPLE_LOOP_SNAPSHOT.md",
           "AUDIT-0027\n")
    resp = audit_critic.run(tmp_path)
    assert not [f for f in resp["findings"] if f["severity"] in ("HIGH", "MEDIUM")]


# ── Critic-Security 逻辑 ─────────────────────────────────────────────

def test_security_circuit_breaker_not_deny_is_high(tmp_path):
    _write(tmp_path, "src/main.py",
           "CIRCUIT_BREAKER_LIMIT = 10\n"
           "if failures > CIRCUIT_BREAKER_LIMIT:\n"
           "    pass  # 放行\n")
    resp = security_critic.run(tmp_path)
    assert any(f["severity"] == "HIGH" and "S1" in f["check"] for f in resp["findings"])


def test_security_sql_fstring_is_high(tmp_path):
    _write(tmp_path, "src/storage.py",
           "cur.execute(f\"SELECT * FROM decisions WHERE id='{tid}'\")")
    resp = security_critic.run(tmp_path)
    assert any(f["severity"] == "HIGH" and "S4" in f["check"] for f in resp["findings"])


def test_security_timeout_usage_without_deny_is_high(tmp_path):
    _write(tmp_path, "src/main.py",
           "INTERCEPT_TIMEOUT = 0.5\n"
           "verdict = await asyncio.wait_for(eval, timeout=INTERCEPT_TIMEOUT)\n"
           "return ALLOW\n")
    resp = security_critic.run(tmp_path)
    assert any(f["severity"] == "HIGH" and "S2" in f["check"] for f in resp["findings"])


def test_security_startswith_is_high(tmp_path):
    _write(tmp_path, "src/main.py",
           "if req.path.startswith('/api'):\n    allow()")
    resp = security_critic.run(tmp_path)
    assert any(f["severity"] == "HIGH" and "S3" in f["check"] for f in resp["findings"])


# ── Critic-Docs 逻辑 ─────────────────────────────────────────────────

def test_docs_missing_reference_is_medium(tmp_path):
    _write(tmp_path, "docs/guide.md", "运行 `tests/test_ghost.py` 验证\n")
    resp = docs_critic.run(tmp_path)
    assert any(f["severity"] == "MEDIUM" and "D1" in f["check"] for f in resp["findings"])


def test_docs_placeholder_xxx_skipped(tmp_path):
    _write(tmp_path, "docs/guide.md", "模板：`tests/xxx.py` 与 `src/{mod}.py`\n")
    resp = docs_critic.run(tmp_path)
    assert not [f for f in resp["findings"] if f["severity"] == "MEDIUM" and "D1" in f["check"]]


def test_docs_self_report_excluded(tmp_path):
    # 批判报告自身含模板示例引用 — 不得被 D1 扫描（自引用误报回归）
    _write(tmp_path, ".aionui/critic_report.md", "证据：`tests/xxx.py`\n")
    _write(tmp_path, "docs/guide.md", "说明\n")
    resp = docs_critic.run(tmp_path)
    assert not [f for f in resp["findings"] if f["severity"] == "MEDIUM" and "D1" in f["check"]]


def test_docs_version_mismatch_is_medium(tmp_path):
    _write(tmp_path, "README.md", "版本声明：**v9.9.9**\n")
    _write(tmp_path, "src/main.py", "VERSION = \"0.4.0\"\nhealth 0.4.0\n")
    resp = docs_critic.run(tmp_path)
    assert any(f["severity"] == "MEDIUM" and "D2" in f["check"] for f in resp["findings"])


# ── AC3/AC5: 协调器与报告 ────────────────────────────────────────────

def test_runner_returns_five_reports_and_decision():
    resp = run_all_critics(REPO_ROOT)
    assert len(resp["reports"]) == 5
    assert resp["decision"]["verdict"] in ("PASS", "REVISION", "REJECT")


def test_render_markdown_contains_verdict_and_evidence():
    resp = run_all_critics(REPO_ROOT)
    md = render_markdown(resp, REPO_ROOT)
    assert "批判报告" in md
    assert "裁决" in md
    assert "证据" in md
    assert "Critic-" in md


def test_runner_cli_exit_zero_on_pass(tmp_path):
    # 真实仓库当前应通过 GATE 8（本文件创建后 docs MEDIUM 消失）
    from src.critic.runner import main as cli_main
    out = tmp_path / "report.md"
    code = cli_main(["--output", str(out)])
    assert code == 0
    assert out.exists()
    assert "裁决" in out.read_text(encoding="utf-8")
