"""TASK-005f ROUND 11 视觉干跑 — EVAI v1.0 R-I-C-E Recognize 阶段验证.

把 lightweight_env 的合成相机帧 (dohyo 环 + edge zone 带 + 机器人/对手圆盘 + 航向箭头)
叠加到现有 rerun --serve-web 画布 (:9876 gRPC / :9090 Web Viewer)。

设计约束 (PM ROUND 11 裁决):
  - RULES 引擎已宣告 CLOSED (214 步前沿) — 本脚本不生成、不评估任何规则候选。
  - 不新建 Rerun 服务器: 连接已有 :9876 (与 visualizer.py --web 同一画布),
    :9090 为治理回归基线。
  - 感知叠加层 (EVAI R-I-C-E "Recognize"): edge 四向热区 + 对手向量,
    全部派生自已映射的 env 状态属性 (robot_x/y/theta, opponent_x/y/theta)。

用法 (经 outer_loop.py --vision-probe PROFILE 调用, 或直接):
    python3 governance/meta_harness/vision_probe.py --profile aggressive --steps 30
"""
import argparse
import math
import os
import sys
import threading
import time

# repo root = governance/meta_harness/../.. 
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, REPO_ROOT)

import numpy as np
import rerun as rr

from simulation.lightweight_env import (
    LightweightBottleSumoEnv,
    DOHYO_RADIUS,
    DOHYO_EDGE_ZONE,
    ROBOT_RADIUS,
    MAX_STEPS,
)
from simulation.wheel_to_discrete import Action

APP_ID = "bottlesumo_vision_probe"
# 确定性 recording_id — 使 Web Viewer 可通过 ?recording_id= 直接选中本录制
RECORDING_ID = "a3f1d5e2-7b4c-4e6a-9c8d-1f2e3d4c5b6a"
GRPC_URL = "rerun+http://127.0.0.1:9876/proxy"

# --no-rerun 模式: 跳过所有 rr.* 调用 (纯帧落盘, A2 无 Rerun 环境验证)
_RERUN_ENABLED = True

# R-I-C-E Recognize: 四向 edge 热区颜色 (绿->黄->红)
EDGE_COLORS = {
    0: (120, 220, 120, 200),   # front
    1: (220, 220, 120, 200),   # back
    2: (120, 180, 220, 200),   # left
    3: (220, 140, 120, 200),   # right
}
ROBOT_COLOR = (70, 130, 180, 255)
OPPONENT_COLOR = (220, 60, 60, 255)


def log_static_scene():
    """dohyo 环 + edge zone 带 (半透明)。"""
    if not _RERUN_ENABLED:
        return
    th = np.linspace(0.0, 2.0 * math.pi, 97)
    # dohyo 环 (半径 0.40)
    ring = np.stack(
        [DOHYO_RADIUS * np.cos(th), DOHYO_RADIUS * np.sin(th), np.zeros_like(th)], axis=1
    )
    rr.log("vision_probe/world/dohyo", rr.LineStrips3D(
        [ring.tolist()], colors=[255, 255, 255, 160]))
    # edge zone 带 (0.32 ~ 0.40) — Recognize 物理边界
    inner = DOHYO_RADIUS - DOHYO_EDGE_ZONE
    edge_band = np.stack(
        [inner * np.cos(th), inner * np.sin(th), np.zeros_like(th)], axis=1
    )
    rr.log("vision_probe/world/edge_zone", rr.LineStrips3D(
        [edge_band.tolist()], colors=[255, 200, 60, 90]))


