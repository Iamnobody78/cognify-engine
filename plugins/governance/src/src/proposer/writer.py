"""writer — MH-2 候选生成器: 将完整 harness 写入 candidates/{candidate_id}/。

Meta-Harness 原则: 提议者 = 变异算子。候选必须是**完整 harness**
（不是补丁）：candidates/{candidate_id}/src/ 下持有可独立运行的
完整文件树（如完整的调度器、验证器、奖励函数 harness），
candidate.json 记录父轨迹（变异来源）+ 变异说明。

写入流程（幂等）:
  1. import_trace_artifacts(): 从父轨迹复制 artifacts 作为种子
  2. write_source(): 写入候选的完整 src/ 文件树
  3. finalize(): 生成 candidate.json（provenance 血缘）

candidates/ 目录被 .gitignore 忽略（运行时产物）。
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

CANDIDATES_REL = "candidates"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass
class Candidate:
    candidate_id: str
    name: str
    created_at: str = field(default_factory=_now)
    parent_trace_id: str = ""
    mutation_note: str = ""
    files: list[str] = field(default_factory=list)   # src/ 下相对路径
    metrics: dict = field(default_factory=dict)      # 评分结果（MH-3 写入）

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def id(self) -> str:
        """别名: 与 Pareto Point.id 兼容。"""
        return self.candidate_id


class CandidateWriter:
    """候选 harness 的文件系统写入器。"""

    def __init__(self, root: str | Path = "."):
        self.root = Path(root).resolve()
        self.candidates_dir = self.root / CANDIDATES_REL
        self.candidates_dir.mkdir(parents=True, exist_ok=True)

    def create(self, name: str, parent_trace_id: str = "",
               mutation_note: str = "") -> Candidate:
        cid = f"{uuid.uuid4().hex[:10]}_{name}"
        cand = Candidate(candidate_id=cid, name=name,
                         parent_trace_id=parent_trace_id,
                         mutation_note=mutation_note)
        self._write_candidate_json(cand)
        return cand

    def import_trace_artifacts(self, cand: Candidate, trace_id: str,
                               store: "TraceStore") -> int:
        """从父轨迹复制 artifacts 到候选 src/ 作为种子。

        返回复制的文件数。轨迹不存在时静默返回 0（候选可无父轨迹）。
        """
        try:
            trace = store.load(trace_id)
        except KeyError:
            return 0
        n = 0
        for rel in trace.artifacts:
            try:
                data = store.read_artifact(trace_id, rel)
            except (ValueError, OSError):
                continue
            name = Path(rel).name
            self.write_source(cand, name, data)
            n += 1
        return n

    def write_source(self, cand: Candidate, rel_path: str,
                     content: str | bytes) -> Path:
        """写入候选 src/{rel_path}（自动建目录）。"""
        target = self.candidates_dir / cand.candidate_id / "src" / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
        rel = rel_path.replace("\\", "/")
        if rel not in cand.files:
            cand.files.append(rel)
        self._write_candidate_json(cand)
        return target

    def write_tree(self, cand: Candidate, source_dir: str | Path) -> int:
        """整树复制: 将 src_dir 下全部文件复制为候选的 src/。"""
        src = Path(source_dir)
        if not src.is_dir():
            return 0
        n = 0
        for p in sorted(src.rglob("*")):
            if p.is_file():
                rel = p.relative_to(src).as_posix()
                self.write_source(cand, rel, p.read_bytes())
                n += 1
        return n

    def set_metrics(self, cand: Candidate, metrics: dict) -> None:
        """写入评分指标（MH-3 Pareto 层调用）。"""
        cand.metrics = dict(metrics)
        self._write_candidate_json(cand)

    def finalize(self, cand: Candidate) -> Candidate:
        """固化: 重写 candidate.json（含文件清单）。"""
        self._write_candidate_json(cand)
        return cand

    # ---------- 读取 ----------
    def load(self, candidate_id: str) -> Candidate:
        path = self.candidates_dir / candidate_id / "candidate.json"
        if not path.exists():
            raise KeyError(f"候选不存在: {candidate_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return Candidate(
            candidate_id=data["candidate_id"], name=data["name"],
            created_at=data.get("created_at", ""),
            parent_trace_id=data.get("parent_trace_id", ""),
            mutation_note=data.get("mutation_note", ""),
            files=data.get("files", []),
            metrics=data.get("metrics", {}))

    def list_candidates(self) -> list[dict]:
        metas = []
        for path in sorted(self.candidates_dir.glob("*/candidate.json"),
                           reverse=True):
            try:
                metas.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return metas

    # ---------- 内部 ----------
    def _write_candidate_json(self, cand: Candidate) -> None:
        data = asdict(cand)
        path = self.candidates_dir / cand.candidate_id / "candidate.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8")
