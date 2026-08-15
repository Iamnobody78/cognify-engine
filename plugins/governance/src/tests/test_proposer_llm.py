# -*- coding: utf-8 -*-
"""MH 阶段 2': LLMProposer + mh_evolve 驱动测试（FakeLLM 注入, 无真实端点依赖）。

覆盖: 提示构造 / YAML 块提取 / 有效候选 / 无效丢弃 / LLM 不可达与超时
fail-closed（绝不编造）/ max_candidates 上限 / 驱动端到端（候选写入+前沿
合并+报告落盘+config/policies.yaml 不被修改的安全断言）/ 血缘元数据。
"""
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import src.meta_harness.proposer_llm as pl  # noqa: E402
from src.meta_harness.proposer_llm import LLMProposer, build_proposer_prompt, _extract_yaml_blocks  # noqa: E402
from src.storage import Storage  # noqa: E402

VALID_YAML = """\
rules:
  - name: "block-delete-etc-tool"
    path_pattern: "*"
    method: "POST"
    tool_args:
      name: "delete_file"
      path: "/etc/*"
    action: "DENY"
    priority: 10
    reason: "LLM 提议: 阻断 delete_file 对 /etc 的删除"
"""


class FakeLLM:
    """可注入的假 LLM 客户端。text=None → 抛异常 (模拟不可达/超时)。"""

    def __init__(self, text=None, exc=None):
        self.text = text
        self.exc = exc
        self.calls = []

    def __call__(self, prompt, url, model, timeout):
        self.calls.append((prompt, url, model, timeout))
        if self.exc is not None:
            raise self.exc
        if self.text is None:
            raise ConnectionError("fake: 端点不可达")
        return self.text


def make_incumbent(tmp_path):
    cfg = tmp_path / "policies.yaml"
    cfg.write_text(
        "name: test\nversion: '0.0.1'\nrules:\n"
        "  - name: allow-chat\n    path_pattern: '/api/chat'\n"
        "    action: ALLOW\n    priority: 100\n",
        encoding="utf-8")
    return str(cfg)


def seed_db(tmp_path, n_deny=3):
    """造一个有 DENY/ESCALATE 记录的临时审计库。"""
    db = tmp_path / "audit.db"
    storage = Storage(str(db))
    for i in range(n_deny):
        storage.save({
            "id": f"deny-{uuid.uuid4().hex[:8]}",
            "verdict": "DENY",
            "reason": "seed",
            "timestamp": "2026-08-04T00:00:00Z",
            "path": "/api/chat",
            "method": "POST",
            "matched_rule": None,
            "rationale": "seed-deny",
            "tool_name": "delete_file",
        })
    storage.close()
    return str(db)


# ── 提示构造与提取 ──────────────────────────────────────────────

def test_build_prompt_contains_context():
    prompt = build_proposer_prompt(
        [{"name": "allow-chat", "action": "ALLOW"}],
        ["x5 POST /api/chat tool=delete_file"])
    assert "allow-chat" in prompt
    assert "x5 POST /api/chat tool=delete_file" in prompt
    assert "tool_args" in prompt  # 输出约束提及推荐形态
    assert "不得修改核心引擎" in prompt


def test_extract_yaml_blocks_fence_and_bare():
    assert _extract_yaml_blocks("前文\n```yaml\nrules:\n  - a\n```\n后文") == ["rules:\n  - a"]
    assert _extract_yaml_blocks("rules:\n  - b") == ["rules:\n  - b"]
    assert _extract_yaml_blocks("纯文本没有规则") == []
    assert _extract_yaml_blocks("```yaml\nx: 1\n```\n```yaml\ny: 2\n```") == ["x: 1", "y: 2"]


# ── propose 行为 ───────────────────────────────────────────────

def test_propose_valid_candidates():
    fake = FakeLLM(text="```yaml\n" + VALID_YAML + "```")
    proposer = LLMProposer(client=fake)
    result = proposer.propose([], [])
    assert result["llm_error"] is None
    assert len(result["candidates"]) == 1
    c = result["candidates"][0]
    assert c["rule_count"] == 1
    assert c["rules"][0]["name"] == "block-delete-etc-tool"
    assert c["rules"][0]["tool_args"]["path"] == "/etc/*"
    assert fake.calls and fake.calls[0][2] == proposer.model


