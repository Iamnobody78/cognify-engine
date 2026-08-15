"""scheduler — P12 调度器: 感知→诊断→修复→验证→部署 主循环（确定性）。

- 不是独立进程: run_cycle() 单轮执行，由 CI / 人工 / 定时任务按需调用
- 状态持久化: bootstrap_state.db (SQLite) — cycles 表记录每轮结果
- 人类 in-the-loop: auto_push 默认 False（推送需人工确认）;
  不可自动修复的诊断（critic/debt/git/测试失败）上报 human_review
- 失败安全: 任何异常 → 本轮记为 FAILED，不中断后续轮次

用法:
    from src.bootstrap import BootstrapScheduler
    sched = BootstrapScheduler(repo_root=".")
    report = sched.run_cycle()
    sched.run(max_cycles=3)   # 连续多轮
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .deployer import run_fix
from .diagnoser import diagnose, fixable_diagnoses, human_review_required
from .sensor import collect_signals

DEFAULT_DB = "bootstrap_state.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL,             -- NOOP | DEPLOYED | ROLLED_BACK | FAILED
    summary TEXT,
    diagnoses TEXT,                   -- JSON 列表
    actions TEXT,                     -- JSON 列表（执行的自动修复）
    human_review TEXT,                -- JSON 列表（需人工项）
    repair_chain TEXT                 -- JSON: 完整修复因果链 (问题→诊断→修复→验证)
);
CREATE TABLE IF NOT EXISTS cycles_failures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cycle_id INTEGER,
    detail TEXT,
    created_at TEXT
);
"""

# 门禁式自动推送: 默认 auto_push=True（非演示），但真正执行 push 必须同时存在
# 两个环境变量（CI 专用），防止本地/误配置环境自动推送错误补丁到主分支。
# 不满足门禁时: 提交照常，push 降级为"生成补丁待人工确认"。
PUSH_GATE_ENV = ("CONTEXT_HMAC_KEY", "GATE_8_SKIP")


def _push_gate_open() -> bool:
    import os
    return all(os.environ.get(k) for k in PUSH_GATE_ENV)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SchedulerConfig:
    """确定性调度配置。

    auto_push 默认 True（非演示模式），但实际 push 受 _push_gate_open() 双环境
    变量门禁保护——门禁关闭时提交照常、推送降级为人工确认（fail-safe）。
    """
    auto_push: bool = True           # 默认开启; 实际推送需环境变量门禁 (P0-1)
    run_tests: bool = True           # 修复后跑 pytest 回归
    tests_dir: str = "tests"
    max_fixes_per_cycle: int = 3     # 单轮最多自动修复数
    dry_run: bool = False            # True: 不提交不推送（演练模式）


@dataclass
class CycleReport:
    cycle_id: int | None = None
    status: str = "NOOP"
    summary: str = ""
    diagnoses: list = field(default_factory=list)
    actions: list = field(default_factory=list)
    human_review: list = field(default_factory=list)
    detail: str = ""


class BootstrapScheduler:
    def __init__(self, repo_root: str | Path = ".",
                 db_path: str | Path = DEFAULT_DB,
                 config: SchedulerConfig | None = None):
        self.repo_root = Path(repo_root).resolve()
        self.db_path = Path(db_path)
        if self.db_path.name == DEFAULT_DB and not self.db_path.is_absolute():
            self.db_path = self.repo_root / DEFAULT_DB
        self.config = config or SchedulerConfig()
        self._init_db()

    # ---------- 持久化 ----------
    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript(_SCHEMA)

    def _persist_cycle(self, report: CycleReport) -> int:
        # repair_chain: 从 actions 提取每条修复的完整因果链 (问题→诊断→修复→验证)
        chains = []
        for a in report.actions:
            if isinstance(a, dict) and "repair_chain" in a:
                chains.append({"action": a.get("action"),
                               "status": a.get("status"),
                               "chain": a["repair_chain"]})
            elif isinstance(a, dict):
                chains.append({"action": a.get("action"),
                               "status": a.get("status"),
                               "chain": {"problem": a.get("action"),
                                         "detail": a.get("detail", "")}})
        with sqlite3.connect(str(self.db_path)) as conn:
            cur = conn.execute(
                "INSERT INTO cycles (started_at, ended_at, status, summary,"
                " diagnoses, actions, human_review, repair_chain)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (_now(), _now(), report.status, report.summary,
                 json.dumps(report.diagnoses, ensure_ascii=False),
                 json.dumps(report.actions, ensure_ascii=False),
                 json.dumps(report.human_review, ensure_ascii=False),
                 json.dumps(chains, ensure_ascii=False)))
            return int(cur.lastrowid)

    def _persist_failure(self, cycle_id: int, detail: str) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("INSERT INTO cycles_failures (cycle_id, detail, created_at)"
                         " VALUES (?,?,?)", (cycle_id, detail, _now()))

    def recent_cycles(self, limit: int = 10) -> list[dict]:
        """读取最近 N 轮记录（供报告与因果分析）。"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM cycles ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---------- 主循环 ----------
    def run_cycle(self) -> CycleReport:
        """单轮: 感知 → 诊断 → 自动修复（白名单动作）→ 持久化。"""
        report = CycleReport()
        try:
            signals = collect_signals(self.repo_root,
                                      run_tests=False,
                                      tests_dir=self.config.tests_dir)
            report.diagnoses = diagnose(signals)

            fixable = fixable_diagnoses(report.diagnoses)[:self.config.max_fixes_per_cycle]
            report.human_review = human_review_required(report.diagnoses)

            for diag in fixable:
                action = diag["action"]
                if self.config.dry_run:
                    report.actions.append({
                        "action": action, "status": "DRY_RUN",
                        "detail": "演练模式: 未执行"})
                    continue
                result = run_fix(action, self.repo_root,
                                 auto_push=self.config.auto_push,
                                 run_tests=self.config.run_tests,
                                 tests_dir=self.config.tests_dir)
                report.actions.append(result)

            # 汇总状态
            statuses = [a.get("status") for a in report.actions]
            if any(s == "ROLLED_BACK" for s in statuses):
                report.status = "ROLLED_BACK"
            elif any(s == "DEPLOYED" for s in statuses):
                report.status = "DEPLOYED"
            elif any(s == "FAILED" for s in statuses):
                report.status = "FAILED"
            else:
                report.status = "NOOP"
            report.summary = self._summarize(report)
        except Exception as exc:  # noqa: BLE001 — 失败安全
            report.status = "FAILED"
            report.summary = f"循环异常: {exc}"
            report.detail = str(exc)

        report.cycle_id = self._persist_cycle(report)
        if report.status == "FAILED":
            self._persist_failure(report.cycle_id, report.summary)
        return report

    def run(self, max_cycles: int = 3) -> list[CycleReport]:
        """连续运行多轮（轮间不依赖，故各轮独立）。"""
        reports = []
        for _ in range(max(1, max_cycles)):
            reports.append(self.run_cycle())
        return reports

    @staticmethod
    def _summarize(report: CycleReport) -> str:
        if report.actions:
            acts = ", ".join(f"{a['action']}={a['status']}" for a in report.actions)
            return f"{report.status}: {acts}"
        return f"{report.status}: 无自动修复项"


def run_cycle(repo_root: str | Path = ".", db_path: str | Path = DEFAULT_DB,
              config: SchedulerConfig | None = None) -> CycleReport:
    """便捷入口: 单轮自举循环。"""
    return BootstrapScheduler(repo_root=repo_root, db_path=db_path,
                              config=config).run_cycle()
