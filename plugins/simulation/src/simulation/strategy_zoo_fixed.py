#!/usr/bin/env python3
"""
DEBT-005: Strategy Zoo — Fixed for v26 11-action space + 16D observations.

Fixes applied:
  1. Action space: 21-indices → 11-indices (ACTION_MAP from LightweightEnv)
  2. Observation: edge-sensor format → 16D normalized observation
  3. Environment: LightweightBottleSumoEnv → LightweightEnv
  4. info key: info['opponent_out'] → opponent falls off ring check
  5. Tournament: uses v11_select_action as baseline reference

5 Strategy archetypes:
  - AGGRESSIVE: Fast charge, slight steer toward opponent
  - DEFENDER: Edge-avoidant circling
  - FLANKER: Circle opponent, side-attack
  - CAMPER: Center-hold, push intruders
  - V11_EXPERT: v11_select_action (baseline)

Meta-game: UCB + epsilon-greedy over 5×4 payoff matrix
"""

import json
import math
import os
import random
import sys
import time
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests"))
from virtual_mcu import v11_select_action

# ── Environment Constants ──
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
    def __init__(self, seed=None, opponent_profile="random"):
        if seed is not None:
            random.seed(seed)
        self.opponent_profile = opponent_profile
        self.opponent_dir = 0.0
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

        # Opponent AI
        self._opponent_ai()

        self.opp_vel[0] *= FRICTION
        self.opp_vel[1] *= FRICTION
        self.opp_pos[0] += self.opp_vel[0] * DT
        self.opp_pos[1] += self.opp_vel[1] * DT

        # Collision resolution
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
        robot_dist = math.hypot(self.robot_pos[0], self.robot_pos[1])
        op_dist_center = math.hypot(self.opp_pos[0], self.opp_pos[1])
        done = False
        terminal_reward = 0.0
        opponent_off = False
        if robot_dist >= RING_LIMIT:
            done = True
            terminal_reward = -10.0
        elif op_dist_center >= RING_LIMIT:
            done = True
            terminal_reward = 50.0
            opponent_off = True
        elif self.step_count >= 300:
            done = True
            terminal_reward = -5.0
        self._obs = self._get_obs()
        return self._obs, terminal_reward, done, opponent_off

    def _opponent_ai(self):
        """Move opponent based on profile."""
        p = self.opponent_profile
        opponent_dist = math.hypot(
            self.opp_pos[0] - self.robot_pos[0], self.opp_pos[1] - self.robot_pos[1]
        )
        opp_center = math.hypot(self.opp_pos[0], self.opp_pos[1])
        if opp_center >= RING_LIMIT * 0.9:
            # Move toward center
            dx = -self.opp_pos[0]
            dy = -self.opp_pos[1]
        elif p == "aggressive":
            # Move toward robot
            dx = self.robot_pos[0] - self.opp_pos[0]
            dy = self.robot_pos[1] - self.opp_pos[1]
        elif p == "defensive":
            # Move away from robot
            dx = self.opp_pos[0] - self.robot_pos[0]
            dy = self.opp_pos[1] - self.robot_pos[1]
        elif p == "circler":
            # Circle around robot
            self.opponent_dir += 0.1
            dx = -opponent_dist * math.sin(self.opponent_dir)
            dy = opponent_dist * math.cos(self.opponent_dir)
        else:  # random
            dx = random.uniform(-1, 1)
            dy = random.uniform(-1, 1)

        dist = math.hypot(dx, dy)
        if dist > 1e-6:
            speed = 0.3 if p == "aggressive" else 0.15
            self.opp_vel[0] += dx / dist * speed * 0.5
            self.opp_vel[1] += dy / dist * speed * 0.5

    def close(self):
        pass  # No-op for lightweight env


# ── Strategy Definitions (fixed for 16D obs + 11 actions) ──
def extract_h2o(obs):
    """Heading to opponent: -1 to 1 (1=perfectly facing opponent)."""
    _rp_x, _rp_y = obs[0] * RING_LIMIT, obs[1] * RING_LIMIT
    heading = obs[4] * 2 * math.pi
    opp_rel_x, opp_rel_y = obs[6] * RING_LIMIT, obs[7] * RING_LIMIT
    opp_dist = math.hypot(opp_rel_x, opp_rel_y)
    if opp_dist < 1e-6:
        return 0.0
    return (math.cos(heading) * opp_rel_x + math.sin(heading) * opp_rel_y) / opp_dist


def extract_edge_info(obs):
    """Extract safety info from 16D obs."""
    edge_dist = obs[10]  # 0=edge, 1=center
    edge_front = obs[11]  # 1=danger ahead
    edge_back = obs[12]  # 1=danger behind
    edge_left = obs[13]  # 1=danger left
    edge_right = obs[14]  # 1=danger right
    return edge_dist, edge_front, edge_back, edge_left, edge_right


class ZooStrategy:
    """Base class for zoo strategies."""

    def __init__(self, name):
        self.name = name
        self.win_count = 0
        self.loss_count = 0

    def win_rate(self):
        total = self.win_count + self.loss_count
        return self.win_count / total if total > 0 else 0.0

    def record_result(self, win):
        if win:
            self.win_count += 1
        else:
            self.loss_count += 1

    def select_action(self, obs):
        raise NotImplementedError


