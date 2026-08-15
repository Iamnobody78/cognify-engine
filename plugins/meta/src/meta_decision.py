#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
META-DECISION-ENGINE v1.0 — 元决策引擎 (M23 元决策 / M24 元风险 / M25 元学习)
=============================================================================
三层过滤: L1 规则匹配 → L2 案例检索 → L3 风险评估 → 请示
默认自主: 低/中风险且置信度≥0.70 自主执行; 高风险或无匹配 → 请示 (带方案)
学习: 每次用户纠正记录 decision_history.jsonl, audit 分析自动率

用法:
  python meta_decision.py decide "合并 PR"
  python meta_decision.py learn "合并 PR" "approved|rejected|modified"
  python meta_decision.py audit
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
try:
    import yaml
except ImportError:
    yaml = None

sys.path.insert(0, str(Path(__file__).parent))
from trisync_paths import TRI  # noqa: E402

D = TRI / "meta" / "decision"
RULES = D / "decision_rules.yaml"
HISTORY = D / "decision_history.jsonl"
LOGS = D / "decision_log.jsonl"


def load_rules():
    if not RULES.exists():
        return {"rules": [], "risk_keywords": {}}
    return yaml.safe_load(RULES.read_text(encoding="utf-8"))


def risk_of(text, keywords):
    for level, words in keywords.items():
        if any(w in text for w in words):
            return level
    return "low"


def similar(text, hist, threshold=0.4):
    """L2 案例检索: 关键词重叠相似度"""
    toks = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}", text.lower()))
    best = None
    for h in hist:
        h_toks = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{3,}",
                                h.get("decision", "").lower()))
        if not toks or not h_toks:
            continue
        sim = len(toks & h_toks) / max(1, len(toks | h_toks))
        if sim > threshold and (best is None or sim > best[0]):
            best = (sim, h)
    return best


def decide(decision_text):
    data = load_rules()
    rules = data.get("rules", [])
    kw = data.get("risk_keywords", {})
    hist = []
    if HISTORY.exists():
        hist = [json.loads(l) for l in
                HISTORY.read_text(encoding="utf-8").splitlines() if l.strip()]

    # L1: 规则匹配
    for r in rules:
        if r["pattern"] in decision_text:
            result = {"decision": decision_text[:60], "action": r["action"],
                      "reason": f"L1 规则匹配: {r['pattern']}",
                      "confidence": r["confidence"], "risk": r["risk"],
                      "conditions": r.get("conditions", r.get("reason", ""))}
            _log(result)
            return result

    # L2: 案例检索
    hit = similar(decision_text, hist)
    if hit:
        sim, h = hit
        result = {"decision": decision_text[:60], "action": "auto_reference",
                  "reason": f"L2 案例检索: 相似度 {sim:.2f} (案例: {h.get('decision', '')[:30]})",
                  "confidence": 0.75, "risk": risk_of(decision_text, kw),
                  "reference_case_id": h.get("ts", "?")}
        if result["risk"] == "high":
            result["action"] = "ask_user"
            result["reason"] += " (案例风险高 → 请示)"
        _log(result)
        return result

    # L3: 风险评估
    risk = risk_of(decision_text, kw)
    if risk == "high":
        result = {"decision": decision_text[:60], "action": "ask_user",
                  "reason": "L3 风险兜底: 命中高风险词",
                  "confidence": 0.5, "risk": "high",
                  "suggestion": "提供上下文摘要+推荐方案后等待确认"}
    else:
        result = {"decision": decision_text[:60], "action": "auto_low_risk",
                  "reason": "L3 风险兜底: 低风险且无匹配规则, 默认自主",
                  "confidence": 0.70, "risk": "low"}
    _log(result)
    return result


def _log(result):
    LOGS.parent.mkdir(parents=True, exist_ok=True)
    with open(LOGS, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"),
                            **result}, ensure_ascii=False) + "\n")


def learn(decision_text, outcome):
    """M25: 用户纠正学习"""
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": datetime.now().isoformat(timespec="seconds"),
                            "decision": decision_text, "outcome": outcome,
                            "note": "用户纠正"}, ensure_ascii=False) + "\n")
    print(f"[learn] 已记录纠正: {decision_text[:40]} → {outcome}")
    return 0


def audit():
    """周学习分析: 自动率/请示率 + 新规则建议"""
    logs = []
    if LOGS.exists():
        logs = [json.loads(l) for l in
                LOGS.read_text(encoding="utf-8").splitlines() if l.strip()]
    hist = []
    if HISTORY.exists():
        hist = [json.loads(l) for l in
                HISTORY.read_text(encoding="utf-8").splitlines() if l.strip()]
    auto = sum(1 for l in logs if "auto" in l.get("action", ""))
    ask = sum(1 for l in logs if l.get("action") == "ask_user")
    rate = auto / len(logs) if logs else 0
    print(f"[audit] 决策记录 {len(logs)}: 自主 {auto} / 请示 {ask} | 自主率 {rate:.0%}")
    print(f"[audit] 用户纠正 {len(hist)} 条 (学习样本)")
    if logs:
        asks = [l for l in logs if l.get("action") == "ask_user"]
        if asks:
            print("[audit] 高频请示项 (建议新增规则):")
            from collections import Counter
            for d, c in Counter(a["decision"][:20] for a in asks).most_common(5):
                print(f"  {c}x {d}")
    return 0


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "audit"
    if cmd == "decide":
        text = " ".join(sys.argv[2:]) or "运行认证检查"
        r = decide(text)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if "auto" in r.get("action", "") else 2
    if cmd == "learn":
        return learn(" ".join(sys.argv[2:-1]), sys.argv[-1] if len(sys.argv) > 2 else "approved")
    if cmd == "audit":
        return audit()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
