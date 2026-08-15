#!/usr/bin/env python3
"""DEBT-001 HIL Verification: Load DAgger C weights, run 30ep closed-loop."""
import sys, os, re, math, random, struct, time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tests'))
from virtual_mcu import v11_select_action

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
        if seed is not None: random.seed(seed)
        self.reset()
    def reset(self):
        angle = random.uniform(0, 2*math.pi); r = random.uniform(0, 0.2)
        self.robot_pos = [r*math.cos(angle), r*math.sin(angle)]
        self.robot_vel = [0.0, 0.0]; self.heading = random.uniform(0, 2*math.pi); self.angular_v = 0.0
        while True:
            angle = random.uniform(0, 2*math.pi); r = random.uniform(0.3, 0.7)
            self.opp_pos = [r*math.cos(angle), r*math.sin(angle)]
            if math.hypot(self.opp_pos[0]-self.robot_pos[0], self.opp_pos[1]-self.robot_pos[1]) > 2*ROBOT_RADIUS: break
        self.opp_vel = [0.0, 0.0]; self.step_count = 0
        return self._get_obs()
    def _get_obs(self):
        rp, rv, h = self.robot_pos, self.robot_vel, self.heading
        op, ov = self.opp_pos, self.opp_vel
        robot_dist = math.hypot(rp[0], rp[1])
        opp_rel_x = op[0]-rp[0]; opp_rel_y = op[1]-rp[1]
        edge_dist = (RING_LIMIT-robot_dist)/RING_LIMIT
        fd = RING_LIMIT-math.hypot(rp[0]+0.5*math.cos(h), rp[1]+0.5*math.sin(h))
        edge_front = 1.0-min(1.0,max(0.0,max(0,fd)/RING_LIMIT))
        bd = RING_LIMIT-math.hypot(rp[0]-0.5*math.cos(h), rp[1]-0.5*math.sin(h))
        edge_back = 1.0-min(1.0,max(0.0,max(0,bd)/RING_LIMIT))
        la = h+math.pi/2; ld = RING_LIMIT-math.hypot(rp[0]+0.5*math.cos(la), rp[1]+0.5*math.sin(la))
        edge_left = 1.0-min(1.0,max(0.0,max(0,ld)/RING_LIMIT))
        ra = h-math.pi/2; rd = RING_LIMIT-math.hypot(rp[0]+0.5*math.cos(ra), rp[1]+0.5*math.sin(ra))
        edge_right = 1.0-min(1.0,max(0.0,max(0,rd)/RING_LIMIT))
        return np.array([rp[0]/RING_LIMIT, rp[1]/RING_LIMIT, rv[0]/MAX_SPEED, rv[1]/MAX_SPEED,
            h/(2*math.pi), self.angular_v/MAX_ANGULAR, opp_rel_x/RING_LIMIT, opp_rel_y/RING_LIMIT,
            ov[0]/MAX_SPEED, ov[1]/MAX_SPEED, edge_dist, edge_front, edge_back, edge_left, edge_right,
            self.step_count/300.0], dtype=np.float32)
    def step(self, action):
        linear, angular = ACTION_MAP.get(int(action), (0.0,0.0))
        new_heading = (self.heading + angular*DT) % (2*math.pi)
        wvx = math.cos(new_heading)*linear; wvy = math.sin(new_heading)*linear
        self.robot_vel[0] = self.robot_vel[0]*FRICTION + wvx*(1-FRICTION)
        self.robot_vel[1] = self.robot_vel[1]*FRICTION + wvy*(1-FRICTION)
        self.robot_pos[0] += self.robot_vel[0]*DT; self.robot_pos[1] += self.robot_vel[1]*DT
        self.heading = new_heading; self.angular_v = angular
        self.opp_vel[0] *= FRICTION; self.opp_vel[1] *= FRICTION
        self.opp_pos[0] += self.opp_vel[0]*DT; self.opp_pos[1] += self.opp_vel[1]*DT
        dv = np.array([self.robot_pos[0]-self.opp_pos[0], self.robot_pos[1]-self.opp_pos[1]])
        d = np.linalg.norm(dv)
        if d < 2*ROBOT_RADIUS and d > 1e-6:
            overlap = 2*ROBOT_RADIUS-d; direction = dv/d
            self.robot_pos[0] += direction[0]*overlap*0.5; self.robot_pos[1] += direction[1]*overlap*0.5
            self.opp_pos[0] -= direction[0]*overlap*0.5; self.opp_pos[1] -= direction[1]*overlap*0.5
            rv_arr = np.array([self.robot_vel[0]-self.opp_vel[0], self.robot_vel[1]-self.opp_vel[1]])
            vn = rv_arr[0]*direction[0]+rv_arr[1]*direction[1]
            if vn < 0: self.robot_vel[0] -= vn*direction[0]*0.5; self.robot_vel[1] -= vn*direction[1]*0.5; self.opp_vel[0] += vn*direction[0]*0.5; self.opp_vel[1] += vn*direction[1]*0.5
        self.step_count += 1
        robot_dist = math.hypot(self.robot_pos[0], self.robot_pos[1])
        opp_dist = math.hypot(self.opp_pos[0], self.opp_pos[1])
        done = False; reward = 0.0
        if robot_dist >= RING_LIMIT: done = True; reward = -10.0
        elif opp_dist >= RING_LIMIT: done = True; reward = 50.0
        elif self.step_count >= 300: done = True; reward = -5.0
        return self._get_obs(), reward, done

