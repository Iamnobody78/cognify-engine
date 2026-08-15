"""
analyze_aggressive_traj.py — Queue #4 failure-mode analysis
================================================================
Reads models/mujoco_aggressive_trajectories/ep_*.json and answers:

  1. Win/timeout/OOB breakdown (baseline = gate 40%)
  2. Which decision fired most in LOSING episodes vs WINNING ones
     (rules that lead to losses should be over-represented in losses)
  3. '?' default-action ratio (ABDL engine returned no rule → FW_SLOW)
     — big '?' share means the rule set under-covers the MuJoCo state space
  4. Action distribution in losses (e.g. too much spin / reverse?)
  5. Sensor context at the LAST frame of losses (were they near an edge?
     opponent far? mid-push?)

Usage: python3 _tmp/analyze_aggressive_traj.py [--out models/mujoco_aggressive_trajectories]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def analyze(root: Path) -> None:
    files = sorted(root.glob("ep_*.json"))
    if not files:
        print(f"no trajectory files in {root}")
        return

    wins, timeouts, oob, terminated = 0, 0, 0, 0
    win_decisions, loss_decisions = Counter(), Counter()
    win_actions, loss_actions = Counter(), Counter()
    loss_last_sensors = []
    total_frames = 0
    qmark_frames = 0
    last_frames = []

    for f in files:
        d = json.loads(f.read_text())
        won = d["won"]
        reason = d["reason"]
        steps = d["steps"]
        total_frames += steps

        tr = d["trajectory"]
        dec_counter = Counter(x["decision"] for x in tr)
        act_counter = Counter(x["action"] for x in tr)
        qmark_frames += sum(1 for x in tr if x["decision"] == "?")

        if won:
            wins += 1
            win_decisions.update(dec_counter)
            win_actions.update(act_counter)
        else:
            loss_decisions.update(dec_counter)
            loss_actions.update(act_counter)
            if "out-of-bounds" in reason or "oob" in reason or "pushed_out" in reason:
                oob += 1
            elif reason == "timeout":
                timeouts += 1
            else:
                terminated += 1
            if tr:
                last_frames.append((tr[-1], reason))

    n = len(files)
    print(f"===== aggressive trajectory analysis ({n} eps) =====")
    print(f"wins={wins} ({100*wins/n:.1f}%)  timeouts={timeouts}  "
          f"OOB={oob}  terminated-other={terminated}")
    print(f"total frames={total_frames}  '?' default-action frames="
          f"{qmark_frames} ({100*qmark_frames/max(1,total_frames):.1f}%)")

    def top(c: Counter, k: int = 8) -> str:
        return ", ".join(f"{d}:{n}" for d, n in c.most_common(k))

    print(f"\n-- decisions in WINS:   {top(win_decisions)}")
    print(f"-- decisions in LOSSES: {top(loss_decisions)}")

    # discrimination: which decisions are loss-skewed?
    loss_total = sum(loss_decisions.values())
    win_total = sum(win_decisions.values()) or 1
    print("\n-- loss-skewed decisions (fired more often in losses than wins):")
    skewed = []
    for d, cnt in loss_decisions.items():
        wshare = win_decisions.get(d, 0) / win_total
        lshare = cnt / max(1, loss_total)
        if lshare > wshare + 0.03 and lshare > 0.05:
            skewed.append((d, round(lshare, 3), round(wshare, 3), cnt))
    skewed.sort(key=lambda t: -t[3])
    for d, ls, ws, cnt in skewed[:10]:
        print(f"  {d:45s} loss_share={ls:.2f} win_share={ws:.2f} n={cnt}")

    print(f"\n-- actions in WINS:   {top(win_actions, 10)}")
    print(f"-- actions in LOSSES: {top(loss_actions, 10)}")

    print("\n-- last-frame sensor context of losses (first 12):")
    for frame, reason in last_frames[:12]:
        s = frame
        print(f"  [{reason:12s}] dist={s['opp_dist']:.2f} angle={s['opp_angle_deg']:+.0f} "
              f"action={s['action']:3d} decision={s['decision']:35s} "
              f"edges=({s['obs'][0]:.1f},{s['obs'][1]:.1f},{s['obs'][2]:.1f},{s['obs'][3]:.1f})")

    # aggregate last-frame stats
    if last_frames:
        avg_dist = sum(f[0]["opp_dist"] for f in last_frames) / len(last_frames)
        avg_angle = sum(abs(f[0]["opp_angle_deg"]) for f in last_frames) / len(last_frames)
        near_edge = sum(1 for f in last_frames if min(f[0]["obs"][:4]) < 0.15)
        print(f"\n-- loss end-state aggregate: avg_opp_dist={avg_dist:.2f} "
              f"avg|angle|={avg_angle:.1f}deg near_edge(<0.15)={near_edge}/{len(last_frames)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="models/mujoco_aggressive_trajectories")
    args = ap.parse_args()
    analyze(Path(args.out))


if __name__ == "__main__":
    main()
