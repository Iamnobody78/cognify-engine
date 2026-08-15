#!/usr/bin/env python3
"""TASK-006b 预研补充: 更深边缘场景 (r=0.36/0.38/0.39) 检测稳定性验证。"""
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
    for r in [0.36, 0.38, 0.39]:
        env.robot_x, env.robot_y, env.robot_theta = r, 0.0, 0.0
        env.opponent_x, env.opponent_y = -0.30, 0.0
        obs = env._get_obs()
        tag = f"ext_d{int(r*100)}_t0"
        png = _render_frame_png(0, env, obs)
        fp = os.path.join(OUT, f"frame_{tag}.png")
        with open(fp, "wb") as fh:
            fh.write(png)
        try:
            d = insight(fp, OUT)
            m = d.get("_meta", {})
            print(f"{tag}: vis_edge_min={d.get('edge_min')} zone={d.get('zone')} "
                  f"lat={m.get('latency_s')}", flush=True)
        except Exception as e:
            print(f"{tag}: FAIL {type(e).__name__} {str(e)[:80]}", flush=True)

if __name__ == "__main__":
    main()
