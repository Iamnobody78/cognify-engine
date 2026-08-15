"""
hybrid_agent.py — DQN-TD3 Hierarchical Agent for BottleSumo V11

Architecture:
  L4_Decision (DQN): discrete strategy selector → {push, approach, defend, retreat}
  L4_Execution (TD3): conditional continuous controller → (linear, angular)
  
The DQN sees global state and picks a strategy. The TD3 receives state +
strategy embedding and outputs precise continuous actions.
"""
from __future__ import annotations

import copy
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Tuple, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))

from bottlesumo_pi.common.continuous_agents import Critic


# ═══════════════════════════════════════════════════════════════════
# Strategy Definitions
# ═══════════════════════════════════════════════════════════════════

STRATEGY_PUSH = 0      # opponent is close & aligned → full speed forward
STRATEGY_APPROACH = 1  # opponent is far → navigate closer
STRATEGY_DEFEND = 2    # opponent is behind / flanking → turn to face
STRATEGY_RETREAT = 3   # too close to edge → back away

STRATEGY_NAMES = {0: "push", 1: "approach", 2: "defend", 3: "retreat"}
N_STRATEGIES = 4

# Strategy transition heuristics (for curriculum and safety checks)
FORBIDDEN_TRANSITIONS = [
    # (from_obs_condition, prohibited_strategy)
    # E.g.: "if any edge sensor < 0.05, forbid push (you'll fall off)"
]


# ═══════════════════════════════════════════════════════════════════
# Strategy DQN (discrete decision layer)
# ═══════════════════════════════════════════════════════════════════

