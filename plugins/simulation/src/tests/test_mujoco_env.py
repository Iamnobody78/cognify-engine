"""Unit tests for MuJoCoBottleSumoEnv (Phase G / MuJoCo integration).

Covers: gym API shape, action mapping bounds, edge sensor semantics,
reset determinism, physics sanity (motion, push-out win), termination
semantics (out-of-bounds / win / timeout), and observation dtype/space.

These are the physics-backend twin of tests/test_lightweight_env.py —
both environments must stay API-compatible for the V9 gate evaluator.
"""

import math

import numpy as np
import pytest

from simulation.mujoco_env import (
    MuJoCoBottleSumoEnv,
    DOHYO_RADIUS,
    DOHYO_SAFE_RADIUS,
    ROBOT_RADIUS,
    MAX_STEPS,
    MAX_WHEEL_VEL,
)
from simulation.wheel_to_discrete import Action, ACTION_MAP


def _linear(action):
    return ACTION_MAP.get(action, ACTION_MAP[Action.STOP])[0]


def _angular(action):
    return ACTION_MAP.get(action, ACTION_MAP[Action.STOP])[1]


@pytest.fixture
def env():
    return MuJoCoBottleSumoEnv(opponent_profile="aggressive", seed=7)


# ── gym API shape ──

def test_reset_returns_7dim_obs_and_info(env):
    obs, info = env.reset(seed=42)
    assert isinstance(obs, np.ndarray)
    assert obs.shape == (7,)
    assert info == {}


def test_observation_space_matches_lightweight(env):
    """V9 gate requires backend-swappable observation (identical Box).

    Sprint 37 T1: the lightweight backend upgraded to a 9-dim obs (appended
    opponent velocity v_fwd/v_right, FP-RL-003 fix); MuJoCo remains on the
    original 7-dim contract until the physics backend is ported (S38+).
    Backend-swap contract is now: identical FIRST 7 dims (policy prefix
    transfer), lightweight carries the 9-dim extension.

    Contract (prefix mirrors lightweight_env exactly): speed low is -0.7 in
    the declared Box even though obs construction clips it to [0.0, 0.7]."""
    from simulation.lightweight_env import LightweightBottleSumoEnv as L
    assert env.observation_space.shape == (7,)
    low, high = env.observation_space.low, env.observation_space.high
    assert low[0] == 0.0 and high[0] == 1.0       # edge sensors [0,1]
    assert low[5] == -180.0 and high[5] == 180.0  # opponent angle deg
    # prefix contract: lightweight's first 7 dims match MuJoCo's 7 dims
    lw = L(opponent_profile="aggressive", seed=7)
    assert lw.observation_space.shape == (9,)
    assert np.array_equal(low, lw.observation_space.low[:7])
    assert np.array_equal(high, lw.observation_space.high[:7])
    # speed clip is applied in obs (never negative in practice)
    env.reset(seed=1)
    obs, _, _, _, _ = env.step(Action.STOP)
    assert obs[6] >= 0.0


def test_action_space_is_discrete_21(env):
    assert env.action_space.n == 21


def test_step_returns_five_tuple(env):
    env.reset(seed=42)
    out = env.step(0)
    assert len(out) == 5
    obs, reward, terminated, truncated, info = out
    assert obs.shape == (7,)
    assert isinstance(reward, float)
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert set(info) >= {"robot_x", "robot_y", "opponent_x", "opponent_y",
                         "robot_out", "opp_out", "steps"}


# ── action mapping (differential drive consistency) ──

def test_all_21_actions_map_to_finite_velocities(env):
    """Every action in Discrete(21) must map to a (linear, angular) command
    that stays inside the robot's physical envelope."""
    env.reset(seed=0)
    for a in range(21):
        lin, ang = ACTION_MAP.get(a, ACTION_MAP[Action.STOP])
        assert math.isfinite(lin) and math.isfinite(ang)
        # wheel targets computed in step() must be within MAX_WHEEL_VEL
        v_l = (lin - ang * 0.13 / 2) / 0.017
        v_r = (lin + ang * 0.13 / 2) / 0.017
        assert abs(v_l) <= MAX_WHEEL_VEL + 1e-6, f"action {a}: wheel_l target {v_l:.2f} rad/s"
        assert abs(v_r) <= MAX_WHEEL_VEL + 1e-6, f"action {a}: wheel_r target {v_r:.2f} rad/s"


def test_stop_action_is_zero(env):
    assert _linear(Action.STOP) == 0.0
    assert _angular(Action.STOP) == 0.0


# ── edge sensor semantics ──

def test_edge_sensors_in_unit_range(env):
    """Sensors are normalized distances: 1.0 = safe center, 0.0 = at rim."""
    env.reset(seed=1)
    obs, _, _, _, _ = env.step(Action.FW_MAX)
    for i in range(4):
        assert 0.0 <= obs[i] <= 1.0, f"edge sensor {i} out of [0,1]: {obs[i]}"


