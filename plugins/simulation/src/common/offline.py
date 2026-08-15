"""
offline.py — Offline RL support for BottleSumo.

Provides:
- TrajectoryDataset: build supervised dataset from collected episodes
- CQLAgent: Conservative Q-Learning wrapper (prevents overestimation from OOD actions)
- BC pretraining: behavior cloning warm-start for better sample efficiency

Architecture position: common/offline.py → used when online interaction is limited.
Enables training from recorded game logs without live simulator.
"""

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim


class TrajectoryDataset:
    """Dataset of (s, a, r, s', done) transitions from recorded episodes.

    Architecture position: Feed into CQLAgent or behavior cloning pretraining.
    Source: JSON logs from lightweight_env.py evaluations or real robot telemetry.
    """

    def __init__(self, capacity: int = 100000):
        self.capacity = capacity
        self.states: list[np.ndarray] = []
        self.actions: list[int] = []
        self.rewards: list[float] = []
        self.next_states: list[np.ndarray] = []
        self.dones: list[float] = []

    def add_episode(self, transitions: list[tuple[np.ndarray, int, float, np.ndarray, bool]]):
        """Add a full episode of transitions."""
        for s, a, r, ns, d in transitions:
            if len(self.states) >= self.capacity:
                idx = np.random.randint(0, len(self.states))
                self.states[idx] = s.copy()
                self.actions[idx] = a
                self.rewards[idx] = r
                self.next_states[idx] = ns.copy()
                self.dones[idx] = float(d)
            else:
                self.states.append(s.copy())
                self.actions.append(a)
                self.rewards.append(r)
                self.next_states.append(ns.copy())
                self.dones.append(float(d))

    def sample(self, batch_size: int) -> tuple[torch.FloatTensor, ...]:
        """Sample a random batch."""
        idxs = np.random.choice(len(self.states), batch_size, replace=True)
        s_batch = torch.FloatTensor(np.array([self.states[i] for i in idxs]))
        a_batch = torch.LongTensor([self.actions[i] for i in idxs])
        r_batch = torch.FloatTensor([self.rewards[i] for i in idxs])
        ns_batch = torch.FloatTensor(np.array([self.next_states[i] for i in idxs]))
        d_batch = torch.FloatTensor([self.dones[i] for i in idxs])
        return s_batch, a_batch, r_batch, ns_batch, d_batch

    def __len__(self) -> int:
        return len(self.states)


def behavior_cloning_pretrain(
    model: nn.Module,
    dataset: TrajectoryDataset,
    n_epochs: int = 20,
    batch_size: int = 256,
    lr: float = 1e-3,
    device: torch.device | None = None,
) -> float:
    """Pretrain Q-network via behavior cloning on collected trajectories.

    This is a supervised learning phase that brings the network close to
    the demonstrated policy before RL fine-tuning.

    Architecture position: Step 1 of offline-to-online pipeline.
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    model.to(device)
    optimizer = optim.Adam(model.parameters(), lr=lr)
    n_batches = max(1, len(dataset) // batch_size)

    final_loss = 0.0
    for epoch in range(n_epochs):
        total_loss = 0.0
        for _ in range(n_batches):
            s, a, r, _, _ = dataset.sample(batch_size)
            s, a = s.to(device), a.to(device)

            q_values = model(s)
            # Cross-entropy on action distribution (treat collected actions as "expert")
            loss = F.cross_entropy(q_values, a.long())

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        avg_loss = total_loss / n_batches
        final_loss = avg_loss
        if epoch == 0 or (epoch + 1) % 10 == 0:
            print(f"  BC epoch {epoch + 1}/{n_epochs}: loss={avg_loss:.4f}")

    return final_loss


class CQLLoss:
    """Conservative Q-Learning loss for offline RL.

    CQL prevents overestimation of OOD (out-of-distribution) actions
    by adding a penalty term that pushes down Q-values for actions
    not seen in the dataset.

    L_CQL = L_DQN + α * E_{s~D, a~μ}[Q(s,a)] - E_{s~D, a~D}[Q(s,a)]

    Architecture position: Step 2 of offline-to-online pipeline.
    """

    def __init__(self, alpha: float = 1.0, n_action_samples: int = 10):
        self.alpha = alpha
        self.n_action_samples = n_action_samples

    def compute(
        self, q_net, target_net, s, a, r, ns, d, action_dim: int, gamma: float = 0.99, device=None
    ) -> torch.Tensor:
        """Compute CQL loss for a batch.

        Returns total loss = standard DQN loss + α * CQL penalty.
        """
        if device is None:
            device = s.device

        batch_size = s.shape[0]

        # Standard Double DQN loss
        q_values = q_net(s).gather(1, a.unsqueeze(1)).squeeze(1)

        with torch.no_grad():
            best_actions = q_net(ns).argmax(dim=1)
            target_next = target_net(ns).gather(1, best_actions.unsqueeze(1)).squeeze(1)
            target = r + gamma * target_next * (1 - d)

        dqn_loss = F.smooth_l1_loss(q_values, target)

        # CQL penalty: push up dataset actions, push down random actions
        # E_{a~D}[Q(s,a)] - E_{a~μ}[Q(s,a)]
        q_all = q_net(s)  # [B, action_dim]
        q_data = q_all.gather(1, a.unsqueeze(1)).mean()  # actions from dataset

        # Sample random OOD actions
        random_actions = torch.randint(
            0, action_dim, (batch_size, self.n_action_samples), device=device
        )  # [B, n_samples]
        q_random = q_all.gather(1, random_actions).mean()  # mean over all random actions

        cql_penalty = q_random - q_data  # positive when random > data (overestimation)

        total_loss = dqn_loss + self.alpha * cql_penalty

        return total_loss, dqn_loss.item(), cql_penalty.item()
