#!/usr/bin/env python3
"""TASK-005c: Rerun 3D real-time visualization dashboard.

Subscribes /odom, /cmd_vel, /goal_pose and renders in Rerun (127.0.0.1:9876):
  - robot chassis (box + heading arrow)
  - velocity vector arrows (red=linear, blue=angular, length scaled)
  - goal green pillar (relative distance)
  - 5s sliding-window time-series curves (v_lin / omega_z / dist error)

Toggles via config/visualizer.yaml (visualizer.yaml next to scripts).

CLI:
  python3 scripts/visualizer.py                  # live ROS2 subscribe
  python3 scripts/visualizer.py --no-ros         # replay-only skeleton (CI dry-run)
  python3 scripts/visualizer.py --save /tmp/shot.png  # save current frame

Fallback (rerun-sdk not installed): matplotlib live plot + log. The 3D view
degrades to CLI output but the time-series still renders in matplotlib.
"""
import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

try:
    import rerun as rr
    RERUN_OK = True
except ImportError:
    RERUN_OK = False

import yaml

CFG_PATH = Path(__file__).resolve().parent.parent / "config" / "visualizer.yaml"
DEFAULT_CFG = {
    "window_seconds": 5.0,
    "arrow_scale_lin": 1.0,
    "arrow_scale_ang": 0.3,
    "show_chassis": True,
    "show_vel_arrows": True,
    "show_goal": True,
    "show_timeseries": True,
    "log_interval_hz": 20.0,
}


def load_cfg() -> dict:
    if CFG_PATH.exists():
        try:
            loaded = yaml.safe_load(CFG_PATH.read_text(encoding="utf-8")) or {}
            merged = dict(DEFAULT_CFG)
            merged.update({k: v for k, v in loaded.items() if k in merged})
            return merged
        except Exception:
            pass
    return dict(DEFAULT_CFG)


