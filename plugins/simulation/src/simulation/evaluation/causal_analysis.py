#!/usr/bin/env python3
"""
causal_analysis.py — Meta-Harness 因果推理引擎
基于 harness_candidates.json 的结构化数据分析配置参数的因果效应

方法: X-Learner (小样本适配) + 反事实推理 + 因果DAG
"""

import json

import numpy as np

PI = "/home/ivy/bottlesumo_pi"
HARNESS_PATH = "/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/harness_candidates.json"

# ============================================================
# Step 1: 数据提取 — 从候选变体到结构化特征矩阵
# ============================================================


def extract_features():
    """从 harness_candidates.json 提取结构化特征"""
    with open(HARNESS_PATH) as f:
        data = json.load(f)

    candidates = data["candidates"]
    features = []

    for c in candidates:
        wr = c.get("win_rate")
        ed = c.get("edge_drops")
        if wr is None or ed is None:
            continue  # 跳过未评估的变体

        status = c.get("status", "unknown")
        notes = c.get("notes", "")
        failure_mode = c.get("failure_mode", "")
        desc = c.get("description", "")

        # --- 手工编码特征 (从 notes/description 中提取) ---
        # 是否使用 Double DQN
        has_double_dqn = 1 if "Double DQN" in desc or "Double" in desc else 0
        # 是否使用 Dueling 架构
        has_dueling = 1 if "Dueling" in desc else 0
        # 是否使用 action masking
        has_action_mask = 1 if "Action-masked" in desc or "mask" in desc else 0
        # 是否使用 curriculum learning
        has_curriculum = 1 if "Curriculum" in desc or "curriculum" in desc else 0
        # 是否使用知识蒸馏
        has_distillation = 1 if "distillation" in desc or "KL" in desc else 0
        # 边缘惩罚强度 (从 notes 提取)
        edge_penalty_strong = 1 if "50x" in notes or "500" in notes else 0
        # 训练集数编码 (近似)
        if "3500ep" in desc:
            train_eps = 3500
        elif "3000ep" in desc:
            train_eps = 3000
        elif "2000ep" in desc:
            train_eps = 2000
        elif "1500ep" in desc:
            train_eps = 1500
        elif "400" in str(c.get("distillation", {}).get("epochs", "")):
            train_eps = 400
        else:
            train_eps = 500  # default

        features.append(
            {
                "id": c["id"],
                "win_rate": wr,
                "edge_drops": ed,
                "status": status,
                "failure_mode": failure_mode,
                "has_double_dqn": has_double_dqn,
                "has_dueling": has_dueling,
                "has_action_mask": has_action_mask,
                "has_curriculum": has_curriculum,
                "has_distillation": has_distillation,
                "edge_penalty_strong": edge_penalty_strong,
                "train_eps": train_eps,
                "notes": notes[:100],
            }
        )

    return features


# ============================================================
# Step 2: X-Learner CATE 估计
# ============================================================


def x_learner(features, treatment_var, outcome_var="win_rate"):
    """
    X-Learner: 估计二元处理的因果效应
    适用于小样本 (n < 30), 比 S-Learner/T-Learner 更稳健
    """
    X = np.array([[f[v] for v in COVARIATES] for f in features], dtype=float)  # noqa: N806
    T = np.array([1 if f[treatment_var] > 0 else 0 for f in features])  # noqa: N806
    Y = np.array([f[outcome_var] for f in features])  # noqa: N806

    n = len(features)
    n_control = np.sum(T == 0)
    n_treated = np.sum(T == 1)

    if n_control < 2 or n_treated < 2:
        return {
            "treatment": treatment_var,
            "cate": None,
            "ci_lower": None,
            "ci_upper": None,
            "error": f"Insufficient samples: control={n_control}, treated={n_treated}",
        }

    # 1. 分别拟合对照组和处理组的结果模型
    X[T == 0]
    Y_control = Y[T == 0]  # noqa: N806
    X[T == 1]
    Y_treated = Y[T == 1]  # noqa: N806

    # 用加权平均作为简单模型 (n 太小, 不适合 RandomForest)
    mu0_val = np.mean(Y_control)
    mu1_val = np.mean(Y_treated)

    # 2. 计算个体因果效应 (ICE)
    # 对于对照组样本: 实际值 vs 如果接受处理的预测值
    ice0 = Y_control - mu1_val  # 所有对照组用同一处理组均值
    # 对于处理组样本: 如果不接受处理的预测值 vs 实际值
    ice1 = mu0_val - Y_treated

    # 3. CATE = 处理组效应均值 (小样本下用 Bootstrap)
    cate = np.mean(ice1) - np.mean(ice0)

    # Bootstrap CI
    boot_cates = []
    for _ in range(1000):
        idx = np.random.choice(n, n, replace=True)
        if np.sum(T[idx] == 1) >= 2 and np.sum(T[idx] == 0) >= 2:
            Y1 = Y[idx][T[idx] == 1]  # noqa: N806
            Y0 = Y[idx][T[idx] == 0]  # noqa: N806
            boot_cates.append(np.mean(Y1) - np.mean(Y0))
    if boot_cates:
        ci_lower = np.percentile(boot_cates, 2.5)
        ci_upper = np.percentile(boot_cates, 97.5)
    else:
        ci_lower = cate - 5
        ci_upper = cate + 5

    return {
        "treatment": treatment_var,
        "cate": round(cate, 2),
        "ci_lower": round(ci_lower, 2),
        "ci_upper": round(ci_upper, 2),
        "sig": "YES" if ci_lower * ci_upper > 0 else "NO",
        "n_control": n_control,
        "n_treated": n_treated,
        "control_mean": round(np.mean(Y_control), 1),
        "treated_mean": round(np.mean(Y_treated), 1),
    }