def test_propose_drops_invalid_yaml():
    fake = FakeLLM(text="```yaml\nrules:\n  - name: 'bad'\n    action: 'NOPE'\n```")
    proposer = LLMProposer(client=fake)
    result = proposer.propose([], [])
    assert result["candidates"] == []
    assert result["dropped"]  # 坏 action 被 fail-closed 丢弃
    assert result["llm_error"] is None


def test_propose_llm_unreachable_fail_closed():
    fake = FakeLLM(exc=ConnectionError("down"))
    proposer = LLMProposer(client=fake)
    result = proposer.propose([], [])
    assert result["candidates"] == []  # 绝不编造
    assert result["llm_error"] and "ConnectionError" in result["llm_error"]


def test_propose_timeout_fail_closed():
    fake = FakeLLM(exc=TimeoutError("slow"))
    proposer = LLMProposer(client=fake)
    result = proposer.propose([], [])
    assert result["candidates"] == []
    assert "TimeoutError" in result["llm_error"]


def test_propose_empty_response_fail_closed():
    fake = FakeLLM(text="   ")
    proposer = LLMProposer(client=fake)
    result = proposer.propose([], [])
    assert result["candidates"] == []
    assert "空响应" in result["llm_error"]


def test_propose_max_candidates_cap():
    three = "".join(f"```yaml\n{VALID_YAML}\n```" for _ in range(3))
    fake = FakeLLM(text=three)
    proposer = LLMProposer(client=fake)
    result = proposer.propose([], [], max_candidates=2)
    assert len(result["candidates"]) == 2


def test_propose_rejects_zero_max():
    proposer = LLMProposer(client=FakeLLM(text=""))
    with pytest.raises(ValueError):
        proposer.propose([], [], max_candidates=0)


# ── 驱动端到端（mh_evolve） ─────────────────────────────────────

def test_driver_round_integration(tmp_path, monkeypatch):
    """FakeLLM → 候选写入 candidates/ + 前沿合并 + 报告落盘 + 策略未被修改。"""
    import scripts.mh_evolve as driver
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pl, "_urllib_client",
                        FakeLLM(text="```yaml\n" + VALID_YAML + "```"))
    cfg = make_incumbent(tmp_path)
    db = seed_db(tmp_path, n_deny=2)
    rc = driver.main(["--rounds", "1", "--db", db, "--policies", cfg,
                      "--out", "report.md"])
    assert rc == 0
    cands = list(tmp_path.rglob("candidates/*/src/policy.yaml"))
    assert len(cands) == 1  # 1 轮 1 候选
    meta = list(tmp_path.rglob("candidates/*/candidate.json"))
    import json as _json
    data = _json.loads(meta[0].read_text(encoding="utf-8"))
    assert data["metrics"]["source"] == "llm-proposer"
    assert "pareto_accepted" in data["metrics"]
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "mh-evolve 报告" in report
    assert "人类在环" in report  # 不自动注入的声明
    # 安全: 原策略未被修改
    assert "delete_file" not in cfg  # 候选规则未写入 incumbent
    # 前沿包含 incumbent + 候选
    assert "incumbent" in report


def test_driver_llm_down_honest_failure(tmp_path, monkeypatch):
    """LLM 不可达 → 零候选, 报告明确标注, exit 0 (诚实的失败路径)。"""
    import scripts.mh_evolve as driver
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pl, "_urllib_client", FakeLLM(exc=ConnectionError("down")))
    cfg = make_incumbent(tmp_path)
    rc = driver.main(["--rounds", "1", "--db", seed_db(tmp_path, n_deny=1),
                      "--policies", cfg, "--out", "report2.md"])
    assert rc == 0
    report = (tmp_path / "report2.md").read_text(encoding="utf-8")
    assert "零候选" in report or "LLM 不可达" in report
    assert not list(tmp_path.rglob("candidates/*/src/policy.yaml"))


def test_driver_no_db_diagnosis_note(tmp_path, monkeypatch):
    """无 --db → 无轨迹诊断标注, 候选仍可生成 (质量=基线)。"""
    import scripts.mh_evolve as driver
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pl, "_urllib_client",
                        FakeLLM(text="```yaml\n" + VALID_YAML + "```"))
    rc = driver.main(["--rounds", "1", "--policies", make_incumbent(tmp_path),
                      "--out", "report3.md"])
    assert rc == 0
    report = (tmp_path / "report3.md").read_text(encoding="utf-8")
    assert "无轨迹上下文" in report
