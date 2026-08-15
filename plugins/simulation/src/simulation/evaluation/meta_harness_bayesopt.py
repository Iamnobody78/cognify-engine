#!/usr/bin/env python3
"""
meta_harness_bayesopt.py — 因果先验驱动的贝叶斯优化
用已识别的6个因果变量作为搜索空间, Optuna做贝叶斯采样
"""

import json
import os
from datetime import datetime

import numpy as np

# ============================================================
# 因果搜索空间 (从 harness_candidates.json + 因果分析推导)
# ============================================================
SEARCH_SPACE = {
    "push_threshold": {
        "type": "float",
        "min": 0.10,
        "max": 0.40,
        "causal_evidence": "V10-C+D 的+500/-500非对称惩罚 → threshold应≥0.20",
        "prior": "normal",
        "prior_mu": 0.22,
        "prior_sigma": 0.05,
    },
    "edge_penalty_weight": {
        "type": "float",
        "min": 1.0,
        "max": 100.0,
        "log": True,
        "causal_evidence": "50x惩罚 → +25.5% (与curriculum协变, 需消融确认)",
        "prior": "log_normal",
        "prior_mu": 3.0,
        "prior_sigma": 1.0,
    },
    "action_bins": {
        "type": "int",
        "min": 11,
        "max": 21,
        "step": 2,
        "causal_evidence": "11→21: 理论上+5.7% (但数据不支持统计显著)",
        "prior": None,
    },
    "lr": {
        "type": "float",
        "min": 1e-5,
        "max": 1e-3,
        "log": True,
        "causal_evidence": "V10-E坍塌可能与lr过大有关 → 优先搜索低lr区",
        "prior": "log_normal",
        "prior_mu": -9.0,
        "prior_sigma": 1.5,
    },
    "target_update_freq": {
        "type": "int",
        "min": 50,
        "max": 500,
        "step": 50,
        "causal_evidence": "Double DQN target网络更新频率直接影响Q值稳定性",
        "prior": None,
    },
    "n_episodes": {
        "type": "int",
        "min": 500,
        "max": 2000,
        "step": 250,
        "causal_evidence": "训练非单调: 1500ep > 3500ep → 存在最优区间",
        "prior": None,
    },
}

# 固定配置 (因果分析确认为正向, 不再搜索)
FIXED_CONFIG = {
    "use_double_dqn": True,  # +37%: 10→47, 因果确认为强正向
    "use_dueling": False,  # -47%: 唯一确定负因果效应, 排除
    "use_action_mask": False,  # -8%: 过度保守 → 排除
    "use_curriculum": True,  # +25.5%: 与penalty协变但大概率正向
    "use_distillation": True,  # +20%: 92.5% > 72.5%, 需复制确认
    "distillation_temp": 4.0,  # 来自Nano-M1配置
    "distillation_alpha": 0.5,  # KL权重
}


# ============================================================
# 优化器核心
# ============================================================
class CausalBayesianOptimizer:
    def __init__(self, study_name="meta_harness_bayesopt"):
        self.study_name = study_name
        self.search_space = SEARCH_SPACE
        self.fixed = FIXED_CONFIG
        self.trials_log = []

    def suggest_config(self, trial):
        """Optuna suggest — 只采样因果变量"""
        config = dict(self.fixed)
        for name, spec in self.search_space.items():
            if spec["type"] == "float":
                if spec.get("log"):
                    config[name] = trial.suggest_float(name, spec["min"], spec["max"], log=True)
                else:
                    config[name] = trial.suggest_float(name, spec["min"], spec["max"])
            elif spec["type"] == "int":
                config[name] = trial.suggest_int(
                    name, spec["min"], spec["max"], step=spec.get("step", 1)
                )
        return config

    def evaluate(self, config):
        """
        评估函数 — 此处为桩, 实际需接入仿真环境

        返回: {"win_rate": float, "edge_drops": float, "avg_steps": int}
        """
        # 桩实现: 基于因果模型的快速预测 (用于测试)
        score = 45  # baseline V10-C

        # 特征贡献 (基于因果分析的方向估计)
        if config.get("push_threshold", 0) > 0.25:
            score += 3
        if config.get("edge_penalty_weight", 1) > 30:
            score += 12  # 强惩罚 → 留在战斗区
        if config.get("n_episodes", 1000) <= 1500:
            score += 5  # 非单调效应
        if not config.get("use_dueling", True):
            score += 15  # 无Dueling → 无坍塌风险
        if config.get("use_distillation", False):
            score += 10  # 蒸馏去噪

        # 噪声
        score += np.random.normal(0, 5)
        return {
            "win_rate": min(95, max(5, round(score, 1))),
            "edge_drops": round(np.random.beta(3, 7) * 100, 1),
            "avg_steps": int(np.random.gamma(50, 2)),
        }

    def run_manual_demo(self, n_trials=20):
        """手动演示 (不依赖Optuna) — 用随机+贪心混合"""
        print(f"# 贝叶斯优化演示: {n_trials} 次试验")
        print(f"# 搜索空间: {len(self.search_space)} 个因果变量")
        print(f"# 固定配置: {len(self.fixed)} 项 (因果确认为正向/负向)")
        print()

        best_score = 0
        best_config = None

        for i in range(n_trials):
            config = dict(self.fixed)
            for name, spec in self.search_space.items():
                if spec["type"] == "float":
                    v = np.random.uniform(spec["min"], spec["max"])
                    if spec.get("log"):
                        v = np.exp(np.random.uniform(np.log(spec["min"]), np.log(spec["max"])))
                elif spec["type"] == "int":
                    v = np.random.randint(spec["min"], spec["max"] + 1)
                    if spec.get("step"):
                        v = (v // spec["step"]) * spec["step"]
                config[name] = round(v, 5) if isinstance(v, float) else v

            result = self.evaluate(config)
            wr = result["win_rate"]
            self.trials_log.append({"trial": i + 1, "win_rate": wr, "config": config})

            if wr > best_score:
                best_score = wr
                best_config = config
                marker = " ⭐ NEW BEST"
            else:
                marker = ""

            print(
                f"  Trial {i + 1:2d}: WR={wr:.1f}%  push_th={config['push_threshold']:.2f}  "
                f"penalty={config['edge_penalty_weight']:.0f}x  lr={config['lr']:.6f}"
                f"{marker}"
            )

        print()
        print(f"## 最佳配置 (n={n_trials})")
        print(f"  胜率: {best_score:.1f}%")
        if best_config:
            for k, v in best_config.items():
                if k in self.fixed:
                    continue
                spec = self.search_space.get(k, {})
                causal = spec.get("causal_evidence", "")
                print(f"  {k}: {v}  ← {causal[:60]}...")

        return best_config, best_score


if __name__ == "__main__":
    opt = CausalBayesianOptimizer()
    best_config, best_score = opt.run_manual_demo(n_trials=20)

    # 保存结果
    out = {
        "study": "meta_harness_bayesopt",
        "timestamp": datetime.now().isoformat(),
        "search_space": {
            k: {"type": v["type"], "range": f"[{v['min']}, {v['max']}]"}
            for k, v in SEARCH_SPACE.items()
        },
        "fixed": FIXED_CONFIG,
        "best_win_rate": best_score,
        "best_config": best_config,
        "n_trials": 20,
        "trials": opt.trials_log,
    }
    outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bayesopt_result.json")
    with open(outpath, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\n结果已保存: {outpath}")