class AggressiveStrategy(ZooStrategy):
    """Charge opponent at max speed. Edge safety only in emergency."""

    def __init__(self):
        super().__init__("aggressive")

    def select_action(self, obs):
        _, edge_front, edge_back, edge_left, edge_right = extract_edge_info(obs)
        h2o = extract_h2o(obs)

        # Emergency: edge danger ahead → reverse
        if edge_front > 0.85:
            return 1  # REV (action 1 = (-0.3, 0))

        # Steer toward opponent
        if h2o > 0.3:
            return 8  # FW_MAX_FAST (action 8 = (0.8, 0))
        elif h2o < -0.3:
            # Turn toward opponent (spin in place)
            return 10  # TURN_180 (action 10 = (0, π))
        elif h2o > 0:
            return 4  # FW_LEFT (action 4 = (0.35, π/2))
        else:
            return 5  # FW_RIGHT (action 5 = (0.35, -π/2))


class DefenderStrategy(ZooStrategy):
    """Edge-safe circling. Avoids edges, circles to find opponent."""

    def __init__(self):
        super().__init__("defender")
        self.phase = 0

    def select_action(self, obs):
        edge_dist, edge_front, edge_back, edge_left, edge_right = extract_edge_info(obs)
        h2o = extract_h2o(obs)

        # Priority 1: edge safety
        if edge_front > 0.70:
            return 1  # REV
        if edge_back > 0.70:
            return 8  # FW_FAST
        if edge_left > 0.70:
            return 5  # FW_RIGHT
        if edge_right > 0.70:
            return 4  # FW_LEFT

        # Priority 2: face opponent and maintain distance
        self.phase = (self.phase + 1) % 8
        if abs(h2o) < 0.2:
            return 8  # FW_FAST — chase
        elif h2o > 0:
            return 2  # TURN_LEFT
        else:
            return 3  # TURN_RIGHT


class FlankerStrategy(ZooStrategy):
    """Circle opponent, attack from side."""

    def __init__(self):
        super().__init__("flanker")
        self.dir = 1

    def select_action(self, obs):
        _, edge_front, _, _, _ = extract_edge_info(obs)
        extract_h2o(obs)
        opp_rel_x, opp_rel_y = obs[6] * RING_LIMIT, obs[7] * RING_LIMIT
        opp_dist = math.hypot(opp_rel_x, opp_rel_y)

        if edge_front > 0.80:
            return 1  # REV

        # Change direction occasionally
        if random.random() < 0.05:
            self.dir *= -1

        # Far: circle around
        if opp_dist > 0.5:
            return 2 if self.dir > 0 else 3  # TURN_LEFT or TURN_RIGHT
        # Medium: steer with speed
        elif opp_dist > 0.25:
            return 4 if self.dir > 0 else 5  # FW_LEFT or FW_RIGHT
        # Close: attack!
        else:
            return 8  # FW_MAX_FAST


class CamperStrategy(ZooStrategy):
    """Stay near center, push intruders away."""

    def __init__(self):
        super().__init__("camper")

    def select_action(self, obs):
        edge_dist, edge_front, edge_back, edge_left, edge_right = extract_edge_info(obs)
        h2o = extract_h2o(obs)
        opp_rel_x, opp_rel_y = obs[6] * RING_LIMIT, obs[7] * RING_LIMIT
        opp_dist = math.hypot(opp_rel_x, opp_rel_y)

        # Priority 1: stay centered
        if edge_dist < 0.20:  # Near edge
            if edge_front > 0.5:
                return 1  # REV
            if edge_back > 0.5:
                return 8  # FW_FAST
            if edge_left > 0.5:
                return 5  # FW_RIGHT
            return 4  # FW_LEFT

        # Priority 2: push opponent if close
        if opp_dist < 0.35 and abs(h2o) > 0.7:
            return 8  # FW_MAX_FAST — push!

        # Priority 3: face and approach opponent
        if abs(h2o) < 0.3:
            return 0  # FW_MILD (action 0 = (0.5, 0))
        elif h2o > 0:
            return 2  # TURN_LEFT
        else:
            return 3  # TURN_RIGHT


class V11ExpertStrategy(ZooStrategy):
    """v11_select_action expert (baseline)."""

    def __init__(self):
        super().__init__("v11_expert")

    def select_action(self, obs):
        action, _ = v11_select_action(obs.tolist())
        return action