class StrategyDQN(nn.Module):
    """Lightweight DQN for strategy selection: state(7) → Q(strategy=4).

    Smaller than the full DQN because 4 strategies << 21 actions.
    """

    def __init__(self, state_dim: int = 7, n_strategies: int = N_STRATEGIES,
                 hidden_dims: list = None):
        super().__init__()
        hidden_dims = hidden_dims or [128, 128]
        layers = []
        in_dim = state_dim
        for h in hidden_dims:
            layers.extend([nn.Linear(in_dim, h), nn.ReLU()])
            in_dim = h
        layers.append(nn.Linear(in_dim, n_strategies))
        self.net = nn.Sequential(*layers)
        self._init()

    def _init(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m is self.net[-1]:
                    nn.init.uniform_(m.weight, -0.003, 0.003)
                nn.init.zeros_(m.bias)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.net(state)


# ═══════════════════════════════════════════════════════════════════
# Conditional TD3 Actor: state + strategy → continuous action
# ═══════════════════════════════════════════════════════════════════

class ConditionalActor(nn.Module):
    """TD3 actor that conditions on strategy mode.

    Input: [state(7), strategy_embedding(4)]
    Output: action(2) ∈ [-1, 1] via tanh
    """

    def __init__(self, state_dim: int = 7, action_dim: int = 2,
                 n_strategies: int = N_STRATEGIES, max_action: float = 1.0,
                 hidden_dims: list = None):
        super().__init__()
        hidden_dims = hidden_dims or [256, 256]
        self.strategy_embedding = nn.Embedding(n_strategies, 4)

        layers = []
        in_dim = state_dim + 4  # state + strategy embedding
        for h in hidden_dims:
            layers.extend([nn.Linear(in_dim, h), nn.ReLU()])
            in_dim = h
        layers.append(nn.Linear(in_dim, action_dim))
        self.net = nn.Sequential(*layers)
        self.max_action = max_action
        self._init()

    def _init(self):
        nn.init.normal_(self.strategy_embedding.weight, 0, 0.1)
        for m in self.net.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m is self.net[-1]:
                    nn.init.uniform_(m.weight, -0.003, 0.003)
                    nn.init.uniform_(m.bias, -0.003, 0.003)
                else:
                    nn.init.zeros_(m.bias)

    def forward(self, state: torch.Tensor, strategy: torch.Tensor) -> torch.Tensor:
        """strategy: LongTensor of shape (batch,)"""
        emb = self.strategy_embedding(strategy)  # (batch, 4)
        x = torch.cat([state, emb], dim=-1)
        return self.max_action * torch.tanh(self.net(x))


# ═══════════════════════════════════════════════════════════════════
# HybridAgent Config
# ═══════════════════════════════════════════════════════════════════

@dataclass
class HybridConfig:
    state_dim: int = 7
    action_dim: int = 2          # continuous action
    n_strategies: int = N_STRATEGIES
    max_action: float = 1.0

    # DQN (strategy)
    dqn_hidden: list = field(default_factory=lambda: [128, 128])
    dqn_lr: float = 1e-3
    dqn_epsilon: float = 1.0
    dqn_epsilon_min: float = 0.05
    dqn_epsilon_decay: float = 0.995

    # TD3 (execution)
    actor_hidden: list = field(default_factory=lambda: [256, 256])
    critic_hidden: list = field(default_factory=lambda: [256, 256])
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    gamma: float = 0.99
    tau: float = 0.005
    policy_noise: float = 0.2
    noise_clip: float = 0.5
    policy_freq: int = 2
    exploration_noise: float = 0.1

    batch_size: int = 256
    buffer_capacity: int = 100_000
    device: str = "cpu"


# ═══════════════════════════════════════════════════════════════════
# HybridAgent
# ═══════════════════════════════════════════════════════════════════

class HybridAgent:
    """Hierarchical DQN-TD3 agent.

    DQN selects strategy mode (push/approach/defend/retreat).
    TD3 executes continuous action conditioned on strategy.
    Both are trained jointly from shared replay buffer.

    Buffer stores: (state, strategy, action, reward, next_state, done)
    """

    def __init__(self, cfg: HybridConfig = None):
        self.cfg = cfg or HybridConfig()
        self.device = torch.device(self.cfg.device)

        # ── Strategy DQN ──
        self.strategy_dqn = StrategyDQN(
            self.cfg.state_dim, self.cfg.n_strategies, self.cfg.dqn_hidden
        ).to(self.device)
        self.strategy_dqn_target = copy.deepcopy(self.strategy_dqn)
        self.dqn_optimizer = optim.Adam(self.strategy_dqn.parameters(), lr=self.cfg.dqn_lr)
        self.epsilon = self.cfg.dqn_epsilon

        # ── Conditional TD3 ──
        self.actor = ConditionalActor(
            self.cfg.state_dim, self.cfg.action_dim,
            self.cfg.n_strategies, self.cfg.max_action, self.cfg.actor_hidden
        ).to(self.device)
        self.actor_target = copy.deepcopy(self.actor)
        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr=self.cfg.actor_lr)

        self.critic1 = Critic(
            self.cfg.state_dim, self.cfg.action_dim, self.cfg.critic_hidden
        ).to(self.device)
        self.critic1_target = copy.deepcopy(self.critic1)
        self.critic1_optimizer = optim.Adam(self.critic1.parameters(), lr=self.cfg.critic_lr)

        self.critic2 = Critic(
            self.cfg.state_dim, self.cfg.action_dim, self.cfg.critic_hidden
        ).to(self.device)
        self.critic2_target = copy.deepcopy(self.critic2)
        self.critic2_optimizer = optim.Adam(self.critic2.parameters(), lr=self.cfg.critic_lr)

        # ── Replay Buffer (stores strategy index too) ──
        self.replay_buffer = HybridReplayBuffer(
            self.cfg.state_dim, self.cfg.action_dim,
            self.cfg.buffer_capacity, self.cfg.batch_size, self.cfg.device
        )

        self.total_it = 0
        self.train_mode = True

    def select_strategy(self, state: np.ndarray, explore: bool = True) -> int:
        """Select discrete strategy mode."""
        if explore and self.train_mode and np.random.random() < self.epsilon:
            return np.random.randint(0, self.cfg.n_strategies)

        state_t = torch.FloatTensor(state.reshape(1, -1)).to(self.device)
        with torch.no_grad():
            q_vals = self.strategy_dqn(state_t)
        return int(q_vals.argmax(dim=-1).item())

    def select_action(self, state: np.ndarray, strategy: int,
                      explore: bool = True) -> np.ndarray:
        """Generate continuous action for a given strategy."""
        state_t = torch.FloatTensor(state.reshape(1, -1)).to(self.device)
        strat_t = torch.tensor([strategy], dtype=torch.long).to(self.device)

        with torch.no_grad():
            action = self.actor(state_t, strat_t).cpu().numpy().flatten()

        if explore and self.train_mode:
            noise = np.random.normal(0, self.cfg.exploration_noise, size=action.shape)
            action = np.clip(action + noise, -self.cfg.max_action, self.cfg.max_action)

        return action

    def act(self, state: np.ndarray, explore: bool = True) -> Tuple[int, np.ndarray]:
        """Full hierarchical decision: strategy + action."""
        strategy = self.select_strategy(state, explore)
        action = self.select_action(state, strategy, explore)
        return strategy, action

    def push(self, state, strategy, action, reward, next_state, done):
        self.replay_buffer.push(state, strategy, action, reward, next_state, done)

    def update(self) -> dict:
        """Train both DQN and TD3 from shared buffer."""
        if not self.replay_buffer.is_ready():
            return {"dqn_loss": 0.0, "critic_loss": 0.0, "actor_loss": 0.0}

        self.total_it += 1
        states, strategies, actions, rewards, next_states, dones = self.replay_buffer.sample()
        strategies = strategies.long()

        # ── DQN Update (strategy selection) ──
        with torch.no_grad():
            # TD3 executes best strategy → Q-target from critic
            next_strategies = self.strategy_dqn_target(next_states).argmax(dim=-1)
            next_actions = self.actor_target(next_states, next_strategies)
            q1_t = self.critic1_target(next_states, next_actions)
            q2_t = self.critic2_target(next_states, next_actions)
            q_target = rewards + self.cfg.gamma * (1 - dones) * torch.min(q1_t, q2_t)

        # DQN loss: MSE(Q_dqn(s)[strategy_taken], q_target)
        q_dqn = self.strategy_dqn(states)
        q_taken = q_dqn.gather(1, strategies.unsqueeze(-1))
        dqn_loss = nn.functional.mse_loss(q_taken, q_target.detach())

        self.dqn_optimizer.zero_grad()
        dqn_loss.backward()
        self.dqn_optimizer.step()

        # ── TD3 Critic Update ──
        with torch.no_grad():
            noise = (torch.randn_like(actions) * self.cfg.policy_noise).clamp(
                -self.cfg.noise_clip, self.cfg.noise_clip)
            next_strategies_td3 = self.strategy_dqn(next_states).argmax(dim=-1)
            next_actions_td3 = (self.actor_target(next_states, next_strategies_td3) + noise).clamp(
                -self.cfg.max_action, self.cfg.max_action)
            q1_target = self.critic1_target(next_states, next_actions_td3)
            q2_target = self.critic2_target(next_states, next_actions_td3)
            q_td3_target = rewards + self.cfg.gamma * (1 - dones) * torch.min(q1_target, q2_target)

        q1 = self.critic1(states, actions)
        q2 = self.critic2(states, actions)
        critic_loss = nn.functional.mse_loss(q1, q_td3_target) + nn.functional.mse_loss(q2, q_td3_target)

        self.critic1_optimizer.zero_grad()
        self.critic2_optimizer.zero_grad()
        critic_loss.backward()
        self.critic1_optimizer.step()
        self.critic2_optimizer.step()

        # ── TD3 Actor Update (delayed) ──
        actor_loss_val = 0.0
        if self.total_it % self.cfg.policy_freq == 0:
            actor_actions = self.actor(states, strategies)
            actor_loss = -self.critic1(states, actor_actions).mean()
            actor_loss_val = float(actor_loss.item())

            self.actor_optimizer.zero_grad()
            actor_loss.backward()
            self.actor_optimizer.step()

            # Soft update targets
            for src, tgt in [(self.actor, self.actor_target),
                             (self.critic1, self.critic1_target),
                             (self.critic2, self.critic2_target),
                             (self.strategy_dqn, self.strategy_dqn_target)]:
                for sp, tp in zip(src.parameters(), tgt.parameters()):
                    tp.data.copy_(self.cfg.tau * sp.data + (1 - self.cfg.tau) * tp.data)

        # ── Epsilon Decay ──
        self.epsilon = max(self.cfg.dqn_epsilon_min,
                           self.epsilon * self.cfg.dqn_epsilon_decay)

        return {
            "dqn_loss": float(dqn_loss.item()),
            "critic_loss": float(critic_loss.item()),
            "actor_loss": actor_loss_val,
            "epsilon": self.epsilon,
        }

    def train(self):
        self.train_mode = True
        self.strategy_dqn.train()
        self.actor.train()
        self.critic1.train()
        self.critic2.train()

    def eval(self):
        self.train_mode = False
        self.strategy_dqn.eval()
        self.actor.eval()
        self.critic1.eval()
        self.critic2.eval()

    def save(self, path: str):
        torch.save({
            "strategy_dqn": self.strategy_dqn.state_dict(),
            "strategy_dqn_target": self.strategy_dqn_target.state_dict(),
            "dqn_opt": self.dqn_optimizer.state_dict(),
            "actor": self.actor.state_dict(),
            "actor_target": self.actor_target.state_dict(),
            "actor_opt": self.actor_optimizer.state_dict(),
            "critic1": self.critic1.state_dict(),
            "critic1_target": self.critic1_target.state_dict(),
            "critic1_opt": self.critic1_optimizer.state_dict(),
            "critic2": self.critic2.state_dict(),
            "critic2_target": self.critic2_target.state_dict(),
            "critic2_opt": self.critic2_optimizer.state_dict(),
            "total_it": self.total_it,
            "epsilon": self.epsilon,
            "config": self.cfg,
        }, path)

    def load(self, path: str):
        d = torch.load(path, map_location=self.device, weights_only=True)
        self.strategy_dqn.load_state_dict(d["strategy_dqn"])
        self.strategy_dqn_target.load_state_dict(d["strategy_dqn_target"])
        self.dqn_optimizer.load_state_dict(d["dqn_opt"])
        self.actor.load_state_dict(d["actor"])
        self.actor_target.load_state_dict(d["actor_target"])
        self.actor_optimizer.load_state_dict(d["actor_opt"])
        self.critic1.load_state_dict(d["critic1"])
        self.critic1_target.load_state_dict(d["critic1_target"])
        self.critic1_optimizer.load_state_dict(d["critic1_opt"])
        self.critic2.load_state_dict(d["critic2"])
        self.critic2_target.load_state_dict(d["critic2_target"])
        self.critic2_optimizer.load_state_dict(d["critic2_opt"])
        self.total_it = d["total_it"]
        self.epsilon = d["epsilon"]


