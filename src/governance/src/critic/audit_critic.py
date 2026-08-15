"""Critic-Audit — 审计批判者.

职责（协议 §第三部分）:
  A1 债务清偿是否附带证据（commit hash）—— 失败 MEDIUM
  A2 审计日志（AUDIT-XXXX）是否含时间戳/任务名/关键产出 —— 失败 MEDIUM
  A3 relay_state.json 是否与实际状态一致 —— 失败 HIGH
  A4 迁移是否无损（无 DROP，ALTER 保留旧列） —— 失败 HIGH
  A5 快照版本与最近审计同步 —— 失败 LOW

对抗性: 默认假设债务是"口头标记"，直到找到 commit hash / 测试输出证据。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

COMMIT_RE = re.compile(r"[0-9a-fA-F]{7,}")  # noqa: policy (technical parser regex, not policy)
AUDIT_RE = re.compile(r"^## AUDIT-(\d{4})", re.MULTILINE)  # noqa: policy (audit-log header parser)
TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")  # noqa: policy (timestamp parser)
VERSION_RE = re.compile(r"v(\d+\.\d+\.\d+)")  # noqa: policy (version-string parser)

SEVERITY_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _finding(severity: str, check: str, evidence: str, suggestion: str) -> dict:
    return {
        "severity": severity,
        "check": check,
        "evidence": evidence,
        "suggestion": suggestion,
    }


def run(repo_root: Path) -> dict:
    """运行 Critic-Audit 全部检查，返回结构化 findings（可复核：含文件路径证据）。"""
    findings: list[dict] = []
    _check_debt_evidence(repo_root, findings)
    _check_audit_log(repo_root, findings)
    _check_relay_state(repo_root, findings)
    _check_migration_lossless(repo_root, findings)
    _check_snapshot_sync(repo_root, findings)
    return {"critic": "audit", "findings": findings}


def _check_debt_evidence(repo_root: Path, findings: list[dict]) -> None:
    """A1: debt_registry.md 已清偿区每一行必须引用 commit hash 或测试证据。"""
    path = repo_root / "debt_registry.md"
    if not path.exists():
        findings.append(_finding("HIGH", "A1: 债务登记缺失",
                                 "debt_registry.md 不存在", "创建债务登记"))
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    # 仅检查表格行（| 开头）且含 DEBT- 编号的清偿记录 —— 批判者 v1.0.1
    # 修正（自记录）: 原实现把章节标题/说明行（含"已清偿"字样）误计为记录。
    cleared = [ln for ln in lines
               if ln.lstrip().startswith("|") and re.search(r"DEBT-\d+", ln)
               and re.search(r"已清偿|已清除|cleared|CLEARED", ln)]
    if not cleared:
        return  # 无已清偿表格记录，无断言可做
    bare = [ln for ln in cleared if not COMMIT_RE.search(ln)]
    for ln in bare[:3]:
        findings.append(_finding(
            "MEDIUM", "A1: 债务清偿缺少证据",
            f"debt_registry.md: `{ln.strip()[:80]}` 无 commit hash 引用",
            "补上清偿 commit hash 或测试输出证据"))
    if bare:
        findings.append(_finding(
            "LOW", "A1: 清偿证据不完整",
            f"debt_registry.md 共 {len(cleared)} 行清偿记录，{len(bare)} 行无 hash",
            "全部清偿行都应可复核"))


def _check_audit_log(repo_root: Path, findings: list[dict]) -> None:
    """A2: audit_log.md 最近 5 条 AUDIT 记录必须含时间戳 + 任务名。"""
    path = repo_root / ".aionui" / "audit_log.md"
    if not path.exists():
        findings.append(_finding("MEDIUM", "A2: 审计日志缺失",
                                 ".aionui/audit_log.md 不存在", "建立审计日志"))
        return
    text = path.read_text(encoding="utf-8")
    entries = AUDIT_RE.findall(text)
    if not entries:
        findings.append(_finding("MEDIUM", "A2: 审计日志为空",
                                 "未找到 ## AUDIT-XXXX 条目", "按模板记录审计"))
        return
    # 批判者 v1.0.1 修正（自记录）: 原实现固定要求最近 5 块中 ≥3 完整，
    # 对记录总数 <5 的仓库必然误报。按比例: 总块数 n → 需完整块
    # min(3, n)（n=1 时 1/1 完整即通过）。v1.0.2: split 首元素为空串
    # 被误计为 block（1/2 而非 1/1）→ 过滤空块。
    recent = [b for b in text.split("## AUDIT-")[-6:] if b.strip()]
    n_blocks = len(recent)
    require = min(3, n_blocks)
    with_ts = sum(1 for b in recent if TS_RE.search(b))
    with_task = sum(1 for b in recent if ("TASK-" in b or "标题" in b or "PR:" in b))
    if with_ts < require or with_task < require:
        findings.append(_finding(
            "MEDIUM", "A2: 审计日志不完整",
            f"最近审计块: 时间戳 {with_ts}/{n_blocks}, 任务标识 {with_task}/{n_blocks}"
            f"（需 ≥{require}）",
            "每条 AUDIT 需含 ISO 时间戳 + 任务名/PR + 关键产出"))


def _check_relay_state(repo_root: Path, findings: list[dict]) -> None:
    """A3: relay_state.json 必须为 COMPLETED 且 task_id 与最近审计一致。"""
    path = repo_root / ".aionui" / "scheduler" / "relay_state.json"
    if not path.exists():
        findings.append(_finding("HIGH", "A3: relay_state 缺失",
                                 ".aionui/scheduler/relay_state.json 不存在",
                                 "调度中继状态必须存在且反映实际状态"))
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        findings.append(_finding("HIGH", "A3: relay_state 非法",
                                 f"JSON 解析失败: {exc}", "修复 JSON"))
        return
    status = state.get("status")
    task_id = state.get("task_id")
    phases = state.get("phases") or {}
    if status == "COMPLETED":
        pass  # 合法终态
    elif status == "IN_PROGRESS" and phases:
        # 多阶段长任务：任一 phase 未完成则 IN_PROGRESS 合法（REAL-012 自进化引擎场景）
        pending = [n for n, p in phases.items()
                   if not isinstance(p, dict) or p.get("status") != "COMPLETED"]
        if pending:
            findings.append(_finding(
                "LOW", "A3: relay_state 多阶段进行中",
                f"task_id={task_id!r} status=IN_PROGRESS"
                f"（未完成 phase: {', '.join(sorted(pending))}）",
                "多阶段长任务合法状态；全部 phase 完成后将 status 更新为 COMPLETED"))
        else:
            findings.append(_finding(
                "HIGH", "A3: relay_state 陈旧",
                f"status=IN_PROGRESS 但全部 {len(phases)} 个 phase 均已 COMPLETED",
                "全部 phase 完成后必须将 status 更新为 COMPLETED"))
    else:
        findings.append(_finding(
            "HIGH", "A3: relay_state 未完成",
            f"task_id={task_id!r} status={status!r}"
            "（应为 COMPLETED，或带未完成 phases 的 IN_PROGRESS）",
            "任务未完成不可宣称完成；若已结束需更新 relay_state"))
    # task_id 应与最近 AUDIT 对应（宽松：audit_log 提到该 task_id）
    audit = repo_root / ".aionui" / "audit_log.md"
    if task_id and audit.exists() and task_id not in audit.read_text(encoding="utf-8"):
        findings.append(_finding(
            "LOW", "A3: task_id 未在审计日志中对应",
            f"relay_state.task_id={task_id} 未出现在 audit_log.md",
            "保持审计与调度一致"))


def _check_migration_lossless(repo_root: Path, findings: list[dict]) -> None:
    """A4: storage 迁移必须无损 —— 禁止 DROP TABLE / 删除列。"""
    path = repo_root / "src" / "storage.py"
    if not path.exists():
        findings.append(_finding("HIGH", "A4: storage 缺失",
                                 "src/storage.py 不存在", "检查源码完整性"))
        return
    text = path.read_text(encoding="utf-8")
    for bad, why in [
        ("DROP TABLE", "删表 = 数据丢失"),
        ("ALTER TABLE .* DROP", "删列 = 数据丢失"),
    ]:
        for m in re.finditer(bad, text, re.IGNORECASE):
            line_no = text[: m.start()].count("\n") + 1
            findings.append(_finding(
                "HIGH", "A4: 迁移可能丢数据",
                f"src/storage.py:{line_no} `{m.group(0)}` — {why}",
                "SQLite 迁移必须用 ADD COLUMN（无损）"))
    if not re.search(r"ADD COLUMN|CREATE TABLE", text, re.IGNORECASE):
        findings.append(_finding(
            "MEDIUM", "A4: 无法确认迁移策略",
            "src/storage.py 未发现 ADD COLUMN/CREATE TABLE",
            "确认迁移路径存在且无损"))


def _check_snapshot_sync(repo_root: Path, findings: list[dict]) -> None:
    """A5: 快照版本号应与最近审计时间同步（低权重提示）。"""
    snap = repo_root / ".aionui" / "context" / "TRIPLE_LOOP_SNAPSHOT.md"
    audit = repo_root / ".aionui" / "audit_log.md"
    if not snap.exists() or not audit.exists():
        return
    snap_text = snap.read_text(encoding="utf-8")
    audit_text = audit.read_text(encoding="utf-8")
    latest_audit = AUDIT_RE.findall(audit_text)
    if not latest_audit:
        return
    newest = max(int(n) for n in latest_audit)
    if f"AUDIT-{newest:04d}" not in snap_text:
        findings.append(_finding(
            "LOW", "A5: 快照滞后",
            f"TRIPLE_LOOP_SNAPSHOT.md 未提及最近审计 AUDIT-{newest:04d}",
            "快照应反映最近审计，供新会话 30 秒恢复"))


def aggregate_severity(findings: list[dict]) -> str:
    """返回 findings 的最高严重度（供 runner 使用）。"""
    if not findings:
        return "PASS"
    return max(f["severity"] for f in findings)
