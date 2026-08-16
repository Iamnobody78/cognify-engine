#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
transparent_plan.py — TRANSPARENT-PLAN v1.0 透明计划检查器
==========================================================
- activate: 记录透明计划模式激活状态
- check:    检查最近输出/报告是否包含"下一步计划"结构

用法:
  python transparent_plan.py activate
  python transparent_plan.py check
"""
import faulthandler
import json
import sys
from datetime import datetime
from pathlib import Path

faulthandler.enable()
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    pass

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
TP = TRI / "transparent-plan"
STATE = TP / "state.json"
HEARTBEAT = Path(r"C:\Users\ivy\.dsh\heartbeat\latest.md")


def _now():
    return datetime.now().isoformat(timespec="seconds")


def activate() -> None:
    TP.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"ts": _now(), "mode": "active",
                                 "protocol": "TRANSPARENT-PLAN v1.0"},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    print("[plan] ✅ 透明计划模式已激活 (TRANSPARENT-PLAN v1.0)")


def check() -> int:
    """检查最近报告是否含"下一步计划"结构 (强制要求 1)。"""
    ok = True
    if STATE.exists():
        st = json.loads(STATE.read_text(encoding="utf-8"))
        print(f"[plan] 模式: {st.get('mode')} | 协议: {st.get('protocol')}")
    else:
        print("[plan] ⚠️ 模式未激活 (运行 cognify meta plan --activate)")
        ok = False
    # 检查最近心跳报告是否含计划章节
    if HEARTBEAT.exists():
        txt = HEARTBEAT.read_text(encoding="utf-8", errors="replace")
        has_plan = "下一步计划" in txt
        has_action = "具体动作" in txt
        has_dep = "依赖" in txt
        has_time = "时间估计" in txt
        print(f"[plan] 最近报告结构: 计划章节={'✅' if has_plan else '❌'} "
              f"动作={'✅' if has_action else '❌'} "
              f"依赖={'✅' if has_dep else '❌'} "
              f"时间={'✅' if has_time else '❌'}")
        if not all((has_plan, has_action, has_dep, has_time)):
            ok = False
    else:
        print("[plan] ⚠️ 无最近心跳报告")
        ok = False
    print(f"[plan] 检查结果: {'✅ 符合透明计划协议' if ok else '⚠️ 需补充计划章节'}")
    return 0 if ok else 1


def main():
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "check").lstrip("-")
    if cmd == "activate":
        activate()
        return 0
    if cmd == "check":
        return check()
    if cmd == "transparency":
        return check()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