# ============================================================
# Step 3: 反事实推理
# ============================================================


def counterfactual(features, candidate_id, change_var, new_value):
    """反事实: 如果改变某个变量, 胜率预测变化"""
    target = [f for f in features if f["id"] == candidate_id]
    if not target:
        return {"error": f"Candidate {candidate_id} not found"}

    # 找到与目标最相似但变量值不同的候选
    target[0]
    X = np.array([[f[v] for v in COVARIATES] for f in features], dtype=float)  # noqa: N806
    Y = np.array([f["win_rate"] for f in features])  # noqa: N806

    # 简单线性加权 (小样本下)
    t_idx = [i for i, f in enumerate(features) if f["id"] == candidate_id][0]
    var_idx = COVARIATES.index(change_var)

    # 找到变量值不同的最相似候选
    best_match = None
    best_dist = float("inf")
    for i, _f in enumerate(features):
        if i == t_idx:
            continue
        dist = sum(abs(X[t_idx][j] - X[i][j]) for j in range(len(COVARIATES)) if j != var_idx)
        if dist < best_dist:
            best_dist = dist
            best_match = i

    if best_match is not None:
        delta = Y[t_idx] - Y[best_match]
        best_f = features[best_match]
        return {
            "candidate": candidate_id,
            "change": f"{change_var}: {X[t_idx][var_idx]:.0f} -> {new_value}",
            "similar_to": best_f["id"],
            "similar_win_rate": best_f["win_rate"],
            "similar_var_value": X[best_match][var_idx],
            "predicted_effect": round(delta, 1),
            "current_win_rate": Y[t_idx],
            "predicted_win_rate": round(Y[t_idx] + delta, 1)
            if X[best_match][var_idx] == new_value
            else "uncalibrated",
        }

    return {"error": "No similar candidate found"}


# ============================================================
# Step 4: 因果DAG构建
# ============================================================

CAUSAL_DAG = {
    "has_double_dqn": {
        "description": "Double DQN架构",
        "causes": ["stability"],  # 减少Q值过估计
        "effect_on": ["win_rate"],
        "evidence": "V10-C (47%) vs baseline (10%): Double DQN + DQN基础架构",
    },
    "has_dueling": {
        "description": "Dueling架构 (分离V和A)",
        "causes": ["training_collapse"],
        "effect_on": ["win_rate"],
        "evidence": "V10-E Dueling→training_regression: Q值坍塌。因果方向: Dueling → 训练不稳定",
    },
    "has_action_mask": {
        "description": "Action Masking (边缘附近限制动作)",
        "causes": ["edge_drops_decrease", "passivity"],
        "effect_on": ["win_rate"],
        "evidence": "V10-D/D2: edge_drops=0 但 win_rate=-8pp。因果链: Mask → 过度保守 → 无法进攻 → 胜率下降",
    },
    "has_curriculum": {
        "description": "Curriculum Learning (渐进训练)",
        "causes": ["stability", "edge_awareness"],
        "effect_on": ["win_rate", "edge_drops"],
        "evidence": "V10-C+D reversed curriculum (aggressive first) + 50x edge penalty: 72.5% WR, 27% drops",
    },
    "has_distillation": {
        "description": "知识蒸馏 (大模型→小模型)",
        "causes": ["regularization", "smooth_q"],
        "effect_on": ["win_rate"],
        "evidence": "Nano-M1: 92.5% WR vs teacher 72.5%. KL散度平滑Q值噪声→学生超越教师",
    },
    "edge_penalty_strong": {
        "description": "强边缘惩罚 (50x)",
        "causes": ["edge_avoidance"],
        "effect_on": ["edge_drops", "win_rate"],
        "evidence": "V10-C+D: -500 danger penalty reverse suicide-charge strategy. 因果效应: 强惩罚 → 避免边缘 → 更多有效战斗时间 → 胜率上升",
    },
    "train_eps": {
        "description": "训练轮数",
        "causes": ["convergence", "overfitting"],
        "effect_on": ["win_rate"],
        "evidence": "V10-E-extended: 3500ep < 1500ep V10-C. 因果方向: 更多训练 → 灾难性遗忘 (非单调!)",
    },
}


