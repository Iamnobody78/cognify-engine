#!/usr/bin/env python3
"""
DEBT-003: Profiler v2 — Opponent Archetype Classification
Target: >70% accuracy on 4 opponent types

Opponent archetypes:
  0: AGGRESSIVE  — charges straight, fast speed, doesn't avoid edges
  1: DEFENSIVE   — stays near center, faces opponent, slow speed
  2: CIRCLER     — circles around the opponent, constant angular velocity
  3: RANDOM      — random walk, erratic direction changes

Features (from sliding window of N=10 frames):
  - speed mean/std
  - angular velocity mean/std
  - distance from center mean/std
  - distance to opponent mean/std
  - heading change rate
  - edge proximity count
  - acceleration (speed change) mean/max

Output: [4] class probabilities, argmax = opponent type
"""

import math
import os
import random
import sys
from collections import deque

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler

# Add tests/ directory for virtual_mcu import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from virtual_mcu import v11_select_action

# ─── Constants ───
RING_RADIUS = 1.0
ROBOT_RADIUS = 0.15
MAX_SPEED = 0.5
MAX_ANGULAR = math.pi
DT = 0.05
FRICTION = 0.9
RING_LIMIT = RING_RADIUS - ROBOT_RADIUS
EPISODE_LENGTH = 300


# ─── Opponent Archetypes ───
def aggressive_opponent(env, obs):
    """Charge directly at the bottle (player) at high speed."""
    rp = np.array(env.opp_pos)
    bp = np.array(env.robot_pos)
    to_target = bp - rp
    dist = np.linalg.norm(to_target)
    if dist < 1e-6:
        return 0.0, 0.0  # stop
    desired_heading = math.atan2(to_target[1], to_target[0])
    heading_error = (desired_heading - env.opp_heading + math.pi) % (2 * math.pi) - math.pi
    # Aggressive: high speed, sharp turns
    speed = 0.45 if abs(heading_error) < 0.3 else 0.3
    angular = np.clip(heading_error * 8.0, -MAX_ANGULAR, MAX_ANGULAR)
    return speed, angular


def defensive_opponent(env, obs):
    """Stay near center, always face the player, move slowly."""
    rp = np.array(env.opp_pos)
    bp = np.array(env.robot_pos)
    # Priority: stay near center
    center_vec = -rp
    center_dist = np.linalg.norm(center_vec)
    if center_dist > 0.3:
        # Move toward center
        desired_heading = math.atan2(center_vec[1], center_vec[0])
        heading_error = (desired_heading - env.opp_heading + math.pi) % (2 * math.pi) - math.pi
        speed = min(center_dist * 0.5, 0.25)
        angular = np.clip(heading_error * 5.0, -MAX_ANGULAR, MAX_ANGULAR)
    else:
        # Face opponent
        to_opp = bp - rp
        desired_heading = math.atan2(to_opp[1], to_opp[0])
        heading_error = (desired_heading - env.opp_heading + math.pi) % (2 * math.pi) - math.pi
        speed = 0.1
        angular = np.clip(heading_error * 4.0, -MAX_ANGULAR, MAX_ANGULAR)
    return speed, angular


def circler_opponent(env, obs):
    """Circle around the opponent at fixed angular velocity."""
    rp = np.array(env.opp_pos)
    bp = np.array(env.robot_pos)
    to_target = bp - rp
    dist = np.linalg.norm(to_target)
    # Maintain ~0.3 distance, circle perpendicular
    if dist < 0.25:
        speed = -0.2  # back away
        angular = 0.7 * (1 if random.random() > 0.5 else -1)  # random dir
    elif dist > 0.45:
        speed = 0.3  # approach
        desired_heading = math.atan2(to_target[1], to_target[0])
        heading_error = (desired_heading - env.opp_heading + math.pi) % (2 * math.pi) - math.pi
        angular = np.clip(heading_error * 3.0, -MAX_ANGULAR, MAX_ANGULAR)
    else:
        # Circle: move perpendicular to line-of-sight
        los_angle = math.atan2(to_target[1], to_target[0])
        # Perpendicular direction (clockwise or counter-clockwise based on hash of position)
        sign = 1 if (int(env.opp_pos[0] * 100) + int(env.opp_pos[1] * 100)) % 2 == 0 else -1
        desired_heading = los_angle + sign * math.pi / 2
        heading_error = (desired_heading - env.opp_heading + math.pi) % (2 * math.pi) - math.pi
        speed = 0.35
        angular = np.clip(heading_error * 5.0, -MAX_ANGULAR, MAX_ANGULAR)
    return speed, angular


