#!/usr/bin/env python3
"""TASK-006b 预研: 边缘危险帧采集 + 7b 检测验证 (PM 2026-08-06 裁决 2).

构造 lightweight_env 中机器人贴近环边的 pose (r=0.34~0.39, 朝向环边),
渲染合成相机帧 (复用 vision_probe._render_frame_png), POST /insight (7b),
验证视觉能否稳定检测 edge_min < 0.20 (危险)。

用法:
  python bottlesumo_pi/governance/meta_harness/edge_frame_collect.py --out-dir docs/vision_frames/TASK006B_EDGE_<ts>
"""
import argparse
import base64
import glob
import json
import math
import os
import sys
import time
import urllib.request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, REPO_ROOT)

from simulation.lightweight_env import LightweightBottleSumoEnv
from governance.meta_harness.vision_probe import _render_frame_png  # 复用合成帧渲染

# TASK-006b 预研: 直连 ollama 原生 API (绕开 vision_proxy 的 fallback 链 —
# 2026-08-06 实测 proxy 链路在 7b 冷加载期会拉 3b 竞争 + 客户端超时后服务端队列堆积,
# 原生直连单模型串行最稳定; 7b 热推理实测 50-125s).
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = "qwen2.5vl:7b"
# 预算必须 > 服务端耗时 (实测负载下 124.7s), 否则客户端超时后服务端遗留请求阻塞后续调用.
TIMEOUT_S = 240
KEEP_ALIVE_S = 1800  # 30m: 串行流程间保持驻留, 避免重复冷加载


def insight(frame_path: str, out_dir: str) -> dict:
    """原生 ollama 直连 (7b, 单模型串行, 无 proxy fallback 链)。

    预算 240s > 服务端实测 124.7s, 保证串行流程无遗留请求堆积。
    """
    with open(frame_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("utf-8")
    payload = {"model": OLLAMA_MODEL,
               "prompt": ("Analyze this bottle sumo arena frame. Respond in JSON: "
                          "{\"edge_min\": <0..1 distance to nearest edge, "
                          "0=at edge 1=center>, \"zone\": <safe|edge|danger>}"),
               "images": [b64], "stream": False, "keep_alive": KEEP_ALIVE_S}
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    text = raw.get("response", "")
    # 从模型响应提取 JSON 字段 (模型可能附加解释文本)
    import re
    m = re.search(r"\{.*\}", text, re.S)
    parsed = json.loads(m.group(0)) if m else {}
    parsed["_meta"] = {"model": OLLAMA_MODEL,
                       "latency_s": round(time.time() - t0, 2),
                       "raw": text[:200]}
    return parsed

# 贴边场景: (r, label) — 机器人中心到环心距离
EDGE_SCENES = [
    (0.34, "d34_near"),     # 边缘区外沿 (安全区边)
    (0.36, "d36_edge"),     # 边缘区
    (0.38, "d38_edge"),     # 深边缘区
    (0.385, "d385_crit"),   # 临界
    (0.39, "d39_crit"),     # 临界
]
# 朝环边方向 (指向最近边缘), 让传感器看到危险
THETA_CASES = [0.0, math.pi / 2]  # 0 = 朝 +x 环边; pi/2 = 朝 +y 环边


def insight(frame_path: str, out_dir: str) -> dict:
    """原生 ollama 直连 (7b, 单模型串行, 无 proxy fallback 链)。

    关键: 请求前等待 ollama 空闲, 避免客户端超时后遗留请求阻塞队列。
    """
    with open(frame_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("utf-8")
    payload = {"model": OLLAMA_MODEL,
               "prompt": ("Analyze this bottle sumo arena frame. Respond in JSON: "
                          "{\"edge_min\": <0..1 distance to nearest edge, "
                          "0=at edge 1=center>, \"zone\": <safe|edge|danger>}"),
               "images": [b64], "stream": False}
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate",
                                 data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    text = raw.get("response", "")
    # 从模型响应提取 JSON 字段 (模型可能附加解释文本)
    import re
    m = re.search(r"\{.*\}", text, re.S)
    parsed = json.loads(m.group(0)) if m else {}
    parsed["_meta"] = {"model": OLLAMA_MODEL,
                       "latency_s": round(time.time() - t0, 2),
                       "raw": text[:200]}
    return parsed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--limit", type=int, default=0,
                    help="最多跑多少个 (scene, theta) 组合的 7b 洞察 (0=全部)")
    args = ap.parse_args()
    out_dir = args.out_dir or os.path.join(REPO_ROOT, "docs", "vision_frames",
                                           f"TASK006B_EDGE_{time.strftime('%Y%m%d_%H%M%S')}")
    os.makedirs(out_dir, exist_ok=True)
    print(f"[edge_collect] out_dir={out_dir}", flush=True)

    env = LightweightBottleSumoEnv()
    env.reset(seed=42)  # 确定对手 profile/初始 pose

    rows = []
    rendered = 0
    for r, label in EDGE_SCENES:
        for theta in THETA_CASES:
            if args.limit and rendered >= args.limit:
                break
            rendered += 1
            # 直接置位机器人 pose (预研用, 非正式闭环)
            env.robot_x = r
            env.robot_y = 0.0
            env.robot_theta = theta
            env.robot_speed = 0.0
            # 对手放到远处, 避免干扰视觉判断 (目标: 纯边缘危险检测)
            env.opponent_x = -0.30
            env.opponent_y = 0.0
            env.opponent_theta = math.pi
            env.opponent_speed = 0.0
            obs = env._get_obs()
            tag = f"{label}_t{int(math.degrees(theta))}"
            png = _render_frame_png(0, env, obs)
            fp = os.path.join(out_dir, f"frame_{tag}.png")
            with open(fp, "wb") as fh:
                fh.write(png)
            print(f"[edge_collect] rendered {tag}  env_edge_min={obs[0:4].min():.3f} "
                  f"r={env.robot_x:.3f}", flush=True)
            # 7b 洞察
            try:
                d = insight(fp, out_dir)
                m = d.get("_meta", {})
                rows.append({
                    "scene": tag, "env_edge_min": round(float(obs[0:4].min()), 3),
                    "vis_edge_min": d.get("edge_min"), "zone": d.get("zone"),
                    "confidence": d.get("confidence"), "model": m.get("model"),
                    "latency_s": m.get("latency_s"),
                    "fallback": m.get("fallback_triggered", False),
                })
                print(f"  -> vis_edge_min={d.get('edge_min')} zone={d.get('zone')} "
                      f"conf={d.get('confidence')} model={m.get('model')}", flush=True)
            except Exception as e:
                rows.append({"scene": tag, "error": str(e)[:120]})
                print(f"  -> insight FAIL: {e}", flush=True)

    summary = {"scenes": rows,
               "danger_detected": [r for r in rows
                                   if r.get("vis_edge_min") is not None
                                   and r["vis_edge_min"] < 0.20]}
    with open(os.path.join(out_dir, "edge_collect_summary.json"), "w",
              encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(f"[edge_collect] 危险帧 (vis_edge_min<0.20): {len(summary['danger_detected'])} "
          f"/ {len(rows)}", flush=True)
    for r in summary["danger_detected"]:
        print(f"  DANGER: {r['scene']} vis_edge_min={r['vis_edge_min']} "
              f"zone={r['zone']}", flush=True)
    return 0 if len(summary["danger_detected"]) >= 3 else 1


if __name__ == "__main__":
    sys.exit(main())
