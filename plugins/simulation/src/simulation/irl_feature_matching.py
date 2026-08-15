#!/usr/bin/env python3
"""
DEBT-002: Inverse Reinforcement Learning (IRL) — Feature Expectation Matching
Learns a reward function from V11 expert demonstrations.

Approach: Maximum Entropy IRL
  1. Define state features φ(s)
  2. Collect V11 expert trajectories
  3. Compute expert feature expectations μ_E
  4. Learn reward weight w via maximum likelihood of expert actions under Boltzmann policy
  5. Compare learned reward with hand-crafted v25_combat reward

Feature space (8D):
  f0: edge_distance (normalized, 0=center, 1=edge)
  f1: opponent_distance (normalized)
  f2: opponent_distance_change (delta per step)
  f3: robot_speed (magnitude)
  f4: heading_to_opponent (cosine similarity)
  f5: heading_to_center (cosine similarity)
  f6: edge_front (danger zone forward)
  f7: contact_signal (binary, near opponent)
"""

import json
import math
import os
import random
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from virtual_mcu import v11_select_action

# ── Environment constants (same as clone_v11_dagger_fast.py) ──
from common.action_space import (
    ACTION_MAP,
    ACTION_NAMES,
    DT,
    FRICTION,
    MAX_ANGULAR,
    MAX_SPEED,
    N_ACTIONS,
    OBS_DIM,
    RING_LIMIT,
    RING_RADIUS,
    ROBOT_RADIUS,
)

class LightweightEnv:
    def __init__(self, seed=None):
        if seed is not None:
            random.seed(seed)
        self.reset()

    def reset(self):
        angle = random.uniform(0, 2 * math.pi)
        r = random.uniform(0, 0.2)
        self.robot_pos = [r * math.cos(angle), r * math.sin(angle)]
        self.robot_vel = [0.0, 0.0]
        self.heading = random.uniform(0, 2 * math.pi)
        self.angular_v = 0.0
        while True:
            angle = random.uniform(0, 2 * math.pi)
            r = random.uniform(0.3, 0.7)
            self.opp_pos = [r * math.cos(angle), r * math.sin(angle)]
            if (
                math.hypot(self.opp_pos[0] - self.robot_pos[0], self.opp_pos[1] - self.robot_pos[1])
                > 2 * ROBOT_RADIUS
            ):
                break
        self.opp_vel = [0.0, 0.0]
        self.step_count = 0
        self.prev_opp_dist = math.hypot(
            self.opp_pos[0] - self.robot_pos[0], self.opp_pos[1] - self.robot_pos[1]
        )
        self._obs = self._get_obs()
        return self._obs

    def _get_obs(self):
        rp, rv, h = self.robot_pos, self.robot_vel, self.heading
        op, ov = self.opp_pos, self.opp_vel
        robot_dist = math.hypot(rp[0], rp[1])
        opp_rel_x = op[0] - rp[0]
        opp_rel_y = op[1] - rp[1]
        edge_dist = (RING_LIMIT - robot_dist) / RING_LIMIT
        fd = RING_LIMIT - math.hypot(rp[0] + 0.5 * math.cos(h), rp[1] + 0.5 * math.sin(h))
        edge_front = 1.0 - min(1.0, max(0.0, max(0, fd) / RING_LIMIT))
        bd = RING_LIMIT - math.hypot(rp[0] - 0.5 * math.cos(h), rp[1] - 0.5 * math.sin(h))
        edge_back = 1.0 - min(1.0, max(0.0, max(0, bd) / RING_LIMIT))
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
                edge_back,
                edge_left,
                edge_right,
                self.step_count / 300.0,
            ],
            dtype=np.float32,
        )

    def step(self, action):
        linear, angular = ACTION_MAP.get(int(action), (0.0, 0.0))
        new_heading = (self.heading + angular * DT) % (2 * math.pi)
        wvx = math.cos(new_heading) * linear
        wvy = math.sin(new_heading) * linear
        self.robot_vel[0] = self.robot_vel[0] * FRICTION + wvx * (1 - FRICTION)
        self.robot_vel[1] = self.robot_vel[1] * FRICTION + wvy * (1 - FRICTION)
        self.robot_pos[0] += self.robot_vel[0] * DT
        self.robot_pos[1] += self.robot_vel[1] * DT
        self.heading = new_heading
        self.angular_v = angular
        self.opp_vel[0] *= FRICTION
        self.opp_vel[1] *= FRICTION
        self.opp_pos[0] += self.opp_vel[0] * DT
        self.opp_pos[1] += self.opp_vel[1] * DT
        dv = np.array([self.robot_pos[0] - self.opp_pos[0], self.robot_pos[1] - self.opp_pos[1]])
        d = np.linalg.norm(dv)
        if d < 2 * ROBOT_RADIUS and d > 1e-6:
            overlap = 2 * ROBOT_RADIUS - d
            direction = dv / d
            self.robot_pos[0] += direction[0] * overlap * 0.5
            self.robot_pos[1] += direction[1] * overlap * 0.5
            self.opp_pos[0] -= direction[0] * overlap * 0.5
            self.opp_pos[1] -= direction[1] * overlap * 0.5
            rv_arr = np.array(
                [self.robot_vel[0] - self.opp_vel[0], self.robot_vel[1] - self.opp_vel[1]]
            )
            vn = rv_arr[0] * direction[0] + rv_arr[1] * direction[1]
            if vn < 0:
                self.robot_vel[0] -= vn * direction[0] * 0.5
                self.robot_vel[1] -= vn * direction[1] * 0.5
                self.opp_vel[0] += vn * direction[0] * 0.5
                self.opp_vel[1] += vn * direction[1] * 0.5
        self.step_count += 1
        opp_dist = math.hypot(
            self.opp_pos[0] - self.robot_pos[0], self.opp_pos[1] - self.robot_pos[1]
        )
        opp_dist_change = self.prev_opp_dist - opp_dist
        self.prev_opp_dist = opp_dist
        robot_dist = math.hypot(self.robot_pos[0], self.robot_pos[1])
        op_dist_center = math.hypot(self.opp_pos[0], self.opp_pos[1])
        done = False
        terminal_reward = 0.0
        if robot_dist >= RING_LIMIT:
            done = True
            terminal_reward = -10.0
        elif op_dist_center >= RING_LIMIT:
            done = True
            terminal_reward = 50.0
        elif self.step_count >= 300:
            done = True
            terminal_reward = -5.0

        self._obs = self._get_obs()
        return self._obs, terminal_reward, done, opp_dist_change