def log_frame(step: int, env: LightweightBottleSumoEnv, obs):
    """一帧合成相机画面 + R-I-C-E Recognize 感知叠加层。"""
    if not _RERUN_ENABLED:
        return
    rr.set_time("frame", sequence=step)

    # 机器人圆盘 + 航向箭头
    rr.log("vision_probe/world/robot", rr.Points3D(
        [[env.robot_x, env.robot_y, 0.0]], radii=[ROBOT_RADIUS], colors=[ROBOT_COLOR]))
    hx = env.robot_x + 0.16 * math.cos(env.robot_theta)
    hy = env.robot_y + 0.16 * math.sin(env.robot_theta)
    rr.log("vision_probe/world/robot_heading", rr.LineStrips3D(
        [[[env.robot_x, env.robot_y, 0.0], [hx, hy, 0.0]]], colors=[ROBOT_COLOR]))

    # 对手圆盘 + 航向箭头
    rr.log("vision_probe/world/opponent", rr.Points3D(
        [[env.opponent_x, env.opponent_y, 0.0]], radii=[ROBOT_RADIUS],
        colors=[OPPONENT_COLOR]))
    ox = env.opponent_x + 0.16 * math.cos(env.opponent_theta)
    oy = env.opponent_y + 0.16 * math.sin(env.opponent_theta)
    rr.log("vision_probe/world/opponent_heading", rr.LineStrips3D(
        [[[env.opponent_x, env.opponent_y, 0.0], [ox, oy, 0.0]]],
        colors=[OPPONENT_COLOR]))

    # R-I-C-E Recognize 叠加层 1: 四向 edge 热区 (从机器人中心伸出, 长度 ∝ 传感器值)
    for idx, (label, color) in enumerate(EDGE_COLORS.items()):
        ang = {0: env.robot_theta, 1: env.robot_theta + math.pi,
               2: env.robot_theta + math.pi / 2, 3: env.robot_theta - math.pi / 2}[label]
        d = float(obs[idx]) * 0.30
        ex = env.robot_x + d * math.cos(ang)
        ey = env.robot_y + d * math.sin(ang)
        rr.log(f"vision_probe/recognize/edge_{label}", rr.LineStrips3D(
            [[[env.robot_x, env.robot_y, 0.0], [ex, ey, 0.0]]], colors=[color]))
        rr.log(f"vision_probe/recognize/edge_{label}_tip", rr.Points3D(
            [[ex, ey, 0.0]], radii=[0.012], colors=[color]))

    # R-I-C-E Recognize 叠加层 2: 对手向量 (距离 + 角度)
    rr.log("vision_probe/recognize/opp_vector", rr.LineStrips3D(
        [[[env.robot_x, env.robot_y, 0.0],
          [env.opponent_x, env.opponent_y, 0.0]]],
        colors=[255, 255, 255, 120]))
    rr.log("vision_probe/recognize/opp_label",
           rr.TextLog(f"step={step} opp_dist={obs[4]:.3f} opp_angle={obs[5]:+6.1f}° "
                      f"speed={obs[6]:.2f} edge_min={obs[0:4].min():.3f}"))


# ---------------------------------------------------------------------------
# A2: 帧落盘 PNG (PM ROUND 11 Phase A2 验收)
#   - 落盘路径: docs/vision_frames/ROUNDN/frame_<tag>_<ts>_<seq>.png
#   - 异步写盘 (背景线程 + queue), 不阻塞主循环
#   - 每帧 < 500KB (matplotlib 默认 PNG 远超小余量)
# ---------------------------------------------------------------------------
_FRAME_QUEUE = None
_FRAME_WORKER = None
_FRAME_DIR = None


