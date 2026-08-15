"""
Agent — unified DQN/Double DQN agent with epsilon-greedy exploration.

Replaces duplicated Agent/DQNAgent/DoubleDQNAgent classes across train_*.py.
Single implementation; toggles between standard DQN and Double DQN via config.
"""

import random

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim

from .config import Config
from .network import DQN
from .replay_buffer import ReplayBuffer


class DQNAgent:
    """Unified DQN / Double DQN agent.

    Features:
    - Standard DQN (use_double_dqn=False): Q(s,a) = r + γ max_a' Q_target(s',a')
    - Double DQN (use_double_dqn=True): Q(s,a) = r + γ Q_target(s', argmax_a' Q(s',a'))
    - Epsilon-greedy exploration with linear decay
    - Gradient clipping
    """

    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        self.action_dim = self.cfg.action_dim
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        # Q-networks
        self.q_net = DQN(
            self.cfg.state_dim,
            self.cfg.action_dim,
            self.cfg.hidden_dim,
            self.cfg.n_hidden,
        ).to(self.device)

        self.target_net = DQN(
            self.cfg.state_dim,
            self.cfg.action_dim,
            self.cfg.hidden_dim,
            self.cfg.n_hidden,
        ).to(self.device)
        self.target_net.load_state_dict(self.q_net.state_dict())

        self.optimizer = optim.Adam(self.q_net.parameters(), lr=self.cfg.learning_rate)
        self.replay_buffer = ReplayBuffer(self.cfg.buffer_size)

        # Exploration state
        self.epsilon = self.cfg.epsilon_start
        self.total_steps = 0

    def select_action(self, state: np.ndarray, training: bool = True) -> int:
        """Select action with epsilon-greedy exploration."""
        if training and random.random() < self.epsilon:
            return random.randrange(self.action_dim)
        with torch.no_grad():
            state_t = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            return self.q_net(state_t).argmax(dim=1).item()

    def update(self) -> float:
        """Perform one Q-learning update step. Returns loss."""
        if len(self.replay_buffer) < self.cfg.batch_size:
            return 0.0

        s, a, r, ns, d = self.replay_buffer.sample(self.cfg.batch_size)
        s, a, r, ns, d = (
            s.to(self.device),
            a.to(self.device),
            r.to(self.device),
            ns.to(self.device),
            d.to(self.device),
        )

        # Current Q-values
        q_values = self.q_net(s).gather(1, a.unsqueeze(1)).squeeze(1)

        with torch.no_grad():
            if self.cfg.use_double_dqn:
                # Double DQN: online net selects action, target net evaluates
                best_actions = self.q_net(ns).argmax(dim=1)
                target_next = self.target_net(ns).gather(1, best_actions.unsqueeze(1)).squeeze(1)
            else:
                # Standard DQN: target net selects and evaluates
                target_next = self.target_net(ns).max(dim=1).values

            target = r + self.cfg.gamma * target_next * (1 - d)

        loss = F.smooth_l1_loss(q_values, target)

        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.q_net.parameters(), self.cfg.clip_grad_norm)
        self.optimizer.step()

        # Update exploration rate
        self.total_steps += 1
        self.epsilon = max(
            self.cfg.epsilon_end,
            self.cfg.epsilon_start
            - self.total_steps
            * (self.cfg.epsilon_start - self.cfg.epsilon_end)
            / self.cfg.epsilon_decay,
        )

        # Target network update
        if self.total_steps % self.cfg.target_update_freq == 0:
            self.target_net.load_state_dict(self.q_net.state_dict())

        return loss.item()

    def save(self, path: str) -> None:
        """Save model state dict."""
        torch.save(self.q_net.state_dict(), path)

    def load(self, path: str) -> None:
        """Load model state dict."""
        self.q_net.load_state_dict(torch.load(path, map_location=self.device, weights_only=True))
        self.target_net.load_state_dict(self.q_net.state_dict())