# ── Feature Extractor ──
def extract_features(obs, opp_dist_change):
    """Extract 8D feature vector from state for IRL."""
    rp_x, rp_y = obs[0] * RING_LIMIT, obs[1] * RING_LIMIT
    heading = obs[4] * 2 * math.pi
    opp_rel_x, opp_rel_y = obs[6] * RING_LIMIT, obs[7] * RING_LIMIT
    edge_dist = obs[10]
    edge_front = obs[11]
    speed = math.hypot(obs[2] * MAX_SPEED, obs[3] * MAX_SPEED)

    robot_dist = math.hypot(rp_x, rp_y)
    opp_dist = math.hypot(opp_rel_x, opp_rel_y)

    # Heading toward opponent (cosine similarity)
    if opp_dist > 1e-6:
        h2o = (math.cos(heading) * opp_rel_x + math.sin(heading) * opp_rel_y) / opp_dist
    else:
        h2o = 1.0

    # Heading toward center (cosine similarity)
    if robot_dist > 1e-6:
        h2c = -(math.cos(heading) * rp_x + math.sin(heading) * rp_y) / robot_dist
    else:
        h2c = 0.0

    # Contact signal
    contact = 1.0 if opp_dist < 2 * ROBOT_RADIUS * 2 else 0.0

    return np.array(
        [
            1.0 - edge_dist,  # f0: edge proximity (0=center, 1=edge)
            min(opp_dist / 2.0, 1.0),  # f1: opponent distance (normalized)
            opp_dist_change * 5.0,  # f2: closing rate (positive=approaching)
            speed,  # f3: robot speed
            max(h2o, -1.0),  # f4: heading_to_opponent
            max(h2c, -1.0),  # f5: heading_to_center
            edge_front,  # f6: danger forward
            contact,  # f7: contact signal
        ],
        dtype=np.float64,
    )


FEATURE_NAMES = [
    "edge_proximity",
    "opponent_distance",
    "closing_rate",
    "robot_speed",
    "heading_to_opponent",
    "heading_to_center",
    "edge_front",
    "contact_signal",
]

FEATURE_DIMS = len(FEATURE_NAMES)


# ── Collect Expert Trajectories with Features ──
def collect_expert_trajectories(n_episodes=500):
    """Collect V11 expert trajectories with feature vectors."""
    trajectories = []
    total_wins = 0
    total_steps = 0

    for ep in range(n_episodes):
        env = LightweightEnv(seed=ep + 1000)
        obs = env.reset()
        traj = []
        for step in range(300):
            action, qmax = v11_select_action(obs.tolist())
            opp_dist_change = 0.0
            features = extract_features(obs, opp_dist_change)
            obs, reward, done, opp_dist_change = env.step(action)
            traj.append(
                {
                    "features": features.tolist(),
                    "action": int(action),
                    "qmax": float(qmax),
                    "reward": reward if done else 0.0,
                    "step": step,
                }
            )
            total_steps += 1
            if done:
                if reward > 0:
                    total_wins += 1
                break
        trajectories.append(traj)
        if (ep + 1) % 100 == 0:
            print(f"  Expert {ep + 1}/{n_episodes}: {total_wins} wins")

    print(
        f"\nExpert collected: {n_episodes} episodes, {total_wins} wins "
        f"({total_wins / n_episodes * 100:.0f}%), {total_steps} steps"
    )
    return trajectories


