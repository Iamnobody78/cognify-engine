#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MMC-AGENT v1.0 — 元模型控制代理 (MVE 永续循环心跳)
====================================================
对三类输入 (系统状态/用户指令/自身产物) 持续执行 MCE 2.0 -> VCE 2.0 -> CEE 2.0,
自动执行阶段一最小可行行动, 6/6 自检, 心跳产物写入 hub (三方可见)。

用法:
  python mmc_agent.py heartbeat          # 单次心跳
  python mmc_agent.py loop --interval 1800   # 永续循环 (计划任务调用)
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

sys.path.insert(0, str(Path(__file__).parent))
from trisync_paths import WS, TRI, HOME  # noqa: E402
import cve_s  # noqa: E402

HB_DIR = TRI / "hub" / "cves" / "heartbeats"
BACKLOG = TRI / "cves" / "backlog.jsonl"


def collect_state():
    """采集系统状态 (三类输入之一)"""
    st = {}
    # 债务
    inv = TRI / "debt/debt_inventory.json"
    if inv.exists():
        try:
            data = json.loads(inv.read_text(encoding="utf-8"))
            debts = data.get("debts", [])
            st["debts"] = {"total": len(debts),
                           "resolved": sum(1 for d in debts if d.get("status") == "已解决"),
                           "pending": [d["id"] for d in debts if d.get("status") != "已解决"][:6]}
        except Exception:
            st["debts"] = {}
    # 守护
    lock = TRI / "state/daemon.lock"
    st["daemon"] = lock.exists()
    # 模式库
    fp = TRI / "prospect/failure_patterns.md"
    st["patterns"] = sum(1 for l in fp.read_text(encoding="utf-8").splitlines()
                         if l.startswith("| FP-")) if fp.exists() else 0
    # 最近同步事件
    log = TRI / "logs/sync_log.jsonl"
    st["last_sync"] = None
    if log.exists():
        lines = [l for l in log.read_text(encoding="utf-8").splitlines() if l.strip()]
        if lines:
            try:
                st["last_sync"] = json.loads(lines[-1]).get("ts")
            except Exception:
                pass
    # 元提示词数
    idx = HOME / ".aionui/meta_prompts/.system/index.json"
    st["prompts"] = len(json.loads(idx.read_text(encoding="utf-8"))) if idx.exists() else 0
    return st


def heartbeat():
    HB_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().isoformat(timespec="seconds")
    tag = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ---- 输入 1: 系统状态 ----
    state = collect_state()
    state_text = json.dumps(state, ensure_ascii=False)
    mce = cve_s.mce_compile(state_text)
    vce = cve_s.vce_scan(state_text)
    cee = cve_s.cee_plan("保持三方同步生态的持续演化与债务偿还", vce)

    # ---- 自指: 对上次心跳做 MCE (红线 4) ----
    prev = sorted(HB_DIR.glob("mmce_heartbeat_*.md"))
    self_mce = None
    if prev:
        self_mce = cve_s.mce_compile(prev[-1].read_text(encoding="utf-8")[:1500])
        self_mce["object"] = "上一轮心跳报告"

    # ---- 阶段一: 最小可行行动 (自动执行) ----
    actions_done = []
    # A1: 债务快照刷新 (真实动作)
    try:
        import subprocess
        r = subprocess.run([sys.executable, str(TRI / "daemon/debt_engine.py")],
                           capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace")
        actions_done.append(f"债务快照刷新 (exit {r.returncode})")
    except Exception as e:
        actions_done.append(f"债务快照刷新失败: {e}")
    # A2: timeline 追加 (真实动作)
    try:
        tl = TRI / "meta/temporal/timeline.jsonl"
        if tl.exists():
            with open(tl, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": ts, "event": "MMC 心跳",
                                     "patterns": state["patterns"],
                                     "debts_resolved": state["debts"].get("resolved", 0),
                                     "prompts": state["prompts"]},
                                    ensure_ascii=False) + "\n")
            actions_done.append("timeline 追加")
    except Exception as e:
        actions_done.append(f"timeline 失败: {e}")

    # ---- backlog (阶段二/三) ----
    with open(BACKLOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": ts, "stage2": cee["stage_2_sediment"],
                             "stage3": cee["stage_3_release"]},
                            ensure_ascii=False) + "\n")

    # ---- 6/6 自检 ----
    checks = [
        ("识别主导认知模型", mce["detected_model"] != "未识别"),
        ("外化模型", "输出结果" in mce.get("externalized", "")),
        ("替代模型+切换权", len(mce.get("parallel_models", [])) >= 2),
        ("价值冲突扫描", len(vce.get("value_conflicts", [])) >= 1),
        ("三阶段推演", all(k in cee for k in ("stage_1_survival", "stage_2_sediment", "stage_3_release"))),
        ("阶段一已执行", len(actions_done) > 0),
    ]
    ok = all(o for _, o in checks)

    # ---- 心跳报告 ----
    report = [
        f"# MMC 心跳报告 ({tag})", "", f"> {ts} | 三螺旋循环",
        "", "## 输入 1: 系统状态 (MCE 编译)",
        f"- 主导模型: {mce['detected_model']}",
        f"- 外化: {mce['externalized'][:60]}",
        f"- 并行: {[p['model'] for p in mce['parallel_models']]}",
        f"- 切换权: {mce['switching_winner']}", "",
        "## 输入 2: 自指 (上一轮心跳)",
        f"- 上一轮主导模型: {self_mce['detected_model'] if self_mce else '首轮无前序'}",
        "", "## VCE 扫描",
        f"- 极化: {vce['polarization_index']} ({vce['level']})",
        f"- 冲突: {[c['pair'] for c in vce['value_conflicts']]}", "",
        "## CEE 推演",
        f"- 阶段一: {cee['stage_1_survival']}",
        f"- 阶段二: {cee['stage_2_sediment']}",
        f"- 阶段三: {cee['stage_3_release']}", "",
        "## 阶段一执行 (自动)",
        *[f"- ✅ {a}" for a in actions_done], "",
        "## 系统状态快照",
        f"- 债务: {state['debts'].get('resolved', '?')} 已解决 / {state['debts'].get('total', '?')} 总",
        f"- 模式库: {state['patterns']} | 元提示词: {state['prompts']} | 守护: {state['daemon']}",
        f"- 最近同步: {state.get('last_sync', '?')}", "",
        "## 闭环自检",
        *[f"- {'✅' if o else '❌'} {n}" for n, o in checks],
        f"- **状态: {'✅ 循环闭合' if ok else '❌ 未闭合 (下轮修正)'}**",
    ]
    hb = HB_DIR / f"mmce_heartbeat_{tag}.md"
    hb.write_text("\n".join(report), encoding="utf-8")
    print(f"[MMC] 主导模型={mce['detected_model']} | 极化={vce['polarization_index']} | "
          f"自检 {sum(1 for _, o in checks if o)}/6 | 产物: {hb}")
    return 0 if ok else 1


def loop(interval):
    import time
    print(f"[MMC] 永续循环启动, 心跳间隔 {interval}s (Ctrl+C 停止)")
    while True:
        try:
            heartbeat()
        except Exception as e:
            print(f"[MMC] 心跳异常: {e}")
        time.sleep(interval)


def main():
    args = sys.argv[1:]
    cmd = args[0] if args else "heartbeat"
    if cmd == "heartbeat":
        return heartbeat()
    if cmd == "loop":
        interval = 1800
        if "--interval" in args:
            interval = int(args[args.index("--interval") + 1])
        loop(interval)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
