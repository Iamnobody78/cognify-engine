"""Regression tests for lightweight env fixes (2026-08-05).

Covers: opponent spawn inside ring, edge sensor ramp (was dead),
gymnasium-style reset/step API used by the V9 gate evaluator.
"""

import math

import pytest

from simulation.lightweight_env import (
    LightweightBottleSumoEnv,
    DOHYO_RADIUS,
    ROBOT_RADIUS,
)


@pytest.fixture
def env():
    return LightweightBottleSumoEnv(opponent_profile="aggressive", seed=7)


def test_opponent_spawns_inside_ring(env):
    """DEBT D-005 fix: opponent must spawn INSIDE the dohyo (was up to
    DOHYO_RADIUS+0.2 away → out of bounds → instant +200 'wins')."""
    for seed in range(20):
        obs, _ = env.reset(seed=seed)
        opp_dc = math.hypot(env.opponent_x, env.opponent_y)
        assert opp_dc < DOHYO_RADIUS - ROBOT_RADIUS, (
            f"seed {seed}: opponent spawned off-ring at dist {opp_dc:.3f}"
        )


def test_edge_sensor_ramp_is_live(env):
    """FIXED 2026-08-05: sensors must vary across the arena (0=center, 1=edge).
    Before: constant 1.0 until 0.32m, then robot already falling → dead sensor."""
    env.reset(seed=0)
    # Place robot near center: sensor should read high (safe).
    env.robot_x, env.robot_y = 0.0, 0.0
    env.robot_theta = 0.0
    obs_center = env._get_obs()
    # Place robot near edge: sensor should read low (danger).
    env.robot_x = DOHYO_RADIUS * 0.9
    env.robot_y = 0.0
    env.robot_theta = 0.0
    obs_edge = env._get_obs()
    assert obs_center[0] > 0.85, f"center front sensor should be safe, got {obs_center[0]}"
    assert obs_edge[0] < 0.5, f"edge front sensor should warn, got {obs_edge[0]}"
    assert obs_center[0] > obs_edge[0], "sensor must decrease toward the edge"


def test_reset_returns_obs_info_tuple(env):
    """gymnasium-style API expected by v9_gate_evaluator."""
    out = env.reset(seed=0)
    assert isinstance(out, tuple) and len(out) == 2


def test_step_returns_five_tuple(env):
    """gymnasium-style step: (obs, reward, terminated, truncated, info)."""
    obs, _ = env.reset(seed=0)
    out = env.step(3)
    assert isinstance(out, tuple) and len(out) == 5


def test_opponent_strategy_override(env):
    """V9 gate uses callable opponent_strategy — env must honor it."""
    calls = []

    def strat(obs, step):
        calls.append(step)
        return 3  # forward

    env.opponent_strategy = strat
    obs, _ = env.reset(seed=0)
    env.step(3)
    assert len(calls) >= 1, "opponent strategy was never called"
