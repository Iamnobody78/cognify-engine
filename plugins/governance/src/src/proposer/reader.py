"""reader — MH-2 轨迹阅读器: 从文件系统真相层检索与搜索执行轨迹。

Meta-Harness 原则: 提议者是变异算子，先读取历史轨迹（作为反馈），
再生成候选 harness。reader 提供:
  - read_trace(trace_id): 读取完整轨迹
  - list_traces(): 元数据列表
  - search_traces(query): 按名称/摘要/步骤文本子串检索
  - grep_traces(pattern): 正则搜索步骤 detail/summary（grep 式）
  - cat_trace(trace_id): 轨迹全文展开（cat 式，供 LLM 直接消费）

所有读取均为只读，绝不修改轨迹。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from src.trace import Trace, TraceStore, token_estimate


class TraceReader:
    """基于 TraceStore 的只读检索层。"""

    def __init__(self, store: TraceStore | None = None, root: str | Path = "."):
        self.store = store or TraceStore(root)

    # ---------- 基础读取 ----------
    def read_trace(self, trace_id: str) -> Trace:
        return self.store.load(trace_id)

    def list_traces(self) -> list[dict]:
        return self.store.list_traces()

    def cat_trace(self, trace_id: str, max_chars: int | None = None) -> str:
        """cat 式全文展开: 人类/LLM 可读的完整轨迹文本。"""
        t = self.store.load(trace_id)
        lines = [
            f"# trace {t.trace_id} — {t.name}",
            f"status={t.status} started={t.started_at} ended={t.ended_at}",
            f"tokens={t.total_tokens} steps={t.step_count} artifacts={t.artifact_count}",
            f"summary={t.summary}",
        ]
        for i, s in enumerate(t.steps, 1):
            lines.append(f"[{i:03d}] {s.name} ({s.status}) — {s.detail}")
        for art in t.artifacts:
            lines.append(f"[art] {art}")
        text = "\n".join(lines)
        if max_chars and len(text) > max_chars:
            text = text[:max_chars] + "\n...[truncated]"
        return text

    # ---------- 检索 ----------
    def search_traces(self, query: str) -> list[dict]:
        """按 trace 名/摘要/步骤文本做大小写不敏感子串检索。"""
        q = query.lower()
        hits = []
        for meta in self.store.list_traces():
            haystack = (meta.get("name", "") + " " + meta.get("summary", "")).lower()
            if q in haystack:
                hits.append(meta)
                continue
            try:
                t = self.store.load(meta["trace_id"])
                if any(q in s.detail.lower() or q in s.name.lower()
                       for s in t.steps):
                    hits.append(meta)
            except (KeyError, json.JSONDecodeError):
                continue
        return hits

    def grep_traces(self, pattern: str) -> list[dict]:
        """正则检索步骤 detail/summary（grep 式）。

        返回 [{trace_id, name, status, matches: [step 文本]}]
        """
        try:
            rx = re.compile(pattern)
        except re.error:
            raise ValueError(f"非法正则: {pattern}")
        out = []
        for meta in self.store.list_traces():
            t = self.store.load(meta["trace_id"])
            matches = []
            for s in t.steps:
                if rx.search(s.detail) or rx.search(s.name):
                    matches.append(f"{s.name}: {s.detail}")
            if rx.search(t.summary):
                matches.append(f"summary: {t.summary}")
            if matches:
                out.append({"trace_id": t.trace_id, "name": t.name,
                            "status": t.status, "matches": matches})
        return out

    # ---------- 反馈预算 ----------
    def feedback_budget(self, max_tokens: int = 10_000_000) -> dict:
        """计算历史轨迹总 token 与预算占用（Meta-Harness 10M 上限）。"""
        total = 0
        counts = {}
        for meta in self.store.list_traces():
            tokens = meta.get("total_tokens", 0)
            total += tokens
            counts[tokens] = counts.get(tokens, 0) + 1
        return {"total_tokens": total, "budget": max_tokens,
                "used_pct": round(total / max_tokens * 100, 2) if max_tokens else 0,
                "trace_count": len(self.store.list_traces())}