# ── Strategy Zoo Manager ──
class StrategyZoo:
    def __init__(self):
        self.strategies: dict[str, ZooStrategy] = {
            "aggressive": AggressiveStrategy(),
            "defender": DefenderStrategy(),
            "flanker": FlankerStrategy(),
            "camper": CamperStrategy(),
            "v11_expert": V11ExpertStrategy(),
        }
        self.matchup_history: dict[str, dict[str, tuple[int, int]]] = defaultdict(
            lambda: defaultdict(lambda: (0, 0))
        )
        self.current_strategy = "v11_expert"
        self.opponent_profile = "unknown"
        self.exploration_rate = 0.10

    def select_action(self, obs, opponent_profile=None):
        strategy = self.strategies.get(self.current_strategy)
        if strategy is None:
            return 0
        return strategy.select_action(obs)

    def update_strategy(self, opponent_profile):
        self.opponent_profile = opponent_profile
        if random.random() < self.exploration_rate:
            names = list(self.strategies.keys())
            self.current_strategy = random.choice(names)
            return
        best = self.current_strategy
        best_score = 0.0
        for name in self.strategies:
            w, loss_count = self.matchup_history[name][opponent_profile]
            total = w + loss_count
            if total >= 3:
                wr = w / total
                bonus = 0.1 / math.sqrt(total + 1)
                if wr + bonus > best_score:
                    best_score = wr + bonus
                    best = name
        self.current_strategy = best

    def record_matchup(self, strategy, opponent, win):
        w, loss_count = self.matchup_history[strategy][opponent]
        if win:
            self.matchup_history[strategy][opponent] = (w + 1, loss_count)
        else:
            self.matchup_history[strategy][opponent] = (w, loss_count + 1)
        s = self.strategies.get(strategy)
        if s:
            s.record_result(win)

    def get_payoff_matrix(self):
        matrix = {}
        for strat, opps in self.matchup_history.items():
            matrix[strat] = {}
            for opp, (w, losses) in opps.items():
                total = w + losses
                matrix[strat][opp] = {
                    "wins": w,
                    "losses": losses,
                    "rate": w / total if total > 0 else 0.0,
                    "games": total,
                }
        return matrix


# ── Tournament ──
def run_strategy_tournament(n_matches=20, verbose=True):
    """Round-robin: all strategies vs all opponent profiles."""
    strategies = ["aggressive", "defender", "flanker", "camper", "v11_expert"]
    profiles = ["aggressive", "defensive", "circler", "random"]
    zoo = StrategyZoo()
    results = {}
    total_matches = 0
    total_wins = 0

    print("=" * 70)
    print("  DEBT-005: Strategy Zoo Tournament (5 strategies × 4 profiles)")
    print(f"  Matches per matchup: {n_matches}")
    print("=" * 70)

    for strat_name in strategies:
        strategy = zoo.strategies[strat_name]
        results[strat_name] = {}

        for opp_profile in profiles:
            wins = 0
            total = 0
            for match in range(n_matches):
                env = LightweightEnv(seed=70000 + match, opponent_profile=opp_profile)
                obs = env.reset()
                for _step in range(300):
                    action = strategy.select_action(obs)
                    obs, reward, done, opp_off = env.step(action)
                    if done:
                        if opp_off:  # opponent fell off
                            wins += 1
                            zoo.record_matchup(strat_name, opp_profile, True)
                        else:
                            zoo.record_matchup(strat_name, opp_profile, False)
                        total += 1
                        break
                env.close()

            wr = wins / max(total, 1)
            results[strat_name][opp_profile] = {"wins": wins, "total": total, "rate": wr}
            total_matches += total
            total_wins += wins
            if verbose:
                print(f"  {strat_name:>12s} vs {opp_profile:<10s}: {wr:.0%} ({wins}/{total})")

    # Summary table
    print(f"\n{'─' * 60}")
    print(f"  PAYOFF MATRIX ({n_matches} matches per cell)")
    print(f"  {'':>12s}", end="")
    for p in profiles:
        print(f"{p:>10s}", end="")
    print(f"  {'AVG':>8s}")
    for strat in strategies:
        print(f"  {strat:>12s}", end="")
        wr_sum = 0
        for p in profiles:
            wr = results[strat][p]["rate"]
            print(f"{wr:>9.0%}", end=" ")
            wr_sum += wr
        avg = wr_sum / len(profiles)
        print(f"  {avg:>7.0%}")

    # Identify best strategy per opponent profile
    print("\n  BEST STRATEGY PER PROFILE:")
    for p in profiles:
        best_strat = max(strategies, key=lambda s: results[s][p]["rate"])
        best_wr = results[best_strat][p]["rate"]
        print(f"    vs {p:<10s}: {best_strat:>12s} ({best_wr:.0%})")

    ozone_wr = total_wins / max(total_matches, 1)
    print(f"\n  Overall win rate: {ozone_wr:.1%} ({total_wins}/{total_matches})")

    return results, zoo.get_payoff_matrix()


def main():
    t0 = time.time()
    results, payoff = run_strategy_tournament(n_matches=20, verbose=False)
    elapsed = time.time() - t0
    print(f"\n  Tournament completed in {elapsed:.1f}s")

    # Save results
    out_dir = os.path.join(os.path.dirname(__file__), "..", "tests", "results")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "debt005_strategy_zoo_results.json")
    with open(out_path, "w") as f:
        json.dump(
            {
                "debt": "DEBT-005",
                "elapsed_s": elapsed,
                "n_matches_per": 20,
                "results": results,
                "payoff": payoff,
            },
            f,
            indent=2,
        )
    print(f"  Results saved: {out_path}")


if __name__ == "__main__":
    main()
