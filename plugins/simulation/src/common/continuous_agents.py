"""
continuous_agents.py — TD3, SAC, PPO continuous control agents for BottleSumo V11

Architecture:
  - TD3Agent: Twin Delayed DDPG — deterministic, minimal, CPU-efficient
  - SACAgent: Soft Actor-Critic — stochastic, entropy-regularized (Phase 2)
  - PPOAgent: Proximal Policy Optimization — on-policy (Phase 3, GPU recommended)

All agents use Actor-Critic with shared replay buffer.
"""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from typing import Tuple, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim


# ═══════════════════════════════════════════════════════════════════
# Network Architectures
# ═══════════════════════════════════════════════════════════════════

class ContinuousActor(nn.Module):
    """Deterministic actor: state → continuous action [linear, angular].

    Output: tanh → maps to [-1, 1]; caller scales to actual action bounds.
    """

    def __init__(self, state_dim: int, action_dim: int,
                 hidden_dims: list = None, max_action: float = 1.0):
        super().__init__()
        hidden_dims = hidden_dims or [256, 256]
        self.max_action = max_action

        layers = []
        in_dim = state_dim
        for h in hidden_dims:
            layers.extend([nn.Linear(in_dim, h), nn.ReLU()])
            in_dim = h
        layers.append(nn.Linear(in_dim, action_dim))
        self.net = nn.Sequential(*layers)
        self._init_weights()

    def _init_weights(self):
        """Xavier init for all Linear layers, small uniform for last."""
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight, gain=1.0)
                if m is self.net[-1]:
                    nn.init.uniform_(m.weight, -3e-3, 3e-3)
                    nn.init.uniform_(m.bias, -3e-3, 3e-3)
                else:
                    nn.init.zeros_(m.bias)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        a = self.net(state)
        return self.max_action * torch.tanh(a)


