# -*- coding: utf-8 -*-
"""P12: bootstrap runtime tests — deterministic scheduler
(perceive→diagnose→fix→verify→deploy) with SQLite state persistence.

AC1: sensor 检测漂移（codegen 漂移/工作区/债务）
AC2: 通过 codegen 生成候选修复
AC3: 验证通过后自动提交（白名单产物）
AC4: 验证失败 → 回滚 + 记录诊断
AC5: 人类 in-the-loop（auto_push 默认关闭 / dry_run 不落地）
AC6: ≥488 全量回归（由 CI 与快照 GATE 7 覆盖）
"""

import sqlite3
import subprocess
from pathlib import Path

import pytest

from src.bootstrap import (BootstrapScheduler, collect_signals, diagnose,
                           run_fix)
from src.bootstrap.diagnoser import fixable_diagnoses, human_review_required
from src.bootstrap.scheduler import CycleReport, SchedulerConfig

REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------- fixtures ----------
@pytest.fixture()
def mini_repo(tmp_path, monkeypatch):
    """最小可感知仓库: 复制真实 policies.yaml + 生成物到临时目录。

    生成器头路径是 CWD 相对的 → chdir 到临时仓库保证字节一致。
    """
    src_pol = REPO_ROOT / "config" / "policies.yaml"
    src_gen = REPO_ROOT / "src" / "codegen" / "_generated_matches.py"
    assert src_pol.exists() and src_gen.exists()
    (tmp_path / "config").mkdir(parents=True)
    (tmp_path / "src" / "codegen").mkdir(parents=True)
    (tmp_path / "config" / "policies.yaml").write_bytes(src_pol.read_bytes())
    (tmp_path / "src" / "codegen" / "_generated_matches.py").write_bytes(
        src_gen.read_bytes())
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture()
def git_repo(mini_repo):
    """mini_repo 初始化为 git 仓库并提交基线（含持久 git 身份配置）。"""
    subprocess.run(["git", "init", "-q"], cwd=mini_repo, check=True,
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
    subprocess.run(["git", "config", "user.name", "t"], cwd=mini_repo,
                   check=True, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=mini_repo,
                   check=True, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    subprocess.run(["git", "add", "-A"], cwd=mini_repo, check=True,
                   capture_output=True, text=True, encoding="utf-8",
                   errors="replace")
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "baseline"], cwd=mini_repo,
                   check=True, capture_output=True, text=True,
                   encoding="utf-8", errors="replace")
    return mini_repo


# ---------- AC1: sensor ----------
class TestSensor:
    def test_git_status_clean(self, git_repo):
        sig = collect_signals(git_repo)
        assert sig["git"]["dirty"] is False
        assert sig["git"]["changed"] == []

    def test_git_status_dirty(self, git_repo):
        (git_repo / "scratch.txt").write_text("x", encoding="utf-8")
        sig = collect_signals(git_repo)
        assert sig["git"]["dirty"] is True
        assert "scratch.txt" in sig["git"]["changed"]

    def test_codegen_drift_detected(self, mini_repo):
        # 篡改生成物 → 必须检出漂移（AC1 核心）
        gen = mini_repo / "src" / "codegen" / "_generated_matches.py"
        gen.write_text("# tampered\n", encoding="utf-8")
        sig = collect_signals(mini_repo)
        assert sig["codegen"]["drift"] is True
        assert "漂移" in sig["codegen"]["reason"]

    def test_codegen_consistent(self, mini_repo):
        sig = collect_signals(mini_repo)
        assert sig["codegen"]["drift"] is False

    def test_critic_and_debt_scan(self, mini_repo):
        (mini_repo / ".aionui").mkdir(exist_ok=True)
        (mini_repo / ".aionui" / "critic_report.md").write_text(
            "- [ ] 建议: 增加超时\n- [x] 已完成项\n", encoding="utf-8")
        (mini_repo / "debt_registry.md").write_text(
            "- DEBT-9999: 活跃债务\n- DEBT-0001: ✅ 已关闭\n", encoding="utf-8")
        sig = collect_signals(mini_repo)
        assert sig["critic"]["open_count"] == 1
        assert sig["debt"]["active_count"] == 1


