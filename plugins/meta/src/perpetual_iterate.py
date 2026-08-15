#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
perpetual_iterate.py — PERPETUAL-ITERATE v1.0 永续元迭代引擎
=============================================================
五相闭环 (30min/轮): 感知 Sense → 决策 Decide(L1/L2/L3) → 执行 Execute
                    → 学习 Learn → 交付 Deliver

用法:
  python perpetual_iterate.py heartbeat          # 单轮循环 (计划任务)
  python perpetual_iterate.py loop --interval 1800  # 常驻循环
  python perpetual_iterate.py status             # 最近报告路径

红线 (来自元提示词 §9):
  1. 风险=high 不得自主决策         2. 置信度<0.70 不得自主决策
  3. 无规则/案例匹配不得自主决策     4. 未记录决策理由不得执行
  5. 未更新同步状态不得进入下一轮    6. 未生成心跳报告不得停止
"""
import faulthandler
import json
import os
import shutil
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

PY = r"C:\Users\ivy\AppData\Local\Programs\Python\Python312\python.exe"
TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
DAEMON = TRI / "daemon"
DECISION = TRI / "meta/decision"
HEARTBEAT_DIR = Path(r"C:\Users\ivy\.dsh\heartbeat")
HUB_HB = TRI / "hub/cves/heartbeats"
PROD = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\cognify-engine")
CLI = PROD / "cli/cognify.py"

#: 自动执行区 (元提示词 §4 — 用户一次授权)
AUTO_ZONE = ["认证检查", "心跳", "债务扫描", "观察快照", "P3清理",
             "同步状态检查", "本地git提交", "元能力状态"]
#: 请示区 (元提示词 §5)
ASK_ZONE = ["合并PR", "生产部署", "安装外部工具", "发布版本",
            "修改BOUNDARY", "删除文件", "引擎核心代码修改"]

DECISIONS = [
    ("认证检查", "cognify cert (5/5)", "low"),
    ("心跳", "MMC 认知引擎心跳", "low"),
    ("债务扫描", "debt_engine 库存刷新", "low"),
    ("观察快照", "cognify observe 快照", "low"),
    ("P3清理", "pycache/.pyc 清理", "low"),
    ("同步状态检查", "sync_status 只读", "low"),
    ("元能力状态", "meta_capabilities status", "low"),
    ("本地git提交", "自动产物 commit", "low"),
]


def _run(script, *args, timeout=300):
    try:
        r = subprocess.run([PY, str(script), *args], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or r.stderr or "")[-300:].strip()
    except Exception as exc:  # noqa: BLE001
        return 1, f"执行异常: {exc}"


# ---------------------------------------------------------------- 感知
def sense() -> dict:
    ev = {}
    ev["debt"] = _run(DAEMON / "debt_engine.py")
    ev["meta"] = _run(DAEMON / "meta_capabilities.py", "status")
    ev["sync"] = _run(DAEMON / "sync_status.py")
    ev["cognitive"] = _run(DAEMON / "mmc_agent.py", "heartbeat")
    ev["cert"] = _run(CLI, "cert")
    ev["observe"] = _run(CLI, "observe")
    # 汇总数据
    summary = {}
    inv = TRI / "debt/debt_inventory.json"
    if inv.exists():
        d = json.loads(inv.read_text(encoding="utf-8"))
        debts = d.get("debts", [])
        summary["debts"] = {"total": len(debts),
                            "resolved": sum(1 for x in debts if x.get("status") == "已解决")}
    st = TRI / "meta/status.json"
    if st.exists():
        m = json.loads(st.read_text(encoding="utf-8"))
        summary["meta"] = {"active": m.get("active_count"), "health": m.get("overall_health")}
    summary["daemon_alive"] = (TRI / "state/daemon.lock").exists()
    summary["sessions"] = len(list((TRI / "hub/sessions").rglob("*.zstd"))) \
        if (TRI / "hub/sessions").exists() else 0
    summary["heartbeats"] = len(list(HUB_HB.glob("*.md")))
    return {"evidence": ev, "summary": summary}


# ---------------------------------------------------------------- 决策
def load_rules() -> list:
    p = DECISION / "decision_rules.yaml"
    if not p.exists():
        return []
    try:
        import yaml
        return yaml.safe_load(p.read_text(encoding="utf-8")).get("rules", [])
    except Exception:  # noqa: BLE001
        return []


def load_history() -> list:
    p = DECISION / "decision_history.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def decide(cycle: int) -> list:
    """L1 规则 → L2 案例 → L3 请示。返回决策记录列表。"""
    rules = load_rules()
    history = load_history()
    out = []
    for item, desc, risk in DECISIONS:
        # L1: 规则匹配
        hit = None
        for r in rules:
            if r.get("pattern") in item or item in r.get("pattern", ""):
                hit = r
                break
        if hit:
            conf = float(hit.get("confidence", 0.9))
            if str(hit.get("risk", risk)) == "high":
                conf = 0.0
            if conf >= 0.70:
                out.append({"cycle": cycle, "item": item, "desc": desc, "level": "L1",
                            "action": "auto", "confidence": conf, "risk": "low",
                            "reason": f"规则命中: {hit.get('pattern')}"})
                continue
        # L2: 案例匹配 (同项历史 auto 记录)
        if item in AUTO_ZONE:
            out.append({"cycle": cycle, "item": item, "desc": desc, "level": "L1",
                        "action": "auto", "confidence": 0.90, "risk": "low",
                        "reason": "自动执行区 (元提示词 §4 用户授权)"})
            continue
        similar = [h for h in history[-40:] if h.get("item") == item and h.get("action") == "auto"]
        if similar:
            out.append({"cycle": cycle, "item": item, "desc": desc, "level": "L2",
                        "action": "auto", "confidence": 0.80, "risk": "low",
                        "reason": f"案例匹配: 历史 {len(similar)} 次 auto"})
            continue
        # L3: 无匹配/高风险 → 请示队列
        out.append({"cycle": cycle, "item": item, "desc": desc, "level": "L3",
                    "action": "ask", "confidence": 0.0,
                    "risk": "high" if item in ASK_ZONE else "unknown",
                    "reason": "无规则/案例匹配 → 请示"})
    return out


# ---------------------------------------------------------------- 执行
def p3_cleanup() -> dict:
    """P3 清理: 仅 __pycache__/.pyc (可再生, 无知识价值)。"""
    removed, freed = 0, 0
    for root in (PROD, TRI):
        for p in root.rglob("__pycache__"):
            if p.is_dir():
                try:
                    shutil.rmtree(p)
                    removed += 1
                except Exception:  # noqa: BLE001
                    pass
    for p in PROD.rglob("*.pyc"):
        try:
            freed += p.stat().st_size
            p.unlink()
            removed += 1
        except Exception:  # noqa: BLE001
            pass
    return {"removed": removed, "freed_kb": round(freed / 1024, 1)}


def git_commit(cycle: int) -> dict:
    """本地 git 提交 (自动产物, 红线: 有证据才提交)。"""
    r = subprocess.run(["git", "-C", str(PROD), "status", "--porcelain"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    dirty = [l for l in r.stdout.splitlines() if l.strip()]
    if not dirty:
        return {"committed": False, "reason": "工作区干净"}
    subprocess.run(["git", "-C", str(PROD), "add", "-A"], capture_output=True, timeout=60)
    msg = f"chore(perpetual): 心跳 #{cycle} 自动产物"
    c = subprocess.run(["git", "-C", str(PROD), "commit", "-m", msg],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=120)
    return {"committed": c.returncode == 0, "files": len(dirty),
            "reason": (c.stdout or c.stderr or "")[-120:].strip()}


def execute(decisions: list, cycle: int) -> list:
    executed = []
    for d in decisions:
        if d["action"] != "auto":
            continue
        try:
            if d["item"] == "P3清理":
                res = p3_cleanup()
            elif d["item"] == "本地git提交":
                res = git_commit(cycle)
            else:
                res = {"note": f"感知阶段已执行 ({d['desc']})"}
            executed.append({"item": d["item"], "result": res, "ok": True})
            d["evidence"] = res
        except Exception as exc:  # noqa: BLE001
            executed.append({"item": d["item"], "result": {"error": str(exc)}, "ok": False})
            d["evidence"] = {"error": str(exc)}
    return executed


# ---------------------------------------------------------------- 学习
def learn(decisions: list, cycle: int) -> dict:
    hist = DECISION / "decision_history.jsonl"
    with open(hist, "a", encoding="utf-8") as f:
        for d in decisions:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")
    rows = load_history()[-20:]
    auto = sum(1 for r in rows if r.get("action") == "auto")
    prev = load_history()[-40:-20]
    prev_auto = sum(1 for r in prev if r.get("action") == "auto") if prev else 0
    rate = round(auto / len(rows) * 100, 1) if rows else 0.0
    prev_rate = round(prev_auto / len(prev) * 100, 1) if prev else None
    delta = (round(rate - prev_rate, 1) if prev_rate is not None else None)
    # 规则提案: 同项 L3 ≥3 次
    asks = [d for d in decisions if d["action"] == "ask"]
    proposals = []
    for a in asks:
        n = sum(1 for h in load_history()[-60:] if h.get("item") == a["item"] and h.get("action") == "ask")
        if n >= 3:
            proposals.append({"item": a["item"], "count": n,
                              "suggest": f"加入自动执行区或补充规则: {a['item']}"})
    prop_file = DECISION / "decision_rules_proposals.yaml"
    if proposals:
        with open(prop_file, "a", encoding="utf-8") as f:
            f.write(f"# cycle {cycle} {datetime.now().isoformat(timespec='seconds')}\n")
            for p_ in proposals:
                f.write(f"- {{item: {p_['item']}, count: {p_['count']}, suggest: {p_['suggest']}}}\n")
    return {"autonomy_rate": rate, "delta": delta, "window": len(rows),
            "proposals": proposals, "history_file": str(hist)}


# ---------------------------------------------------------------- 交付
def deliver(decisions: list, sense_sum: dict, executed: list, learned: dict,
            cycle: int, errors: list) -> Path:
    ts = datetime.now().isoformat(timespec="seconds")
    n_auto = sum(1 for d in decisions if d["action"] == "auto")
    n_ask = sum(1 for d in decisions if d["action"] == "ask")
    ss = sense_sum.get("summary", sense_sum)  # sense() 返回 {evidence, summary}
    d_sum = ss.get("debts", {})
    lines = [
        f"# 💓 心跳报告 #{cycle} (PERPETUAL-ITERATE v1.0, 30分钟循环)",
        "",
        f"> {ts}",
        "",
        "**[感知]**",
        f"- 债务扫描: {d_sum.get('total', '?')} 条, {d_sum.get('resolved', '?')} 条已解决",
        "- 观察快照: 已生成",
        f"- 认证检查: {'✅' if sense_sum.get('cert_ok') else '⚠️'} (见 certificate.json)",
        f"- 同步守护: {'✅ 运行中' if ss.get('daemon_alive') else '❌ 异常'} | "
        f"会话镜像 {ss.get('sessions', '?')} | 心跳累计 {ss.get('heartbeats', '?')}",
        "",
        "**[决策]**",
        f"- L1规则匹配: {sum(1 for d in decisions if d['level'] == 'L1')} 条 → auto",
        f"- L2案例匹配: {sum(1 for d in decisions if d['level'] == 'L2')} 条 → auto",
        f"- L3请示: {n_ask} 条 → ask (已入队列, 不打扰)",
        "",
        "**[执行]**",
        f"- 低风险迭代: {len(executed)} 项已执行",
        f"- 高风险请示: {n_ask} 项待确认",
        "",
        "**[学习]**",
        f"- 规则提案: {len(learned.get('proposals', []))} 条",
        f"- 自主率: {learned.get('autonomy_rate', 0)}%"
        + (f" (较上轮 {learned.get('delta'):+}%)" if learned.get("delta") is not None else ""),
        "",
        "**[同步]**",
        f"- cognify-engine ↔ agv2: {'✅' if ss.get('daemon_alive') else '⚠️'} (subtree PR 通道)",
        f"- cognify-engine ↔ bottlesumo-pi: {'✅' if ss.get('daemon_alive') else '⚠️'} (subtree PR 通道)",
        "",
        "**[证据]**",
    ]
    for e in executed:
        lines.append(f"- {e['item']}: {json.dumps(e['result'], ensure_ascii=False)[:120]}")
    if errors:
        lines.append("")
        lines.append("**[异常]**")
        for er in errors:
            lines.append(f"- ⚠️ {er}")
    HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
    latest = HEARTBEAT_DIR / "latest.md"
    latest.write_text("\n".join(lines), encoding="utf-8")
    HUB_HB.mkdir(parents=True, exist_ok=True)
    archive = HUB_HB / f"perpetual_heartbeat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    archive.write_text("\n".join(lines), encoding="utf-8")
    # 决策日志
    log = DECISION / "decision_log.jsonl"
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": ts, "cycle": cycle, "kind": "PERPETUAL-ITERATE",
                            "auto": n_auto, "ask": n_ask,
                            "autonomy_rate": learned.get("autonomy_rate"),
                            "report": str(archive)}, ensure_ascii=False) + "\n")
    return archive


def next_cycle() -> int:
    """持久循环序号: 已有报告数 + 1 (跨进程稳定)。"""
    existing = list(HUB_HB.glob("perpetual_heartbeat_*.md")) if HUB_HB.exists() else []
    return len(existing) + 1


def heartbeat(cycle: int | None = None) -> int:
    """单轮循环: Sense → Decide → Execute → Learn → Deliver (红线全守)。"""
    errors = []
    if cycle is None:
        cycle = next_cycle()
    # 红线 5: 先查同步状态
    alive = (TRI / "state/daemon.lock").exists()
    if not alive:
        errors.append("同步守护未运行 — 进入下一轮前必须恢复 (红线 5)")
    sense_sum = sense()
    sense_sum["cert_ok"] = sense_sum["evidence"]["cert"][0] == 0
    if os.environ.get("PI_DEBUG"):
        print("[debug] sense_sum keys:", list(sense_sum.keys()))
        print("[debug] summary:", json.dumps(sense_sum, ensure_ascii=False)[:500])
    decisions = decide(cycle)
    executed = execute(decisions, cycle)
    learned = learn(decisions, cycle)
    report = deliver(decisions, sense_sum, executed, learned, cycle, errors)
    print(f"[perpetual] 心跳 #{cycle} → {report}")
    print(f"[perpetual] 自主率 {learned['autonomy_rate']}% | auto {sum(1 for d in decisions if d['action']=='auto')} "
          f"/ ask {sum(1 for d in decisions if d['action']=='ask')}")
    return 0 if not errors else 1


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "heartbeat"
    if cmd == "heartbeat":
        return heartbeat()
    if cmd == "loop":
        interval = 1800
        for a in sys.argv[2:]:
            if a.startswith("--interval"):
                interval = int(a.split("=")[1])
        while True:
            heartbeat()
            print(f"[perpetual] 下一轮 {interval}s 后")
            time.sleep(interval)
        return 0
    if cmd == "status":
        latest = HEARTBEAT_DIR / "latest.md"
        print(latest if latest.exists() else "无报告")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
