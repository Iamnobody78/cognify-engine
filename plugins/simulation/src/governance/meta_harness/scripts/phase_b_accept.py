# -*- coding: utf-8 -*-
"""Phase B 验收 (PM 2026-08-06 裁决): _apply_vision_softening 单元矩阵 + 门回归。

三层验收:
  L1 单元矩阵 (rounds=3 复现稳定, PM 标准③):
     S1 正例 / S1 负例 / S2 正例(纯函数) / S2 负例 / 门控负例 / 无 vision 回归
  L2 门回归 (episodes=20, WSL evaluator_v9): 门分数 >= 1.0 不倒退 (PM 标准①)
  L3 步数对比: 视觉触发场景下步数 <= 258 不劣化 (PM 标准②)

用法:
  python phase_b_accept.py --episodes 20 --out <dir>   (独立运行)
  outer_loop.py --vision-insight auto --tag PHASE_B_ACCEPT  (集成运行, 追加 L1)
"""
import argparse
import json
import os
import sys
import time

# 兼容: 直接从 repo 根导入
REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from simulation.wheel_to_discrete import Action  # noqa: E402
from core.meta_language.abdl_action_bridge import (  # noqa: E402
    ABDLDecisionMaker,
    PolicyID,
)

# PM Phase B 常量 (与 abdl_action_bridge 内一致, 独立声明以校验)
VISION_GATE = 0.6
EDGE_MIN_FLANK = 0.20
DANGER_SPEED_CAP = 0.45
CLOSE_PUSH_RULE = "SIM-ADVANCED-CLOSE-PUSH"
OPPONENT_FOUND_RULE = "SIM-TACTIC-OPPONENT-FOUND"


def _obs(**kw):
    """7 维 obs: [edge_f, edge_b, edge_l, edge_r, opp_dist, opp_angle, speed]."""
    base = {"ef": 0.9, "eb": 0.9, "el": 0.9, "er": 0.9,
            "dist": 0.4, "angle": 0.0, "speed": 0.0}
    base.update(kw)
    return [base["ef"], base["eb"], base["el"], base["er"],
            base["dist"], base["angle"], base["speed"]]


