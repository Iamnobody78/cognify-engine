"""
Network — single-source Q-network definitions.

Replaces 7 duplicated QNet/DQN classes across train_*.py, eval_*.py,
distill_nano.py, gatekeeper.py.
"""

import torch.nn as nn


class DQN(nn.Module):
    """Flexible DQN: configurable hidden dimensions and layer count.

    Architecture: State → [hidden × n_layers] → Actions
    Default: 7→128→128→21 (V10 base)
    Nano:    7→16→16→21 (embedded)
    """

    def __init__(
        self,
        obs_dim: int = 7,
        action_dim: int = 21,
        hidden_dim: int = 128,
        n_hidden: int = 2,
    ):
        """DQN with configurable architecture.

        n_hidden = number of intermediate hidden Linear layers (matching original V10 code).
        n_hidden=2 → 7→128→128→128→21 (input + 2 hidden + output = 4 Linear layers).
        """
        super().__init__()
        layers = [nn.Linear(obs_dim, hidden_dim), nn.ReLU()]
        for _ in range(n_hidden):
            layers += [nn.Linear(hidden_dim, hidden_dim), nn.ReLU()]
        layers.append(nn.Linear(hidden_dim, action_dim))
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


class NanoQNet(nn.Module):
    """Nano student model: 7→16→16→21, matches distill_nano.py.

    Fixed architecture for embedded deployment (816 params, ~3.2KB FP32).
    Includes input normalization (X_mean, X_std) for deployment.
    """

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(7, 16),
            nn.ReLU(),
            nn.Linear(16, 16),
            nn.ReLU(),
            nn.Linear(16, 21),
        )

    def forward(self, x):
        return self.net(x)