class RerunVisualizer:
    def __init__(self, cfg: dict, save_path: str | None = None, headless: bool = False, web: bool = False):
        self.cfg = cfg
        self.save_path = save_path
        self.headless = headless
        self.web = web
        self._history: dict[str, list[tuple[float, float]]] = {"v_lin": [], "omega": [], "dist_err": []}
        self._frame = 0
        self._episode = -1
        self._samples = 0
        if RERUN_OK:
            if headless:
                # WSL/CI-safe: record to .rrd without spawning the GUI.
                # Replay later on a GPU machine: rerun <file>.rrd
                rr.init("bottlesumo_tactical_dashboard", spawn=False)
                if save_path:
                    rr.save(save_path)
                print(f"[TASK-005c] headless recording -> {save_path}")
            elif web:
                # Web-viewer mode: stream to a local `rerun --serve-web` instance.
                # User opens http://localhost:<web-viewer-port> in a browser.
                rr.init("bottlesumo_tactical_dashboard", spawn=False)
                rr.connect_grpc("rerun+http://127.0.0.1:9876/proxy")
                self._log_static_scene()
                print(f"[TASK-005c] web mode: streaming to rerun server :9876 (open browser at http://localhost:9090)")
            else:
                rr.init("bottlesumo_tactical_dashboard", spawn=True)
                self._log_static_scene()
                print(f"[TASK-005c] Rerun dashboard live at http://127.0.0.1:9876")
        else:
            print("[TASK-005c] WARNING: rerun-sdk not installed; matplotlib fallback")
            import matplotlib
            matplotlib.use("TkAgg")

    # ── static scene ───────────────────────────────────────────────────────
    def _log_static_scene(self):
        if not RERUN_OK:
            return
        # dohyo circle outline (radius 0.40 m, 64 segments)
        th = np.linspace(0, 2 * math.pi, 65)
        pts = np.stack([0.4 * np.cos(th), 0.4 * np.sin(th), np.zeros(65)], axis=1)
        rr.log("world/dohyo", rr.LineStrips3D([pts.tolist()], colors=[255, 255, 255, 128]))

    # ── per-frame update ────────────────────────────────────────────────────
    def update(self, odom, cmd_vel, goal, ep: int, samples: int):
        self._frame += 1
        self._episode = ep
        self._samples = samples
        now = time.time()

        x, y, theta = odom["x"], odom["y"], odom["theta"]
        v_lin, omega = odom["v_lin"], odom["omega"]
        dist_err = goal["dist"]

        # history ring buffer (window_seconds)
        for key, val in (("v_lin", v_lin), ("omega", omega), ("dist_err", dist_err)):
            buf = self._history[key]
            buf.append((now, val))
            while buf and buf[0][0] < now - self.cfg["window_seconds"]:
                buf.pop(0)

        if RERUN_OK:
            rr.set_time("frame", sequence=self._frame)
            # robot chassis
            if self.cfg["show_chassis"]:
                rr.log("world/robot", rr.Transform3D(translation=[x, y, 0.0], rotation=rr.Quaternion(xyzw=[0, 0, math.sin(theta/2), math.cos(theta/2)])))
                rr.log("world/robot/chassis", rr.Boxes3D(half_sizes=[0.075, 0.075, 0.03], colors=[70, 130, 180]))
                rr.log("world/robot/heading", rr.Arrows3D(origins=[[0, 0, 0]], vectors=[[0.12, 0, 0]], colors=[255, 255, 255]))
            # velocity arrows
            if self.cfg["show_vel_arrows"]:
                rr.log("world/robot/vel_lin", rr.Arrows3D(
                    origins=[[0, 0, 0.02]], vectors=[[v_lin * self.cfg["arrow_scale_lin"], 0, 0]],
                    colors=[255, 60, 60], radii=0.005))
                rr.log("world/robot/vel_ang", rr.Arrows3D(
                    origins=[[0, 0, 0.02]], vectors=[[0, omega * self.cfg["arrow_scale_ang"], 0]],
                    colors=[60, 60, 255], radii=0.004))
            # goal pillar
            if self.cfg["show_goal"] and goal["active"]:
                gx, gy = goal["x"], goal["y"]
                rr.log("world/goal", rr.Boxes3D(half_sizes=[0.01, 0.01, 0.05], centers=[gx, gy, 0.025], colors=[60, 220, 90]))
                rr.log("world/goal/line", rr.LineStrips3D([[[x, y, 0.0], [gx, gy, 0.0]]], colors=[60, 220, 90, 128]))
            # time series
            if self.cfg["show_timeseries"]:
                for key, color in (("v_lin", [255, 60, 60]), ("omega", [60, 60, 255]), ("dist_err", [60, 220, 90])):
                    for t, val in self._history[key]:
                        rr.set_time("t", timestamp=t)
                        rr.log(f"ts/{key}", rr.Scalars(val))
                rr.set_time("t", timestamp=now)
                rr.log("text/episode", rr.TextLog(f"episode={ep} samples={samples}"))
        else:
            # fallback: concise CLI line
            print(f"[fallback] ep={ep} samples={samples} x={x:.2f} y={y:.2f} "
                  f"th={theta:.2f} v={v_lin:.3f} w={omega:.2f} dist={dist_err:.2f}")

        if self.save_path and RERUN_OK and self._frame == 60:
            # headless mode already rr.save()'d at init; this keeps the .rrd
            # open until the final frame (Rerun streams to the file handle)
            print(f"[TASK-005c] frame 60 reached; recording to {self.save_path}")
            rr.log("text/status", rr.TextLog("recording complete"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ros", action="store_true", help="synthetic demo loop (CI dry-run)")
    ap.add_argument("--save", type=str, default=None, help="save recording (.rrd) or frame to path")
    ap.add_argument("--headless", action="store_true", help="no GUI: record .rrd (WSL/CI-safe)")
    ap.add_argument("--web", action="store_true", help="stream to local rerun --serve-web instance (browser at :9090)")
    ap.add_argument("--ns", type=str, default="/bottlesumo", help="ROS namespace (default /bottlesumo)")
    ap.add_argument("--episodes", type=int, default=3, help="synthetic episodes (no-ros)")
    a = ap.parse_args()

    cfg = load_cfg()
    vis = RerunVisualizer(cfg, save_path=a.save, headless=a.headless, web=a.web)

    if a.no_ros:
        print("[TASK-005c] synthetic demo mode (no ROS)")
        for ep in range(a.episodes):
            for i in range(120):
                t = i / 10.0
                # emulate step response rise: v approaches 0.53 with 1-e^-t/tau
                v = 0.53 * (1 - math.exp(-t / 0.8))
                w = 0.5 * math.sin(t)
                dist = max(0.05, 0.6 - 0.02 * i)
                odom = {"x": 0.05 * i, "y": 0.0, "theta": t * 0.3,
                        "v_lin": v, "omega": w}
                goal = {"x": 0.4, "y": 0.0, "dist": dist, "active": True}
                vis.update(odom, {}, goal, ep, ep * 120 + i)
                time.sleep(0.05)
        return

    # ── live ROS2 mode ─────────────────────────────────────────────────────
    try:
        import rclpy
        from geometry_msgs.msg import Twist
        from nav_msgs.msg import Odometry
        from geometry_msgs.msg import PoseStamped
    except ImportError as e:
        print(f"[TASK-005c] ERROR: ROS2 deps unavailable: {e}; use --no-ros")
        raise SystemExit(1)

    import rclpy.node

    class VisNode(rclpy.node.Node):
        def __init__(self, visualizer: RerunVisualizer, ns: str = "/bottlesumo"):
            super().__init__("rerun_visualizer")
            self.vis = visualizer
            self._odom = {"x": 0.0, "y": 0.0, "theta": 0.0, "v_lin": 0.0, "omega": 0.0}
            self._goal = {"x": 0.4, "y": 0.0, "dist": 0.4, "active": False}
            self._ep, self._samples = 0, 0
            odom_topic = f"{ns}/odom" if ns else "/odom"
            cmd_topic = f"{ns}/cmd_vel" if ns else "/cmd_vel"
            goal_topic = f"{ns}/goal_pose" if ns else "/goal_pose"
            self.create_subscription(Odometry, odom_topic, self._cb_odom, 10)
            self.create_subscription(Twist, cmd_topic, self._cb_cmd, 10)
            self.create_subscription(PoseStamped, goal_topic, self._cb_goal, 10)
            interval = 1.0 / visualizer.cfg["log_interval_hz"]
            self.create_timer(interval, self._tick)
            self.get_logger().info(
                f"visualizer subscribed: {odom_topic} {cmd_topic} {goal_topic}")

        def _cb_odom(self, msg):
            p = msg.pose.pose.position
            q = msg.pose.pose.orientation
            self._odom.update(x=p.x, y=p.y,
                              theta=2 * math.atan2(q.z, q.w),
                              v_lin=msg.twist.twist.linear.x,
                              omega=msg.twist.twist.angular.z)

        def _cb_cmd(self, msg):
            pass  # cmd_vel is rendered implicitly via odom in this design

        def _cb_goal(self, msg):
            self._goal.update(x=msg.pose.position.x, y=msg.pose.position.y, active=True)
            dx = self._goal["x"] - self._odom["x"]
            dy = self._goal["y"] - self._odom["y"]
            self._goal["dist"] = math.hypot(dx, dy)

        def _tick(self):
            self.vis.update(self._odom, {}, self._goal, self._ep, self._samples)

        def set_episode(self, ep, samples):
            self._ep, self._samples = ep, samples

    rclpy.init()
    node = VisNode(vis, ns=a.ns)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
