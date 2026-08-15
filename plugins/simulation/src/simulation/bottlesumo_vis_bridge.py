#!/usr/bin/env python3
"""
bottlesumo_vis_bridge.py — G1 Lightweight Gym → RViz bridge (GUI Phase G)

Publishes the lightweight BottleSumo env state as RViz markers so the
V9 ABDL rule agent's behavior is visible in a GUI (digital-world,
simulation-first, no real hardware).

Topics published (frame_id: "dohyo", z=0 ground plane, meters):
  /bottlesumo/vis/markers  visualization_msgs/MarkerArray
      - dohyo ring    (cylinder, translucent, r=0.40)
      - robot         (red cylinder) + heading arrow
      - opponent      (blue cylinder) + heading arrow
      - robot trail   (line strip)
  /bottlesumo/vis/state   std_msgs/String  — decision/mode/episode summary

Usage (WSL, ROS2 sourced):
  python3 bottlesumo_pi/simulation/bottlesumo_vis_bridge.py [--opponent counter] [--agent abdl]
  # in a second terminal:
  rviz2 -d bottlesumo_pi/simulation/rviz/bottlesumo_gym.rviz
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from typing import Optional

# ── Project paths (single source of truth: reuse gate evaluator + env) ──
_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from simulation.lightweight_env import LightweightBottleSumoEnv, DOHYO_RADIUS
from simulation.v9_gate_evaluator import V9RuleAgent, OpponentStrategies

import rclpy
from rclpy.node import Node
from visualization_msgs.msg import Marker, MarkerArray
from std_msgs.msg import String


def _color(r: float, g: float, b: float, a: float = 1.0):
    from std_msgs.msg import ColorRGBA
    c = ColorRGBA()
    c.r, c.g, c.b, c.a = float(r), float(g), float(b), float(a)
    return c


class VisBridge(Node):
    def __init__(self, opponent_name: str, agent_kind: str, seed: int, backend: str = "lightweight"):
        super().__init__("bottlesumo_vis_bridge")
        self.backend = backend
        self.pub_markers = self.create_publisher(MarkerArray, "/bottlesumo/vis/markers", 10)
        self.pub_state = self.create_publisher(String, "/bottlesumo/vis/state", 10)
        self.pub_debug = self.create_publisher(MarkerArray, "/bottlesumo/vis/debug", 10)

        # Agent: abdl (V9 rules) or heuristic fallback / v11 template
        if agent_kind == "heuristic":
            self.agent = V9RuleAgent(force_heuristic=True)
        else:
            self.agent = V9RuleAgent(force_heuristic=False)
        self.agent_kind = agent_kind

        # Opponent strategy
        self.opponent_fn = OpponentStrategies.get(opponent_name)
        self.opponent_name = opponent_name

        if backend == "mujoco":
            from simulation.mujoco_env import MuJoCoBottleSumoEnv
            self.env = MuJoCoBottleSumoEnv(
                opponent_strategy=self.opponent_fn,
                opponent_strategy_name=opponent_name,
            )
        else:
            self.env = LightweightBottleSumoEnv(
                opponent_strategy=self.opponent_fn,
                render_mode="none",
            )
        self.seed = seed
        self.episode = 0
        self.episode_steps = 0
        self.total_wins = 0
        self.total_eps = 0
        self.trail = []  # (x, y) robot positions for line strip

        obs, _ = self.env.reset(seed=self.seed)
        self.obs = obs

    # ── helpers ──

    def _base_marker(self, ns: str, mid: int, mtype: int) -> Marker:
        m = Marker()
        m.header.frame_id = "dohyo"
        m.header.stamp = self.get_clock().now().to_msg()
        m.ns = ns
        m.id = mid
        m.type = mtype
        m.action = Marker.ADD
        m.pose.orientation.w = 1.0
        m.scale.x = m.scale.y = m.scale.z = 0.05
        m.color = _color(1, 1, 1, 1)
        return m

    # ── publishing ──

    def publish(self, reward: float, done: bool, trace: Optional[dict] = None):
        from geometry_msgs.msg import Point, Quaternion
        import math

        arr = MarkerArray()
        e = self.env

        # 1) Dohyo ring (translucent disc)
        ring = self._base_marker("dohyo", 0, Marker.CYLINDER)
        ring.scale.x = ring.scale.y = 2 * DOHYO_RADIUS
        ring.scale.z = 0.005
        ring.pose.position.z = -0.01
        ring.color = _color(1.0, 1.0, 1.0, 0.25)
        arr.markers.append(ring)

        # 2) Robot (red cylinder) + heading arrow
        rob = self._base_marker("robot", 1, Marker.CYLINDER)
        rob.pose.position.x = float(e.robot_x)
        rob.pose.position.y = float(e.robot_y)
        rob.pose.position.z = 0.025
        rob.scale.x = rob.scale.y = 0.15
        rob.scale.z = 0.05
        rob.color = _color(1.0, 0.2, 0.2, 0.95)
        rob.pose.orientation = Quaternion(
            x=0.0, y=0.0,
            z=float(math.sin(e.robot_theta / 2)), w=float(math.cos(e.robot_theta / 2)),
        )
        arr.markers.append(rob)

        rob_arrow = self._base_marker("robot", 2, Marker.ARROW)
        p0 = Point(x=float(e.robot_x), y=float(e.robot_y), z=0.03)
        p1 = Point(
            x=float(e.robot_x) + 0.12 * math.cos(e.robot_theta),
            y=float(e.robot_y) + 0.12 * math.sin(e.robot_theta),
            z=0.03,
        )
        rob_arrow.points = [p0, p1]
        rob_arrow.scale.x = 0.015
        rob_arrow.scale.y = 0.03
        rob_arrow.color = _color(1.0, 1.0, 0.0, 0.9)
        arr.markers.append(rob_arrow)

        # 3) Opponent (blue cylinder) + heading arrow
        opp = self._base_marker("opponent", 3, Marker.CYLINDER)
        opp.pose.position.x = float(e.opponent_x)
        opp.pose.position.y = float(e.opponent_y)
        opp.pose.position.z = 0.025
        opp.scale.x = opp.scale.y = 0.15
        opp.scale.z = 0.05
        opp.color = _color(0.2, 0.4, 1.0, 0.95)
        opp.pose.orientation = Quaternion(
            x=0.0, y=0.0,
            z=float(math.sin(e.opponent_theta / 2)), w=float(math.cos(e.opponent_theta / 2)),
        )
        arr.markers.append(opp)

        # 4) Robot trail (yellow line strip, last 120 positions)
        self.trail.append((float(e.robot_x), float(e.robot_y)))
        if len(self.trail) > 120:
            self.trail.pop(0)
        trail_m = self._base_marker("trail", 4, Marker.LINE_STRIP)
        trail_m.points = [Point(x=float(x), y=float(y), z=0.02) for x, y in self.trail]
        trail_m.scale.x = 0.008
        trail_m.color = _color(1.0, 0.8, 0.1, 0.8)
        arr.markers.append(trail_m)

        self.pub_markers.publish(arr)

        # 5) State string (decision transparency: agent_mode / episode / reward)
        msg = String()
        trace_s = ""
        if trace is not None:
            if trace.get("mode") == "abdl":
                trace_s = (
                    f" [ABDL rule={trace.get('rule_id')} "
                    f"policy={trace.get('policy_id')} reason={trace.get('reason', '')[:40]}]"
                )
            else:
                trace_s = f" [heuristic branch={trace.get('branch')}]"
        msg.data = (
            f"agent={self.agent_kind}({self.agent.mode}) opp={self.opponent_name} "
            f"ep={self.episode} step={self.episode_steps} "
            f"reward={reward:+.2f} score={self.total_wins}/{self.total_eps} "
            f"done={done}{trace_s}"
        )
        self.pub_state.publish(msg)

        # ── G3 debug overlay: /bottlesumo/vis/debug ──
        # Decision transparency — show which rule fired and the target direction.
        if trace is not None:
            dbg = MarkerArray()
            # 6) Decision text above robot (TEXT_VIEW_FACING)
            txt = self._base_marker("g3", 10, Marker.TEXT_VIEW_FACING)
            txt.pose.position.x = float(e.robot_x)
            txt.pose.position.y = float(e.robot_y)
            txt.pose.position.z = 0.16
            txt.scale.z = 0.055
            if trace.get("mode") == "abdl":
                txt.text = f"{trace.get('rule_id')} / {trace.get('policy_id')}"
                txt.color = _color(0.3, 1.0, 0.4, 1.0)  # green = ABDL decided
            else:
                txt.text = f"HEUR:{trace.get('branch')}"
                txt.color = _color(1.0, 0.75, 0.2, 1.0)  # orange = heuristic
            dbg.markers.append(txt)

            # 7) Decision arrow: robot → opponent target (only when tracking)
            sens = trace.get("sensors", {})
            opp_d = float(sens.get("opp_dist", 0.0))
            if 0.0 < opp_d <= 0.5:
                a = self._base_marker("g3", 11, Marker.ARROW)
                p0 = Point(x=float(e.robot_x), y=float(e.robot_y), z=0.04)
                p1 = Point(x=float(e.opponent_x), y=float(e.opponent_y), z=0.04)
                a.points = [p0, p1]
                a.scale.x = 0.012
                a.scale.y = 0.02
                a.color = _color(0.9, 0.3, 1.0, 0.9)  # magenta: target lock
                dbg.markers.append(a)

            # 8) Danger box: red wireframe near edges (any edge < 0.15)
            edges = [
                float(sens.get(k, 1.0)) for k in ("edge_f", "edge_b", "edge_l", "edge_r")
            ]
            if edges and min(edges) < 0.15:
                warn = self._base_marker("g3", 12, Marker.CUBE)
                warn.pose.position.x = float(e.robot_x)
                warn.pose.position.y = float(e.robot_y)
                warn.pose.position.z = 0.06
                warn.scale.x = warn.scale.y = warn.scale.z = 0.24
                warn.color = _color(1.0, 0.1, 0.1, 0.55)  # translucent red box
                dbg.markers.append(warn)

            self.pub_debug.publish(dbg)

    # ── main loop ──

    def run(self):
        import time
        # NOTE: rclpy Rate.sleep() blocks forever without an executor in
        # Humble; use plain time.sleep at TIMESTEP pace instead.
        while rclpy.ok():
            action, trace = self.agent.select_action_traced(self.obs)
            self.obs, reward, terminated, truncated, _ = self.env.step(action)
            self.episode_steps += 1
            done = bool(terminated or truncated)

            if self.episode_steps % 25 == 1:
                self.get_logger().info(
                    f"step {self.episode_steps}: pos=({self.env.robot_x:.2f}, "
                    f"{self.env.robot_y:.2f}) th={self.env.robot_theta:.2f} "
                    f"opp=({self.env.opponent_x:.2f}, {self.env.opponent_y:.2f})"
                )

            try:
                self.publish(float(reward), done, trace=trace)
            except Exception as exc:  # noqa: BLE001 — keep loop alive, surface error
                self.get_logger().error(f"publish failed: {type(exc).__name__}: {exc}")
                import traceback
                traceback.print_exc()

            if done:
                win = bool(terminated and reward > 5)
                self.total_eps += 1
                self.total_wins += 1 if win else 0
                self.episode += 1
                self.episode_steps = 0
                self.trail = []
                self.obs, _ = self.env.reset(seed=self.seed + 1000 * self.episode)
                self.get_logger().info(
                    f"episode {self.episode}: {'WIN' if win else 'LOSS'} "
                    f"({self.total_wins}/{self.total_eps})"
                )
            time.sleep(0.08)  # matches env TIMESTEP


def main():
    parser = argparse.ArgumentParser(description="BottleSumo G1 RViz bridge")
    parser.add_argument("--opponent", default="counter",
                        choices=["random", "aggressive", "defensive", "circler", "counter"],
                        help="opponent strategy (default: counter)")
    parser.add_argument("--agent", default="abdl",
                        choices=["abdl", "heuristic"],
                        help="agent decision mode (default: abdl)")
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--backend", default="lightweight",
                        choices=["lightweight", "mujoco"],
                        help="physics backend (default: lightweight)")
    args = parser.parse_args()

    rclpy.init()
    node = VisBridge(args.opponent, args.agent, args.seed, args.backend)
    try:
        node.get_logger().info(
            f"G1 bridge up: agent={args.agent} opponent={args.opponent} "
            f"backend={args.backend} "
            f"— publish /bottlesumo/vis/markers (frame 'dohyo')"
        )
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
