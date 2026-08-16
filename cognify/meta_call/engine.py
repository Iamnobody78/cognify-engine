#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
engine.py — META-CALL-FORCE v1.0 元能力强制调用引擎
====================================================
"部署了不等于用上了" → 强制调用链: 每次任务真实调用已部署元能力并审计。

调用链 (真实调用, 不造假):
  1. 元记忆   — 检索 learning/ledger.jsonl 历史 (任务开始前)
  2. 元思考   — cve_s.mce_compile 认知编译 (复杂推理前)
  3. 元决策   — 协议网关 evaluate_verified 五层裁决 (决策前)
  4. 元认知   — meta/status.json 30 维核验 (输出前)
  5. 元反思   — 最近 mmce 心跳闭环检查 (任务完成后)
  6. 元验证   — 全链完整性认证 (工具调用前)

用法:
  python engine.py force      # 执行一次完整调用链
  python engine.py status     # 认证状态 + 强制清单
  python engine.py log        # 调用日志尾部
"""
import faulthandler
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

faulthandler.enable()
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
PROD = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\cognify-engine")
MC = TRI / "meta-call"
LOG = MC / "call_log.jsonl"
CERT = MC / "certification_report.json"
VERSION = "2.1.9"

CHECKLIST = ["元记忆", "元思考", "元决策", "元认知", "元反思", "元验证"]


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


# ---------------------------------------------------------------- 调用链
def call_memory() -> dict:
    """元记忆: 检索学习账本最近条目 (真实读取)。"""
    p = TRI / "learning/ledger.jsonl"
    rows = []
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[-50:]:
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    hit = bool(rows)
    return {"module": "元记忆", "ok": hit, "detail": f"检索到 {len(rows)} 条历史记录",
            "sample": (rows[-1].get("entry", "")[:50] if rows else None)}


def call_thinking() -> dict:
    """元思考: cve_s MCE 认知编译 (真实引擎调用)。"""
    try:
        sys.path.insert(0, str(PROD / "plugins/cognitive/src"))
        sys.path.insert(0, str(PROD / "plugins/sync/src"))
        import cve_s  # noqa: PLC0415
        text = "分析当前系统同步状态与自主迭代方向"
        mce = cve_s.mce_compile(text)
        ok = bool(mce) and mce.get("detected_model", "未识别") != "未识别"
        return {"module": "元思考", "ok": ok,
                "detail": f"MCE 编译 → 主导模型: {mce.get('detected_model')}"}
    except Exception as exc:  # noqa: BLE001
        return {"module": "元思考", "ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def call_decision() -> dict:
    """元决策: 协议网关五层裁决 (真实网关调用)。"""
    try:
        sys.path.insert(0, str(PROD / "plugins/governance/src"))
        from src.protocol_gateway import ProtocolGateway  # noqa: PLC0415
        gw = ProtocolGateway()
        r = gw.evaluate_verified("/governance/evaluate", "POST",
                                 {"input": "执行下一轮自主迭代",
                                  "governance": {"protocols": {"entropy_denoise": {"triggered": True}}}})
        action = r.get("action")
        return {"module": "元决策", "ok": action is not None and action != "DENY",
                "detail": f"五层裁决 → {action} (rule: {r.get('rule')})"}
    except Exception as exc:  # noqa: BLE001
        return {"module": "元决策", "ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def call_cognition() -> dict:
    """元认知: 30 维元能力核验 (真实状态读取)。"""
    st = _json(TRI / "meta/status.json", {})
    active = st.get("active_count", "0/30")
    ok = str(active).startswith("30")
    return {"module": "元认知", "ok": ok,
            "detail": f"元能力 {active} active, health={st.get('overall_health')}"}


def call_reflection() -> dict:
    """元反思: 最近 mmce 心跳闭环检查 (真实文件核验)。"""
    hb = sorted((TRI / "hub/cves/heartbeats").glob("mmce_heartbeat_*.md"))
    if not hb:
        return {"module": "元反思", "ok": False, "detail": "无心跳数据"}
    latest = hb[-1]
    txt = latest.read_text(encoding="utf-8", errors="replace")
    closed = "循环闭合" in txt
    return {"module": "元反思", "ok": closed,
            "detail": f"最近心跳 {latest.name[:30]} {'✅ 闭环' if closed else '❌ 未闭合'}"}


def call_verify(results: list) -> dict:
    """元验证: 全链完整性认证。"""
    ok_count = sum(1 for r in results if r["ok"])
    ok = ok_count == len(results)
    return {"module": "元验证", "ok": ok,
            "detail": f"调用链完整性 {ok_count}/{len(results)}"}


CALLS = [call_memory, call_thinking, call_decision, call_cognition, call_reflection]


def run_chain() -> dict:
    MC.mkdir(parents=True, exist_ok=True)
    results = [f() for f in CALLS]
    verify = call_verify(results)
    results.append(verify)
    entry = {"id": f"MC-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}",
             "ts": _now(), "version": VERSION, "results": results,
             "certified": verify["ok"]}
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    CERT.write_text(json.dumps({"id": entry["id"], "ts": entry["ts"],
                                "certified": entry["certified"],
                                "checklist": {r["module"]: r["ok"] for r in results}},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return entry


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "force"
    if cmd == "force":
        e = run_chain()
        print(f"[meta-call] 调用链 {e['id']} | 认证: {'✅ CERTIFIED' if e['certified'] else '❌ 未经验证'}")
        for r in e["results"]:
            print(f"  {'✅' if r['ok'] else '❌'} {r['module']}: {r['detail']}")
        print(f"[meta-call] → {LOG}")
        return 0 if e["certified"] else 1
    if cmd == "status":
        c = _json(CERT, None)
        if c is None:
            print("[meta-call] 尚无认证记录")
            return 1
        print(f"[meta-call] 最近认证: {c['ts'][:16]} | {'✅ CERTIFIED' if c['certified'] else '❌ 未经验证'}")
        for mod, ok in c.get("checklist", {}).items():
            print(f"  {'✅' if ok else '❌'} {mod}")
        return 0 if c["certified"] else 1
    if cmd == "log":
        if not LOG.exists():
            print("[meta-call] 无调用日志")
            return 0
        for line in LOG.read_text(encoding="utf-8").splitlines()[-5:]:
            try:
                e = json.loads(line)
                print(f"  {e['ts'][:16]} | {e['id']} | {'✅' if e['certified'] else '❌'}")
            except Exception:
                continue
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