def random_opponent(env, obs):
    """Random walk with frequent direction changes."""
    speed = random.uniform(0.1, 0.4)
    angular = random.uniform(-1.5, 1.5)
    # Sometimes stop
    if random.random() < 0.1:
        speed = 0.0
        angular = random.uniform(-2.0, 2.0)  # spin in place
    return speed, angular


OPPONENT_ARCHETYPES = {
    0: {"name": "AGGRESSIVE", "fn": aggressive_opponent},
    1: {"name": "DEFENSIVE", "fn": defensive_opponent},
    2: {"name": "CIRCLER", "fn": circler_opponent},
    3: {"name": "RANDOM", "fn": random_opponent},
}


# ─── Lightweight Env (stands in for player, opponent controlled by archetype) ───
class ProfilerEnv:
    """Simulation environment where player runs V11 expert, opponent runs archetype."""

    def __init__(self, seed=None):
        if seed is not None:
            random.seed(seed)
        self.reset()

    def reset(self):
        # Player starts near center
        angle = random.uniform(0, 2 * math.pi)
        r = random.uniform(0, 0.15)
        self.robot_pos = [r * math.cos(angle), r * math.sin(angle)]
        self.robot_vel = [0.0, 0.0]
        self.heading = random.uniform(0, 2 * math.pi)
        self.angular_v = 0.0
        # Opponent starts further out
        while True:
            angle = random.uniform(0, 2 * math.pi)
            r = random.uniform(0.3, 0.6)
            self.opp_pos = [r * math.cos(angle), r * math.sin(angle)]
            if (
                math.hypot(self.opp_pos[0] - self.robot_pos[0], self.opp_pos[1] - self.robot_pos[1])
                > 2 * ROBOT_RADIUS
            ):
                break
        self.opp_vel = [0.0, 0.0]
        self.opp_heading = random.uniform(0, 2 * math.pi)
        self.opp_angular_v = 0.0
        self.step_count = 0
        # History for feature extraction
        self.opp_pos_history = deque(maxlen=10)
        self.opp_heading_history = deque(maxlen=10)
        return self._get_obs()

    def _get_obs(self):
        rp = self.robot_pos
        rv = self.robot_vel
        h = self.heading
        op = self.opp_pos
        ov = self.opp_vel
        robot_dist = math.hypot(rp[0], rp[1])
        opp_rel_x = op[0] - rp[0]
        opp_rel_y = op[1] - rp[1]
        edge_dist = (RING_LIMIT - robot_dist) / RING_LIMIT
        fd = RING_LIMIT - math.hypot(rp[0] + 0.5 * math.cos(h), rp[1] + 0.5 * math.sin(h))
        edge_front = 1.0 - min(1.0, max(0.0, max(0, fd) / RING_LIMIT))
        la = h + math.pi / 2
        ld = RING_LIMIT - math.hypot(rp[0] + 0.5 * math.cos(la), rp[1] + 0.5 * math.sin(la))
        edge_left = 1.0 - min(1.0, max(0.0, max(0, ld) / RING_LIMIT))
        ra = h - math.pi / 2
        rd = RING_LIMIT - math.hypot(rp[0] + 0.5 * math.cos(ra), rp[1] + 0.5 * math.sin(ra))
        edge_right = 1.0 - min(1.0, max(0.0, max(0, rd) / RING_LIMIT))
        return np.array(
            [
                rp[0] / RING_LIMIT,
                rp[1] / RING_LIMIT,
                rv[0] / MAX_SPEED,
                rv[1] / MAX_SPEED,
                h / (2 * math.pi),
                self.angular_v / MAX_ANGULAR,
                opp_rel_x / RING_LIMIT,
                opp_rel_y / RING_LIMIT,
                ov[0] / MAX_SPEED,
                ov[1] / MAX_SPEED,
                edge_dist,
                edge_front,
                edge_left,
                edge_right,
                self.step_count / 300.0,
                self.opp_pos[0] / RING_LIMIT,
                self.opp_pos[1] / RING_LIMIT,
                self.opp_vel[0] / MAX_SPEED,
                self.opp_vel[1] / MAX_SPEED,
                self.opp_heading / (2 * math.pi),
                self.opp_angular_v / MAX_ANGULAR,
            ],
            dtype=np.float32,
        )

    def step(self, player_action, opponent_fn):
        """Step both player (V11 expert) and opponent (archetype)."""
        # Player physics — use V11 expert action
        p_action, _ = v11_select_action(self._get_obs()[:16].tolist())
        linear, angular = {
            0: (0.5, 0.0),
            1: (-0.3, 0.0),
            2: (0.0, math.pi / 2),
            3: (0.0, -math.pi / 2),
            4: (0.35, math.pi / 2),
            5: (0.35, -math.pi / 2),
            6: (-0.2, math.pi / 2),
            7: (-0.2, -math.pi / 2),
            8: (0.8, 0.0),
            9: (0.0, 0.0),
            10: (0.0, math.pi),
        }.get(p_action, (0.0, 0.0))
        nh = (self.heading + angular * DT) % (2 * math.pi)
        wvx = math.cos(nh) * linear
        wvy = math.sin(nh) * linear
        self.robot_vel[0] = self.robot_vel[0] * FRICTION + wvx * (1 - FRICTION)
        self.robot_vel[1] = self.robot_vel[1] * FRICTION + wvy * (1 - FRICTION)
        self.robot_pos[0] += self.robot_vel[0] * DT
        self.robot_pos[1] += self.robot_vel[1] * DT
        self.heading = nh
        self.angular_v = angular

        # Opponent physics (archetype decides)
        opp_speed, opp_angular = opponent_fn(self, self._get_obs())
        opp_nh = (self.opp_heading + opp_angular * DT) % (2 * math.pi)
        owvx = math.cos(opp_nh) * opp_speed
        owvy = math.sin(opp_nh) * opp_speed
        self.opp_vel[0] = self.opp_vel[0] * FRICTION + owvx * (1 - FRICTION)
        self.opp_vel[1] = self.opp_vel[1] * FRICTION + owvy * (1 - FRICTION)
        self.opp_pos[0] += self.opp_vel[0] * DT
        self.opp_pos[1] += self.opp_vel[1] * DT
        self.opp_heading = opp_nh
        self.opp_angular_v = opp_angular

        # Track history
        self.opp_pos_history.append(tuple(self.opp_pos))
        self.opp_heading_history.append(self.opp_heading)

        # Collision
        dv = np.array([self.robot_pos[0] - self.opp_pos[0], self.robot_pos[1] - self.opp_pos[1]])
        d = np.linalg.norm(dv)
        if d < 2 * ROBOT_RADIUS and d > 1e-6:
            overlap = 2 * ROBOT_RADIUS - d
            direction = dv / d
            self.robot_pos[0] += direction[0] * overlap * 0.5
            self.robot_pos[1] += direction[1] * overlap * 0.5
            self.opp_pos[0] -= direction[0] * overlap * 0.5
            self.opp_pos[1] -= direction[1] * overlap * 0.5

        self.step_count += 1
        r_dist = math.hypot(self.robot_pos[0], self.robot_pos[1])
        o_dist = math.hypot(self.opp_pos[0], self.opp_pos[1])
        done = r_dist >= RING_LIMIT or o_dist >= RING_LIMIT or self.step_count >= EPISODE_LENGTH
        return self._get_obs(), done


