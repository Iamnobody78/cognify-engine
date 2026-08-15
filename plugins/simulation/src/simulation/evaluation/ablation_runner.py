"""
ablation_runner.py — 2x2 Factorial Ablation: Curriculum vs Edge Penalty

Executes the causal ablation design from ablation_design.json.
4 conditions × 3 reps = 12 mini-training runs.
Reports win rate per condition + causal effect estimates.

Usage: python ablation_runner.py
"""

import json
import os
import sys
import time
from collections import deque

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lightweight_env import LightweightBottleSumoEnv

N_ACTIONS = 21
STATE_DIM = 7

# ── Short training HP for fast ablation ──
HP = {
    "n_episodes": 500,  # short for speed
    "batch_size": 128,
    "buffer_size": 50000,
    "learning_rate": 1e-4,
    "gamma": 0.99,
    "epsilon_start": 1.0,
    "epsilon_end": 0.05,
    "epsilon_decay": 400,
    "target_update_freq": 100,
    "hidden_dim": 128,
    "n_hidden_layers": 2,
    "eval_freq": 100,
    "eval_episodes": 30,
}

RESULTS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bottlesumo_pi", "simulation", "evaluation"
)
os.makedirs(RESULTS_DIR, exist_ok=True)


# ── Neural Network ──
class DQN(nn.Module):
    def __init__(self, obs_dim=7, action_dim=21, hidden_dim=128, n_layers=2):
        super().__init__()
        layers = [nn.Linear(obs_dim, hidden_dim), nn.ReLU()]
        for _ in range(n_layers - 1):
            layers += [nn.Linear(hidden_dim, hidden_dim), nn.ReLU()]
        layers.append(nn.Linear(hidden_dim, action_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


# ── Modified Reward with adjustable edge penalty ──
class AblationReward:
    """Edge penalty multiplier version for ablation"""

    def __init__(self, edge_penalty_multiplier=1.0):
        self.mult = edge_penalty_multiplier
        self.critical = 0.05  # < 1cm normalized
        self.danger = 0.15  # < 3cm
        self.warning = 0.30  # < 6cm
        self.caution = 0.50  # < 10cm

    def compute_edge_reward(self, edge_sensors, heading_to_edge=0.0):
        edge_min = min(edge_sensors)
        if edge_min < self.critical:
            return -150.0 * self.mult, True
        reward = 0.0
        if edge_min < self.danger:
            danger_factor = (self.danger - edge_min) / self.danger
            reward += -40.0 * self.mult * danger_factor
            if heading_to_edge > 0:
                reward += -20.0 * self.mult * heading_to_edge
            if edge_min < 0.05:
                reward += -15.0 * self.mult
        elif edge_min < self.warning:
            warning_factor = (self.warning - edge_min) / (self.warning - self.danger)
            reward += -10.0 * self.mult * warning_factor
            if heading_to_edge > 0:
                reward += -5.0 * self.mult * heading_to_edge
        elif edge_min < self.caution:
            caution_factor = (self.caution - edge_min) / (self.caution - self.warning)
            reward += -3.0 * self.mult * caution_factor
            reward += 0.5 * (1.0 - caution_factor)
        else:
            reward += 0.2 * (edge_min - self.caution) / self.caution
            if heading_to_edge < -0.3:
                reward += 0.3
        return reward, False

    def compute_opponent_reward(self, opp_dist, opp_angle, speed):
        reward = 0.0
        if opp_dist < 1.5:
            reward += 3.0 * (1.0 - opp_dist / 1.5)
        if abs(opp_angle) < 90 and opp_dist < 1.0:
            reward += 2.0 * (1.0 - abs(opp_angle) / 90.0)
        if opp_dist < 0.2 and abs(opp_angle) < 30 and speed > 0.3:
            reward += 8.0
        if speed < 0.05 and opp_dist < 0.5:
            reward -= 1.0
        reward += 0.05
        return reward

    def compute(self, edge_sensors, opp_dist, opp_angle, speed, heading_to_edge=0.0, opp_oob=False):
        edge_r, edge_done = self.compute_edge_reward(edge_sensors, heading_to_edge)
        if edge_done:
            return edge_r, True
        if opp_oob:
            return 200.0, True
        opp_r = self.compute_opponent_reward(opp_dist, opp_angle, speed)
        return edge_r + opp_r, False


# ── Replay Buffer ──
class ReplayBuffer:
    def __init__(self, capacity):
        self.buffer = deque(maxlen=capacity)

    def push(self, *args):
        self.buffer.append(args)

    def __len__(self):
        return len(self.buffer)

    def sample(self, batch_size):
        idxs = np.random.choice(len(self.buffer), batch_size, replace=False)
        batch = [self.buffer[i] for i in idxs]
        s, a, r, ns, d = zip(*batch, strict=False)
        return (
            torch.FloatTensor(np.array(s)),
            torch.LongTensor(a),
            torch.FloatTensor(r),
            torch.FloatTensor(np.array(ns)),
            torch.FloatTensor(d),
        )


# ── Agent (Double DQN, no Dueling, no ActionMasking) ──
class Agent:
    def __init__(self, obs_dim=7, action_dim=21, hp=None):
        self.hp = hp or HP
        self.action_dim = action_dim
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.q_net = DQN(obs_dim, action_dim, self.hp["hidden_dim"], self.hp["n_hidden_layers"]).to(
            self.device
        )
        self.target_net = DQN(
            obs_dim, action_dim, self.hp["hidden_dim"], self.hp["n_hidden_layers"]
        ).to(self.device)
        self.target_net.load_state_dict(self.q_net.state_dict())
        self.optimizer = optim.Adam(self.q_net.parameters(), lr=self.hp["learning_rate"])
        self.buffer = ReplayBuffer(self.hp["buffer_size"])
        self.epsilon = self.hp["epsilon_start"]
        self.steps = 0

    def select_action(self, state, training=True):
        if training and np.random.random() < self.epsilon:
            return np.random.randint(self.action_dim)
        with torch.no_grad():
            q = self.q_net(torch.FloatTensor(state).unsqueeze(0).to(self.device))
            return q.argmax(dim=1).item()

    def update(self):
        if len(self.buffer) < self.hp["batch_size"]:
            return 0.0
        s, a, r, ns, d = self.buffer.sample(self.hp["batch_size"])
        s, a, r, ns, d = (
            s.to(self.device),
            a.to(self.device),
            r.to(self.device),
            ns.to(self.device),
            d.to(self.device),
        )
        qv = self.q_net(s).gather(1, a.unsqueeze(1)).squeeze(1)
        with torch.no_grad():
            best_a = self.q_net(ns).argmax(dim=1)
            target = r + self.hp["gamma"] * self.target_net(ns).gather(
                1, best_a.unsqueeze(1)
            ).squeeze(1) * (1 - d)
        loss = F.smooth_l1_loss(qv, target)
        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.q_net.parameters(), 10.0)
        self.optimizer.step()
        self.steps += 1
        self.epsilon = max(
            self.hp["epsilon_end"],
            self.hp["epsilon_start"]
            - self.steps
            * (self.hp["epsilon_start"] - self.hp["epsilon_end"])
            / self.hp["epsilon_decay"],
        )
        if self.steps % self.hp["target_update_freq"] == 0:
            self.target_net.load_state_dict(self.q_net.state_dict())
        return loss.item()


# ── Curriculum opponent profile sequences ──
REVERSE_CURRICULUM = ["aggressive", "aggressive", "moderate", "passive", "stationary"]


def train_with_curriculum(
    agent, reward_fn, curriculum_profiles, n_episodes=500, eval_freq=100, eval_eps=30, seed_base=0
):
    """Train with a sequenced opponent profile curriculum"""
    (HP["epsilon_start"] - HP["epsilon_end"]) / HP["epsilon_decay"]

    eval_env = LightweightBottleSumoEnv(
        opponent_profile="aggressive", render_mode="none", seed=seed_base + 9999
    )

    for ep in range(n_episodes):
        # Pick curriculum stage
        stage = min(ep * len(curriculum_profiles) // n_episodes, len(curriculum_profiles) - 1)
        profile = curriculum_profiles[stage]

        env = LightweightBottleSumoEnv(
            opponent_profile=profile, render_mode="none", seed=seed_base + ep
        )
        obs, _ = env.reset()
        done = False
        ep_reward = 0.0

        while not done:
            action = agent.select_action(obs, training=True)
            next_obs, r_env, done, truncated, info = env.step(action)

            # Override reward with ablation reward
            np.array(
                [
                    info.get("edge_front", obs[4]),
                    info.get("edge_back", obs[5]),
                    info.get("edge_left", obs[6]),
                    info.get("edge_right", obs[6]),
                ]
            )
            # simplified: front/back/left/right from obs[4:7] or simulation
            max(0, 1.0 - abs(obs[0]) / 0.77)  # approximate from robot position
            max(0, 1.0 - abs(obs[0]) / 0.77)
            max(0, 1.0 - abs(obs[1]) / 0.77)
            max(0, 1.0 - abs(obs[1]) / 0.77)

            # Use env reward directly (already computed by lightweight_env with its own reward)
            # For ablation, we'll modify the environment config instead
            agent.buffer.push(obs, action, r_env, next_obs, float(done))
            agent.update()

            obs = next_obs
            ep_reward += r_env

            if truncated:
                done = True

        env.close()

        # Eval checkpoints
        if (ep + 1) % eval_freq == 0:
            win_rate, avg_reward, drops = evaluate(agent, eval_env, eval_eps)
            print(
                f"  Ep {ep + 1:4d}/{n_episodes} | WR={win_rate:5.1f}% | avgR={avg_reward:7.1f} | eps={agent.epsilon:.3f} | drops={drops}"
            )

    eval_env.close()
    return evaluate(agent, eval_env, eval_eps)


def evaluate(agent, env, n_eps=30):
    wins = drops = total_r = 0
    for _ in range(n_eps):
        obs, _ = env.reset(seed=np.random.randint(0, 100000))
        done = False
        while not done:
            action = agent.select_action(obs, training=False)
            obs, reward, done, truncated, _ = env.step(action)
            total_r += reward
            if truncated:
                done = True
        if reward >= 100:
            wins += 1
        elif reward < -50:
            drops += 1
    return wins / n_eps * 100, total_r / n_eps, drops


# ── Condition-specific environment wrapper ──
class AblationEnvWrapper:
    """Environment wrapper that injects ablation edge penalty"""

    def __init__(self, opponent_profile, edge_penalty_mult=1.0, seed=0):
        self.env = LightweightBottleSumoEnv(
            opponent_profile=opponent_profile, render_mode="none", seed=seed
        )
        self.mult = edge_penalty_mult

    def reset(self, seed=None):
        return self.env.reset(seed=seed)

    def step(self, action):
        obs, reward, done, truncated, info = self.env.step(action)

        # Apply edge penalty multiplier to the reward
        # The env's internal reward already includes edge penalty via V10Reward
        # We multiply the edge-related portion
        if "edge_reward" in info:
            base_reward = reward - info["edge_reward"]
            edge_portion = info["edge_reward"] * self.mult
            reward = base_reward + edge_portion

        return obs, reward, done, truncated, info

    def close(self):
        self.env.close()


def train_condition(
    condition_id, curriculum_profiles, edge_penalty_mult, seed_base, n_episodes=500
):
    """Train a single condition"""
    print(f"\n{'=' * 60}")
    print(
        f" Condition {condition_id}: curriculum={'reverse' if curriculum_profiles else 'none'}, "
        f"edge_penalty={edge_penalty_mult}x"
    )
    print(f"{'=' * 60}")

    agent = Agent(obs_dim=STATE_DIM, action_dim=N_ACTIONS)

    # Environment for data collection
    env = LightweightBottleSumoEnv(
        opponent_profile="aggressive", render_mode="none", seed=seed_base
    )

    eval_env = LightweightBottleSumoEnv(
        opponent_profile="aggressive", render_mode="none", seed=seed_base + 99999
    )

    # Modify reward by adjusting environment's reward function multiplier
    # We'll create a custom reward computation for edge penalty
    reward_fn = AblationReward(edge_penalty_multiplier=edge_penalty_mult)

    for ep in range(n_episodes):
        # Determine opponent profile based on curriculum
        if curriculum_profiles:
            stage = min(ep * len(curriculum_profiles) // n_episodes, len(curriculum_profiles) - 1)
            profile = curriculum_profiles[stage]
            env.close()
            env = LightweightBottleSumoEnv(
                opponent_profile=profile, render_mode="none", seed=seed_base + ep
            )

        obs, _ = env.reset()
        done = False

        while not done:
            action = agent.select_action(obs, training=True)
            next_obs, env_reward, done, truncated, info = env.step(action)

            # Compute ablation reward: override edge penalty
            edge_sensors = (obs[4], obs[5], obs[6], obs[6] if len(obs) > 6 else 1.0)
            opp_dist = obs[2] if len(obs) > 2 else 2.0
            opp_angle = obs[3] if len(obs) > 3 else 0.0

            # Get robot speed from env info or approximate
            speed = info.get("robot_speed", 0.3)

            ab_reward, ab_done = reward_fn.compute(
                edge_sensors,
                opp_dist,
                opp_angle,
                speed,
                heading_to_edge=0.0,
                opp_oob=(env_reward > 100),
            )

            # Use ablation reward instead of env reward
            agent.buffer.push(obs, action, ab_reward, next_obs, float(done or ab_done))
            agent.update()

            obs = next_obs
            if truncated:
                done = True

        # Eval
        if (ep + 1) % HP["eval_freq"] == 0:
            wr, ar, drops = evaluate(agent, eval_env, HP["eval_episodes"])
            print(
                f"  Ep {ep + 1:4d}/{n_episodes} | WR={wr:5.1f}% | R={ar:7.1f} | eps={agent.epsilon:.3f} | drops={drops}"
            )

    env.close()
    final_wr, final_ar, final_drops = evaluate(agent, eval_env, HP["eval_episodes"] * 2)
    eval_env.close()

    print(f"  FINAL: WR={final_wr:.1f}% | R={final_ar:.1f} | drops={final_drops}")
    return {"win_rate": final_wr, "avg_reward": final_ar, "edge_drops": final_drops}


# ── Main ──
def main():
    print("=" * 70)
    print(" 2x2 Factorial Ablation: Curriculum x Edge Penalty")
    print(f" n_episodes={HP['n_episodes']} | 4 conditions x 3 reps = 12 runs")
    print("=" * 70)

    conditions = [
        {"id": "A", "curriculum": None, "penalty": 1.0, "label": "Baseline (V10-C eq.)"},
        {"id": "B", "curriculum": None, "penalty": 50.0, "label": "Strong Penalty Only"},
        {
            "id": "C",
            "curriculum": REVERSE_CURRICULUM,
            "penalty": 1.0,
            "label": "Reverse Curriculum Only",
        },
        {"id": "D", "curriculum": REVERSE_CURRICULUM, "penalty": 50.0, "label": "V10-C+D Full"},
    ]

    all_results = {}
    t0 = time.time()

    for cond in conditions:
        cond_results = []
        for rep in range(3):
            seed = hash(cond["id"]) % 10000 + rep * 1000
            print(
                f"\n--- [{cond['id']}-R{rep + 1}] {cond['label']} | "
                f"curriculum={'Y' if cond['curriculum'] else 'N'} | penalty={cond['penalty']:.0f}x ---"
            )
            r = train_condition(
                cond["id"], cond["curriculum"], cond["penalty"], seed, HP["n_episodes"]
            )
            cond_results.append(r)

        all_results[cond["id"]] = {
            "label": cond["label"],
            "config": {
                "curriculum": bool(cond["curriculum"]),
                "edge_penalty_mult": cond["penalty"],
            },
            "runs": cond_results,
            "mean_wr": np.mean([r["win_rate"] for r in cond_results]),
            "std_wr": np.std([r["win_rate"] for r in cond_results]),
        }
        print(
            f"\n  [{cond['id']}] MEAN WR = {all_results[cond['id']]['mean_wr']:.1f}% +/- {all_results[cond['id']]['std_wr']:.1f}%"
        )

    # ── Causal Effect Computation ──
    wa = all_results["A"]["mean_wr"]
    wb = all_results["B"]["mean_wr"]
    wc = all_results["C"]["mean_wr"]
    wd = all_results["D"]["mean_wr"]

    penalty_effect = (wb + wd) / 2 - (wa + wc) / 2
    curriculum_effect = (wc + wd) / 2 - (wa + wb) / 2
    interaction = wd - wa - ((wb - wa) + (wc - wa))

    elapsed = time.time() - t0

    report = {
        "experiment": "ablation_curriculum_vs_penalty",
        "executed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_episodes_per_run": HP["n_episodes"],
        "total_duration_s": elapsed,
        "results": {
            "A_baseline": {"mean_wr": wa, "std": all_results["A"]["std_wr"]},
            "B_penalty_only": {"mean_wr": wb, "std": all_results["B"]["std_wr"]},
            "C_curriculum_only": {"mean_wr": wc, "std": all_results["C"]["std_wr"]},
            "D_full_V10CD": {"mean_wr": wd, "std": all_results["D"]["std_wr"]},
        },
        "causal_effects": {
            "penalty_main_effect": {
                "value": penalty_effect,
                "interpretation": "Penalty strength causal effect on WR",
            },
            "curriculum_main_effect": {
                "value": curriculum_effect,
                "interpretation": "Curriculum causal effect on WR",
            },
            "interaction": {
                "value": interaction,
                "interpretation": "Super-additive (+) or sub-additive (-) interaction",
            },
        },
        "per_condition_details": {
            k: {kk: vv for kk, vv in v.items() if kk != "runs"} for k, v in all_results.items()
        },
    }

    # Save
    result_path = os.path.join(RESULTS_DIR, "ablation_result.json")
    with open(result_path, "w") as f:
        json.dump(report, f, indent=2, default=float)

    print("\n" + "=" * 70)
    print(" ABLATION RESULTS")
    print("=" * 70)
    print(f"  A (baseline):     WR = {wa:.1f}% ± {all_results['A']['std_wr']:.1f}")
    print(f"  B (penalty only): WR = {wb:.1f}% ± {all_results['B']['std_wr']:.1f}")
    print(f"  C (curric only):  WR = {wc:.1f}% ± {all_results['C']['std_wr']:.1f}")
    print(f"  D (V10-C+D full): WR = {wd:.1f}% ± {all_results['D']['std_wr']:.1f}")
    print(f"\n  Penalty Main Effect:   {penalty_effect:+.1f}%")
    print(f"  Curriculum Main Effect: {curriculum_effect:+.1f}%")
    print(f"  Interaction Effect:     {interaction:+.1f}%")
    print(f"\n  Total time: {elapsed:.0f}s ({elapsed / 60:.1f}min)")
    print(f"  Results saved: {result_path}")

    return report


if __name__ == "__main__":
    main()
