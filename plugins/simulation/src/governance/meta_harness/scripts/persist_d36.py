#!/usr/bin/env python3
"""补落盘 d36 危险帧洞察 JSON (供 vision_physics_controller 收集)。"""
import json
import os

OUT = "bottlesumo_pi/docs/vision_frames/TASK006B_EDGE_20260806_211142"
record = {
    "scene": "ext_d36_t0_v2",
    "edge_min": 0.0,
    "zone": "safe",
    "_meta": {"model": "qwen2.5vl:7b", "latency_s": 97.74,
              "note": "hand-verified via edge_collect_d36.py, edge_min=0 (at edge)"},
}
fp = os.path.join(OUT, "insight_ext_d36.json")
with open(fp, "w", encoding="utf-8") as fh:
    json.dump(record, fh, ensure_ascii=False, indent=2)
print(f"written: {fp}")
