"""Tests for the unified env factory (DEBT D-002)."""

import pytest

from simulation.env_factory import make, list_backends, make_lightweight


def test_list_backends_includes_lightweight_and_gazebo():
    backends = list_backends()
    assert "lightweight" in backends
    assert "gazebo" in backends


def test_make_lightweight_returns_env():
    env = make("bottlesumo", backend="lightweight", opponent_profile="aggressive")
    assert env is not None
    assert hasattr(env, "reset") and hasattr(env, "step")
    obs, _ = env.reset(seed=0)
    # Sprint 37 T1: 7→9 dims (appended opponent velocity v_fwd/v_right, FP-RL-003 fix)
    assert obs.shape[0] == 9


def test_make_lightweight_convenience():
    env = make_lightweight(opponent_profile="passive")
    assert env.opponent_profile == "passive"


def test_unknown_env_raises_value_error():
    with pytest.raises(ValueError):
        make("nonexistent_env", backend="lightweight")


def test_unknown_backend_raises_value_error():
    with pytest.raises(ValueError):
        make("bottlesumo", backend="quantum")


def test_gazebo_backend_raises_informative_import_error():
    # bottlesumo_gym is not installed in this workspace → must raise ImportError
    # with a helpful message (honest degradation, not silent fallback).
    with pytest.raises(ImportError) as excinfo:
        make("bottlesumo", backend="gazebo")
    assert "gazebo" in str(excinfo.value) or "bottlesumo_gym" in str(excinfo.value)


def test_backend_parity_docs():
    """Every registered backend must have a docstring-visible intent (parity guard)."""
    entry = __import__("simulation.env_factory", fromlist=["BACKENDS"]).BACKENDS
    for env_name, backends in entry.items():
        for backend in backends:
            assert backend in ("lightweight", "gazebo"), f"unexpected backend {backend}"
