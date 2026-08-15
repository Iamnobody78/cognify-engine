"""store — MH-1 执行轨迹的文件系统持久化层。

文件系统是 Meta-Harness 的唯一真实来源（single source of truth）:
  traces/{trace_id}/manifest.json      # 轨迹元数据（schema/时间/状态/摘要）
  traces/{trace_id}/steps/NNN_*.json   # 有序步骤（增量追加，崩溃可恢复）
  traces/{trace_id}/artifacts/*        # 产物（文本/字节/文件复制）

设计契约（MH-1）:
  - 追加式写入: 每步立即落盘，进程崩溃不丢已记录步骤
  - 完整轨迹: manifest 记录起止时间/状态/步骤数/产物数/token 估算
  - 最大 10M token 反馈预算: 提供 token_estimate 供 Pareto 层裁剪
  - 无单点: 全部为 JSON/纯文本，任何工具可读
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "mh-trace/v1"

TRACES_REL = "traces"  # 仓库根下的轨迹目录（.gitignore 忽略）


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def token_estimate(text: str) -> int:
    """粗粒度 token 估算: 4 字符 ≈ 1 token（中英混排近似）。"""
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass
class TraceStep:
    name: str
    detail: str = ""
    status: str = "ok"          # ok | warn | failed
    ts: str = field(default_factory=_now)
    tokens: int = 0

    def __post_init__(self) -> None:
        if not self.tokens:
            self.tokens = token_estimate(self.detail)


@dataclass
class Trace:
    """单条执行轨迹的内存表示。"""
    trace_id: str
    name: str
    started_at: str = field(default_factory=_now)
    ended_at: str = ""
    status: str = "running"     # running | ok | failed | cancelled
    summary: str = ""
    steps: list[TraceStep] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)  # 相对路径
    meta: dict = field(default_factory=dict)

    @property
    def step_count(self) -> int:
        return len(self.steps)

    @property
    def artifact_count(self) -> int:
        return len(self.artifacts)

    @property
    def total_tokens(self) -> int:
        return sum(s.tokens for s in self.steps) + token_estimate(self.summary)


class TraceStore:
    """文件系统轨迹存储。"""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.traces_dir = self.root / TRACES_REL
        self.traces_dir.mkdir(parents=True, exist_ok=True)

    # ---------- 写入 ----------
    def create(self, name: str, meta: dict | None = None) -> Trace:
        trace = Trace(trace_id=uuid.uuid4().hex[:12], name=name,
                      meta=meta or {})
        self._write_manifest(trace)
        return trace

    def append_step(self, trace: Trace, step: TraceStep) -> None:
        trace.steps.append(step)
        idx = f"{len(trace.steps):03d}"
        path = self._step_path(trace.trace_id, idx, step.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(step), ensure_ascii=False, indent=2),
                        encoding="utf-8")
        # 每次步骤后刷新 manifest（增量可见）
        self._write_manifest(trace)

    def add_artifact(self, trace: Trace, name: str,
                     content: str | bytes | Path) -> Path:
        art_dir = self.traces_dir / trace.trace_id / "artifacts"
        art_dir.mkdir(parents=True, exist_ok=True)
        safe = name.replace("\\", "_").replace("/", "_")
        path = art_dir / safe
        if isinstance(content, Path):
            shutil.copy2(content, path)
        elif isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
        rel = f"artifacts/{safe}"
        if rel not in trace.artifacts:
            trace.artifacts.append(rel)
        self._write_manifest(trace)
        return path

    def finalize(self, trace: Trace, status: str, summary: str = "") -> None:
        trace.status = status
        trace.summary = summary
        trace.ended_at = _now()
        self._write_manifest(trace)

    # ---------- 读取 ----------
    def list_traces(self) -> list[dict]:
        """返回轨迹元数据列表（manifest 摘要），最新在前。"""
        metas = []
        for manifest in sorted(self.traces_dir.glob("*/manifest.json"),
                               reverse=True):
            try:
                metas.append(json.loads(manifest.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        # started_at 毫秒精度：同一毫秒内多个 trace 时用 trace_id 作
        # tiebreaker，保证排序确定性（AUDIT-0047，CI 快速执行 flaky 修复）
        metas.sort(key=lambda m: (m.get("started_at", ""), m.get("trace_id", "")),
                   reverse=True)
        return metas

    def load(self, trace_id: str) -> Trace:
        """加载完整轨迹（manifest + steps + artifacts 清单）。"""
        mpath = self.traces_dir / trace_id / "manifest.json"
        if not mpath.exists():
            raise KeyError(f"轨迹不存在: {trace_id}")
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        trace = Trace(
            trace_id=manifest["trace_id"],
            name=manifest["name"],
            started_at=manifest.get("started_at", ""),
            ended_at=manifest.get("ended_at", ""),
            status=manifest.get("status", "running"),
            summary=manifest.get("summary", ""),
            artifacts=manifest.get("artifacts", []),
            meta=manifest.get("meta", {}),
        )
        steps_dir = self.traces_dir / trace_id / "steps"
        for sp in sorted(steps_dir.glob("*.json")):
            data = json.loads(sp.read_text(encoding="utf-8"))
            trace.steps.append(TraceStep(
                name=data.get("name", sp.stem),
                detail=data.get("detail", ""),
                status=data.get("status", "ok"),
                ts=data.get("ts", ""),
                tokens=data.get("tokens", 0)))
        return trace

    def read_artifact(self, trace_id: str, rel: str) -> bytes:
        """读取产物（rel 形如 artifacts/xxx）。"""
        path = (self.traces_dir / trace_id / rel).resolve()
        base = (self.traces_dir / trace_id).resolve()
        # is_relative_to (Py3.9+): exact boundary check — startswith prefix
        # matching would also accept sibling ids (abc vs abcd). (AUDIT-0047)
        if not path.is_relative_to(base):
            raise ValueError("产物路径越界")
        return path.read_bytes()

    # ---------- 内部 ----------
    def _write_manifest(self, trace: Trace) -> None:
        manifest = {
            "schema": SCHEMA_VERSION,
            "trace_id": trace.trace_id,
            "name": trace.name,
            "started_at": trace.started_at,
            "ended_at": trace.ended_at,
            "status": trace.status,
            "summary": trace.summary,
            "step_count": trace.step_count,
            "artifact_count": trace.artifact_count,
            "total_tokens": trace.total_tokens,
            "artifacts": trace.artifacts,
            "meta": trace.meta,
        }
        path = self.traces_dir / trace.trace_id / "manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2),
                        encoding="utf-8")

    def _step_path(self, trace_id: str, idx: str, name: str) -> Path:
        safe = "".join(c if c.isalnum() else "_" for c in name)[:60] or "step"
        return self.traces_dir / trace_id / "steps" / f"{idx}_{safe}.json"