# ═══════════════════════════════════════════════════════════════════
# Hybrid Replay Buffer (stores strategy index)
# ═══════════════════════════════════════════════════════════════════

class HybridReplayBuffer:
    """Extended buffer that stores strategy index alongside transitions."""

    def __init__(self, state_dim: int, action_dim: int,
                 capacity: int = 100_000, batch_size: int = 256,
                 device: str = "cpu"):
        self.capacity = capacity
        self.batch_size = batch_size
        self.device = torch.device(device)

        self.states = np.zeros((capacity, state_dim), dtype=np.float32)
        self.strategies = np.zeros(capacity, dtype=np.int64)
        self.actions = np.zeros((capacity, action_dim), dtype=np.float32)
        self.rewards = np.zeros(capacity, dtype=np.float32)
        self.next_states = np.zeros((capacity, state_dim), dtype=np.float32)
        self.dones = np.zeros(capacity, dtype=np.float32)

        self.ptr = 0
        self.size = 0

    def push(self, state, strategy, action, reward, next_state, done):
        idx = self.ptr % self.capacity
        self.states[idx] = state
        self.strategies[idx] = strategy
        self.actions[idx] = action
        self.rewards[idx] = reward
        self.next_states[idx] = next_state
        self.dones[idx] = float(done)
        self.ptr += 1
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size: int = None):
        batch_size = batch_size or self.batch_size
        idx = np.random.randint(0, self.size, size=batch_size)
        return (
            torch.FloatTensor(self.states[idx]).to(self.device),
            torch.tensor(self.strategies[idx], dtype=torch.long).to(self.device),
            torch.FloatTensor(self.actions[idx]).to(self.device),
            torch.FloatTensor(self.rewards[idx]).unsqueeze(-1).to(self.device),
            torch.FloatTensor(self.next_states[idx]).to(self.device),
            torch.FloatTensor(self.dones[idx]).unsqueeze(-1).to(self.device),
        )

    def is_ready(self):
        return self.size >= self.batch_size

    def __len__(self):
        return self.size


