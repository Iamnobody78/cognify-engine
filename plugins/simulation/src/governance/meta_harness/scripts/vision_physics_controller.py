#!/usr/bin/env python3
"""TASK-006b 视觉->物理实时闭环控制器 (PM 2026-08-06 裁决 2 批准立项).

PM 映射公式 (强约束):
  * 若帧洞察 safe (edge_min >= 0.20): 不触发任何调整, 维持 decay=0.06 (当前最优)
  * 若 edge_min < 0.20 (危险): decay = 0.06 + 0.02 * (0.20 - edge_min) / 0.20
    线性插值, 范围 [0.06, 0.10]; 若 edge_min < 0.05 封顶 0.10 (防止过激调整)

闭环: 视觉洞察 (edge_min) -> 实时 decay 计算 -> BOTTLE_GRIP_DECAY 环境变量注入
      -> 门回归验证 (score >= 1.0 且 steps <= 419).

验收标准 (PM 裁决 2):
  ① 至少 3 个危险帧场景, 触发实时注入
  ② 注入后门分数 >= 1.0 (不倒退)
  ③ 步数 <= 419 (不劣化, TASK-006 新基线)

用法:
  python bottlesumo_pi/governance/meta_harness/vision_physics_controller.py \
      --episodes 20 --tag TASK006B_VERIFY
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VISION_FRAMES_ROOT = os.path.join(REPO_ROOT, "docs", "vision_frames")

# TASK-006 基线 (PM 2026-08-06 裁决 1): decay=0.06 -> score=1.0, 419 步
TASK006_BEST_DECAY = 0.06
TASK006_BASELINE_STEPS = 419
TASK006_BASELINE_SCORE = 1.0

# PM 映射公式参数
EDGE_TRIGGER = 0.20      # edge_min < 0.20 -> 危险, 触发实时注入
DECAY_BASE = 0.06        # safe 时维持的最优衰减
DECAY_SLOPE = 0.02       # 线性插值斜率
DECAY_CAP = 0.10         # edge_min < 0.05 封顶

EDGE_FRAME_GLOBS = [
    "TASK006B_EDGE_*/*.json",          # 预研采集 summary (含 vis_edge_min)
    "TASK006B_EDGE_*/frame_*.png",     # 预研帧
]

# TASK-007 验收标准 (PM 2026-08-06 TASK-007 立项)
TASK007_MIN_EVENTS = 10    # >=10 次边缘接近事件检测并触发
TASK007_BASELINE_STEPS = 418   # TASK-006b 新基线 (b01377b)


def log(msg: str) -> None:
    print(f"[controller] {msg}", flush=True)


def _is_wsl() -> bool:
    return os.path.exists("/mnt/c") or os.environ.get("WSL_DISTRO_NAME")


def _to_wsl_path(p: str) -> str:
    if _is_wsl():
        return p
    p = os.path.normpath(p).replace("\\", "/")
    drive, rest = p.split(":", 1)
    return f"/mnt/{drive.lower()}{rest}"


def run_gate(decay: float, episodes: int, tag: str, out_dir: str) -> dict:
    """跑 evaluator_v9 门回归; BOTTLE_GRIP_DECAY 环境变量注入。"""
    out = os.path.join(out_dir, f"gate_decay_{decay:.3f}.json")
    repo = _to_wsl_path(REPO_ROOT)
    out_w = _to_wsl_path(out)
    cmd = (f"cd {repo} && BOTTLE_GRIP_DECAY={decay} "
           f"python3 governance/meta_harness/evaluator_v9.py "
           f"--episodes {episodes} --tag {tag}_D{decay:.3f} --json {out_w}")
    log(f"gate decay={decay:.3f}")
    if _is_wsl():
        proc = subprocess.run(["bash", "-c", cmd], capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              timeout=3600)
    else:
        proc = subprocess.run(["wsl", "-e", "bash", "-c", cmd],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=3600)
    if proc.returncode != 0:
        return {"decay": decay, "ok": False, "stderr": proc.stderr[-300:]}
    try:
        with open(out, "r", encoding="utf-8") as fh:
            report = json.load(fh)
        score = report.get("score")
        steps = (report.get("cost") or {}).get("total_steps")
        log(f"  -> score={score} total_steps={steps}")
        return {"decay": decay, "ok": True, "score": score, "steps": steps,
                "report": out}
    except Exception as e:
        return {"decay": decay, "ok": False, "stderr": str(e)}


def collect_danger_insights() -> list:
    """从预研采集产物收集危险帧洞察 (真实磁盘证据: vis_edge_min < 0.20)。"""
    hits = []
    # 1) 从 summary JSON 提取
    for f in sorted(glob.glob(os.path.join(VISION_FRAMES_ROOT,
                                           "TASK006B_EDGE_*",
                                           "edge_collect_summary.json"))):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            for r in d.get("scenes", []):
                em = r.get("vis_edge_min")
                if em is not None and float(em) < EDGE_TRIGGER:
                    hits.append({"scene": r.get("scene"), "edge_min": float(em),
                                 "zone": r.get("zone"),
                                 "latency_s": r.get("latency_s"),
                                 "source": os.path.basename(os.path.dirname(f))})
        except Exception:
            continue
    # 2) 直接读单个帧的 insight JSON (edge_collect_ext / d36 落盘的)
    for f in sorted(glob.glob(os.path.join(VISION_FRAMES_ROOT,
                                           "TASK006B_EDGE_*", "*.json"))):
        if f.endswith("edge_collect_summary.json"):
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            if isinstance(d, dict) and "edge_min" in d:
                em = d.get("edge_min")
                if em is not None and float(em) < EDGE_TRIGGER:
                    hits.append({"scene": os.path.basename(f), "edge_min": float(em),
                                 "zone": d.get("zone"),
                                 "latency_s": (d.get("_meta") or {}).get("latency_s"),
                                 "source": "raw"})
        except Exception:
            continue
    return hits


def collect_gazebo_edges() -> list:
    """从 Gazebo 真实仿真采集产物收集边缘接近事件 (TASK-007).

    真实危险帧数据流: 机器人在 Gazebo 中动态移动至边缘时, odom 几何量
    edge_min<0.20 触发记录 (含 TCRT5000 传感器证据 + 注入 decay 值).
    """
    hits = []
    for f in sorted(glob.glob(os.path.join(VISION_FRAMES_ROOT,
                                           "TASK007_GAZEBO_*", "*.json"))):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            for ev in d.get("events", []):
                em = ev.get("edge_min")
                if em is not None and float(em) < EDGE_TRIGGER:
                    hits.append({
                        "scene": f"gazebo_ep{ev.get('episode')}",
                        "edge_min": float(em),
                        "zone": ev.get("zone"),
                        "decay_injected": ev.get("decay_injected"),
                        "t_sec": ev.get("t_sec"),
                        "sensors": ev.get("sensors"),
                        "pose": ev.get("pose"),
                        "source": os.path.basename(f),
                    })
        except Exception:
            continue
    return hits

def pm_mapping(edge_min: float) -> float:
    """PM 映射公式: decay = 0.06 + 0.02*(0.20 - edge_min)/0.20, [0.06, 0.10]."""
    if edge_min >= EDGE_TRIGGER:
        return TASK006_BEST_DECAY  # safe: 维持最优, 不触发
    if edge_min < 0.05:
        return DECAY_CAP  # 封顶 0.10
    return DECAY_BASE + DECAY_SLOPE * (EDGE_TRIGGER - edge_min) / EDGE_TRIGGER


def main() -> int:
    ap = argparse.ArgumentParser(description="视觉->物理实时闭环控制器 (TASK-006b/TASK-007)")
    ap.add_argument("--episodes", type=int, default=20)
    ap.add_argument("--tag", default="TASK006B_VERIFY")
    ap.add_argument("--source", choices=["prestudy", "gazebo"], default="prestudy",
                    help="危险帧数据源: prestudy=构造帧(TASK-006b) / gazebo=真实仿真(TASK-007)")
    args = ap.parse_args()

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(VISION_FRAMES_ROOT, f"{args.tag}_{ts}")
    os.makedirs(out_dir, exist_ok=True)
    log(f"产物目录: {out_dir}")

    # ── ① 危险帧采集 ──
    if args.source == "gazebo":
        danger = collect_gazebo_edges()
        baseline_steps = TASK007_BASELINE_STEPS
        min_events = TASK007_MIN_EVENTS
        log(f"Gazebo 真实危险帧事件 (edge_min<0.20): {len(danger)} 条")
        for d in danger[:5]:
            log(f"  {d['scene']}: edge_min={d['edge_min']} zone={d['zone']} "
                f"t={d.get('t_sec')}s decay_注入={d.get('decay_injected')}")
        if len(danger) > 5:
            log(f"  ... 共 {len(danger)} 条")
    else:
        danger = collect_danger_insights()
        baseline_steps = TASK006_BASELINE_STEPS
        min_events = 3
        log(f"预研危险帧洞察 (edge_min<0.20): {len(danger)} 条")
        for d in danger:
            log(f"  {d['scene']}: edge_min={d['edge_min']} zone={d['zone']} "
                f"lat={d.get('latency_s')}")

    # ── ② 实时映射 (每事件独立计算) ──
    mapped = [{"scene": d["scene"], "edge_min": d["edge_min"],
               "decay": round(pm_mapping(d["edge_min"]), 3)} for d in danger]
    for m in mapped[:5]:
        log(f"  映射 {m['scene']}: edge_min={m['edge_min']} -> decay={m['decay']}")
    if not mapped:
        log("FAIL: 无危险帧, 实时注入未触发")
        return 2
    # 选最有代表性的: 最小 edge_min (最危险) 对应的 decay (保守注入)
    worst = min(mapped, key=lambda m: m["edge_min"])
    inject_decay = worst["decay"]
    log(f"注入 decay = {inject_decay} (来自最危险事件 {worst['scene']}, "
        f"edge_min={worst['edge_min']})")

    # ── ③ 门回归: 注入 decay vs 基线 ──
    r_inject = run_gate(inject_decay, args.episodes, args.tag, out_dir)
    r_base = run_gate(TASK006_BEST_DECAY, args.episodes, args.tag, out_dir)

    # ── ④ 验收判定 (source 相关标准) ──
    crit1 = len(danger) >= min_events
    crit2 = (r_inject.get("score") is not None
             and r_inject["score"] >= TASK006_BASELINE_SCORE)
    crit3 = (r_inject.get("steps") is not None
             and r_inject["steps"] <= baseline_steps)
    report = {
        "tag": args.tag, "source": args.source, "timestamp": ts,
        "episodes": args.episodes,
        "baseline": {"decay": TASK006_BEST_DECAY,
                     "score": TASK006_BASELINE_SCORE,
                     "steps": baseline_steps},
        "danger_frames": danger,
        "mapping": [{"scene": m["scene"], "edge_min": m["edge_min"],
                     "decay": m["decay"]} for m in mapped],
        "inject_decay": inject_decay,
        "gate_inject": r_inject,
        "gate_base": r_base,
        "acceptance": {
            "c1_min_events": crit1,
            "c2_score_ge_1.0": crit2,
            "c3_steps_le_baseline": crit3,
            "passed": bool(crit1 and crit2 and crit3),
        },
    }
    report_path = os.path.join(out_dir, "controller_report.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    log(f"报告 -> {report_path}")
    log(f"验收: ①事件>={min_events}={crit1} ({len(danger)}) ②score>=1.0={crit2} "
        f"({r_inject.get('score')}) ③steps<={baseline_steps}={crit3} "
        f"({r_inject.get('steps')})")
    log(f"总体: {'PASS' if report['acceptance']['passed'] else 'FAIL'}")
    return 0 if report["acceptance"]["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
