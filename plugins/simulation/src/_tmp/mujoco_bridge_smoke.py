#!/usr/bin/env python3
"""Smoke test: VisBridge --backend mujoco branch without a ROS2 runtime.

Mocks rclpy + ROS message classes, then instantiates VisBridge with the
MuJoCo backend and verifies marker assembly from real physics state.

Run: python3 _tmp/mujoco_bridge_smoke.py  (from project root)
"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "simulation"))

# ── mock rclpy ──
class _Clock:
    def now(self):
        class _M:
            def to_msg(self):
                return 0
        return _M()


class _Logger:
    def info(self, *a, **k): print("[bridge]", *a)
    def error(self, *a, **k): print("[bridge ERR]", *a)


class _Node:
    def __init__(self, name):
        self.name = name
        self._log = _Logger()
    def create_publisher(self, *a, **k):
        class P:
            def publish(self, msg):
                self.msg = msg
        return P()
    def get_logger(self): return self._log
    def get_clock(self): return _Clock()


rclpy = types.ModuleType("rclpy")
rclpy.ok = lambda: False
rclpy.init = lambda: None
rclpy.shutdown = lambda: None
rclpy.node = types.SimpleNamespace(Node=_Node)

# ── mock ROS msg modules ──
def _mk_msg(name):
    return types.ModuleType(name)


def _mk_cls(**fields):
    def __init__(self, **kw):
        for f, d in self._defaults().items():
            setattr(self, f, d)
        for f, v in kw.items():
            setattr(self, f, v)
    m = types.SimpleNamespace(__init__=__init__)
    cls = types.new_class("_" + "x", exec_body=lambda ns: ns.update(
        __init__=__init__, _defaults=lambda self, _d=fields: _d))
    return cls


vis_msgs = _mk_msg("visualization_msgs.msg")
_H = types.SimpleNamespace(frame_id="", stamp=types.SimpleNamespace(sec=0, nanosec=0))
MarkerCls = _mk_cls(header=_H, ns="", id=0, type=0, action=0,
                    pose=types.SimpleNamespace(position=types.SimpleNamespace(x=0.0, y=0.0, z=0.0),
                                               orientation=types.SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0)),
                    scale=types.SimpleNamespace(x=0.0, y=0.0, z=0.0),
                    color=types.SimpleNamespace(r=1.0, g=1.0, b=1.0, a=1.0),
                    points=[])
for _cn, _cv in {"CYLINDER": 3, "ARROW": 0, "LINE_STRIP": 4, "ADD": 0}.items():
    setattr(MarkerCls, _cn, _cv)
vis_msgs.Marker = MarkerCls
vis_msgs.MarkerArray = _mk_cls(markers=[])
std_msgs = _mk_msg("std_msgs.msg")
std_msgs.String = _mk_cls(data="")
std_msgs.ColorRGBA = _mk_cls(r=0.0, g=0.0, b=0.0, a=1.0)
geom_msgs = _mk_msg("geometry_msgs.msg")
geom_msgs.Point = _mk_cls(x=0.0, y=0.0, z=0.0)
geom_msgs.Quaternion = _mk_cls(x=0.0, y=0.0, z=0.0, w=1.0)

sys.modules["rclpy"] = rclpy
sys.modules["rclpy.node"] = rclpy.node
sys.modules["visualization_msgs"] = types.ModuleType("visualization_msgs")
sys.modules["visualization_msgs.msg"] = vis_msgs
sys.modules["std_msgs"] = types.ModuleType("std_msgs")
sys.modules["std_msgs.msg"] = std_msgs
sys.modules["geometry_msgs"] = types.ModuleType("geometry_msgs")
sys.modules["geometry_msgs.msg"] = geom_msgs

# ── import bridge (mocked) and run mujoco branch ──
from simulation.bottlesumo_vis_bridge import VisBridge

node = VisBridge(opponent_name="counter", agent_kind="abdl", seed=20260805, backend="mujoco")
assert node.backend == "mujoco", node.backend
from simulation.mujoco_env import MuJoCoBottleSumoEnv
assert isinstance(node.env, MuJoCoBottleSumoEnv), type(node.env)

# run a few steps + publish (marker assembly from real MuJoCo state)
import time
t0 = time.time()
for i in range(30):
    action = node.agent.select_action(node.obs)
    node.obs, reward, terminated, truncated, _ = node.env.step(action)
    node.episode_steps += 1
    done = bool(terminated or truncated)
    node.publish(float(reward), done)
    if done:
        node.episode += 1
        node.episode_steps = 0
        node.obs, _ = node.env.reset(seed=node.seed + 1000 * node.episode)
print(f"bridge mujoco smoke OK: 30 steps, {node.episode} episodes, {time.time()-t0:.1f}s")
print(f"  robot@({node.env.robot_x:.3f},{node.env.robot_y:.3f}) theta={node.env.robot_theta:.2f}")
print(f"  opponent@({node.env.opponent_x:.3f},{node.env.opponent_y:.3f})")
print("  trail points:", len(node.trail))