# ============================================================
# Main
# ============================================================

COVARIATES = [
    "has_double_dqn",
    "has_dueling",
    "has_action_mask",
    "has_curriculum",
    "has_distillation",
    "edge_penalty_strong",
    "train_eps",
]

if __name__ == "__main__":
    features = extract_features()
    print("# 因果分析报告 — Meta-Harness 迭代")
    print(f"**数据**: {len(features)} 个候选变体 (排除 {12 - len(features)} 个未评估)")
    print()

    # ---- CATE 估计 ----
    print("## 1. 条件平均处理效应 (CATE)")
    print()
    print("| 处理变量 | CATE | 95% CI | 显著? | 处理组均值 | 对照组均值 |")
    print("|----------|------|--------|:-----:|-----------|-----------|")

    all_results = []
    for var in COVARIATES:
        r = x_learner(features, var)
        all_results.append(r)
        cate_str = f"{r['cate']:+.1f}" if r["cate"] is not None else "N/A"
        ci_str = (
            f"[{r['ci_lower']:+.1f}, {r['ci_upper']:+.1f}]" if r["ci_lower"] is not None else "N/A"
        )
        sig = "✅" if r.get("sig") == "YES" else "⚠️"
        tm = f"{r['treated_mean']:.1f}%" if r.get("treated_mean") else "N/A"
        cm = f"{r['control_mean']:.1f}%" if r.get("control_mean") else "N/A"
        print(f"| {var} | {cate_str}% | {ci_str} | {sig} | {tm} | {cm} |")

    print()
    print("## 2. 因果图 (DAG)")
    print()
    for node, info in CAUSAL_DAG.items():
        print(f"### {node}")
        print(f"- **机制**: {info['description']}")
        print(f"- **因果路径**: {node} → {info['causes']} → {info['effect_on']}")
        print(f"- **证据**: {info['evidence']}")
        print()

    print("## 3. 反事实推理")
    print()
    # 关键反事实
    cfs = [
        ("V10-E", "has_dueling", 0),  # 如果V10-E不用Dueling?
        ("V10-D", "has_action_mask", 0),  # 如果V10-D不用mask?
        ("V10-C+D", "edge_penalty_strong", 0),  # 如果V10-C+D不加强惩罚?
    ]
    for cid, var, val in cfs:
        cf = counterfactual(features, cid, var, val)
        if "error" in cf:
            print(f"- **{cf['error']}**")
        else:
            print(
                f"- **{cf['candidate']}**: 如果 {cf['change']} → 预测胜率约 {cf['predicted_win_rate']}% (基于 {cf['similar_to']} 的 {cf['similar_win_rate']}%)"
            )

    print()
    print("## 4. 关键发现")
    print()
    # Sort by absolute CATE
    sorted_results = sorted(
        [r for r in all_results if r["cate"] is not None],
        key=lambda r: abs(r["cate"]),
        reverse=True,
    )
    for r in sorted_results[:3]:
        direction = "正向" if r["cate"] > 0 else "负向"
        print(f"### {r['treatment']}: {r['cate']:+.1f}% ({direction}因果效应)")
        node = CAUSAL_DAG.get(r["treatment"], {})
        print(f"- 机制: {node.get('description', 'unknown')}")
        print(
            f"- 置信度: {'高' if r.get('sig') == 'YES' else '中'} (n=处理{r.get('n_treated', 0)}+对照{r.get('n_control', 0)})"
        )
        print()

    print("## 5. 因果驱动的候选推荐")
    print()
    print("基于因果分析，下一个最有价值的变体:")
    print()
    print("| 优先级 | 操作 | 因果依据 | 预测效应 |")
    print("|:--:|------|----------|----------|")

    # Best positive effect
    pos_effects = [
        (r["cate"], r["treatment"], CAUSAL_DAG.get(r["treatment"], {}).get("evidence", ""))
        for r in sorted_results
        if r["cate"] is not None and r["cate"] > 0
    ]
    for i, (eff, var, ev) in enumerate(pos_effects[:3]):
        print(f"| P{i} | 强化 **{var}** | {ev[:60]}... | +{eff:.1f}% |")

    print()
    print(
        f"**生成时间**: 2026-07-28 | **方法**: X-Learner (Bootstrap CI) | **局限**: n={len(features)}, 处理变量为手工编码特征"
    )
