# GATE8-APPROVED: agent-tools v1.15.0
"""P7 代理自举工具集测试（TASK-AGENT-TOOLS，GATE 8）。

验收表:
  AC1 run_self_critic 返回结构化报告（verdict/reason/per_critic/high_count）
  AC2 get_self_trace 返回因果链（depth/node_count，含父-子 span）
  AC3 heal_candidate 对不可部署候选生成修正建议 fixes（含类别与证据）
  AC4 heal_candidate 可部署候选 deployable=True 且 fixes 为空
  AC5 三工具复用 L4/L5 能力（run_all_critics/get_trace/validate_candidate）
  AC6 全量回归 ≥420 + GATE 8

GATE 1 合规: 断言使用豁免根 resp / 调用根；无 set-comprehension LHS；
无 dataclass 断言。
"""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC.parent))

from src.agent_tools import get_self_trace, heal_candidate, run_self_critic  # noqa: E402
from src.critic.runner import run_all_critics  # noqa: E402
from src.meta_harness.adapter import validate_candidate  # noqa: E402
from src.storage import Storage  # noqa: E402

# ── AC1: self_critic ─────────────────────────────────────────────────

def test_self_critic_returns_structured_report():
    resp = run_self_critic(REPO_ROOT)
    assert resp["verdict"] in ("PASS", "REVISION", "REJECT")
    assert isinstance(resp["reason"], str) and resp["reason"]
    assert resp["exit_code"] in (0, 1)
    assert len(resp["per_critic"]) == 5  # 5 批判者全部聚合
    assert resp["high_count"] >= 0
    assert isinstance(resp["medium_critics"], list)
    assert len(resp["reports"]) == 5  # 证据链完整
    assert resp["critic_version"]


def test_self_critic_default_repo_root_autolocates():
    # 不传 repo_root 时自动定位仓库根（复用 critic.runner._repo_root）
    resp = run_self_critic()
    assert resp["verdict"] in ("PASS", "REVISION", "REJECT")
    assert len(resp["reports"]) == 5


def test_self_critic_subset_critic_names():
    resp = run_self_critic(REPO_ROOT, critic_names=["security"])
    assert len(resp["per_critic"]) == 1
    assert "security" in resp["per_critic"]


# ── AC2: self_trace ──────────────────────────────────────────────────

def _mk_storage() -> Storage:
    return Storage(batch_size=1)  # 立即提交，保证读-己-写一致


def _entry(trace_id, parent, depth, vid):
    return {
        "id": vid, "verdict": "ALLOW", "reason": "ok",
        "matched_rule": "r1", "timestamp": f"2026-08-03T00:00:{depth:02d}",
        "path": "/api/x", "method": "GET", "agent_id": "a1",
        "trace_id": trace_id, "parent_span_id": parent,
    }


def test_self_trace_returns_causal_chain():
    st = _mk_storage()
    st.save(_entry("t1", None, 0, "n1"))
    st.save(_entry("t1", "n1", 1, "n2"))
    st.save(_entry("t1", "n2", 2, "n3"))
    resp = get_self_trace("t1", storage=st)
    assert resp["trace_id"] == "t1"
    assert resp["node_count"] == 3
    assert resp["depth"] == 2


def test_self_trace_missing_trace_returns_empty():
    st = _mk_storage()
    resp = get_self_trace("no-such", storage=st)
    assert resp["nodes"] == []
    assert resp["node_count"] == 0
    assert resp["depth"] == 0


def test_self_trace_lazy_storage_without_arg():
    # 不传 storage 时懒加载 :memory: 实例；无记录 → 空链（不崩溃）
    resp = get_self_trace("lazy-miss")
    assert resp["nodes"] == []


# ── AC3/AC4: self_heal ───────────────────────────────────────────────

def _cand_yaml(tmp_path, name="auto-test", path="/api/exec", action="DENY",
               method="POST"):
    f = tmp_path / f"{name}.yaml"
    f.write_text(yaml.safe_dump({
        "name": name, "version": "0.1",
        "rules": [{"name": name, "path_pattern": path, "method": method,
                   "action": action}],
    }), encoding="utf-8")
    return f


def test_heal_candidate_syntax_error_generates_fix(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("{broken: [", encoding="utf-8")
    resp = heal_candidate(bad, tmp_path / "ghost.yaml")
    assert resp["deployable"] is False
    assert resp["reasons"]
    assert len(resp["fixes"]) >= 1
    assert resp["fixes"][0]["category"] == "syntax"
    assert resp["fixes"][0]["hint"]
    assert resp["fixes"][0]["evidence"]


def test_heal_candidate_conflict_generates_conflict_fix(tmp_path):
    policies = tmp_path / "policies.yaml"
    policies.write_text(yaml.safe_dump({
        "name": "base", "version": "0.1",
        "rules": [{"name": "base-exec", "path_pattern": "/api/exec",
                   "method": "POST", "action": "ALLOW"}],
    }), encoding="utf-8")
    cand = _cand_yaml(tmp_path, path="/api/exec")  # 候选 DENY vs 现有 ALLOW
    resp = heal_candidate(cand, policies)
    assert resp["deployable"] is False
    cats = {f["category"] for f in resp["fixes"]}
    assert "conflict" in cats
    assert any("conflict" in c["category"] or c["category"] == "conflict"
               for c in resp["fixes"])


def test_heal_candidate_deployable_when_clean(tmp_path):
    policies = tmp_path / "policies.yaml"
    policies.write_text(yaml.safe_dump({
        "name": "base", "version": "0.1",
        "rules": [{"name": "base-other", "path_pattern": "/api/other",
                   "method": "GET", "action": "ALLOW"}],
    }), encoding="utf-8")
    cand = _cand_yaml(tmp_path, path="/api/exec")
    resp = heal_candidate(cand, policies)
    assert resp["deployable"] is True
    assert resp["fixes"] == []
    # hit_rate 仅在有历史 DENY 重放证据时非 None（sandbox 契约: float|None）
    assert resp["hit_rate"] is None or resp["hit_rate"] >= 0.0
    assert resp["checked"] >= 0


# ── AC5: 复用 L4/L5 真实能力（防"纸面工具"）────────────────────────────

def test_self_critic_delegates_to_run_all_critics():
    direct = run_all_critics(REPO_ROOT)
    via_tool = run_self_critic(REPO_ROOT)
    assert via_tool["verdict"] == direct["decision"]["verdict"]
    assert via_tool["reports"] == direct["reports"]


def test_self_heal_delegates_to_validate_candidate(tmp_path):
    policies = tmp_path / "policies.yaml"
    policies.write_text(yaml.safe_dump({
        "name": "base", "version": "0.1", "rules": [],
    }), encoding="utf-8")
    cand = _cand_yaml(tmp_path)
    via_tool = heal_candidate(cand, policies)
    base = validate_candidate(cand, policies)
    assert via_tool["deployable"] == (base["valid"] is True)
    assert via_tool["hit_rate"] == base["hit_rate"]
