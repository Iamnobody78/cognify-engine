"""
Config — type-safe, single-source-of-truth hyperparameter management.

Replaces scattered HP dicts in train_*.py.
"""

from dataclasses import dataclass


@dataclass
class Config:
    """Centralized training & evaluation configuration.

    All values have been validated against the causal analysis.
    Defaults reflect the BayesOpt best config (trial 13, WR=87.0%).
    """

    # ── Environment ──
    # Sprint 37 T1 (FP-RL-003 fix): 7→9 dims — appended opponent velocity in
    # robot-relative frame (v_forward, v_right) to unlock pursuit skills.
    state_dim: int = 9
    action_dim: int = 21
    opponent_profile: str = "aggressive"

    # ── Sensor Noise (sim-to-real transfer) ──
    # "none" = clean sim, "realistic" = VL53L0X + IR seeker + encoder
    # "harsh" = worst-case, "mild" = fine-tuning
    noise_profile: str = "none"

    # ── Network Architecture ──
    hidden_dim: int = 128
    n_hidden: int = 2  # number of intermediate hidden Linear layers (original V10 default)

    # ── Training Loop ──
    n_episodes: int = 2000
    batch_size: int = 128
    buffer_size: int = 100000
    learning_rate: float = 3e-4
    gamma: float = 0.99

    # ── Exploration ──
    epsilon_start: float = 1.0
    epsilon_end: float = 0.05
    epsilon_decay: int = 1500

    # ── Target Network ──
    target_update_freq: int = 100
    use_double_dqn: bool = True

    # ── Optimization ──
    clip_grad_norm: float = 10.0

    # ── Evaluation ──
    eval_freq: int = 50
    eval_episodes: int = 30
    win_threshold: float = 100.0  # reward > this → win
    edge_threshold: float = -50.0  # reward < this → edge drop

    # ── Persistence ──
    save_dir: str = "models"
    save_name: str = "v10_dqn.pt"

    # ── Distillation ──
    distillation_temperature: float = 4.0
    distillation_alpha: float = 0.5

    # Reward Shaping (from CausalPrior BayesOpt)
    edge_penalty_weight: float = 1.0  # global scale for V10 edge penalties
    push_threshold: float = 0.2  # distance threshold for push bonus (meters)

    @property
    def save_path(self) -> str:
        """Full save path, os-independent."""
        import os

        return os.path.join(self.save_dir, self.save_name)

    @classmethod
    def bayesopt_best(cls) -> "Config":
        """Best config from CausalPrior Bayesian Optimization (trial 13, WR=87.0%)."""
        return cls(
            n_episodes=750,
            learning_rate=3e-5,
            batch_size=128,
            buffer_size=50000,
            epsilon_decay=400,
            target_update_freq=400,
            hidden_dim=128,
            n_hidden=2,
            clip_grad_norm=10.0,
            eval_freq=100,
            eval_episodes=30,
            edge_penalty_weight=71.58911304978123,
            push_threshold=0.28479493743255073,
        )

    @classmethod
    def bayesopt_dqn(cls) -> "Config":
        """BayesOpt DQN — causal-prior params adapted for RL (not heuristic).

        edge_penalty_weight=5.0: strong enough to prevent edge deaths,
        but leaves [-100,100] range differentiation for gradient learning.
        n_episodes=1000, epsilon_decay=800: more exploration than bayesopt_best.
        """
        return cls(
            n_episodes=1000,
            learning_rate=1e-4,
            batch_size=128,
            buffer_size=80000,
            epsilon_decay=800,
            target_update_freq=400,
            hidden_dim=128,
            n_hidden=2,
            clip_grad_norm=10.0,
            eval_freq=100,
            eval_episodes=30,
            edge_penalty_weight=5.0,
            push_threshold=0.28479493743255073,
        )

    @classmethod
    def bayesopt_dqn_noisy(cls) -> "Config":
        """BayesOpt DQN with realistic sensor noise for sim-to-real transfer.

        Same as bayesopt_dqn but with noise_profile="realistic".
        More episodes to compensate for noise-induced variance in Q-estimates.
        """
        return cls(
            n_episodes=1500,
            learning_rate=1e-4,
            batch_size=128,
            buffer_size=100000,
            epsilon_decay=1000,
            target_update_freq=400,
            hidden_dim=128,
            n_hidden=2,
            clip_grad_norm=10.0,
            eval_freq=100,
            eval_episodes=30,
            edge_penalty_weight=5.0,
            push_threshold=0.28479493743255073,
            noise_profile="realistic",
        )

    @classmethod
    def nano(cls) -> "Config":
        """Nano student config (7→16→16→21, for embedded deployment)."""
        return cls(
            hidden_dim=16,
            n_hidden=2,
            n_episodes=500,
            learning_rate=1e-4,
            batch_size=64,
            buffer_size=10000,
            epsilon_decay=200,
            target_update_freq=50,
        )

    @classmethod
    def quick_test(cls) -> "Config":
        """Ultra-fast config for CI / testing."""
        return cls(
            n_episodes=100,
            hidden_dim=32,
            n_hidden=1,
            buffer_size=5000,
            batch_size=32,
            epsilon_decay=50,
            eval_freq=20,
            eval_episodes=10,
            target_update_freq=20,
        )