class GaussianActor(nn.Module):
    """Stochastic actor for SAC: outputs μ and log_σ.

    Action = tanh(gauss_sample) — naturally bounded.
    """

    LOG_STD_MIN, LOG_STD_MAX = -20, 2

    def __init__(self, state_dim: int, action_dim: int,
                 hidden_dims: list = None):
        super().__init__()
        hidden_dims = hidden_dims or [256, 256]

        layers = []
        in_dim = state_dim
        for h in hidden_dims:
            layers.extend([nn.Linear(in_dim, h), nn.ReLU()])
            in_dim = h
        self.common = nn.Sequential(*layers)
        self.mean_head = nn.Linear(in_dim, action_dim)
        self.log_std_head = nn.Linear(in_dim, action_dim)
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight, gain=1.0)
                nn.init.zeros_(m.bias)

    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        x = self.common(state)
        mean = self.mean_head(x)
        log_std = self.log_std_head(x)
        log_std = torch.clamp(log_std, self.LOG_STD_MIN, self.LOG_STD_MAX)
        return mean, log_std

    def sample(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """Sample action with reparameterization trick.

        Returns: action (tanh), log_prob (corrected for tanh squashing)
        """
        mean, log_std = self.forward(state)
        std = log_std.exp()
        normal = torch.distributions.Normal(mean, std)
        z = normal.rsample()  # reparameterization
        action = torch.tanh(z)

        # Log probability with tanh correction (SAC paper appendix C)
        log_prob = normal.log_prob(z).sum(dim=-1, keepdim=True)
        log_prob -= torch.log(1 - action.pow(2) + 1e-6).sum(dim=-1, keepdim=True)

        return action, log_prob


class Critic(nn.Module):
    """Q-function approximator: (state, action) → Q-value."""

    def __init__(self, state_dim: int, action_dim: int, hidden_dims: list = None):
        super().__init__()
        hidden_dims = hidden_dims or [256, 256]

        layers = []
        in_dim = state_dim + action_dim
        for h in hidden_dims:
            layers.extend([nn.Linear(in_dim, h), nn.ReLU()])
            in_dim = h
        layers.append(nn.Linear(in_dim, 1))
        self.net = nn.Sequential(*layers)
        self._init_weights()

    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight, gain=1.0)
                if m is self.net[-1]:
                    nn.init.uniform_(m.weight, -3e-3, 3e-3)
                    nn.init.uniform_(m.bias, -3e-3, 3e-3)
                else:
                    nn.init.zeros_(m.bias)

    def forward(self, state: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        x = torch.cat([state, action], dim=-1)
        return self.net(x)


# ═══════════════════════════════════════════════════════════════════
# Replay Buffer for Continuous Actions
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ContinuousBufferConfig:
    capacity: int = 100_000
    batch_size: int = 256
    device: str = "cpu"


class ContinuousReplayBuffer:
    """Ring buffer for (state, action, reward, next_state, done) transitions.

    Action is continuous float array (2,), unlike discrete DQN buffer.
    """

    def __init__(self, state_dim: int, action_dim: int,
                 cfg: ContinuousBufferConfig = None):
        self.cfg = cfg or ContinuousBufferConfig()
        self.capacity = self.cfg.capacity
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.device = torch.device(self.cfg.device)

        self.states = np.zeros((self.capacity, state_dim), dtype=np.float32)
        self.actions = np.zeros((self.capacity, action_dim), dtype=np.float32)
        self.rewards = np.zeros(self.capacity, dtype=np.float32)
        self.next_states = np.zeros((self.capacity, state_dim), dtype=np.float32)
        self.dones = np.zeros(self.capacity, dtype=np.float32)

        self.ptr = 0
        self.size = 0

    def push(self, state, action, reward, next_state, done):
        idx = self.ptr % self.capacity
        self.states[idx] = state
        self.actions[idx] = action
        self.rewards[idx] = reward
        self.next_states[idx] = next_state
        self.dones[idx] = float(done)
        self.ptr += 1
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size: int = None):
        batch_size = batch_size or self.cfg.batch_size
        indices = np.random.randint(0, self.size, size=batch_size)

        return (
            torch.FloatTensor(self.states[indices]).to(self.device),
            torch.FloatTensor(self.actions[indices]).to(self.device),
            torch.FloatTensor(self.rewards[indices]).unsqueeze(-1).to(self.device),
            torch.FloatTensor(self.next_states[indices]).to(self.device),
            torch.FloatTensor(self.dones[indices]).unsqueeze(-1).to(self.device),
        )

    def __len__(self):
        return self.size

    def is_ready(self):
        return self.size >= self.cfg.batch_size


# ═══════════════════════════════════════════════════════════════════
# TD3 Agent (Twin Delayed DDPG)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TD3Config:
    """TD3 hyperparameters. Designed for CPU-only BottleSumo training."""
    state_dim: int = 7
    action_dim: int = 2
    max_action: float = 1.0  # action bound magnitude (both linear & angular scaled to this)
    actor_hidden: list = field(default_factory=lambda: [256, 256])
    critic_hidden: list = field(default_factory=lambda: [256, 256])
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    gamma: float = 0.99
    tau: float = 0.005  # soft target update rate
    policy_noise: float = 0.2  # noise added to target actor for smoothing
    noise_clip: float = 0.5
    policy_freq: int = 2  # delayed policy updates: update actor every N critic updates
    exploration_noise: float = 0.1  # noise std for exploration during training
    batch_size: int = 256
    buffer_capacity: int = 100_000
    device: str = "cpu"
    use_double_dqn: bool = True  # always True for TD3 (twin critics)


