# -*- coding: utf-8 -*-
"""core 单元测试 — 插件平台核心 (PLUGINIFY v1.0)。"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.event_bus import EventBus  # noqa: E402
from core.plugin_manager import PluginManager, PluginState  # noqa: E402


@pytest.fixture(scope="module")
def pm():
    m = PluginManager(ROOT)
    m.discover()
    return m


def test_discover_seven_plugins(pm):
    # P0 整改: 插件数只增不减 → 断言 ≥7 且核心 7 个必须存在 (动态, 与仓库 10 插件一致)
    assert len(pm.records()) >= 7
    ids = {r.plugin_id for r in pm.records()}
    core_ids = {
        "cognify.governance", "cognify.simulation", "cognify.cognitive",
        "cognify.sync", "cognify.meta", "cognify.debt", "cognify.dashboard",
    }
    assert core_ids <= ids, f"核心插件缺失: {core_ids - ids}"


def test_manifests_valid(pm):
    for rec in pm.records():
        assert rec.version != "?", f"{rec.plugin_id} 版本缺失"
        assert (Path(rec.path) / "plugin.py").exists(), f"{rec.plugin_id} 无入口"


def test_dependency_order(pm):
    order = pm.resolve_order()
    assert len(order) >= 7
    # sync 依赖 cognitive -> sync 必须排在 cognitive 之后
    assert order.index("cognify.sync") > order.index("cognify.cognitive")


def test_lifecycle_smoke(pm):
    report = pm.lifecycle_smoke()
    assert report["ok"], report["steps"]
    assert all(r.state == PluginState.UNLOADED for r in pm.records())


def test_hot_swap_simulation(pm):
    pm.load("cognify.simulation")
    pm.enable("cognify.simulation")
    assert pm.get("cognify.simulation").state == PluginState.ENABLED
    pm.disable("cognify.simulation")
    assert pm.get("cognify.simulation").state == PluginState.DISABLED
    pm.enable("cognify.simulation")  # 热插拔回切
    assert pm.get("cognify.simulation").state == PluginState.ENABLED
    pm.unload("cognify.simulation")


def test_dependency_gate(pm):
    """sync 未就绪时直接启用必须被拒绝 (红线 2)。"""
    with pytest.raises(RuntimeError):
        pm.enable("cognify.sync")  # sync 依赖 cognitive, 尚未加载


def test_dashboard_stub_honest(pm):
    """dashboard 是诚实桩: 不伪称服务能力。"""
    rec = pm.get("cognify.dashboard")
    assert rec is not None and not rec.verified


def test_event_bus_isolated_failure():
    bus = EventBus()

    def bad(_data):
        raise RuntimeError("boom")

    seen = []
    bus.subscribe("t", bad)
    bus.subscribe("t", lambda d: seen.append(d))
    n = bus.publish("t", 42)
    assert n == 1  # 坏订阅者不影响好订阅者
    assert seen == [42]
    assert any("boom" in str(e.get("error", "")) for e in bus.history())


def test_event_bus_unsubscribe():
    bus = EventBus()
    seen = []
    tok = bus.subscribe("x", lambda d: seen.append(d))
    bus.publish("x", 1)
    assert bus.unsubscribe(tok)
    bus.publish("x", 2)
    assert seen == [1]


def test_registry_roundtrip(tmp_path, pm):
    reg = tmp_path / "registry.json"
    pm.registry_path = reg
    pm.save_registry()
    data = json.loads(reg.read_text(encoding="utf-8"))
    assert data["count"] >= 7  # P0 整改: 动态插件数 (当前 10)
    assert data["plugins"][0]["id"].startswith("cognify.")