# ─── Feature Extraction ───
def extract_features(env, obs):
    """Extract classification features from opponent trajectory history."""
    if len(env.opp_pos_history) < 3:
        return np.zeros(12, dtype=np.float32)

    pos = np.array(env.opp_pos_history)
    headings = np.array(env.opp_heading_history)

    # Speed features
    displacements = np.diff(pos, axis=0) / DT
    speeds = np.linalg.norm(displacements, axis=1)
    speed_mean = np.mean(speeds) / MAX_SPEED
    speed_std = np.std(speeds) / MAX_SPEED
    speed_max = np.max(speeds) / MAX_SPEED

    # Angular velocity
    heading_diffs = np.diff(headings)
    # Handle wrap-around
    heading_diffs = np.array([(d + math.pi) % (2 * math.pi) - math.pi for d in heading_diffs])
    angular_speeds = heading_diffs / DT
    ang_mean = np.mean(np.abs(angular_speeds)) / MAX_ANGULAR
    ang_std = np.std(angular_speeds) / MAX_ANGULAR

    # Distance from center
    center_dists = np.linalg.norm(pos, axis=1) / RING_LIMIT
    center_dist_mean = np.mean(center_dists)
    center_dist_std = np.std(center_dists)

    # Edge proximity
    edge_prox = np.mean(center_dists > 0.75)  # fraction near edge

    # Speed change (acceleration)
    accels = np.abs(np.diff(speeds)) / DT
    accel_mean = np.mean(accels) / (MAX_SPEED / DT) if len(accels) > 0 else 0.0
    accel_max = np.max(accels) / (MAX_SPEED / DT) if len(accels) > 0 else 0.0

    # Direction consistency (heading entropy)
    if len(heading_diffs) >= 2:
        sign_changes = np.sum(np.sign(heading_diffs[:-1]) != np.sign(heading_diffs[1:]))
        sign_change_rate = sign_changes / len(heading_diffs)
    else:
        sign_change_rate = 0.0

    features = np.array(
        [
            speed_mean,
            speed_std,
            speed_max,
            ang_mean,
            ang_std,
            center_dist_mean,
            center_dist_std,
            edge_prox,
            accel_mean,
            accel_max,
            sign_change_rate,
            float(len(env.opp_pos_history)) / 10.0,  # buffer fill level
        ],
        dtype=np.float32,
    )
    return features