def test_edge_sensors_are_directional(env):
    """Queue #4 regression: 4 edge sensors must NOT all be equal.

    Root cause of abdl 40% on MuJoCo: direction-neutral edges made
    min(edge_f..r) a single rim value -> ABDL rules formed a dead zone
    (rim 0.128~0.16m) where no rule fired -> '?' FW_SLOW crawl -> timeout.
    Fixed by mirroring lightweight_env's directional probes (offset by
    ROBOT_RADIUS along heading/perpendicular). At a non-center pose with
    a heading facing the rim, front vs back must differ.

    F-109 (2026-08-07): reset now spawns the robot FACING the opponent
    (lightweight alignment), so FW_MAX from center terminates on the
    opponent within a few steps — the old "drive 60 FW_MAX steps from
    center" trajectory can no longer reach the rim to manufacture an
    edge crossing. Also, rotation alone cannot create directionality
    (4 probes are symmetric around the body; turning only permutes the
    labels). Directionality is a POSITION effect: a probe reads 0.0 iff
    it pokes past the rim. So we teleport via qpos to an off-center pose
    facing the rim (the pose-injection path the docstring allowed) and
    assert front (off-rim, 0.0) < back (on-rim, > 0).
    """
    from simulation.lightweight_env import LightweightBottleSumoEnv

    env.reset(seed=5)
    # qpos layout: robot_free(7) at offset 0: [x, y, z, qw, qx, qy, qz].
    # Pose: center (0.36, 0.0), heading +x (toward the rim).
    #   front probe  = 0.36 + ROBOT_RADIUS(0.075) = 0.435 > 0.40 -> off -> 0.0
    #   back probe   = 0.36 - 0.075 = 0.285 < 0.40      -> on  -> 1 - 0.9*0.9 = 0.19
    #   lateral      = hypot(0.36, 0.075) = 0.368 < 0.40 -> on  -> 0.19
    q = env.data.qpos
    q[0:3] = [0.36, 0.0, 0.03]
    q[3:7] = [1.0, 0.0, 0.0, 0.0]  # heading 0 quaternion
    env._sync_state()
    obs = env._get_obs()
    front, back, left, right = (float(v) for v in obs[:4])
    assert front != back, f"front {front} == back {back}: probes not directional"
    assert front < back, f"front {front} should read LOWER than back {back} at rim pose"
    assert len({front, back, left, right}) > 1, "all four edge sensors identical"


def test_edge_obs_matches_lightweight_elementwise():
    """Cross-backend contract: same reset pose -> same edge/opp obs.

    Queue #4 regression: observation-space equality was only checked on
    Box boundaries; actual values diverged (MuJoCo direction-neutral edges
    vs lightweight directional). Now both use the same formula. Compare at
    reset (identical pose) + over the first 30 steps with a loose tolerance
    (MuJoCo physics vs kinematic drift only shifts distance traveled).
    """
    from simulation.lightweight_env import LightweightBottleSumoEnv

    mj = MuJoCoBottleSumoEnv(opponent_profile="aggressive",
                             opponent_strategy_name="aggressive", render_mode="none")
    lw = LightweightBottleSumoEnv(opponent_profile="aggressive")

    # identical seeds → identical robot/opponent placement
    obs_mj, _ = mj.reset(seed=123)
    obs_lw, _ = lw.reset(seed=123)

    # same reset pose → edges (0..3) & opp_dist (4) must agree tightly
    for i in range(5):
        assert abs(float(obs_mj[i]) - float(obs_lw[i])) < 0.02, \
            f"reset divergence at idx {i}: mj={obs_mj[i]} lw={obs_lw[i]}"
    # speed (idx 6) starts at 0 in both
    assert abs(float(obs_mj[6]) - float(obs_lw[6])) < 1e-6

    # over 30 FW_MAX steps: directionality pattern must match even though
    # absolute values drift (MuJoCo advances less per step)
    edge_mism = 0
    for _ in range(30):
        obs_mj, _, term_mj, trunc_mj, _ = mj.step(Action.FW_MAX)
        obs_lw, _, term_lw, trunc_lw, _ = lw.step(Action.FW_MAX)
        # both robots move "forward"; edge_front (idx 0) must be the
        # smallest edge in both backends (heading toward the rim) — this
        # is the directional semantic that was missing before the fix.
        if not (term_mj or trunc_mj) and not (term_lw or trunc_lw):
            if min(obs_mj[:4]) == obs_mj[0] and min(obs_lw[:4]) != obs_lw[0]:
                edge_mism += 1
            if min(obs_lw[:4]) == obs_lw[0] and min(obs_mj[:4]) != obs_mj[0]:
                edge_mism += 1
    assert edge_mism == 0, f"directionality pattern diverged {edge_mism} steps"


