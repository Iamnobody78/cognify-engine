"""capture — MH-1 执行轨迹捕获器（上下文管理器 + 函数包装）。

用法:
    from src.trace import capture, TraceStore

    store = TraceStore(".")
    with capture(store, "run_experiment", meta={"variant": "v11"}) as t:
        t.step("load", detail="policies.yaml 解析完成")
        t.step("sensor", detail="git 状态: clean")
        t.artifact("policies.yaml", "config/policies.yaml")   # 复制文件
        t.artifact("note.txt", "人工备注")                     # 文本
        # 异常自动标记 failed，无需手工 finalize
    # 退出后 t.status == "ok"

函数包装（记录返回值/异常）:
    result = capture_run(store, "bench", fn, *args, **kwargs)
"""

from __future__ import annotations

import functools
from pathlib import Path

from .store import Trace, TraceStep, TraceStore


class TraceCapture:
    """上下文管理器: 进入创建轨迹，正常退出标记 ok，异常标记 failed。"""

    def __init__(self, store: TraceStore, name: str, meta: dict | None = None):
        self.store = store
        self.trace: Trace = store.create(name, meta=meta)
        self._forced_status: str | None = None  # 显式标记（如记录失败步骤）

    def __enter__(self) -> "TraceCapture":
        return self

    @property
    def trace_id(self) -> str:
        return self.trace.trace_id

    @property
    def status(self) -> str:
        return self.trace.status

    def fail(self, reason: str) -> None:
        """显式标记轨迹失败（__exit__ 时生效，不会被覆盖为 ok）。"""
        self._forced_status = "failed"
        self.store.append_step(self.trace, TraceStep(
            name="failed", detail=reason, status="failed"))

    def __exit__(self, exc_type, exc, tb) -> bool:
        if self._forced_status == "failed":
            status, summary = "failed", "显式失败标记"
        elif exc_type is None:
            status, summary = "ok", f"{self.trace.step_count} 步完成"
        else:
            status, summary = "failed", f"异常 {exc_type.__name__}: {exc}"
        self.store.finalize(self.trace, status, summary=summary)
        return False  # 不吞异常

    # ---------- 便捷方法 ----------
    def step(self, name: str, detail: str = "", status: str = "ok") -> None:
        self.store.append_step(self.trace, TraceStep(name=name, detail=detail,
                                                     status=status))

    def artifact(self, name: str, content: str | bytes | Path) -> Path:
        return self.store.add_artifact(self.trace, name, content)


def capture(store: TraceStore, name: str, meta: dict | None = None):
    """快捷入口: capture(store, name) → TraceCapture 上下文管理器。"""
    return TraceCapture(store, name, meta=meta)


def capture_run(store: TraceStore, name: str, fn, *args, meta: dict | None = None,
                **kwargs):
    """同步函数包装: 自动建轨迹、记录开始/结束步骤、异常标记 failed。

    返回 (result, Trace)；异常时 result=None 并重抛。
    """
    cap = TraceCapture(store, name, meta=meta)
    cap.step("start", detail=f"调用 {fn.__name__}")
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 — 记录后重抛
        cap.step("failed", detail=f"{type(exc).__name__}: {exc}",
                 status="failed")
        cap.__exit__(type(exc), exc, exc.__traceback__)
        raise
    cap.step("finish", detail="正常返回")
    cap.__exit__(None, None, None)
    return result, cap.trace


def traced(store_factory):
    """装饰器: @traced(lambda: store) 包装任意函数自动捕获轨迹。"""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            store = store_factory() if callable(store_factory) else store_factory
            return capture_run(store, fn.__name__, fn, *args, **kwargs)[0]
        return wrapper
    return decorator