# ═══════════════════════════════════════════════════════════════════
# Smoke Test
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))

    from bottlesumo_pi.simulation.continuous_env import ContinuousBottleSumoEnv

    print("=" * 60)
    print(" HybridAgent Smoke Test — BottleSumo V11")
    print("=" * 60)

    env = ContinuousBottleSumoEnv(opponent_profile="aggressive", seed=42)
    agent = HybridAgent()

    def scale(raw, e):
        ll, lh = e.ACTION_LINEAR_LOW, e.ACTION_LINEAR_HIGH
        al, ah = e.ACTION_ANGULAR_LOW, e.ACTION_ANGULAR_HIGH
        s = np.zeros(2, np.float32)
        s[0] = (raw[0] + 1) / 2 * (lh - ll) + ll
        s[1] = (raw[1] + 1) / 2 * (ah - al) + al
        return s

    rewards = []
    strategy_counts = np.zeros(4, dtype=int)

    for ep in range(20):
        obs, _ = env.reset()
        er, done, trunc = 0.0, False, False

        while not (done or trunc):
            strat, act = agent.act(obs, explore=True)
            strategy_counts[strat] += 1
            scaled = scale(act, env)
            next_obs, r, done, trunc, _ = env.step(scaled)
            agent.push(obs, strat, act, r, next_obs, done)
            if agent.replay_buffer.is_ready():
                agent.update()
            obs = next_obs
            er += r

        rewards.append(er)

    env.close()

    print(f"\n  Mean reward: {np.mean(rewards):.1f} ± {np.std(rewards):.1f}")
    print(f"  Strategy distribution:")
    for i in range(4):
        pct = 100 * strategy_counts[i] / strategy_counts.sum()
        print(f"    {STRATEGY_NAMES[i]:>8}: {strategy_counts[i]:4d} ({pct:.1f}%)")
    print(f"\n[OK] HybridAgent pipeline verified")
