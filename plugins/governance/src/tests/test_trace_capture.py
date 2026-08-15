# -*- coding: utf-8 -*-
"""MH-1: trace capture tests — 完整执行轨迹的文件系统持久化。

AC1: capture 生成 traces/{trace_id}/manifest.json + steps/ + artifacts/
AC2: 每步增量落盘（崩溃可恢复）
AC3: 异常自动标记 failed
AC4: 产物复制/写入
AC5: load/list 读取完整轨迹
AC6: token 估算（10M 预算裁剪输入）
AC7: 上下文管理器与函数包装两种用法
"""

import json
import time
from pathlib import Path

import pytest

from src.trace import (SCHEMA_VERSION, TraceCapture, TraceStore, TraceStep,
                       capture, capture_run, token_estimate, traced)


@pytest.fixture()
def store(tmp_path):
    return TraceStore(tmp_path)


# ---------- AC1: 基本持久化 ----------
class TestStoreBasic:
    def test_capture_writes_manifest_and_steps(self, store):
        with capture(store, "run_exp") as t:
            t.step("load", detail="policies.yaml")
            t.step("evaluate", detail="10 episodes")
        assert t.status == "ok"
        manifest = store.traces_dir / t.trace_id / "manifest.json"
        assert manifest.exists()
        steps = sorted((store.traces_dir / t.trace_id / "steps").glob("*.json"))
        assert len(steps) == 2
        m = json.loads(manifest.read_text(encoding="utf-8"))
        assert m["schema"] == SCHEMA_VERSION
        assert m["step_count"] == 2
        assert m["status"] == "ok"
        assert m["name"] == "run_exp"

    def test_trace_id_unique(self, store):
        ids = set()
        for i in range(5):
            with capture(store, f"run{i}") as t:
                ids.add(t.trace_id)
        assert len(ids) == 5

    def test_steps_persisted_incrementally(self, store, tmp_path):
        """AC2: 每步立即落盘，未 finalize 也可读取。"""
        cap = TraceCapture(store, "partial")
        cap.step("first", detail="已落盘")
        # 未退出上下文即断言步骤文件存在
        p = store.traces_dir / cap.trace.trace_id / "steps"
        assert len(list(p.glob("*.json"))) == 1
        cap.__exit__(None, None, None)


# ---------- AC3: 异常处理 ----------
class TestFailure:
    def test_exception_marks_failed(self, store):
        with pytest.raises(RuntimeError):
            with capture(store, "boom") as t:
                t.step("ok_step")
                raise RuntimeError("crash")
        loaded = store.load(t.trace_id)
        assert loaded.status == "failed"
        assert "crash" in loaded.summary

    def test_capture_run_reraises(self, store):
        def bad():
            raise ValueError("bad value")
        with pytest.raises(ValueError):
            capture_run(store, "bad_fn", bad)
        traces = store.list_traces()
        assert traces[0]["status"] == "failed"


# ---------- AC4: 产物 ----------
class TestArtifacts:
    def test_artifact_text_and_bytes(self, store):
        with capture(store, "art") as t:
            t.artifact("note.txt", "人工备注")
            t.artifact("data.bin", b"\x00\x01\x02")
        loaded = store.load(t.trace_id)
        assert loaded.artifact_count == 2
        assert store.read_artifact(t.trace_id, "artifacts/note.txt").decode("utf-8") == "人工备注"
        assert store.read_artifact(t.trace_id, "artifacts/data.bin") == b"\x00\x01\x02"

    def test_artifact_copy_file(self, store, tmp_path):
        src = tmp_path / "config.yaml"
        src.write_text("rules: []", encoding="utf-8")
        with capture(store, "file_art") as t:
            t.artifact("config.yaml", src)
        got = store.read_artifact(t.trace_id, "artifacts/config.yaml")
        assert got.decode("utf-8") == "rules: []"


# ---------- AC5: 读取 ----------
class TestRead:
    def test_load_roundtrip(self, store):
        with capture(store, "round") as t:
            t.step("a", detail="step a")
            t.step("b", detail="step b", status="warn")
            t.artifact("x.txt", "hello")
        loaded = store.load(t.trace_id)
        assert loaded.name == "round"
        assert [s.name for s in loaded.steps] == ["a", "b"]
        assert loaded.steps[1].status == "warn"
        assert loaded.artifacts == ["artifacts/x.txt"]

    def test_list_traces_newest_first(self, store):
        with capture(store, "first") as t1:
            pass
        # started_at 毫秒精度：保证两次 capture 时间戳分离，避免 CI
        # 快速执行下同一毫秒排序不稳定（AUDIT-0047）
        time.sleep(0.005)
        with capture(store, "second") as t2:
            pass
        metas = store.list_traces()
        assert metas[0]["trace_id"] == t2.trace_id
        assert metas[1]["trace_id"] == t1.trace_id

    def test_load_unknown_raises(self, store):
        with pytest.raises(KeyError):
            store.load("does-not-exist")

    def test_artifact_path_traversal_blocked(self, store):
        with capture(store, "trav") as t:
            t.artifact("a.txt", "x")
        with pytest.raises(ValueError):
            store.read_artifact(t.trace_id, "artifacts/../../evil.txt")


# ---------- AC6: token 估算 ----------
class TestTokens:
    def test_token_estimate(self):
        assert token_estimate("") == 0
        assert token_estimate("a" * 4) == 1
        assert token_estimate("a" * 100) == 25

    def test_manifest_total_tokens(self, store):
        with capture(store, "tok") as t:
            t.step("big", detail="x" * 4000)
        m = json.loads((store.traces_dir / t.trace_id / "manifest.json")
                       .read_text(encoding="utf-8"))
        assert m["total_tokens"] >= 1000


# ---------- AC7: 两种用法 ----------
class TestUsages:
    def test_capture_run_function_wrapper(self, store):
        def add(a, b):
            return a + b
        result, trace = capture_run(store, "add_fn", add, 1, 2)
        assert result == 3
        assert trace.status == "ok"
        assert trace.step_count == 2  # start + finish

    def test_traced_decorator(self, store):
        @traced(store)
        def double(x):
            return x * 2
        assert double(21) == 42
        metas = store.list_traces()
        assert metas[0]["name"] == "double"
        assert metas[0]["status"] == "ok"
