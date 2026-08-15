"""RealityBridge P1 test suite.

Tests cover:
  - Model serialization (RealitySample ↔ dict)
  - Simulation adapter (sample emission)
  - Training log adapter (CSV / JSONL parsing)
  - User feedback adapter (keyword extraction)
  - Shadow loop adapter (version snapshots, gate history)
  - RealityCache (insert / query / stats)
  - RealityBridge orchestration (end-to-end gap detection)
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import pytest

# Ensure bottlesumo_pi is on path
import sys
_here = Path(__file__).resolve().parent.parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def temp_dir():
    with tempfile.TemporaryDirectory() as td:
        yield Path(td)


@pytest.fixture
def bridge_cache_db(temp_dir):
    """Provide a RealityBridge with a temp SQLite DB."""
    from bottlesumo_pi.core.reality_bridge.bridge import RealityBridge
    db = temp_dir / "test_reality.sqlite"
    return RealityBridge(db_path=db)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Model tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRealitySample:
    """RealitySample serialization round-trip."""

    def test_default_construction(self):
        from bottlesumo_pi.core.reality_bridge.models import RealitySample
        s = RealitySample()
        assert s.channel.value == "simulation"
        assert s.sample_id is not None
        assert len(s.sample_id) == 12

    def test_dict_roundtrip(self):
        from bottlesumo_pi.core.reality_bridge.models import Channel, RealitySample
        s = RealitySample(
            channel=Channel.TRAINING_LOG,
            episode_id=42,
            reward=1.5,
            loss=0.03,
            q_value=12.5,
            epsilon=0.1,
            tags=["dqn", "v11"],
        )
        d = s.to_dict()
        s2 = RealitySample.from_dict(d)
        assert s2.channel == Channel.TRAINING_LOG
        assert s2.episode_id == 42
        assert s2.reward == 1.5
        assert s2.loss == 0.03
        assert s2.tags == ["dqn", "v11"]

    def test_full_fields_roundtrip(self):
        from bottlesumo_pi.core.reality_bridge.models import Channel, RealitySample
        s = RealitySample(
            channel=Channel.USER_FEEDBACK,
            episode_id=10,
            step=5,
            obs=[0.5, 0.3, 0.1, 0.2, 1.0, 0.8, 0.0],
            action=3,
            reward=-1.0,
            win=False,
            episode_length=120,
            annotation="should have retreated",
            corrected_action=12,
            confidence=0.9,
            gate_decisions={"symbolic": True, "fuzzy": False},
            tags=["edge_case", "explicit"],
            extra={"source": "test"},
        )
        d = s.to_dict()
        s2 = RealitySample.from_dict(d)
        assert s2.channel == Channel.USER_FEEDBACK
        assert s2.obs == [0.5, 0.3, 0.1, 0.2, 1.0, 0.8, 0.0]
        assert s2.corrected_action == 12
        assert s2.gate_decisions == {"symbolic": True, "fuzzy": False}
        assert "edge_case" in s2.tags


class TestGapReport:
    def test_serialization(self):
        from bottlesumo_pi.core.reality_bridge.models import GapReport, Severity
        r = GapReport(
            simulation_gap=0.1,
            training_gap=0.05,
            overall_gap=0.12,
            severity=Severity.LOW,
        )
        d = r.to_dict()
        assert d["simulation_gap"] == 0.1
        assert d["severity"] == "low"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Simulation adapter tests
# ═══════════════════════════════════════════════════════════════════════════

class TestSimulationAdapter:
    def test_basic_wrap(self):
        """SimulationAdapter wraps a simple mock env."""
        from bottlesumo_pi.core.reality_bridge.adapters import SimulationAdapter

        class MockEnv:
            def reset(self):
                return [0.5, 0.3, 0.1, 0.0, 1.0, 0.0, 0.0]

            def step(self, action):
                return ([0.6, 0.4, 0.2, 0.1, 0.9, 0.1, 0.0], 0.5, False, {})

        env = MockEnv()
        adapter = SimulationAdapter(env)

        samples = []
        adapter.on_sample(samples.append)

        adapter.reset()
        adapter.step(3)

        assert len(samples) == 2  # reset + step
        assert samples[0].step == 0
        assert samples[1].step == 1
        assert samples[1].action == 3

    def test_win_detection(self):
        from bottlesumo_pi.core.reality_bridge.adapters import SimulationAdapter

        class WinEnv:
            def reset(self):
                return [0.0] * 7

            def step(self, action):
                return ([0.0] * 7, 10.0, True, {"win": True})

        env = WinEnv()
        adapter = SimulationAdapter(env)

        samples = []
        adapter.on_sample(samples.append)

        adapter.reset()
        adapter.step(0)

        assert samples[-1].win is True
        assert samples[-1].reward == 10.0


# ═══════════════════════════════════════════════════════════════════════════
# 3. Training log adapter tests
# ═══════════════════════════════════════════════════════════════════════════

class TestTrainingLogAdapter:
    def test_parse_csv(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.adapters import TrainingLogAdapter

        csv_path = temp_dir / "train.csv"
        csv_path.write_text(
            "episode,loss,reward,win,epsilon,q_value,lr,steps\n"
            "0,2.5,-1.0,0,1.0,0.0,0.001,100\n"
            "1,2.0,-0.5,0,0.9,5.0,0.001,120\n"
            "2,1.5,5.0,1,0.8,12.0,0.001,80\n"
        )

        adapter = TrainingLogAdapter()
        samples = adapter.parse_csv(csv_path)

        assert len(samples) == 3
        assert samples[0].loss == 2.5
        assert samples[0].win is False
        assert samples[2].loss == 1.5
        assert samples[2].win is True
        assert samples[2].q_value == 12.0

    def test_parse_jsonl(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.adapters import TrainingLogAdapter

        jsonl_path = temp_dir / "train.jsonl"
        jsonl_path.write_text(
            '{"episode": 0, "loss": 2.5, "reward": -1.0, "win": false}\n'
            '{"episode": 1, "loss": 1.5, "reward": 5.0, "win": true}\n'
        )

        adapter = TrainingLogAdapter()
        samples = adapter.parse_jsonl(jsonl_path)

        assert len(samples) == 2
        assert samples[0].loss == 2.5
        assert samples[1].win is True

    def test_iter_samples(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.adapters import TrainingLogAdapter

        csv_path = temp_dir / "iter.csv"
        csv_path.write_text(
            "episode,loss,reward\n0,2.0,-1.0\n1,1.0,5.0\n"
        )

        adapter = TrainingLogAdapter()
        results = list(adapter.iter_samples(csv_path))
        assert len(results) == 2

    def test_column_aliases(self, temp_dir):
        """Test that column aliases (ep, eps, avg_loss, etc.) are handled."""
        from bottlesumo_pi.core.reality_bridge.adapters import TrainingLogAdapter

        csv_path = temp_dir / "aliases.csv"
        csv_path.write_text(
            "ep,avg_loss,avg_reward,won,eps\n"
            "0,2.5,-1.0,0,1.0\n"
        )

        adapter = TrainingLogAdapter()
        samples = adapter.parse_csv(csv_path)
        assert len(samples) == 1
        assert samples[0].loss == 2.5
        assert samples[0].epsilon == 1.0


# ═══════════════════════════════════════════════════════════════════════════
# 4. User feedback adapter tests
# ═══════════════════════════════════════════════════════════════════════════

class TestUserFeedbackAdapter:
    def test_text_keyword_extraction(self):
        from bottlesumo_pi.core.reality_bridge.adapters import UserFeedbackAdapter

        adapter = UserFeedbackAdapter()
        text = (
            "The agent made a wrong decision at the edge. "
            "It should have retreated instead of pushing. "
            "Correct action to 12. scenario: edge_defense_v1"
        )
        samples = adapter.parse_text(text)

        assert len(samples) >= 2  # "should have retreated" + "wrong decision"

    def test_corrected_action_extraction(self):
        from bottlesumo_pi.core.reality_bridge.adapters import UserFeedbackAdapter

        adapter = UserFeedbackAdapter()
        text = "wrong move, corrected action: 8"
        samples = adapter.parse_text(text)

        assert any(s.corrected_action == 8 for s in samples)

    def test_json_feedback_file(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.adapters import UserFeedbackAdapter

        fb_path = temp_dir / "feedback.json"
        fb_path.write_text(json.dumps([
            {
                "scenario": "edge_defense",
                "annotation": "Agent pushed when it should retreat",
                "corrected_action": 12,
                "confidence": 0.95,
            },
        ]))

        adapter = UserFeedbackAdapter()
        samples = adapter.parse_file(fb_path)

        assert len(samples) == 1
        assert samples[0].corrected_action == 12
        assert samples[0].confidence == 0.95

    def test_explicit_feedback(self):
        from bottlesumo_pi.core.reality_bridge.adapters import UserFeedbackAdapter

        adapter = UserFeedbackAdapter()
        sample = adapter.add_explicit_feedback(
            scenario="corner_trap",
            annotation="Agent got stuck in corner, should turn",
            corrected_action=15,
        )

        assert sample.annotation == "Agent got stuck in corner, should turn"
        assert sample.corrected_action == 15

    def test_aggregation(self):
        from bottlesumo_pi.core.reality_bridge.adapters import UserFeedbackAdapter

        adapter = UserFeedbackAdapter()
        adapter.add_explicit_feedback("edge_defense", "push->retreat", 12)
        adapter.add_explicit_feedback("edge_defense", "push->retreat", 12)
        adapter.add_explicit_feedback("edge_defense", "different approach", 5)

        agg = adapter.get_aggregated()
        assert "edge_defense" in agg
        fb = agg["edge_defense"]
        assert fb.annotation_count == 3
        assert fb.corrected_action_counts.get(12) == 2
        assert fb.corrected_action_counts.get(5) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 5. Shadow loop adapter tests
# ═══════════════════════════════════════════════════════════════════════════

class TestShadowLoopAdapter:
    def test_version_snapshot(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.adapters import ShadowLoopAdapter

        snap_path = temp_dir / "version_v9.3.json"
        snap_path.write_text(json.dumps({
            "version": "v9.3",
            "rules": [{"id": "R001"}, {"id": "R002"}, {"id": "R003"}],
            "stats": {"winrate": 0.47, "total_episodes": 100},
        }))

        adapter = ShadowLoopAdapter()
        samples = adapter.parse_version_snapshot(snap_path)

        assert len(samples) == 1
        assert samples[0].rule_version == "v9.3"
        assert samples[0].extra["rule_count"] == 3

    def test_gate_history(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.adapters import ShadowLoopAdapter

        gate_path = temp_dir / "gate_history.json"
        gate_path.write_text(json.dumps([
            {"episode": 1, "step": 10, "version": "v9.3",
             "gates": {"symbolic": True, "fuzzy": False, "nn": True}},
            {"episode": 1, "step": 20, "version": "v9.3",
             "gates": {"symbolic": True, "fuzzy": True, "nn": True}},
            {"episode": 2, "step": 5, "version": "v9.3",
             "gates": {"symbolic": False, "fuzzy": False, "nn": True}},
        ]))

        adapter = ShadowLoopAdapter()
        samples = adapter.parse_gate_history(gate_path)

        assert len(samples) == 3
        assert samples[0].gate_decisions == {"symbolic": True, "fuzzy": False, "nn": True}

    def test_compute_evolution_metrics(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.adapters import ShadowLoopAdapter

        # Create version snapshots with increasing winrate
        versions = []
        for i, (v, wr) in enumerate([("v9.1", 0.30), ("v9.2", 0.40), ("v9.3", 0.47)]):
            p = temp_dir / f"version_{v}.json"
            p.write_text(json.dumps({
                "version": v,
                "rules": [{"id": f"R{x}"} for x in range(5 + i)],
                "stats": {"winrate": wr, "total_episodes": 50},
            }))
            versions.append(p)

        adapter = ShadowLoopAdapter()
        all_samples = []
        for p in versions:
            all_samples.extend(adapter.parse_version_snapshot(p))

        # Add gate history
        gate_path = temp_dir / "gate_history.json"
        gate_path.write_text(json.dumps([
            {"episode": 1, "step": 1, "version": "v9.3",
             "gates": {"symbolic": True, "nn": True}},
        ]))
        all_samples.extend(adapter.parse_gate_history(gate_path))

        metrics = adapter.compute_evolution_metrics(all_samples)

        assert len(metrics["versions_observed"]) == 3
        assert metrics["winrate_trend"] == [0.30, 0.40, 0.47]
        assert metrics["gate_pass_rate"]["symbolic"] == 1.0


# ═══════════════════════════════════════════════════════════════════════════
# 6. Cache tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRealityCache:
    def test_insert_and_query(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.cache import RealityCache
        from bottlesumo_pi.core.reality_bridge.models import Channel, RealitySample

        db = temp_dir / "test.sqlite"
        with RealityCache(db) as cache:
            s = RealitySample(
                channel=Channel.TRAINING_LOG,
                episode_id=1,
                reward=5.0,
                loss=0.02,
                tags=["test"],
            )
            cache.insert(s)

            results = cache.query(channel=Channel.TRAINING_LOG)
            assert len(results) == 1
            assert results[0].reward == 5.0

    def test_insert_many(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.cache import RealityCache
        from bottlesumo_pi.core.reality_bridge.models import Channel, RealitySample

        db = temp_dir / "test.sqlite"
        samples = [
            RealitySample(channel=Channel.TRAINING_LOG, episode_id=i, reward=float(i))
            for i in range(10)
        ]

        with RealityCache(db) as cache:
            count = cache.insert_many(samples)
            assert count == 10
            assert cache.total_count(Channel.TRAINING_LOG) == 10

    def test_stats(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.cache import RealityCache
        from bottlesumo_pi.core.reality_bridge.models import Channel, RealitySample

        db = temp_dir / "test.sqlite"
        with RealityCache(db) as cache:
            for i in range(5):
                cache.insert(RealitySample(
                    channel=Channel.SIMULATION,
                    episode_id=i,
                    reward=1.0 if i < 3 else 10.0,
                    win=i >= 3,
                    episode_length=100,
                ))

            stats = cache.stats(Channel.SIMULATION)
            assert stats["total_samples"] == 5
            assert stats["total_wins"] == 2
            assert stats["winrate"] == 0.4
            assert stats["avg_reward"] == (3 * 1.0 + 2 * 10.0) / 5

    def test_query_filters(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.cache import RealityCache
        from bottlesumo_pi.core.reality_bridge.models import Channel, RealitySample

        db = temp_dir / "test.sqlite"
        with RealityCache(db) as cache:
            now = time.time()
            cache.insert(RealitySample(
                channel=Channel.SIMULATION, timestamp=now - 100,
                episode_id=1, tags=["early"],
            ))
            cache.insert(RealitySample(
                channel=Channel.SIMULATION, timestamp=now - 10,
                episode_id=2, tags=["late"],
            ))

            # Time range filter
            results = cache.query(since=now - 50)
            assert len(results) == 1
            assert results[0].episode_id == 2

            # Tag filter
            results = cache.query(tag="early")
            assert len(results) == 1
            assert results[0].episode_id == 1

    def test_gap_report_persistence(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.cache import RealityCache
        from bottlesumo_pi.core.reality_bridge.models import GapReport, Severity

        db = temp_dir / "test.sqlite"
        with RealityCache(db) as cache:
            report = GapReport(
                overall_gap=0.25,
                severity=Severity.MEDIUM,
                detail="test gap",
            )
            cache.save_gap_report(report)

            loaded = cache.latest_gap_report()
            assert loaded is not None
            assert loaded["overall_gap"] == 0.25
            assert loaded["severity"] == "medium"

    def test_json_fields_roundtrip(self, temp_dir):
        """obs, gate_decisions, tags, extra survive SQLite roundtrip."""
        from bottlesumo_pi.core.reality_bridge.cache import RealityCache
        from bottlesumo_pi.core.reality_bridge.models import Channel, RealitySample

        db = temp_dir / "test.sqlite"
        s = RealitySample(
            channel=Channel.SHADOW_LOOP,
            obs=[0.1, 0.2, 0.3, 0.4, 1.0, 0.5, 0.0],
            gate_decisions={"symbolic": True, "fuzzy": False, "nn": True},
            tags=["shadow", "gate", "test"],
            extra={"nested": {"key": "value"}},
        )

        with RealityCache(db) as cache:
            cache.insert(s)
            results = cache.query(channel=Channel.SHADOW_LOOP)
            assert len(results) == 1
            r = results[0]
            assert r.obs == [0.1, 0.2, 0.3, 0.4, 1.0, 0.5, 0.0]
            assert r.gate_decisions == {"symbolic": True, "fuzzy": False, "nn": True}
            assert "shadow" in r.tags
            assert r.extra["nested"]["key"] == "value"


# ═══════════════════════════════════════════════════════════════════════════
# 7. RealityBridge end-to-end tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRealityBridge:
    def test_open_close(self, bridge_cache_db):
        bridge_cache_db.open()
        assert bridge_cache_db._cache._conn is not None
        bridge_cache_db.close()
        # SQLite connection is closed
        # (can't directly assert this easily, but close() doesn't throw)

    def test_context_manager(self, temp_dir):
        from bottlesumo_pi.core.reality_bridge.bridge import RealityBridge

        db = temp_dir / "ctx.sqlite"
        with RealityBridge(db_path=db) as bridge:
            assert bridge._cache._conn is not None

    def test_on_sample_ingestion(self, bridge_cache_db):
        from bottlesumo_pi.core.reality_bridge.models import Channel, RealitySample

        with bridge_cache_db:
            s = RealitySample(
                channel=Channel.SIMULATION,
                episode_id=1,
                reward=5.0,
            )
            bridge_cache_db.on_sample(s)

            total = bridge_cache_db.total_samples(Channel.SIMULATION)
            assert total == 1

    def test_ingest_training_logs(self, bridge_cache_db, temp_dir):
        csv_path = temp_dir / "logs" / "train.csv"
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_path.write_text(
            "episode,loss,reward,win\n0,2.0,-1.0,0\n1,1.0,5.0,1\n"
        )

        with bridge_cache_db:
            count = bridge_cache_db.ingest_training_logs(str(csv_path.parent))
            assert count == 2
            stats = bridge_cache_db.stats()
            assert stats["total_samples"] == 2

    def test_detect_gap_empty(self, bridge_cache_db):
        """Gap detection on empty cache returns NONE severity."""
        with bridge_cache_db:
            gap = bridge_cache_db.detect_gap()
            assert gap.overall_gap == 0.0
            assert gap.severity.value == "none"

    def test_detect_gap_with_data(self, bridge_cache_db, temp_dir):
        """Gap detection with mismatched data produces meaningful report."""
        from bottlesumo_pi.core.reality_bridge.models import Channel, RealitySample

        with bridge_cache_db:
            # Simulate: winrate below baseline (gap expected)
            for i in range(100):
                bridge_cache_db.on_sample(RealitySample(
                    channel=Channel.SIMULATION,
                    episode_id=i,
                    reward=1.0 if i < 70 else 10.0,
                    win=(i >= 70),
                ))

            # Training: loss increasing (gap expected)
            for i in range(50):
                bridge_cache_db.on_sample(RealitySample(
                    channel=Channel.TRAINING_LOG,
                    episode_id=i,
                    loss=1.0 + (i * 0.05),  # increasing loss!
                ))

            gap = bridge_cache_db.detect_gap()
            assert gap.simulation_gap > 0.0  # 30% WR vs 47% expected
            assert gap.training_gap > 0.0    # loss is increasing
            assert gap.overall_gap > 0.0

    def test_report(self, bridge_cache_db):
        """Full report() returns structured dict."""
        from bottlesumo_pi.core.reality_bridge.models import Channel, RealitySample

        with bridge_cache_db:
            for ch in Channel:
                bridge_cache_db.on_sample(RealitySample(channel=ch, episode_id=1))

            report = bridge_cache_db.report()

            assert "gap_report" in report
            assert "channel_stats" in report
            assert "total_samples" in report
            assert "aggregated_feedback" in report
            assert report["total_samples"]["simulation"] == 1
            assert report["total_samples"]["training_log"] == 1

    def test_listener_callback(self, bridge_cache_db):
        from bottlesumo_pi.core.reality_bridge.models import Channel, RealitySample

        received = []

        with bridge_cache_db:
            bridge_cache_db.add_listener(lambda s: received.append(s))
            bridge_cache_db.on_sample(RealitySample(
                channel=Channel.SIMULATION, episode_id=1,
            ))

        assert len(received) == 1

    def test_noop_on_missing_files(self, bridge_cache_db, temp_dir):
        """Ingestion gracefully handles non-existent paths."""
        with bridge_cache_db:
            count = bridge_cache_db.ingest_training_logs(
                str(temp_dir / "nonexistent")
            )
            assert count == 0

            count = bridge_cache_db.ingest_feedback(
                str(temp_dir / "nonexistent.json")
            )
            assert count == 0

            count = bridge_cache_db.ingest_shadow_loop(
                str(temp_dir / "nonexistent")
            )
            assert count == 0
