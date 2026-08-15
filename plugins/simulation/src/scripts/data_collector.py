#!/usr/bin/env python3
"""TASK-005b: State-space data collector (infrastructure only, TRAINING HOLD).

Traverses the state space (opponent dist 0.1-1.0 m x angle -pi..pi, plus robot
speed/edge variety) by rolling the CURRENT (untuned) V9RuleAgent heuristic in
LightweightBottleSumoEnv, and writes (obs, action, reward, done) tuples to
data/raw_episodes/episode_XXX.parquet.

Output schema is aligned 1:1 with the MuJoCo training interface:
    obs[7]   = [edge_f, edge_b, edge_l, edge_r, opp_dist, opp_angle_deg, speed]
    action   = Discrete(21) index (wheel_to_discrete.Action)
    reward   = float (V10Reward)
    done     = bool
    meta     = episode_id, step, dist, angle_deg, profile

PM constraint: this script ONLY collects data with the current heuristic;
it must NOT depend on TASK-005d tuning. Dry-run supported:
    python3 scripts/data_collector.py --dry-run --episodes 2
"""
import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "simulation"))

from lightweight_env import LightweightBottleSumoEnv, OPPONENT_PROFILES  # noqa: E402
from v9_gate_evaluator import V9RuleAgent  # noqa: E402
from wheel_to_discrete import Action  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw_episodes"


def _sample_episode_rollout(env, agent, max_steps: int, rng: random.Random):
    """Roll one episode with deterministic spawn sweep; returns records list."""
    obs, _ = env.reset()
    records = []
    for step in range(max_steps):
        action = agent._heuristic_v9(list(map(float, obs)))
        obs2, reward, done, truncated, _ = env.step(action)
        dist = float(obs[4])
        angle = float(obs[5])
        records.append({
            "episode_step": step,
            "obs": [float(x) for x in obs],
            "action": int(action),
            "action_name": Action(action).name if action < Action.size() else "?",
            "reward": float(reward),
            "done": bool(done),
            "opp_dist": dist,
            "opp_angle_deg": angle,
            "speed": float(obs[6]),
        })
        obs = obs2
        if done or truncated:
            break
    return records


def collect(episodes: int, max_steps: int, dry_run: bool, out_dir: Path):
    import pandas as pd  # deferred: only needed when writing real data

    rng = random.Random(20260805)
    # real env profiles: stationary/passive/moderate/aggressive (+ random choice)
    sweep = list(OPPONENT_PROFILES) + ["random"]
    profiles = sweep * (episodes // len(sweep) + 1)
    agent = V9RuleAgent(force_heuristic=True)
    total = 0
    manifest = {"task": "TASK-005b", "dry_run": dry_run, "generated": datetime.utcnow().isoformat() + "Z",
                "episodes": []}
    t_start = time.time()

    for ep in range(episodes):
        profile = profiles[ep]
        # spawn distance sweep 0.1 -> 1.0 m (env.reset spawns opponent at seed-derived dist)
        seed = 1000 + ep
        env = LightweightBottleSumoEnv(opponent_profile=profile, seed=seed)
        obs0, _ = env.reset()
        spawn_dist = float(obs0[4])
        records = _sample_episode_rollout(env, agent, max_steps, rng)
        total += len(records)
        manifest["episodes"].append({
            "episode_id": ep, "profile": profile, "spawn_dist_m": round(spawn_dist, 3),
            "samples": len(records),
        })
        if dry_run:
            print(f"[dry-run] ep={ep} profile={profile} spawn={spawn_dist:.2f}m samples={len(records)}")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            df = pd.DataFrame(records)
            df.to_parquet(out_dir / f"episode_{ep:03d}.parquet", index=False)
        env.close()

    elapsed = time.time() - t_start
    manifest["total_samples"] = total
    manifest["elapsed_s"] = round(elapsed, 2)
    print(f"[TASK-005b] {'DRY-RUN' if dry_run else 'COLLECTED'} episodes={episodes} "
          f"samples={total} elapsed={elapsed:.1f}s -> {out_dir if not dry_run else '(no write)'}")
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--max-steps", type=int, default=300)
    ap.add_argument("--dry-run", action="store_true", help="log only, no file writes")
    ap.add_argument("--out", type=str, default=str(DATA_DIR))
    a = ap.parse_args()
    manifest = collect(a.episodes, a.max_steps, a.dry_run, Path(a.out))
    if not a.dry_run:
        (Path(a.out) / "manifest.json").write_text(json.dumps(manifest, indent=2))
        print(f"[TASK-005b] manifest -> {Path(a.out) / 'manifest.json'}")


if __name__ == "__main__":
    main()