def _render_frame_png(step, env, obs):
    """渲染与 Rerun 叠加层一致的合成相机帧为 matplotlib 图。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(5.0, 5.0), dpi=110)
    ax.set_aspect("equal")
    ax.set_xlim(-0.55, 0.55)
    ax.set_ylim(-0.55, 0.55)
    ax.add_artist(plt.Circle((0, 0), DOHYO_RADIUS, fill=False, edgecolor="white",
                             linewidth=2))
    ax.add_artist(plt.Circle((0, 0), DOHYO_RADIUS - DOHYO_EDGE_ZONE, fill=False,
                             edgecolor=(1.0, 0.78, 0.24), linewidth=1.5))
    ax.set_facecolor("#101418")

    # 机器人 (蓝) + 航向
    ax.add_artist(plt.Circle((env.robot_x, env.robot_y), ROBOT_RADIUS,
                             color="#4682b4", zorder=5))
    hx = env.robot_x + 0.16 * math.cos(env.robot_theta)
    hy = env.robot_y + 0.16 * math.sin(env.robot_theta)
    ax.annotate("", xy=(hx, hy), xytext=(env.robot_x, env.robot_y),
                arrowprops=dict(arrowstyle="->", color="#4682b4", lw=2))

    # 对手 (红) + 航向
    ax.add_artist(plt.Circle((env.opponent_x, env.opponent_y), ROBOT_RADIUS,
                             color="#dc3c3c", zorder=5))
    ox = env.opponent_x + 0.16 * math.cos(env.opponent_theta)
    oy = env.opponent_y + 0.16 * math.sin(env.opponent_theta)
    ax.annotate("", xy=(ox, oy), xytext=(env.opponent_x, env.opponent_y),
                arrowprops=dict(arrowstyle="->", color="#dc3c3c", lw=2))

    # R-I-C-E Recognize: edge 四向热区 (长度 ∝ obs)
    for idx in range(4):
        ang = {0: env.robot_theta, 1: env.robot_theta + math.pi,
               2: env.robot_theta + math.pi / 2,
               3: env.robot_theta - math.pi / 2}[idx]
        d = float(obs[idx]) * 0.30
        ex = env.robot_x + d * math.cos(ang)
        ey = env.robot_y + d * math.sin(ang)
        c = EDGE_COLORS[idx]
        ax.plot([env.robot_x, ex], [env.robot_y, ey],
                color=tuple(v / 255.0 for v in c[:3]), lw=1.8)

    # 对手向量
    ax.plot([env.robot_x, env.opponent_x], [env.robot_y, env.opponent_y],
            color="white", lw=1.0, alpha=0.5, ls="--")

    ax.set_title(f"frame {step}  edge_min={obs[0:4].min():.3f}  "
                 f"opp_d={obs[4]:.3f}", color="white", fontsize=9)
    ax.tick_params(colors="white", labelsize=7)
    for sp in ax.spines.values():
        sp.set_color("white")

    import io
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#101418")
    plt.close(fig)
    return buf.getvalue()


def _frame_worker_loop():
    """后台线程: 从队列取 (seq, png_bytes), 写盘。"""
    while True:
        item = _FRAME_QUEUE.get()
        if item is None:
            break
        seq, png = item
        try:
            path = os.path.join(_FRAME_DIR, f"frame_{seq:04d}.png")
            with open(path, "wb") as f:
                f.write(png)
        except Exception as e:
            print(f"[vision_probe] frame write error: {e}", flush=True)
        _FRAME_QUEUE.task_done()


def start_frame_save(tag: str, base_dir: str):
    """启动异步帧落盘。base_dir 如 docs/vision_frames, tag 如 A1_VERIFY。"""
    global _FRAME_QUEUE, _FRAME_WORKER, _FRAME_DIR
    if _FRAME_QUEUE is not None:
        return _FRAME_DIR  # 已启动
    import datetime
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    _FRAME_DIR = os.path.join(base_dir, f"{tag}_{stamp}")
    os.makedirs(_FRAME_DIR, exist_ok=True)
    _FRAME_QUEUE = __import__("queue").Queue()
    _FRAME_WORKER = threading.Thread(target=_frame_worker_loop, daemon=True)
    _FRAME_WORKER.start()
    print(f"[vision_probe] frame save enabled -> {_FRAME_DIR}", flush=True)
    return _FRAME_DIR


def save_frame_async(seq: int, env, obs):
    """渲染并异步入队 (非阻塞)。"""
    if _FRAME_QUEUE is None:
        return
    try:
        png = _render_frame_png(seq, env, obs)
        _FRAME_QUEUE.put((seq, png))
    except Exception as e:
        print(f"[vision_probe] render error: {e}", flush=True)


def stop_frame_save():
    global _FRAME_QUEUE, _FRAME_WORKER
    if _FRAME_QUEUE is None:
        return
    _FRAME_QUEUE.put(None)
    if _FRAME_WORKER:
        _FRAME_WORKER.join(timeout=10)
    _FRAME_QUEUE = None
    _FRAME_WORKER = None
    print("[vision_probe] frame worker stopped", flush=True)


def main():
    ap = argparse.ArgumentParser(description="BottleSumo TASK-005f 视觉干跑")
    ap.add_argument("--profile", default="aggressive",
                    choices=["stationary", "passive", "moderate", "aggressive"])
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--hold", type=float, default=8.0,
                    help="日志推送后保持连接秒数 (确保 gRPC 刷盘)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--save", default="",
                    help="额外保存 .rrd 快照路径 (默认空 = 不保存, 仅流式推送)")
    ap.add_argument("--save-frames", default="",
                    help="A2: 帧落盘 PNG 基目录 (如 docs/vision_frames); 空 = 不落盘")
    ap.add_argument("--tag", default="ROUNDN",
                    help="A2: 帧落盘子目录标签 (如 A1_VERIFY)")
    ap.add_argument("--no-rerun", action="store_true",
                    help="跳过 gRPC 连接 (纯帧落盘模式, 用于 A2 无 Rerun 环境验证)")
    args = ap.parse_args()

    global _RERUN_ENABLED
    _RERUN_ENABLED = not args.no_rerun

    if _RERUN_ENABLED:
        rr.init(APP_ID, recording_id=RECORDING_ID, spawn=False)
        rr.connect_grpc(GRPC_URL)
        print(f"[vision_probe] connected {GRPC_URL} (viewer: http://localhost:9090)",
              flush=True)
        log_static_scene()
    else:
        print("[vision_probe] --no-rerun: 跳过 gRPC, 纯帧落盘模式", flush=True)

    # A2: 可选帧落盘 (异步)
    frame_dir = None
    if args.save_frames:
        frame_dir = start_frame_save(args.tag, args.save_frames)

    env = LightweightBottleSumoEnv(opponent_profile=args.profile, seed=args.seed)
    obs, _ = env.reset(seed=args.seed)

    # 稳健脚本策略: 慢速前进 + 右转 (全 profile 均稳定存活 ≥30 步, 保证视觉帧完整)
    # 仅演示视觉通路, 不涉及规则引擎 (RULES CLOSED)
    script = ([Action.CREEP_FWD] * 5 + [Action.TURN_R_HARD] * 1) * 5
    n = min(args.steps, len(script))

    logged = 0
    for i in range(n):
        action = script[i % len(script)]
        obs, reward, done, truncated, info = env.step(int(action))
        log_frame(i, env, obs)
        if frame_dir:
            save_frame_async(i, env, obs)
        logged += 1
        print(f"[vision_probe] frame {i}: x={env.robot_x:+.3f} y={env.robot_y:+.3f} "
              f"th={math.degrees(env.robot_theta):+6.1f}° opp=({env.opponent_x:+.3f},"
              f"{env.opponent_y:+.3f}) edge_min={obs[0:4].min():.3f}", flush=True)
        if done or truncated:
            print(f"[vision_probe] episode end at step {i} "
                  f"(done={done} trunc={truncated})", flush=True)
            break

    if _RERUN_ENABLED:
        print(f"[vision_probe] logged {logged} frames to {GRPC_URL} "
              f"(app '{APP_ID}' on :9090 canvas)", flush=True)
    else:
        print(f"[vision_probe] logged {logged} frames (no-rerun mode)", flush=True)
    if frame_dir:
        stop_frame_save()
        n_png = len([f for f in os.listdir(frame_dir) if f.endswith(".png")])
        print(f"[vision_probe] A2 frame PNGs: {n_png} -> {frame_dir}", flush=True)
    if args.save and _RERUN_ENABLED:
        rr.save(args.save)
        print(f"[vision_probe] saved .rrd snapshot -> {args.save}", flush=True)
    time.sleep(args.hold)
    print("[vision_probe] done", flush=True)


if __name__ == "__main__":
    main()
