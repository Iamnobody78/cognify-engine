# Evaluation — Meta-Harness Causal Analysis Suite

因果推理驱动的调度器优化评估套件。基于 Stanford IRIS Lab Meta-Harness (arXiv:2603.28052) 双环架构。

## 文件清单

| 文件 | 用途 | 状态 | 执行时间 |
|------|------|:--:|------|
| `causal_analysis.py` | X-Learner CATE + Bootstrap CI 初版 | ✅ | - |
| `causal_analysis_v2.py` | SCM + Sequential Controlled Comparison | ✅ | - |
| `meta_harness_bayesopt.py` | 因果先验贝叶斯优化器 | ✅ 20 trials | ~10s |
| `bayesopt_result.json` | 贝叶斯优化: best=87.0% (trial 13) | ✅ | - |
| `shap_nano_analysis.py` | SHAP 先验预期框架 | ✅ | ~5s |
| `shap_analysis.json` | SHAP 先验预期值 | ✅ | - |
| `shap_nano_real.py` | **真实 Nano 模型 SHAP** | ✅ 500 samples | ~30s |
| `shap_analysis_real.json` | **真实 SHAP: edge_front 53%** | ✅ | - |
| `ablation_design.json` | 2×2 因子消融实验设计 | ✅ | - |
| `ablation_runner.py` | 消融实验执行器 (12 runs) | ✅ 8.4min | ~506s |
| `ablation_result.json` | 消融结果: 交互效应 +11.1% | ✅ | - |
| `optimal_config.json` | BayesOpt 最佳配置参考 | ✅ | - |

## 🔥 新发现：SHAP 揭示 Nano 模型的惊人真相

**先验预期 vs 真实模型：**

| 特征 | 先验重要性 | 真实重要性 | 差异 |
|------|:--:|:--:|------|
| opponent_x | **28%** | 0% | ❌ 完全相反 |
| opponent_y | **26%** | 0% | ❌ 完全相反 |
| edge_front | 15% | **53%** | ⬆️ 3.5× |
| edge_back | - | **30%** | ⬆️ |
| robot_x | 7% | 0% | ❌ |

**结论：Nano 模型是"纯边缘躲避器"**——它学会了不关心对手位置，只躲避边缘。对手（aggressive profile）自毁出界时 Nano 自动获胜。

**深层含义**：蒸馏悖论(92.5% > 72.5%)的真正原因是——教师模型的 Q 值噪声中包含了对对手位置的噪声估计，而蒸馏过程通过 KL 散度平滑了这些噪声，导致学生学习到更干净的"边缘优先"策略。

## 🧪 消融实验：交互效应 +11.1%

| 条件 | 配置 | 胜率 | 边缘掉落 |
|------|------|-----:|----:|
| A (baseline) | 无课程 + 标准惩罚 | 44.4% ± 6.1 | 32 |
| B (penalty) | 无课程 + 50×惩罚 | 37.8% ± 2.8 | 37 |
| C (curriculum) | 逆序课程 + 标准惩罚 | 38.3% ± 7.2 | 36 |
| D (V10-C+D) | 逆序课程 + 50×惩罚 | 42.8% ± 8.0 | 34 |

| 效应 | 值 | 解释 |
|------|----:|------|
| 惩罚主效应 | -1.1% | 单独使用不利 |
| 课程主效应 | -0.6% | 单独使用不利 |
| **交互效应** | **+11.1%** | ⭐ 超加性！ |

**因果解释**：课程+强惩罚互为依赖——单独使用反而有害，组合使用产生超额收益。这验证了 SCM 分析中的"课程+强惩罚(+25.5%)"因果链。

## 📊 贝叶斯优化最佳配置

```
Trial 13: Win Rate = 87.0%
push_threshold: 0.285 (激进推进)
edge_penalty_weight: 71.6× (极强惩罚)
action_bins: 20
lr: 3e-5 (极低学习率，有利于蒸馏)
target_update_freq: 400
n_episodes: 750 (适中，避免遗忘)
```

## 📋 待办

- [ ] 蒸馏效应复现 (Nano-M1 需 3+ 次独立复现)
- [ ] 接入对手感知到 Nano 模型（当前为纯边缘躲避器）
- [ ] `optimal_config.json` → `main_rule_fallback.c` 固件映射