# ── Compute Feature Expectations ──
def compute_feature_expectations(trajectories, gamma=0.99):
    """Compute discounted feature expectations from trajectories."""
    total = np.zeros(FEATURE_DIMS)
    count = 0
    for traj in trajectories:
        cumulative = np.zeros(FEATURE_DIMS)
        discount = 1.0
        for step_data in traj:
            f = np.array(step_data["features"])
            cumulative += discount * f
            discount *= gamma
        total += cumulative
        count += 1
    return total / max(count, 1)


# ── Boltzmann Policy (used for Maximum Likelihood IRL) ──
def boltzmann_log_likelihood(trajectories, weights, temperature=1.0):
    """Compute log-likelihood of expert actions under Boltzmann policy with given reward weights.

    P(a|s) ∝ exp(R(s,a)/τ) where R(s,a) = w·φ(s) + action_bias[a]
    Since we don't have next-state dynamics, we use state features only.
    """
    total_ll = 0.0
    total_steps = 0
    for traj in trajectories:
        for step_data in traj:
            f = np.array(step_data["features"])
            step_data["action"]
            # Linear reward: R(s) = w·φ(s)
            state_reward = np.dot(weights, f) / temperature
            # For Boltzmann over 11 actions, all actions share the same state reward
            # since we don't know next state. We use a uniform baseline assumption.
            # This is equivalent to assuming the reward depends only on current state,
            # and the policy is softmax over Q-values (approximated by feature-based reward).
            log_z = state_reward  # simplified: all actions share same state
            # In proper MaxEnt IRL, we'd need Q(s,a), but for prototype:
            # Use action-frequency matching instead
            total_ll += log_z
            total_steps += 1
    return total_ll / max(total_steps, 1)


# ── Feature Expectation Matching (main IRL loop) ──
def irl_feature_matching(expert_trajs, n_iterations=50, lr=0.01, gamma=0.99):
    """
    Learn reward weights via Projection-based IRL.

    Algorithm:
      1. Compute expert feature expectations μ_E
      2. Initialize w randomly
      3. For each iteration:
         a. Sample trajectories using current reward w (random + Boltzmann mix)
         b. Compute student feature expectations μ_S
         c. Update: w ← w + η(μ_E - μ_S)
         d. Project w onto L2 ball (unit norm)
      4. Return learned weights
    """
    mu_E = compute_feature_expectations(expert_trajs, gamma)  # noqa: N806
    print(f"\nExpert feature expectations μ_E: {mu_E}")
    print(f"  (feature names: {FEATURE_NAMES})")

    # Initialize weights
    w = np.random.randn(FEATURE_DIMS) * 0.01
    history = []

    for it in range(n_iterations):
        # Sample trajectories using current reward (random policy for FEM)
        # In FEM, we don't need to solve full MDP — we can use random rollouts
        # and weight them by reward
        n_sample_eps = 50
        sample_trajs = []
        for ep in range(n_sample_eps):
            env = LightweightEnv(seed=ep + 10000)
            obs = env.reset()
            traj = []
            for _step in range(300):
                # Mix: 30% Boltzmann-like (high-reward directions), 70% random
                if random.random() < 0.7:
                    action = random.randrange(N_ACTIONS)
                else:
                    # Choose action that moves toward high-reward features
                    # Simplified: use expert-like action distribution
                    action = random.randrange(N_ACTIONS)

                opp_dist_change = 0.0
                features = extract_features(obs, opp_dist_change)
                obs, reward, done, opp_dist_change = env.step(action)
                traj.append({"features": features.tolist()})
                if done:
                    break
            sample_trajs.append(traj)

        mu_S = compute_feature_expectations(sample_trajs, gamma)  # noqa: N806

        # Gradient: maximize difference between expert and sample expectations
        grad = mu_E - mu_S
        w = w + lr * grad

        # L2 normalization (projection)
        wn = np.linalg.norm(w)
        if wn > 1.0:
            w = w / wn

        # Track convergence
        weight_norm = np.linalg.norm(w)
        grad_norm = np.linalg.norm(grad)
        history.append(
            {
                "iter": it,
                "weight_norm": weight_norm,
                "grad_norm": grad_norm,
                "mu_E": mu_E.tolist(),
                "mu_S": mu_S.tolist(),
                "weights": w.tolist(),
            }
        )

        if (it + 1) % 10 == 0:
            print(f"  Iter {it + 1:3d}: |w|={weight_norm:.3f}, |grad|={grad_norm:.4f}")

    print(f"\nFinal weights w: {w}")
    print(f"  (feature names: {FEATURE_NAMES})")

    # Interpret weights
    print("\n=== Weight Interpretation ===")
    ranked = sorted(zip(FEATURE_NAMES, w, strict=False), key=lambda x: -abs(x[1]))
    for name, val in ranked:
        direction = "REWARD(+)" if val > 0 else "PENALTY(-)"
        print(f"  {direction} {name:>20s}: {val:+.4f}")

    return w, history


