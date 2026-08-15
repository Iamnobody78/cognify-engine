#!/usr/bin/env python3
"""TASK-006b 预研补充: 单发 d36 帧采集 (内存释放后重试)。"""
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from simulation.lightweight_env import LightweightBottleSumoEnv
from governance.meta_harness.vision_probe import _render_frame_png
from governance.meta_harness.edge_frame_collect import insight

OUT = "bottlesumo_pi/docs/vision_frames/TASK006B_EDGE_20260806_211142"

def main():
    env = LightweightBottleSumoEnv()
    env.reset(seed=42)
    env.robot_x, env.robot_y, env.robot_theta = 0.36, 0.0, 0.0
    env.opponent_x, env.opponent_y = -0.30, 0.0
    obs = env._get_obs()
    png = _render_frame_png(0, env, obs)
    fp = os.path.join(OUT, "frame_ext_d36_t0_v2.png")
    with open(fp, "wb") as fh:
        fh.write(png)
    try:
        d = insight(fp, OUT)
        m = d.get("_meta", {})
        print(f"d36 v2: vis_edge_min={d.get('edge_min')} zone={d.get('zone')} "
              f"lat={m.get('latency_s')}", flush=True)
    except Exception as e:
        print(f"d36 v2: FAIL {type(e).__name__} {str(e)[:80]}", flush=True)

if __name__ == "__main__":
    main()