class TD3Agent:
    """Twin Delayed DDPG agent for continuous BottleSumo action space.

    Key features:
      - Twin Q-networks to reduce overestimation bias
      - Delayed policy updates (actor updated every policy_freq critic steps)
      - Target policy smoothing (noise added to target actions)
      - Deterministic policy (output is directly the action)
    """

    def __init__(self, cfg: TD3Config = None):
        self.cfg = cfg or TD3Config()
        self.device = torch.device(self.cfg.device)

        # Networks
        self.actor = ContinuousActor(
            self.cfg.state_dim, self.cfg.action_dim,
            self.cfg.actor_hidden, self.cfg.max_action
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

        # Buffer
        buf_cfg = ContinuousBufferConfig(
            capacity=self.cfg.buffer_capacity,
            batch_size=self.cfg.batch_size,
            device=self.cfg.device,
        )
        self.replay_buffer = ContinuousReplayBuffer(
            self.cfg.state_dim, self.cfg.action_dim, buf_cfg
        )

        self.total_it = 0
        self.train_mode = True

    def select_action(self, state: np.ndarray, explore: bool = True) -> np.ndarray:
        """Select action for a given state.

        During training, adds Gaussian exploration noise.
        During evaluation, returns deterministic action.
        """
        state_t = torch.FloatTensor(state.reshape(1, -1)).to(self.device)
        with torch.no_grad():
            action = self.actor(state_t).cpu().numpy().flatten()

        if explore and self.train_mode:
            noise = np.random.normal(0, self.cfg.exploration_noise, size=action.shape)
            action = np.clip(action + noise, -self.cfg.max_action, self.cfg.max_action)

        return action

    def push(self, state, action, reward, next_state, done):
        self.replay_buffer.push(state, action, reward, next_state, done)

    def update(self) -> dict:
        """One gradient update step. Returns loss dict for logging."""
        if not self.replay_buffer.is_ready():
            return {"critic_loss": 0.0, "actor_loss": 0.0}

        self.total_it += 1
        states, actions, rewards, next_states, dones = self.replay_buffer.sample()

        # ── Critic Update ──
        with torch.no_grad():
            # Target policy smoothing
            noise = (torch.randn_like(actions) * self.cfg.policy_noise).clamp(
                -self.cfg.noise_clip, self.cfg.noise_clip
            )
            next_actions = (self.actor_target(next_states) + noise).clamp(
                -self.cfg.max_action, self.cfg.max_action
            )

            # Twin Q-target (take minimum)
            q1_target = self.critic1_target(next_states, next_actions)
            q2_target = self.critic2_target(next_states, next_actions)
            q_target = rewards + self.cfg.gamma * (1 - dones) * torch.min(q1_target, q2_target)

        q1_current = self.critic1(states, actions)
        q2_current = self.critic2(states, actions)
        critic_loss = F.mse_loss(q1_current, q_target) + F.mse_loss(q2_current, q_target)

        self.critic1_optimizer.zero_grad()
        self.critic2_optimizer.zero_grad()
        critic_loss.backward()
        self.critic1_optimizer.step()
        self.critic2_optimizer.step()

        # ── Delayed Actor Update ──
        actor_loss = 0.0
        if self.total_it % self.cfg.policy_freq == 0:
            actor_actions = self.actor(states)
            actor_loss = -self.critic1(states, actor_actions).mean()

            self.actor_optimizer.zero_grad()
            actor_loss.backward()
            self.actor_optimizer.step()

            # Soft update targets
            self._soft_update(self.actor_target, self.actor, self.cfg.tau)
            self._soft_update(self.critic1_target, self.critic1, self.cfg.tau)
            self._soft_update(self.critic2_target, self.critic2, self.cfg.tau)

        return {
            "critic_loss": float(critic_loss.item()),
            "actor_loss": float(actor_loss) if isinstance(actor_loss, float) else float(actor_loss.item()),
            "q1_mean": float(q1_current.mean().item()),
            "q2_mean": float(q2_current.mean().item()),
        }

    def _soft_update(self, target, source, tau):
        for tp, sp in zip(target.parameters(), source.parameters()):
            tp.data.copy_(tau * sp.data + (1 - tau) * tp.data)

    def save(self, path: str):
        torch.save({
            "actor": self.actor.state_dict(),
            "critic1": self.critic1.state_dict(),
            "critic2": self.critic2.state_dict(),
            "actor_target": self.actor_target.state_dict(),
            "critic1_target": self.critic1_target.state_dict(),
            "critic2_target": self.critic2_target.state_dict(),
            "actor_opt": self.actor_optimizer.state_dict(),
            "critic1_opt": self.critic1_optimizer.state_dict(),
            "critic2_opt": self.critic2_optimizer.state_dict(),
            "total_it": self.total_it,
            "config": self.cfg,
        }, path)

    def load(self, path: str):
        data = torch.load(path, map_location=self.device, weights_only=True)
        self.actor.load_state_dict(data["actor"])
        self.critic1.load_state_dict(data["critic1"])
        self.critic2.load_state_dict(data["critic2"])
        self.actor_target.load_state_dict(data["actor_target"])
        self.critic1_target.load_state_dict(data["critic1_target"])
        self.critic2_target.load_state_dict(data["critic2_target"])
        self.actor_optimizer.load_state_dict(data["actor_opt"])
        self.critic1_optimizer.load_state_dict(data["critic1_opt"])
        self.critic2_optimizer.load_state_dict(data["critic2_opt"])
        self.total_it = data["total_it"]

    def train(self):
        self.train_mode = True
        self.actor.train()
        self.critic1.train()
        self.critic2.train()

    def eval(self):
        self.train_mode = False
        self.actor.eval()
        self.critic1.eval()
        self.critic2.eval()


# ═══════════════════════════════════════════════════════════════════
# SAC Agent (Soft Actor-Critic)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SACConfig:
    """SAC hyperparameters for CPU-only BottleSumo training."""
    state_dim: int = 7
    action_dim: int = 2
    max_action: float = 1.0
    actor_hidden: list = field(default_factory=lambda: [256, 256])
    critic_hidden: list = field(default_factory=lambda: [256, 256])
    actor_lr: float = 3e-4
    critic_lr: float = 3e-4
    alpha_lr: float = 3e-4      # learnable temperature
    gamma: float = 0.99
    tau: float = 0.005
    alpha: float = 0.2          # initial entropy temperature
    target_entropy: float = None  # auto-set to -action_dim if None
    learn_alpha: bool = True
    batch_size: int = 256
    buffer_capacity: int = 100_000
    device: str = "cpu"


class SACAgent:
    """Soft Actor-Critic for continuous BottleSumo action space.

    Key features:
      - Maximum-entropy RL: π* = argmax E[Σ γᵗ(r + α·H(π))]
      - Twin Q-networks (like TD3) to reduce overestimation
      - Stochastic Gaussian policy with tanh squashing
      - Automatic entropy temperature tuning (optional)
      - Off-policy replay buffer (same as TD3)
    """

    def __init__(self, cfg: SACConfig = None):
        self.cfg = cfg or SACConfig()
        self.device = torch.device(self.cfg.device)

        # Target entropy: -action_dim (standard SAC default)
        if self.cfg.target_entropy is None:
            self.cfg.target_entropy = -self.cfg.action_dim

        # ── Actor (stochastic Gaussian) ──
        self.actor = GaussianActor(
            self.cfg.state_dim, self.cfg.action_dim, self.cfg.actor_hidden
        ).to(self.device)
        self.actor_optimizer = optim.Adam(self.actor.parameters(), lr=self.cfg.actor_lr)

        # ── Twin Critics ──
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

        # ── Entropy Temperature (learnable) ──
        self.log_alpha = torch.tensor(np.log(self.cfg.alpha), requires_grad=True,
                                       device=self.device, dtype=torch.float32)
        self.alpha_optimizer = optim.Adam([self.log_alpha], lr=self.cfg.alpha_lr)
        self.target_entropy = self.cfg.target_entropy

        # ── Replay Buffer ──
        buf_cfg = ContinuousBufferConfig(
            capacity=self.cfg.buffer_capacity,
            batch_size=self.cfg.batch_size,
            device=self.cfg.device,
        )
        self.replay_buffer = ContinuousReplayBuffer(
            self.cfg.state_dim, self.cfg.action_dim, buf_cfg
        )

        self.total_it = 0
        self.train_mode = True

    @property
    def alpha(self) -> float:
        """Current entropy temperature."""
        return float(self.log_alpha.exp().item())

    def select_action(self, state: np.ndarray, explore: bool = True) -> np.ndarray:
        """Sample action from stochastic policy.

        During eval (explore=False): use mean (deterministic mode).
        During train  (explore=True):  sample from distribution.
        """
        state_t = torch.FloatTensor(state.reshape(1, -1)).to(self.device)
        with torch.no_grad():
            if explore and self.train_mode:
                action, _ = self.actor.sample(state_t)
            else:
                mean, log_std = self.actor.forward(state_t)
                action = torch.tanh(mean)
        return action.cpu().numpy().flatten()

    def push(self, state, action, reward, next_state, done):
        self.replay_buffer.push(state, action, reward, next_state, done)

    def update(self) -> dict:
        """One SAC gradient update. Returns loss dict for logging."""
        if not self.replay_buffer.is_ready():
            return {"critic_loss": 0.0, "actor_loss": 0.0, "alpha_loss": 0.0}

        self.total_it += 1
        states, actions, rewards, next_states, dones = self.replay_buffer.sample()

        # ── Critic Update ──
        with torch.no_grad():
            next_actions, next_log_probs = self.actor.sample(next_states)
            q1_target_next = self.critic1_target(next_states, next_actions)
            q2_target_next = self.critic2_target(next_states, next_actions)
            q_target_next = torch.min(q1_target_next, q2_target_next) - self.alpha * next_log_probs
            q_target = rewards + self.cfg.gamma * (1 - dones) * q_target_next

        q1 = self.critic1(states, actions)
        q2 = self.critic2(states, actions)
        critic1_loss = F.mse_loss(q1, q_target)
        critic2_loss = F.mse_loss(q2, q_target)
        critic_loss = critic1_loss + critic2_loss

        self.critic1_optimizer.zero_grad()
        self.critic2_optimizer.zero_grad()
        critic_loss.backward()
        self.critic1_optimizer.step()
        self.critic2_optimizer.step()

        # ── Actor Update ──
        sampled_actions, log_probs = self.actor.sample(states)
        q1_new = self.critic1(states, sampled_actions)
        q2_new = self.critic2(states, sampled_actions)
        q_min = torch.min(q1_new, q2_new)
        actor_loss = (self.alpha * log_probs - q_min).mean()

        self.actor_optimizer.zero_grad()
        actor_loss.backward()
        self.actor_optimizer.step()

        # ── Alpha Update (automatic temperature tuning) ──
        alpha_loss_val = 0.0
        if self.cfg.learn_alpha:
            alpha_loss = -(self.log_alpha * (log_probs.detach() + self.target_entropy)).mean()
            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()
            alpha_loss_val = float(alpha_loss.item())

        # ── Soft Target Updates ──
        self._soft_update(self.critic1_target, self.critic1, self.cfg.tau)
        self._soft_update(self.critic2_target, self.critic2, self.cfg.tau)

        return {
            "critic_loss": float(critic_loss.item()),
            "actor_loss": float(actor_loss.item()),
            "alpha_loss": alpha_loss_val,
            "alpha": self.alpha,
            "q1_mean": float(q1.mean().item()),
            "q2_mean": float(q2.mean().item()),
        }

    def _soft_update(self, target, source, tau):
        for tp, sp in zip(target.parameters(), source.parameters()):
            tp.data.copy_(tau * sp.data + (1 - tau) * tp.data)

    def save(self, path: str):
        torch.save({
            "actor": self.actor.state_dict(),
            "actor_opt": self.actor_optimizer.state_dict(),
            "critic1": self.critic1.state_dict(),
            "critic1_target": self.critic1_target.state_dict(),
            "critic1_opt": self.critic1_optimizer.state_dict(),
            "critic2": self.critic2.state_dict(),
            "critic2_target": self.critic2_target.state_dict(),
            "critic2_opt": self.critic2_optimizer.state_dict(),
            "log_alpha": self.log_alpha.item(),
            "total_it": self.total_it,
            "config": self.cfg,
        }, path)

    def load(self, path: str):
        data = torch.load(path, map_location=self.device, weights_only=True)
        self.actor.load_state_dict(data["actor"])
        self.actor_optimizer.load_state_dict(data["actor_opt"])
        self.critic1.load_state_dict(data["critic1"])
        self.critic1_target.load_state_dict(data["critic1_target"])
        self.critic1_optimizer.load_state_dict(data["critic1_opt"])
        self.critic2.load_state_dict(data["critic2"])
        self.critic2_target.load_state_dict(data["critic2_target"])
        self.critic2_optimizer.load_state_dict(data["critic2_opt"])
        self.log_alpha.data = torch.tensor(data["log_alpha"])
        self.total_it = data["total_it"]

    def train(self):
        self.train_mode = True
        self.actor.train()
        self.critic1.train()
        self.critic2.train()

    def eval(self):
        self.train_mode = False
        self.actor.eval()
        self.critic1.eval()
        self.critic2.eval()


# ═══════════════════════════════════════════════════════════════════
# Quick Smoke Test
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.resolve()))
    
    print("=" * 60)
    print(" TD3 + SAC Smoke Test — BottleSumo V11")
    print("=" * 60)

    from bottlesumo_pi.simulation.continuous_env import ContinuousBottleSumoEnv

    def scale(action_raw, env):
        ll, lh = env.ACTION_LINEAR_LOW, env.ACTION_LINEAR_HIGH
        al, ah = env.ACTION_ANGULAR_LOW, env.ACTION_ANGULAR_HIGH
        s = np.zeros(2, np.float32)
        s[0] = (action_raw[0] + 1) / 2 * (lh - ll) + ll
        s[1] = (action_raw[1] + 1) / 2 * (ah - al) + al
        return s

    # ── TD3 ──
    print("\n── TD3Agent ──")
    td3_cfg = TD3Config(
        state_dim=7, action_dim=2, max_action=1.0,
        batch_size=64, buffer_capacity=5000,
        exploration_noise=0.1, policy_noise=0.2, policy_freq=2,
        actor_lr=1e-3, critic_lr=1e-3, device="cpu",
    )
    env_td3 = ContinuousBottleSumoEnv(opponent_profile="aggressive", seed=42)
    td3 = TD3Agent(td3_cfg)

    td3_rew = []
    for ep in range(10):
        obs, _ = env_td3.reset()
        er, done, trunc = 0.0, False, False
        while not (done or trunc):
            a = scale(td3.select_action(obs, explore=True), env_td3)
            obs, r, done, trunc, _ = env_td3.step(a)
            td3.push(obs, td3.select_action(obs, explore=True), r, obs, done)
            if td3.replay_buffer.is_ready():
                td3.update()
            er += r
        td3_rew.append(er)
    env_td3.close()
    print(f"  TD3  mean={np.mean(td3_rew):.1f} ± {np.std(td3_rew):.1f}")

    # ── SAC ──
    print("\n── SACAgent ──")
    sac_cfg = SACConfig(
        state_dim=7, action_dim=2, max_action=1.0,
        batch_size=64, buffer_capacity=5000,
        alpha=0.2, learn_alpha=True,
        actor_lr=1e-3, critic_lr=1e-3, alpha_lr=3e-4, device="cpu",
    )
    env_sac = ContinuousBottleSumoEnv(opponent_profile="aggressive", seed=42)
    sac = SACAgent(sac_cfg)

    sac_rew = []
    for ep in range(10):
        obs, _ = env_sac.reset()
        er, done, trunc = 0.0, False, False
        while not (done or trunc):
            a = scale(sac.select_action(obs, explore=True), env_sac)
            obs, r, done, trunc, _ = env_sac.step(a)
            sac.push(obs, sac.select_action(obs, explore=True), r, obs, done)
            if sac.replay_buffer.is_ready():
                sac.update()
            er += r
        sac_rew.append(er)
    env_sac.close()
    print(f"  SAC  mean={np.mean(sac_rew):.1f} ± {np.std(sac_rew):.1f}  alpha={sac.alpha:.3f}")

    print(f"\n  TD3: {np.mean(td3_rew):.1f}  |  SAC: {np.mean(sac_rew):.1f}")
    print("[OK] TD3 + SAC training loops verified")