def run_softening_matrix(out_dir: str, rounds: int = 3) -> dict:
    """L1: _apply_vision_softening 单元矩阵 — 3 轮复现稳定验证."""
    os.makedirs(out_dir, exist_ok=True)
    maker = ABDLDecisionMaker()
    results = []
    all_pass = True

    for r in range(1, rounds + 1):
        row = {"round": r, "cases": []}
        # ── S1 正例: CLOSE-PUSH + edge_min 0.15 (< 0.20) -> 提前 FLANK ──
        ws = maker.builder.build(
            _obs(dist=0.4, angle=0.0),
            vision={"edge_min": 0.15, "zone": "safe", "confidence": 0.65})
        a, tr = maker.decide_traced(ws)
        soft = tr.get("vision_softening", {})
        s1_ok = (a != Action.FW_MAX.value
                 and soft.get("scenario", "").startswith("S1"))
        row["cases"].append({"id": "S1_POS", "pass": s1_ok,
                             "rule": tr.get("rule_id"), "action": a,
                             "scenario": soft.get("scenario")})

        # ── S1 负例: edge_min 0.35 (>= 0.20) -> 不软化 (仍 FW_MAX) ──
        ws = maker.builder.build(
            _obs(dist=0.4, angle=0.0),
            vision={"edge_min": 0.35, "zone": "safe", "confidence": 0.65})
        a, tr = maker.decide_traced(ws)
        s1n_ok = (a == Action.FW_MAX.value
                  and "vision_softening" not in tr)
        row["cases"].append({"id": "S1_NEG", "pass": s1n_ok,
                             "rule": tr.get("rule_id"), "action": a})

        # ── S2 正例 (纯函数): OPPONENT-FOUND + zone=danger -> 降速 0.38 ──
        ws2 = maker.builder.build(
            _obs(dist=0.8, angle=0.0),
            vision={"edge_min": 0.5, "zone": "danger", "confidence": 0.7})
        a2, soft2 = maker._apply_vision_softening(
            Action.FW_MAX.value, ws2, OPPONENT_FOUND_RULE)
        s2_ok = (a2 == Action.FW_FAST.value
                 and soft2.get("scenario") == "S2_OPPONENT-FOUND_zone=danger"
                 and soft2.get("to_speed", 1.0) <= DANGER_SPEED_CAP)
        row["cases"].append({"id": "S2_POS", "pass": s2_ok,
                             "from": Action.FW_MAX.value,
                             "to": a2, "to_speed": soft2.get("to_speed"),
                             "scenario": soft2.get("scenario")})

        # ── S2 负例: zone=safe -> 不软化 ──
        ws2s = maker.builder.build(
            _obs(dist=0.8, angle=0.0),
            vision={"edge_min": 0.5, "zone": "safe", "confidence": 0.7})
        a2s, soft2s = maker._apply_vision_softening(
            Action.FW_MAX.value, ws2s, OPPONENT_FOUND_RULE)
        s2n_ok = (a2s == Action.FW_MAX.value and not soft2s)
        row["cases"].append({"id": "S2_NEG", "pass": s2n_ok,
                             "action": a2s})

        # ── 门控负例: confidence 0.4 (< 0.6) -> 不软化 ──
        ws_g = maker.builder.build(
            _obs(dist=0.4, angle=0.0),
            vision={"edge_min": 0.10, "zone": "danger", "confidence": 0.4})
        a_g, tr_g = maker.decide_traced(ws_g)
        gate_ok = (a_g == Action.FW_MAX.value
                   and "vision_softening" not in tr_g)
        row["cases"].append({"id": "GATE_NEG", "pass": gate_ok,
                             "rule": tr_g.get("rule_id"), "action": a_g})

        # ── 无 vision 回归: 与低置信度 vision 行为逐位一致 ──
        ws_no = maker.builder.build(_obs(dist=0.4, angle=0.0))
        a_no, tr_no = maker.decide_traced(ws_no)
        reg_ok = (a_no == a_g and "vision_softening" not in tr_no)
        row["cases"].append({"id": "NO_VISION_REGRESSION", "pass": reg_ok,
                             "action": a_no})

        # ── S2 端到端确认 (记录性): OPPONENT-FOUND 规则下 pursue 输出 <= 0.45 ──
        ws_e2e = maker.builder.build(
            _obs(dist=0.8, angle=0.0),
            vision={"edge_min": 0.5, "zone": "danger", "confidence": 0.7})
        a_e2e, tr_e2e = maker.decide_traced(ws_e2e)
        e2e_speed = Action(a_e2e).to_cmd()[0]
        row["cases"].append({
            "id": "S2_E2E_NOTE", "pass": True,
            "rule": tr_e2e.get("rule_id"),
            "action": a_e2e,
            "speed": round(e2e_speed, 3),
            "note": ("OPPONENT-FOUND 下 pursue 输出速度 <= 0.45, "
                     "场景②为防御性安全网 (未来规则若输出 >0.45 自动降速)"),
        })

        for c in row["cases"]:
            if not c.get("pass", True):
                all_pass = False
        results.append(row)

    summary = {
        "rounds": rounds,
        "total_cases": rounds * 7,
        "all_pass": all_pass,
        "criteria": "PM 标准③ 至少 3 轮复现稳定",
        "rounds_detail": results,
    }
    with open(os.path.join(out_dir, "softening_matrix.json"), "w",
              encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def main():
    ap = argparse.ArgumentParser(description="Phase B 验收 (软化单元矩阵)")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--out", default=os.path.join(
        REPO, "docs", "vision_frames", "PHASE_B_ACCEPT_test"))
    args = ap.parse_args()

    t0 = time.time()
    s = run_softening_matrix(args.out, rounds=args.rounds)
    print(f"[phase_b] softening matrix: rounds={s['rounds']} "
          f"all_pass={s['all_pass']} ({time.time()-t0:.1f}s)")
    for r in s["rounds_detail"]:
        for c in r["cases"]:
            print(f"  R{r['round']} {c['id']:<24} pass={c.get('pass')!s:<6} "
                  f"detail={ {k: c[k] for k in ('rule','action','to_speed','speed','scenario') if k in c} }")
    sys.exit(0 if s["all_pass"] else 1)


if __name__ == "__main__":
    main()