# ─── Data Generation ───
def generate_data(n_episodes_per_type=100, seed=42):
    """Generate classification data by running each archetype against V11 expert."""
    random.seed(seed)
    np.random.seed(seed)

    all_features = []
    all_labels = []

    for opp_type in range(4):
        opp_fn = OPPONENT_ARCHETYPES[opp_type]["fn"]
        print(f"  Generating {OPPONENT_ARCHETYPES[opp_type]['name']}...")

        for ep in range(n_episodes_per_type):
            env = ProfilerEnv(seed=seed + opp_type * 1000 + ep)
            obs = env.reset()
            ep_features = []
            for step in range(EPISODE_LENGTH):
                obs, done = env.step(None, opp_fn)
                # Extract features every 10 steps (to build history)
                if step >= 10 and step % 5 == 0:
                    feat = extract_features(env, obs)
                    ep_features.append(feat)
                if done:
                    break

            if len(ep_features) > 0:
                # Average features over the episode for a stable classification sample
                avg_feat = np.mean(ep_features, axis=0)
                all_features.append(avg_feat)
                all_labels.append(opp_type)

    X = np.array(all_features, dtype=np.float32)  # noqa: N806
    y = np.array(all_labels, dtype=np.int64)
    print(f"\n  Total: {len(X)} samples, {X.shape[1]} features")
    return X, y


# ─── Training ───

def train_and_evaluate(X, y):  # noqa: N803
    """Train multiple classifiers, report results."""
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)  # noqa: N806

    models = {
        "LogisticRegression": LogisticRegression(max_iter=1000, multi_class="multinomial"),
        "RandomForest": RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42),
        "MLP_Small": MLPClassifier(hidden_layer_sizes=(16,), max_iter=500, random_state=42),
        "MLP_Medium": MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=500, random_state=42),
    }

    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    results = {}

    for name, model in models.items():
        scores = cross_val_score(model, X_scaled, y, cv=cv, scoring="accuracy")
        model.fit(X_scaled, y)
        y_pred = model.predict(X_scaled)
        train_acc = np.mean(y_pred == y)

        results[name] = {
            "cv_mean": float(np.mean(scores)),
            "cv_std": float(np.std(scores)),
            "train_acc": float(train_acc),
        }
        print(f"\n{'=' * 50}")
        print(f"  {name}")
        print(f"    CV Accuracy:  {np.mean(scores):.2%} ± {np.std(scores):.2%}")
        print(f"    Train Acc:    {train_acc:.2%}")
        cm = confusion_matrix(y, y_pred)
        print(
            f"    Per-class: { {OPPONENT_ARCHETYPES[i]['name']: f'{cm[i, i] / cm[i].sum():.0%}' for i in range(4)} }"
        )

    return results, scaler, models


# ─── Main ───
def main():
    print("=" * 60)
    print("DEBT-003: Profiler v2 — Opponent Classification")
    print("=" * 60)

    # Generate data
    print("\n── Data Generation ──")
    X, y = generate_data(n_episodes_per_type=100, seed=42)  # noqa: N806
    print(f"  Dataset: {X.shape}, classes={np.unique(y)}")

    # Train
    print("\n── Model Training ──")
    results, scaler, models = train_and_evaluate(X, y)

    # Best model
    best_name = max(results, key=lambda k: results[k]["cv_mean"])
    best_cv = results[best_name]["cv_mean"]
    print(f"\n{'=' * 60}")
    if best_cv >= 0.70:
        print(f"✅ PASS: {best_name} CV={best_cv:.1%} > 70% threshold")
    else:
        print(f"❌ FAIL: {best_name} CV={best_cv:.1%} < 70% threshold")

    # Save best model (export to Python pickle for now, ONNX later)
    import pickle

    save_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")
    os.makedirs(save_dir, exist_ok=True)
    best_model = models[best_name]
    with open(os.path.join(save_dir, "profiler_v2.pkl"), "wb") as f:
        pickle.dump({"model": best_model, "scaler": scaler, "results": results}, f)
    print(f"  Saved: {save_dir}/profiler_v2.pkl")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
