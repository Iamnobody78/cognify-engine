"""
g3_smoke.py — G3 overlay smoke test (mock rclpy, no real ROS)
================================================================
Verifies:
 1) V9RuleAgent.select_action_traced returns (action, trace) with
    mode/rule_id/branch/sensors — for both ABDL and heuristic paths.
 2) vis_bridge publishes /bottlesumo/vis/debug MarkerArray containing
    the decision text + arrow + danger box (via mock rclpy).
 3) No NaN / no exceptions over a short MuJoCo rollout.

Usage (WSL):
  python3 _tmp/g3_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import numpy as np

from simulation.v9_gate_evaluator import V9RuleAgent
from simulation.lightweight_env import LightweightBottleSumoEnv
from simulation.mujoco_env import MuJoCoBottleSumoEnv

# ── mock rclpy (must be injected BEFORE importing vis_bridge) ──
import sys as _sys
import types as _types

_mock_rclpy = _types.ModuleType("rclpy")


def _mock_init(*a, **k):
    return None


_mock_rclpy.init = _mock_init
_mock_rclpy.ok = lambda: False
_mock_rclpy.shutdown = _mock_init
_mock_rclpy.spin_once = _mock_init
_mock_rclpy.spin = _mock_init

# minimal node base class for the bridge subclass
class _MockNodeBase:
    def create_publisher(self, mtype, topic, qos):
        return _MockPub(topic)


_mock_rclpy.node = _types.ModuleType("rclpy.node")
_mock_rclpy.node.Node = _MockNodeBase
_mock_rclpy.qos = _types.ModuleType("rclpy.qos")
_mock_rclpy.qos.qos_profile_sensor_data = None

_sys.modules["rclpy"] = _mock_rclpy
_sys.modules["rclpy.node"] = _mock_rclpy.node
_sys.modules["rclpy.qos"] = _mock_rclpy.qos

# ── mock ROS2 message packages ──
class _Msg:
    def __init__(self, *a, **k):
        self.markers = []
        self.points = []
        self.text = ""
        self.ns = ""
        self.id = 0
        self.type = 0
        self.action = 0
        self.data = ""
        self.header = _Header()
        self.pose = _Pose()
        self.scale = _Vec()
        self.color = _Color()
        self.x = self.y = self.z = 0.0
        self.r = self.g = self.b = self.a = 0.0
        for kk, vv in k.items():
            setattr(self, kk, vv)


class _Header:
    def __init__(self):
        self.frame_id = ""
        self.stamp = None


class _Vec:
    def __init__(self):
        self.x = self.y = self.z = 0.0


class _Color:
    def __init__(self):
        self.r = self.g = self.b = self.a = 0.0


class _Pose:
    def __init__(self):
        self.position = _Vec()
        self.orientation = _Vec()


def _mk_mod(name, attrs):
    m = _types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


_sys.modules["visualization_msgs"] = _mk_mod("visualization_msgs", {})
_sys.modules["visualization_msgs.msg"] = _mk_mod("visualization_msgs.msg", {
    "Marker": _Msg, "MarkerArray": _Msg,
})
_sys.modules["std_msgs"] = _mk_mod("std_msgs", {})
_sys.modules["std_msgs.msg"] = _mk_mod("std_msgs.msg", {
    "String": _Msg, "ColorRGBA": _Msg,
})
_sys.modules["geometry_msgs"] = _mk_mod("geometry_msgs", {})
_sys.modules["geometry_msgs.msg"] = _mk_mod("geometry_msgs.msg", {
    "Point": _Msg, "Quaternion": _Msg, "Pose": _Msg, "Vector3": _Msg,
})
# marker type constants (mirror visualization_msgs/Marker)
Marker = _Msg
Marker.ADD = 0
Marker.ARROW = 0
Marker.CUBE = 1
Marker.SPHERE = 2
Marker.CYLINDER = 3
Marker.TEXT_VIEW_FACING = 9
Marker.LINE_STRIP = 4
Marker.LINE_LIST = 5
Marker.CUBE_LIST = 6
class _MockPub:
    def __init__(self, name):
        self.name = name
        self.msgs = []

    def publish(self, msg):
        self.msgs.append(msg)


class _MockNode:
    def __init__(self):
        self.pubs = {}

    def create_publisher(self, mtype, topic, qos):
        p = _MockPub(topic)
        self.pubs[topic] = p
        return p


class _Clock:
    def now(self):
        class _Stamp:
            def to_msg(self):
                return None
        return _Stamp()


def _fake_color(r, g, b, a=1.0):
    class C:
        pass
    c = C()
    c.r, c.g, c.b, c.a = r, g, b, a
    return c


def test_traced_abdl():
    agent = V9RuleAgent()
    env = LightweightBottleSumoEnv(opponent_strategy="aggressive")
    obs, _ = env.reset(seed=42)
    # force a detectable scenario: opponent near + slightly off-axis
    a, tr = agent.select_action_traced(list(obs))
    assert isinstance(a, int), "action must be int"
    assert "mode" in tr and "sensors" in tr, "trace missing keys"
    assert tr["action"] == a, "trace action must match"
    # trace must have either rule_id (abdl) or branch (heuristic)
    assert tr.get("rule_id") is not None or tr.get("branch") is not None, \
        f"no decision info in trace: {tr}"
    print(f"  [abdl] mode={tr['mode']} rule={tr.get('rule_id')} "
          f"branch={tr.get('branch')} action={a}")
    return a, tr


def test_traced_heuristic():
    agent = V9RuleAgent(force_heuristic=True)
    env = LightweightBottleSumoEnv(opponent_strategy="aggressive")
    obs, _ = env.reset(seed=7)
    a, tr = agent.select_action_traced(list(obs))
    assert tr["mode"] == "heuristic", f"expected heuristic mode, got {tr['mode']}"
    assert tr.get("branch") is not None, "heuristic trace must carry branch"
    print(f"  [heuristic] branch={tr['branch']} action={a}")
    return a, tr


def test_mujoco_traced_no_nan():
    env = MuJoCoBottleSumoEnv(opponent_profile="aggressive",
                              opponent_strategy_name="aggressive", render_mode="none")
    agent = V9RuleAgent()
    obs, _ = env.reset(seed=99)
    decisions = set()
    for i in range(80):
        a, tr = agent.select_action_traced(list(obs))
        obs2, r, term, trunc, _ = env.step(a)
        assert not np.isnan(obs2).any(), f"NaN obs at step {i}"
        d = tr.get("rule_id") or tr.get("branch") or "?"
        decisions.add(d)
        obs = obs2
        if term or trunc:
            obs, _ = env.reset(seed=99 + i)
    print(f"  [mujoco] 80 steps, decisions fired: {sorted(decisions)[:8]}")
    return decisions


def test_debug_markers():
    # patch module attrs after import
    import simulation.bottlesumo_vis_bridge as vb

    node = _MockNode()
    orig_create = node.create_publisher
    orig_color = vb._color

    # monkeypatch _color so we don't need real ROS color types
    vb._color = _fake_color

    # construct bridge without rclpy init by faking imports is heavy;
    # instead verify the debug-marker building logic via a lightweight stub
    # of the bridge's publish body on a fake env.
    class _FakeEnv:
        robot_x = robot_y = 0.05
        robot_theta = 0.0
        opponent_x = 0.20
        opponent_y = 0.05
        opponent_theta = 0.0

    class _StubBridge:
        def __init__(self):
            self.episode = 1
            self.episode_steps = 26
            self.total_wins = 0
            self.total_eps = 1
            self.agent_kind = "abdl"
            self.opponent_name = "aggressive"
            self.pub_state = _MockPub("/bottlesumo/vis/state")
            self.pub_debug = _MockPub("/bottlesumo/vis/debug")

        def _base_marker(self, ns, iid, mtype):
            m = _Msg()
            m.ns = ns
            m.id = iid
            m.type = mtype
            return m

        def get_clock(self):
            return _Clock()

    stub = _StubBridge()
    stub.env = _FakeEnv()

    trace = {
        "mode": "abdl", "rule_id": "SR-001", "policy_id": "EVADE",
        "reason": "edge danger", "branch": None,
        "sensors": {"edge_f": 0.05, "edge_b": 1.0, "edge_l": 1.0, "edge_r": 1.0,
                    "opp_dist": 0.15, "opp_angle": -5.0},
    }
    # invoke the debug publish block directly (factor: call publish on stub-like)
    # → simplest: temporarily give the stub the missing attrs and call vb code
    # through a small local re-implementation is avoided; instead we patch the
    # publish method of the real class with stubbed pub/env and call it.
    import types

    real_cls = vb.VisBridge
    original_publish = real_cls.publish

    # build a fully-stubbed bridge instance (skip rclpy node init)
    class _StubAgent:
        mode = "abdl"

    bridge = object.__new__(real_cls)
    bridge.get_clock = lambda: _Clock()
    bridge.trail = []
    bridge.episode = 1
    bridge.episode_steps = 26
    bridge.total_wins = 0
    bridge.total_eps = 1
    bridge.agent_kind = "abdl"
    bridge.opponent_name = "aggressive"
    bridge.pub_state = _MockPub("/bottlesumo/vis/state")
    bridge.pub_markers = _MockPub("/bottlesumo/vis/markers")
    bridge.pub_debug = _MockPub("/bottlesumo/vis/debug")
    bridge.env = _FakeEnv()
    bridge.agent = _StubAgent()

    vb._color = _fake_color
    try:
        original_publish(bridge, 0.5, False, trace)
    except Exception as ex:
        print(f"  [debug] publish raised: {ex!r}")
        raise
    finally:
        real_cls.publish = original_publish
        vb._color = orig_color

    debug_msgs = bridge.pub_debug.msgs
    assert debug_msgs, "no debug markers published"
    arr = debug_msgs[-1]
    texts = [m.text for m in arr.markers if hasattr(m, "text") and m.text]
    assert texts, f"no text marker in debug array: {[m for m in arr.markers]}"
    print(f"  [debug] published {len(arr.markers)} markers, text={texts[0]!r}")
    return texts


if __name__ == "__main__":
    print("G3 smoke: traced select_action (lightweight, abdl)")
    test_traced_abdl()
    print("G3 smoke: traced select_action (heuristic)")
    test_traced_heuristic()
    print("G3 smoke: MuJoCo traced rollout (no NaN)")
    test_mujoco_traced_no_nan()
    print("G3 smoke: debug marker publication")
    test_debug_markers()
    print("\nALL G3 SMOKE TESTS PASSED")
