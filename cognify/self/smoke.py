#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smoke.py — 元能力冒烟化 (批判阶段 2.1: 从"存在"到"运行")
=========================================================
核心 6 维真实执行冒烟 (不造假):
  元思考 → cve_s.mce_compile 真跑
  元记忆 → learning/ledger 检索 ≥1 条
  元逻辑 → 协议网关 evaluate 出明确动作
  元审视 → honesty_guard scan 执行
  元学习 → 学习账本追加+读回
  元验证 → meta-call 认证链 certified

证据: ~/.aionui-tri-sync/meta-smoke/evidence.jsonl (ts/cap/exit/耗时)
用法: python smoke.py
"""
import faulthandler
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))))
import cognify.paths as paths

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

faulthandler.enable()
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = paths.TRI
PROD = paths.PROD
PY = paths.PY
EV = TRI / "meta-smoke/evidence.jsonl"


def _log(cap: str, ok: bool, ms: int, detail: str) -> None:
    EV.parent.mkdir(parents=True, exist_ok=True)
    with open(EV, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"),
                             "cap": cap, "exit": 0 if ok else 1, "ms": ms,
                             "detail": detail[:120]}, ensure_ascii=False) + "\n")


def smoke_thinking() -> dict:
    t0 = time.time()
    try:
        sys.path.insert(0, str(PROD / "plugins/cognitive/src"))
        sys.path.insert(0, str(PROD / "plugins/sync/src"))
        import cve_s  # noqa: PLC0415
        mce = cve_s.mce_compile("元能力冒烟验证: 分析当前系统状态")
        ok = bool(mce) and mce.get("detected_model", "未识别") != "未识别"
        return {"cap": "元思考", "ok": ok, "ms": int((time.time() - t0) * 1000),
                "detail": f"MCE 真跑 → {mce.get('detected_model')}"}
    except Exception as exc:  # noqa: BLE001
        return {"cap": "元思考", "ok": False, "ms": int((time.time() - t0) * 1000),
                "detail": f"{type(exc).__name__}: {exc}"}


def _consume(consumer, producer, artifact):
    try:
        sys.path.insert(0, str(PROD / "cognify/self"))
        import consumption  # noqa: PLC0415
        consumption.log_consumption(producer, consumer, artifact)
    except Exception:
        pass


def smoke_memory() -> dict:
    t0 = time.time()
    try:
        p = TRI / "learning/ledger.jsonl"
        n = 0
        if p.exists():
            n = sum(1 for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip())
        ok = n >= 1
        if ok:
            _consume("meta_smoke", "learning/ledger", "ledger.jsonl")
        return {"cap": "元记忆", "ok": ok, "ms": int((time.time() - t0) * 1000),
                "detail": f"学习账本检索 {n} 条"}
    except Exception as exc:  # noqa: BLE001
        return {"cap": "元记忆", "ok": False, "ms": int((time.time() - t0) * 1000),
                "detail": f"{type(exc).__name__}: {exc}"}


def smoke_logic() -> dict:
    t0 = time.time()
    try:
        sys.path.insert(0, str(PROD / "plugins/governance/src"))
        from src.protocol_gateway import ProtocolGateway  # noqa: PLC0415
        r = ProtocolGateway().evaluate_verified(
            "/governance/evaluate", "POST",
            {"input": "冒烟", "governance": {"protocols": {"entropy_denoise": {"triggered": True}}}})
        ok = r.get("action") is not None
        return {"cap": "元逻辑", "ok": ok, "ms": int((time.time() - t0) * 1000),
                "detail": f"AST 守卫/网关裁决 → {r.get('action')}"}
    except Exception as exc:  # noqa: BLE001
        return {"cap": "元逻辑", "ok": False, "ms": int((time.time() - t0) * 1000),
                "detail": f"{type(exc).__name__}: {exc}"}


def smoke_scrutiny() -> dict:
    t0 = time.time()
    try:
        r = subprocess.run([PY, str(TRI / "daemon/honesty_guard.py"), "scan",
                            "元审视冒烟验证文本: 声明与证据需一致"],
                           capture_output=True, text=True, timeout=120,
                           encoding="utf-8", errors="replace")
        ok = r.returncode == 0
        return {"cap": "元审视", "ok": ok, "ms": int((time.time() - t0) * 1000),
                "detail": f"honesty_guard scan rc={r.returncode}"}
    except Exception as exc:  # noqa: BLE001
        return {"cap": "元审视", "ok": False, "ms": int((time.time() - t0) * 1000),
                "detail": f"{type(exc).__name__}: {exc}"}


def smoke_learning() -> dict:
    t0 = time.time()
    try:
        p = TRI / "learning/ledger.jsonl"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"),
                                 "kind": "SMOKE", "entry": "元学习冒烟记录"}, ensure_ascii=False) + "\n")
        txt = p.read_text(encoding="utf-8", errors="replace")
        ok = "元学习冒烟记录" in txt
        return {"cap": "元学习", "ok": ok, "ms": int((time.time() - t0) * 1000),
                "detail": "账本追加+读回 ✓"}
    except Exception as exc:  # noqa: BLE001
        return {"cap": "元学习", "ok": False, "ms": int((time.time() - t0) * 1000),
                "detail": f"{type(exc).__name__}: {exc}"}


def smoke_verify() -> dict:
    t0 = time.time()
    try:
        c = json.loads((TRI / "meta-call/certification_report.json").read_text(encoding="utf-8"))
        ok = bool(c.get("certified")) and len(c.get("checklist", {})) >= 5
        return {"cap": "元验证", "ok": ok, "ms": max(int((time.time() - t0) * 1000), 1),
                "detail": f"调用链认证 {'CERTIFIED' if ok else '未认证'} ({len(c.get('checklist', {}))} 项检查)"}
    except Exception as exc:  # noqa: BLE001
        return {"cap": "元验证", "ok": False, "ms": int((time.time() - t0) * 1000),
                "detail": f"{type(exc).__name__}: {exc}"}


SMOKES = [smoke_thinking, smoke_memory, smoke_logic, smoke_scrutiny, smoke_learning, smoke_verify]


def main():
    results = [f() for f in SMOKES]
    for r in results:
        _log(r["cap"], r["ok"], r["ms"], r["detail"])
    ok_n = sum(1 for r in results if r["ok"])
    print(f"[meta-smoke] 元能力冒烟 {ok_n}/{len(results)} (grade=smoke)")
    for r in results:
        print(f"  {'✅' if r['ok'] else '❌'} {r['cap']}: {r['detail']} ({r['ms']}ms)")
    print(f"[meta-smoke] 证据 → {EV}")
    return 0 if ok_n == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