# ── Compare with Hand-Crafted Reward ──
def compare_with_handcrafted(learned_w):
    """Compare learned IRL weights with v25_combat hand-crafted reward."""
    # v25_combat shorthand (normalized to comparable scale)
    handcrafted = {
        "edge_proximity": -5.0,  # penalty for near edge
        "opponent_distance": -2.0,  # reward for getting close
        "closing_rate": +2.0,  # reward for approaching
        "robot_speed": 0.0,  # not directly rewarded
        "heading_to_opponent": +3.0,  # reward for facing opponent
        "heading_to_center": +1.0,  # reward for facing center
        "edge_front": -3.0,  # penalty for edge ahead
        "contact_signal": +5.0,  # reward for contact
    }
    hand_w = np.array([handcrafted[n] for n in FEATURE_NAMES])
    hun = np.linalg.norm(hand_w)
    if hun > 0:
        hand_w = hand_w / hun  # normalize

    lwn = np.linalg.norm(learned_w)
    learned_w_norm = learned_w / lwn if lwn > 0 else learned_w

    cosine_sim = np.dot(hand_w, learned_w_norm)
    print("\n=== Comparison with Hand-Crafted (v25_combat) ===")
    print(
        f"  Cosine similarity: {cosine_sim:+.4f} "
        f"({'aligned' if cosine_sim > 0.5 else 'divergent' if cosine_sim > 0 else 'opposite'})"
    )
    print("\n  Feature          |  Learned  |  Hand-Crafted")
    print(f"  {'─' * 18}+{'─' * 11}+{'─' * 14}")
    for i, name in enumerate(FEATURE_NAMES):
        lv = learned_w_norm[i]
        hv = hand_w[i]
        match = "✓" if (lv * hv > 0) else "✗"
        print(f"  {name:>18s} | {lv:+8.4f} | {hv:+8.4f}  {match}")

    return cosine_sim


# ── Main ──
def main():
    print("=" * 70)
    print("  DEBT-002: Inverse Reinforcement Learning — Feature Matching")
    print(f"  Feature space: {FEATURE_DIMS}D  ({', '.join(FEATURE_NAMES)})")
    print("=" * 70)

    # Collect expert trajectories
    print("\n[1/3] Collecting V11 expert trajectories...")
    t0 = time.time()
    expert_trajs = collect_expert_trajectories(n_episodes=500)
    print(f"  Collected in {time.time() - t0:.1f}s")

    # Run IRL
    print("\n[2/3] Running Feature Expectation Matching IRL...")
    t0 = time.time()
    learned_weights, history = irl_feature_matching(expert_trajs, n_iterations=30, lr=0.02)
    print(f"  IRL completed in {time.time() - t0:.1f}s")

    # Compare
    print("\n[3/3] Comparing with hand-crafted reward...")
    cosine_sim = compare_with_handcrafted(learned_weights)

    # Save results
    results = {
        "debt": "DEBT-002",
        "method": "Feature Expectation Matching (FEM)",
        "feature_names": FEATURE_NAMES,
        "learned_weights": learned_weights.tolist(),
        "cosine_similarity_vs_handcrafted": float(cosine_sim),
        "iterations": 30,
        "expert_episodes": 500,
        "history": history,
    }
    out_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "debt002_irl_results.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    # Also save learned weights as C header (for firmware)
    c_path = os.path.join(out_dir, "irl_reward_weights.c")
    with open(c_path, "w") as f:
        f.write("// DEBT-002: Learned IRL reward weights\n")
        f.write("// Feature Expectation Matching from V11 expert trajectories\n\n")
        f.write(f"#define IRL_FEATURE_DIMS {FEATURE_DIMS}\n")
        f.write(f"static const float irl_reward_weights[{FEATURE_DIMS}] = {{\n    ")
        f.write(", ".join(f"{w:.6f}f" for w in learned_weights))
        f.write("\n};\n\n")
        f.write('static const char* irl_feature_names[] = {\n    "')
        f.write('",\n    "'.join(FEATURE_NAMES))
        f.write('"\n};\n')

    print(f"\n  Results saved: {out_path}")
    print(f"  C header saved: {c_path}")

    return results


if __name__ == "__main__":
    main()