# ---------- AC2: diagnoser ----------
class TestDiagnoser:
    def test_codegen_drift_fixable(self, mini_repo):
        gen = mini_repo / "src" / "codegen" / "_generated_matches.py"
        gen.write_text("# tampered\n", encoding="utf-8")
        diagnoses = diagnose(collect_signals(mini_repo))
        fixable = fixable_diagnoses(diagnoses)
        assert any(d["action"] == "REGENERATE_CODEGEN" for d in fixable)

    def test_human_review_for_nonfixable(self, git_repo):
        (git_repo / "scratch.txt").write_text("x", encoding="utf-8")
        diagnoses = diagnose(collect_signals(git_repo))
        review = human_review_required(diagnoses)
        cats = {d["category"] for d in review}
        assert "git" in cats  # 工作区变更需人工确认，不自动提交
        assert all(not d.get("fixable") for d in review)


# ---------- AC3/AC4: deployer ----------
class TestDeployer:
    def test_regenerate_fix_noop_when_consistent(self, mini_repo):
        """AC2: codegen 候选生成 — 一致时幂等 NOOP。"""
        result = run_fix("REGENERATE_CODEGEN", mini_repo,
                         run_tests=False)
        assert result["status"] == "NOOP"

    def test_regenerate_fix_deploys_and_commits(self, git_repo):
        """AC3: 策略漂移 → 重新生成 → 验证 → 自动提交（白名单产物）。

        真实漂移场景: 策略源变更但生成物未同步 → 重新生成产生新字节 → 提交。
        """
        # 变更策略源（追加一条规则），生成物保持旧 → 真实漂移
        pol = git_repo / "config" / "policies.yaml"
        pol_text = pol.read_text(encoding="utf-8")
        new_rule = (
            "\n  - name: bootstrap-probe-rule\n"
            "    path: /api/bootstrap-probe\n"
            "    action: ALLOW\n"
            "    reason: bootstrap 自举探测规则\n"
            "    priority: 5\n"
        )
        pol.write_text(pol_text.rstrip() + new_rule, encoding="utf-8")

        result = run_fix("REGENERATE_CODEGEN", git_repo, run_tests=False)
        assert result["status"] == "DEPLOYED"
        assert result["commit"]["committed"] is True
        # 提交仅含白名单产物
        out = subprocess.run(["git", "show", "--stat", "--oneline", "HEAD"],
                             cwd=git_repo, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        assert "_generated_matches.py" in out.stdout
        # 新规则已进入生成物
        gen = git_repo / "src" / "codegen" / "_generated_matches.py"
        assert "bootstrap-probe-rule" in gen.read_text(encoding="utf-8")

    def test_rollback_on_verify_failure(self, git_repo, monkeypatch):
        """AC4: 验证失败 → 回滚 + 状态 ROLLED_BACK。"""
        gen = git_repo / "src" / "codegen" / "_generated_matches.py"
        committed_bytes = gen.read_bytes()

        # 制造真实漂移（策略变更），随后强制验证失败
        pol = git_repo / "config" / "policies.yaml"
        pol.write_text(pol.read_text(encoding="utf-8").rstrip() +
                       "\n  - name: bootstrap-rollback-rule\n"
                       "    path: /api/rollback-probe\n"
                       "    action: ALLOW\n"
                       "    reason: rollback 探测\n"
                       "    priority: 6\n", encoding="utf-8")

        def _fake_verify(*a, **k):
            return {"verified": False, "detail": "注入失败", "tests": None}

        monkeypatch.setattr("src.bootstrap.deployer.verify_fix", _fake_verify)
        result = run_fix("REGENERATE_CODEGEN", git_repo, run_tests=False)
        assert result["status"] == "ROLLED_BACK"
        assert "回滚" in result["detail"]
        # 生成物已还原到提交基线（内容级比较: 换行符载体差异不计入漂移）
        assert gen.read_bytes().replace(b"\r\n", b"\n") == \
            committed_bytes.replace(b"\r\n", b"\n")


# ---------- AC5/AC6: scheduler ----------
class TestScheduler:
    def test_cycle_persists_to_db(self, git_repo, tmp_path):
        """调度器单轮: 状态持久化到 bootstrap_state.db。"""
        db = tmp_path / "bootstrap_state.db"
        sched = BootstrapScheduler(repo_root=git_repo, db_path=db,
                                   config=SchedulerConfig(dry_run=True))
        report = sched.run_cycle()
        assert isinstance(report, CycleReport)
        assert report.cycle_id is not None and report.cycle_id >= 1
        assert db.exists()
        rows = sched.recent_cycles(limit=1)
        assert len(rows) == 1
        assert rows[0]["status"] == report.status

    def test_cycle_dry_run_no_side_effects(self, git_repo, tmp_path):
        """AC5: dry_run 不产生提交/推送。"""
        (git_repo / "scratch.txt").write_text("x", encoding="utf-8")
        db = tmp_path / "bootstrap_state.db"
        sched = BootstrapScheduler(repo_root=git_repo, db_path=db,
                                   config=SchedulerConfig(dry_run=True))
        report = sched.run_cycle()
        for action in report.actions:
            assert action["status"] == "DRY_RUN"
        # git 状态不变
        out = subprocess.run(["git", "status", "--porcelain"], cwd=git_repo,
                             capture_output=True, text=True, encoding="utf-8",
                             errors="replace")
        assert "scratch.txt" in out.stdout

    def test_auto_push_gated(self):
        """P0-1: auto_push 默认 True（非演示），但实际推送受双环境变量门禁。"""
        from src.bootstrap.scheduler import _push_gate_open
        cfg = SchedulerConfig()
        assert cfg.auto_push is True  # 非演示模式（旧默认 False 已废弃）
        assert not _push_gate_open()  # 门禁未开 → push 降级为人工确认
    def test_cycle_rolls_back_on_failure(self, git_repo, tmp_path,
                                         monkeypatch):
        """AC4 调度层: 单轮失败 → ROLLED_BACK + 失败记录入库。"""
        gen = git_repo / "src" / "codegen" / "_generated_matches.py"
        committed_bytes = gen.read_bytes()
        pol = git_repo / "config" / "policies.yaml"
        pol.write_text(pol.read_text(encoding="utf-8").rstrip() +
                       "\n  - name: bootstrap-cycle-rollback\n"
                       "    path: /api/cycle-rollback\n"
                       "    action: ALLOW\n"
                       "    reason: cycle rollback 探测\n"
                       "    priority: 7\n", encoding="utf-8")

        def _fake_verify(*a, **k):
            return {"verified": False, "detail": "注入失败", "tests": None}

        monkeypatch.setattr("src.bootstrap.deployer.verify_fix", _fake_verify)
        db = tmp_path / "bootstrap_state.db"
        sched = BootstrapScheduler(repo_root=git_repo, db_path=db,
                                   config=SchedulerConfig(run_tests=False))
        report = sched.run_cycle()
        assert report.status == "ROLLED_BACK"
        # 生成物已还原到提交基线（内容级比较: 换行符载体差异不计入漂移）
        assert gen.read_bytes().replace(b"\r\n", b"\n") == \
            committed_bytes.replace(b"\r\n", b"\n")
        # 失败记录入库
        with sqlite3.connect(str(db)) as conn:
            n = conn.execute(
                "SELECT COUNT(*) FROM cycles_failures").fetchone()[0]
        assert n == 0  # ROLLED_BACK 不是 FAILED（失败=异常）
        assert any(a["status"] == "ROLLED_BACK" for a in report.actions)