# ─── DAgger DQN Parser (16→128→64→11) ───
class DaggerDQN:
    """Parse dqn_weights_dagger.c → numpy arrays. Architecture: 16→128→64→11."""
    def __init__(self, weights_path):
        with open(weights_path, 'r') as f: content = f.read()

        def parse_array(name, expected_size, dims=None):
            pattern = rf'(?:const\s+)?float\s+{re.escape(name)}\[\d+\]\s*=\s*\{{'
            match = re.search(pattern, content)
            if not match: raise ValueError(f"Array '{name}' not found")
            start = match.start()
            brace_start = content.find('{', start)
            pos = brace_start; depth = 0
            while pos < len(content):
                if content[pos] == '{': depth += 1
                elif content[pos] == '}':
                    depth -= 1
                    if depth == 0: break
                pos += 1
            body = content[brace_start:pos+1]
            numbers = re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?', body)
            values = np.array([float(n) for n in numbers[:expected_size]], dtype=np.float32)
            if dims: values = values.reshape(*dims)
            return values

        # Try fixed naming first, fall back to old naming
        try:
            self.fc1_w = parse_array('dqn_fc1_weight', 2048, (128, 16))
            self.fc1_b = parse_array('dqn_fc1_bias', 128)
        except ValueError:
            self.fc1_w = parse_array('dqn_fc1_weight', 2048, (128, 16))
            self.fc1_b = parse_array('dqn_fc0_bias', 128)
        try:
            self.fc2_w = parse_array('dqn_fc2_weight', 8192, (64, 128))
            self.fc2_b = parse_array('dqn_fc2_bias', 64)
        except ValueError:
            self.fc2_w = parse_array('dqn_fc2_weight', 8192, (64, 128))
            self.fc2_b = parse_array('dqn_fc1_bias', 64)
        try:
            self.fc3_w = parse_array('dqn_fc_out_weight', 704, (11, 64))
            self.fc3_b = parse_array('dqn_fc_out_bias', 11)
        except ValueError:
            self.fc3_w = parse_array('dqn_fc3_weight', 704, (11, 64))
            self.fc3_b = parse_array('dqn_fc2_bias', 11)
        total = self.fc1_w.size+self.fc1_b.size+self.fc2_w.size+self.fc2_b.size+self.fc3_w.size+self.fc3_b.size
        print(f"[DaggerDQN] Loaded {total} params ({self.fc1_w.shape},{self.fc2_w.shape},{self.fc3_w.shape})")

    def forward(self, obs):
        x = np.array(obs[:16], dtype=np.float32).reshape(1, 16)
        x = np.maximum(0, x @ self.fc1_w.T + self.fc1_b)  # (1,16)@(16,128)→(1,128)
        x = np.maximum(0, x @ self.fc2_w.T + self.fc2_b)  # (1,128)@(128,64)→(1,64)
        x = x @ self.fc3_w.T + self.fc3_b  # (1,64)@(64,11)→(1,11)
        q = x.flatten()
        return int(np.argmax(q)), float(q[q.argmax()])

def run_hil_test(weights_path, n_episodes=30, seed=42):
    """Run HIL closed-loop validation with DAgger DQN."""
    dqn = DaggerDQN(weights_path)
    print(f"\n{'='*60}")
    print(f"DEBT-001 HIL Test: DAgger DQN, {n_episodes} episodes, seed={seed}")
    print(f"{'='*60}")

    random.seed(seed)
    np.random.seed(seed)

    results = {'wins': 0, 'losses': 0, 'draws': 0, 'total_steps': 0,
               'action_counts': {}, 'fall_offs': 0, 'push_outs': 0, 'timeouts': 0}

    for ep in range(n_episodes):
        env = LightweightEnv(seed=seed+ep)
        obs = env.reset()
        ep_steps = 0
        while True:
            # Use DAgger DQN
            action, qmax = dqn.forward(obs)
            results['action_counts'][action] = results['action_counts'].get(action, 0) + 1
            obs, reward, done = env.step(action)
            ep_steps += 1
            if done:
                if reward > 0:
                    results['wins'] += 1
                    results['push_outs'] += 1
                elif reward < -5:
                    results['losses'] += 1
                    results['fall_offs'] += 1
                else:
                    results['draws'] += 1
                    results['timeouts'] += 1
                results['total_steps'] += ep_steps
                break

    win_rate = results['wins'] / n_episodes
    print(f"\n── Results ──")
    print(f"  Wins:      {results['wins']}/{n_episodes} ({win_rate:.1%})")
    print(f"  Losses:    {results['losses']}")
    print(f"  Timeouts:  {results['timeouts']}")
    print(f"  Avg steps: {results['total_steps']/n_episodes:.1f}")
    print(f"  Action dist: { {ACTION_NAMES.get(k,str(k)):v for k,v in sorted(results['action_counts'].items())} }")

    gate = "PASS" if win_rate >= 0.30 else "FAIL"
    print(f"\nGate (≥30%): {gate}")
    return win_rate, results

if __name__ == '__main__':
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Try multiple paths for the weights file
    # Try new fixed naming first, then old naming
    candidates = [
        os.path.join(script_dir, '..', 'firmware', 'stm32_mcu', 'src', 'dqn_weights_fixed.c'),
        os.path.join(os.path.expanduser('~'), 'bottlesumo_pi', 'firmware', 'stm32_mcu', 'src', 'dqn_weights_fixed.c'),
        os.path.join(script_dir, '..', 'simulation', 'dqn_weights_dagger.c'),
        os.path.join(os.path.expanduser('~'), 'bottlesumo_pi', 'simulation', 'dqn_weights_dagger.c'),
        os.path.join(script_dir, 'dqn_weights_dagger.c'),
    ]
    weights_path = None
    for p in candidates:
        if os.path.exists(p):
            weights_path = p
            break
    if weights_path is None:
        print("ERROR: dqn_weights_dagger.c not found. Tried:", candidates)
        sys.exit(1)

    wr, results = run_hil_test(weights_path, n_episodes=30, seed=42)