def test_forward_action_moves_robot(env):
    """FW_MAX must produce net forward displacement (physics engine alive)."""
    env.reset(seed=42)
    env.step(Action.FW_MAX)
    x0, y0 = env.robot_x, env.robot_y
    # reset again for a clean run, then drive forward 20 steps
    obs, _ = env.reset(seed=42)
    for _ in range(20):
        obs, _, term, trunc, _ = env.step(Action.FW_MAX)
    dx = env.robot_x - x0
    dy = env.robot_y - y0
    assert math.hypot(dx, dy) > 0.05, f"robot barely moved: {math.hypot(dx, dy):.4f} m"


def test_no_nan_in_obs_over_200_random_steps(env):
    """Stability regression: no NaN/Inf in obs, position, or speed."""
    env.reset(seed=11)
    for i in range(200):
        obs, _, term, trunc, _ = env.step(i % 21)
        assert np.isfinite(obs).all(), f"NaN/Inf obs at step {i}"
        assert math.isfinite(env.robot_x) and math.isfinite(env.opponent_x)
        if term or trunc:
            env.reset(seed=100 + i)


# ── termination semantics ──

def test_timeout_truncation_at_max_steps(env):
    """500-step timeout must be truncation, never a win."""
    env.reset(seed=3)
    obs, _, term, trunc, _ = env.step(Action.STOP)
    # STOP keeps robot near center; run to timeout
    for _ in range(MAX_STEPS - 1):
        obs, reward, term, trunc, _ = env.step(Action.STOP)
    assert trunc is True, "expected truncation at 500 steps"
    # win = terminated with reward > 5; STOP cannot win
    assert term is False, "STOP must never terminate"


def test_out_of_bounds_detection():
    """Robot center beyond DOHYO_RADIUS - ROBOT_RADIUS = 0.325 triggers
    termination (V9 gate footprint-edge semantics, matches lightweight)."""
    env = MuJoCoBottleSumoEnv(opponent_strategy_name="passive", seed=9)
    env.reset(seed=9)
    # teleport robot just outside the ring via MuJoCo state
    import simulation.mujoco_env as me
    r = math.hypot(env.robot_x, env.robot_y)
    # force robot beyond rim with a manual qpos write (test-only probe)
    d = env.data
    d.qpos[0] = 0.35
    d.qpos[1] = 0.0
    d.qpos[2] = 0.03
    me.mujoco.mj_forward(env.model, d)
    env._sync_state()
    obs, reward, term, trunc, info = env.step(Action.STOP)
    assert info["robot_out"] is True or term is True, \
        "robot teleported beyond rim must register out-of-bounds"


def test_opponent_passive_can_be_pushed_out_for_win():
    """Regression: robot must physically shove a passive opponent off the ring
    (terminated + reward > 5 = win). Physics push-out path."""
    def passive(obs, steps):
        return (0.0, 0.0)
    env = MuJoCoBottleSumoEnv(
        opponent_strategy=passive, opponent_strategy_name="passive", seed=5)
    obs, _ = env.reset(seed=5)
    # spawn opponent near rim in front of robot, then drive forward
    import simulation.mujoco_env as me
    d = env.data
    # robot at center facing +x; opponent 0.28 m ahead (inside ring)
    d.qpos[0:3] = [0.0, 0.0, 0.03]
    d.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]  # yaw=0 -> faces +x
    d.qpos[me.OPP_QPOS_OFFSET + 0: me.OPP_QPOS_OFFSET + 3] = [0.30, 0.0, 0.03]
    d.qpos[me.OPP_QPOS_OFFSET + 3: me.OPP_QPOS_OFFSET + 7] = [1.0, 0.0, 0.0, 0.0]
    me.mujoco.mj_forward(env.model, d)
    env._sync_state()
    won = False
    for _ in range(60):
        obs, reward, term, trunc, info = env.step(Action.FW_MAX)
        if term and reward > 5:
            won = True
            break
        if trunc:
            break
    assert won, "robot failed to push passive opponent out within 60 steps"


def test_reset_determinism_same_seed(env):
    """Same seed -> identical initial state (spawn + heading)."""
    o1, _ = env.reset(seed=77)
    r1 = (env.robot_x, env.robot_y, env.robot_theta)
    o2, _ = env.reset(seed=77)
    r2 = (env.robot_x, env.robot_y, env.robot_theta)
    assert np.allclose(o1, o2)
    assert r1 == r2


def test_opponent_inside_ring_on_reset(env):
    """DEBT D-005 analog: opponent must spawn inside the ring."""
    for seed in range(15):
        obs, _ = env.reset(seed=seed)
        opp_dc = math.hypot(env.opponent_x, env.opponent_y)
        assert opp_dc < DOHYO_RADIUS - ROBOT_RADIUS, \
            f"seed {seed}: opponent off-ring at {opp_dc:.3f}"
