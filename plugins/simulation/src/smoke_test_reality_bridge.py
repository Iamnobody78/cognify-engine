"""Quick smoke test for RealityBridge."""
import sys
from pathlib import Path
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

import json
import tempfile
from core.reality_bridge.bridge import RealityBridge
from core.reality_bridge.models import Channel, RealitySample


def main():
    td = Path(tempfile.mkdtemp())
    db = td / "smoke.sqlite"

    with RealityBridge(db_path=db) as bridge:
        # Channel 1: simulation (real-time injection)
        for ep in range(50):
            win = ep >= 25  # 50% winrate
            bridge.on_sample(RealitySample(
                channel=Channel.SIMULATION, episode_id=ep,
                reward=10.0 if win else -1.0, win=win,
                obs=[0.5, 0.3, 0.1, 0.0, 1.0, 0.0, 0.0],
                tags=["smoke_test"],
            ))

        # Channel 2: training log (batch parse)
        csv = td / "train.csv"
        csv.write_text("episode,loss,reward,win\n10,2.0,-1.0,0\n11,1.5,5.0,1\n")
        bridge.ingest_training_logs(str(td))

        # Channel 3: user feedback
        fb = td / "feedback.json"
        fb.write_text(json.dumps([{
            "scenario": "edge_defense",
            "annotation": "Agent should retreat at edge, not push",
            "corrected_action": 12,
            "confidence": 0.95,
        }]))
        bridge.ingest_feedback(str(fb))

        # Channel 4: shadow loop
        sl = td / "shadow"
        sl.mkdir()
        (sl / "version_v9.3.json").write_text(json.dumps({
            "version": "v9.3", "rules": [{"id": f"R{i}"} for i in range(5)],
            "stats": {"winrate": 0.47, "total_episodes": 50},
        }))
        bridge.ingest_shadow_loop(str(sl))

        # Report
        report = bridge.report()
        ts = report["total_samples"]
        gap = report["gap_report"]
        print(f"Total samples: sim={ts['simulation']}, train={ts['training_log']}, "
              f"fb={ts['user_feedback']}, shadow={ts['shadow_loop']}")
        print(f"Gap: overall={gap['overall_gap']:.4f}, severity={gap['severity']}")
        print(f"  sim_gap={gap['simulation_gap']:.4f}, train_gap={gap['training_gap']:.4f}")
        print(f"  fb_gap={gap['user_feedback_gap']:.4f}, shadow_gap={gap['shadow_loop_gap']:.4f}")
        print(f"Aggregated feedback: {len(report['aggregated_feedback'])} scenarios")

        assert ts["simulation"] == 50
        assert ts["training_log"] == 2
        assert ts["user_feedback"] == 1
        assert ts["shadow_loop"] == 1
        print("\nOK: RealityBridge smoke test PASSED")


if __name__ == "__main__":
    main()
