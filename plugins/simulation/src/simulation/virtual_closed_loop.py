#!/usr/bin/env python3
"""BottleSumo Virtual Closed-Loop Verification — No Hardware, No Renode, No Gazebo

  Simulates the complete pipeline in pure Python:
    lightweight_env (physics) -> wheel_to_discrete (action) -> mock_firmware (STM32)
    -> HIL logic (sensor injection) -> lightweight_env (next step)

  This verifies:
    - Environment reset/step cycle
    - Action space mapping
    - Mock sensor data generation
    - Firmware-like state machine
    - Multi-episode statistics
"""

import sys
import os
import time
import json
from pathlib import Path
from collections import deque
from typing import Dict, Tuple, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from lightweight_env import LightweightBottleSumoEnv as BottleSumoEnv
from wheel_to_discrete import Action, ACTION_MAP, ACTION_GROUPS, SAFE_ACTIONS_WHEN_EDGE_CLOSE


class NumpyEncoder(json.JSONEncoder):
    """Custom JSON encoder that converts numpy scalars to Python native types."""
    def default(self, obj):
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _sanitize_for_json(obj):
    """Recursively convert numpy types in dicts/lists to Python native types."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


# ============================================================================
# Mock STM32 Firmware State Machine
# ============================================================================

class MockFirmware:
    """Simulates the STM32 firmware behavior without actual hardware.

    Maintains a virtual BSS memory map matching the verified addresses
    from hil_bridge.py, and runs a frame-by-frame execution loop.
    """

    def __init__(self, name: str = "main"):
        self.name = name
        self.frame_count = 0
        self.last_loop_ms = 0
        self.battery_mv = 7400  # 7.4V nominal
        self.estop_active = False

        # Virtual BSS memory (matching F407 addresses from hil_bridge.py)
        self.memory = {
            "bottle_dist_history": deque([0] * 8, maxlen=8),
            "vlx0_dist": [0, 0, 0, 0],
            "bottle_dist_idx": 0,
            "cylinder_detected": 0,
            "enc_a_delta": 0,
            "enc_b_delta": 0,
            "frame_count": 0,
            "last_loop_ms": 0,
            "observation": [0.0] * 16,
            "q_values": [0.0] * 11,
        }

    def tick(self, sensor_data: Dict, action: int) -> Dict:
        """Execute one firmware loop. Returns updated state."""
        self.frame_count += 1
        self.memory["frame_count"] = self.frame_count

        # Simulate loop time (74-86us typical for STM32F4 @ 168MHz)
        self.last_loop_ms = np.random.uniform(0.074, 0.086)
        self.memory["last_loop_ms"] = self.last_loop_ms

        # Update observation vector from sensor data
        obs = sensor_data.get("observation", [0.0] * 16)
        for i in range(min(len(obs), 16)):
            self.memory["observation"][i] = obs[i]

        # Simulate Q-value computation (mock inference, 21-dim for 21-action space)
        q_vals = np.random.uniform(-1, 1, 21)
        q_vals[min(action, 20)] += 0.5  # bias toward selected action
        for i in range(min(len(q_vals), 11)):
            self.memory["q_values"][i] = q_vals[i]

        # Update encoder deltas based on action
        self._simulate_motion(action)

        # Battery drain simulation
        self.battery_mv -= np.random.uniform(0, 0.1)

        return self.get_state()

    def _simulate_motion(self, action: int):
        """Rough encoder simulation based on action type."""
        try:
            action_enum = Action(action)
        except ValueError:
            action_enum = Action.STOP
        act_entry = ACTION_MAP.get(action_enum, (0.0, 0.0))
        speed = abs(act_entry[0]) + abs(act_entry[1])
        self.memory["enc_a_delta"] = int(speed * np.random.uniform(0.8, 1.2) * 10)
        self.memory["enc_b_delta"] = int(speed * np.random.uniform(0.8, 1.2) * 10)

    def get_state(self) -> Dict:
        return {
            "frame_count": self.frame_count,
            "battery_mv": round(self.battery_mv, 1),
            "estop": self.estop_active,
            "enc_a": self.memory["enc_a_delta"],
            "enc_b": self.memory["enc_b_delta"],
        }

    def emergency_stop(self):
        self.estop_active = True
        print(f"  [ESTOP] {self.name} emergency stop activated")


# ============================================================================
# Virtual HIL Bridge
# ============================================================================

class VirtualHILBridge:
    """Connects lightweight_env to mock firmware — the virtual HIL loop.

    Wraps: env.reset/step -> firmware.tick -> sensor_injection -> env.step
    """

    def __init__(self, max_episodes: int = 10, max_steps: int = 500):
        self.env = BottleSumoEnv()
        self.firmware_main = MockFirmware("main")
        self.firmware_aux = MockFirmware("aux")

        self.max_episodes = max_episodes
        self.max_steps = max_steps
        self.episode_stats: List[Dict] = []
        self.total_frames = 0
        self.start_time = 0

    def run(self) -> Dict:
        """Execute the virtual closed-loop verification."""
        self.start_time = time.time()

        for ep in range(self.max_episodes):
            obs, info = self.env.reset()
            episode_reward = 0
            episode_steps = 0
            episode_crashes = 0

            for step in range(self.max_steps):
                # Select action (random for verification; could be DQN policy)
                action = self._select_action(obs, step)

                # Step environment
                obs, reward, terminated, truncated, info = self.env.step(action)
                episode_reward += reward
                episode_steps += 1
                self.total_frames += 1

                # Simulate firmware processing
                sensor_data = self._build_sensor_packet(obs)
                fw_state = self.firmware_main.tick(sensor_data, action)
                self.firmware_aux.tick(sensor_data, 0)  # aux MCU in idle

                # Safety check
                if self._check_estop(info):
                    self.firmware_main.emergency_stop()
                    episode_crashes += 1
                    break

                if terminated or truncated:
                    if terminated:
                        episode_crashes += 1
                    break

            # Record episode stats
            fps = episode_steps / max(time.time() - self.start_time, 0.001)
            self.episode_stats.append({
                "episode": ep + 1,
                "steps": episode_steps,
                "reward": round(episode_reward, 1),
                "crashed": episode_crashes > 0,
                "fps": round(fps, 1),
            })

        elapsed = time.time() - self.start_time
        return self._build_summary(elapsed)

    def _select_action(self, obs: np.ndarray, step: int) -> int:
        """Simple heuristic action selection (replace with DQN for real training)."""
        # 10% random exploration
        if np.random.random() < 0.1:
            return np.random.randint(0, self.env.action_space.n)

        # Edge-aware safety: prefer safe actions when near edge
        min_edge = min(obs[0], obs[1], obs[2], obs[3])
        if min_edge < 0.3:
            safe = SAFE_ACTIONS_WHEN_EDGE_CLOSE
            if safe:
                return np.random.choice(list(safe))

        # Default: forward-ish action
        return 10  # FORWARD

    def _build_sensor_packet(self, obs: np.ndarray) -> Dict:
        """Build a sensor packet matching the observation space (7-dim)."""
        obs_list = obs.tolist() if hasattr(obs, 'tolist') else list(obs)
        n = len(obs_list)
        # obs: [edge_l, edge_fl, edge_fr, edge_r, opponent_dist, bottle_dist, bottle_angle]
        packet = {
            "observation": obs_list,
            "edges": {
                "left": float(obs[0]),
                "front_left": float(obs[1]) if n > 1 else 0,
                "front_right": float(obs[2]) if n > 2 else 0,
                "right": float(obs[3]) if n > 3 else 0,
            },
            "opponent": {
                "distance": float(obs[4]) if n > 4 else 0,
            },
            "bottle": {
                "distance": float(obs[5]) if n > 5 else 0,
                "angle": float(obs[6]) if n > 6 else 0,
            },
        }
        return packet

    def _check_estop(self, info: Dict) -> bool:
        """Check if emergency stop should be triggered."""
        return info.get("emergency_stop", False)

    def _build_summary(self, elapsed: float) -> Dict:
        crashed = sum(1 for s in self.episode_stats if s["crashed"])
        avg_reward = np.mean([s["reward"] for s in self.episode_stats])
        avg_fps = np.mean([s["fps"] for s in self.episode_stats])
        success_rate = (len(self.episode_stats) - crashed) / max(len(self.episode_stats), 1)

        summary = {
            "test": "virtual_closed_loop",
            "status": "PASS" if success_rate > 0 else "PARTIAL",
            "episodes": len(self.episode_stats),
            "total_frames": int(self.total_frames),
            "elapsed_seconds": round(float(elapsed), 1),
            "avg_fps": round(float(avg_fps), 1),
            "success_rate": round(float(success_rate) * 100, 1),
            "avg_reward": round(float(avg_reward), 1),
            "crashes": int(crashed),
            "episode_stats": self.episode_stats,
        }
        return _sanitize_for_json(summary)


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 60)
    print("BottleSumo Virtual Closed-Loop Verification")
    print("No Hardware | No Renode | No Gazebo — Pure Python")
    print("=" * 60)

    bridge = VirtualHILBridge(max_episodes=10, max_steps=200)
    print(f"\nEnvironment: {bridge.env.action_space.n} actions, obs_shape={bridge.env.observation_space.shape}")
    print(f"Firmware: {bridge.firmware_main.name} (mock), {bridge.firmware_aux.name} (mock aux)")
    print(f"Config: {bridge.max_episodes} episodes x {bridge.max_steps} max steps")
    print(f"\nRunning...\n")

    summary = bridge.run()

    print(f"\n{'=' * 60}")
    print(f"RESULTS")
    print(f"{'=' * 60}")
    print(f"  Status:       {summary['status']}")
    print(f"  Episodes:     {summary['episodes']}")
    print(f"  Total Frames: {summary['total_frames']}")
    print(f"  Elapsed:      {summary['elapsed_seconds']}s")
    print(f"  Avg FPS:      {summary['avg_fps']}")
    print(f"  Success Rate: {summary['success_rate']}%")
    print(f"  Avg Reward:   {summary['avg_reward']}")
    print(f"  Crashes:      {summary['crashes']}")
    print(f"\nPer-Episode:")
    for s in summary["episode_stats"]:
        crash = "[CRASH]" if s["crashed"] else "[OK]"
        print(f"  Ep {s['episode']:2d}: {s['steps']:3d} steps, {s['reward']:6.1f} reward, {crash}")

    # Save results
    out_path = Path(__file__).parent / "virtual_closed_loop_results.json"
    out_path.write_text(json.dumps(summary, indent=2, cls=NumpyEncoder))
    print(f"\n[OK] Results saved to {out_path}")

    return 0 if summary["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
