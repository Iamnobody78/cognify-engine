# Sprint 40 执行报告 — DAgger 在线纠正 (FP-RL-005 修复)

**日期**: 2026-08-08
**分支**: `feature/s40_dagger_prototype`（基于 main + sprint39-closed tag）
**PM 裁决**: P0 = DAgger 在线纠正 | P1(T0) = 训练内评估协议统一 | T2 = 门回归验证

---

## 结果摘要 — 全部验收通过 🎯

| 任务 | 验收标准 | 实测 | 判定 |
|------|----------|------|------|
| **T0** 训练内评估协议统一 | 训练内 WR vs 门禁 WR 差距 ≤ 10pp | **2.5pp** (90% vs 92.5%) | ✅ |
| **T1** DAgger 原型 | 微调门禁 ≥ 90% (36/40) | **92.5% (37/40)** | ✅ |
| **T2** 门回归 | 门 ≥ 90% + 双端回归全绿 | 92.5% + 220 passed + 1 skipped | ✅ |

**FP-RL-005 闭环: 恒定 40% → SkillProtected 60% → DAgger 92.5%** — 超越教师 BC (90%)。

---

## T0: 训练内评估协议统一

**发现**: `train.py` 的 GATE_BEHAVIORS 仅 4 策略（缺 aggressive），门禁为 5 策略。

**实现** (`finetune_dqn_s40.py`):
- `GATE_MIX = [random, aggressive, defensive, circler, counter]`
- `mixed_gate_eval()`: 5 策略 × 稳定种子（`_stable_seed` 与门禁同构），defensive 用 `opponent_speed_scale=0.40`，win 判定 = `terminated and total_reward > 5`（与 `v9_gate_evaluator` 逐字一致）
- 训练内每 50ep 评估（30 局 = 5 策略 × 6）

**验证**: S39 的假阳性 97.8%（单一 aggressive + 固定种子）vs 门禁 60% 的 37.8pp 鸿沟 → S40 训练内 90% vs 门禁 92.5% 仅 **2.5pp**。协议统一有效。

---

## T1: DAgger 原型 — 实现与机制

**文件**: `simulation/training/finetune_dqn_s40.py` — `DaggerAgent(DQNAgent)`

**机制**（按 PM 技术细节）:
1. **β 退火 1.0 → 0.1**（线性，2000 steps）：早期完全教师覆盖 → 后期大多自主
2. **教师覆盖**: 每步以 β 概率用冻结 `teacher_net`（BC 权重）动作替代 DQN 动作执行 → 保留数十步时序一致的追踪轨迹（FP-RL-005 根因的正面应对）
3. **dagger_buffer**: 独立 20000 槽 deque 存 `(state, teacher_action)` — 不污染 DQN reward buffer
4. **混合 loss**: TD (DQN replay) + `dagger_lambda=1.0` × CE (dagger buffer → 拉向教师动作) + skill L2 (S39 保留)
5. **保留 S39 SkillProtected**: 冻结 net.0 (fc1) + L2 技能保护正则

**训练**: 1000ep，13-slot 轮转课程（gate×2 + speed ladder），eps 0.05→0.01。后台 6 分钟完成。

---

## 门禁结果 (40ep 稳定种子)

| 策略 | 教师 BC (90%) | S39 SkillProtected (60%) | **S40 DAgger (92.5%)** | Δ vs 教师 |
|------|--------------|--------------------------|------------------------|-----------|
| random | 7/8 | 6/8 | **7/8** | = |
| aggressive | 8/8 | 4/8 | **8/8** | = |
| defensive | 5/8 | 4/8 | **6/8** | **+1** |
| circler | 8/8 | 3/8 | **8/8** | = |
| counter | 8/8 | 7/8 | **8/8** | = |
| **合计** | **36/40** | **24/40** | **37/40** | **+1** |

**关键证据 — 动作多样性恢复**:
- S40 DAgger: `{5: 135, 15: 14, 19: 124, 20: 134}` = **4 种动作**（与教师 {FW_MAX, FW_LEFT_HARD, FW_LEFT_FAST, FW_RIGHT_FAST} 完全一致）
- S39 SkillProtected: `{5: 309}` = 1 种动作（FW_MAX 塌缩）
- **DAgger 的教师覆盖 + dagger_buffer CE 监督成功阻止 Q 值塌缩**，保留全部追踪技能

---

## 回归状态

**双端全绿: 220 passed + 1 skipped**
- `simulation/tests`: 73 passed
- `governance/meta_harness/tests` + `evaluator_diff_test.py`: 134 passed + 1 skipped
- `governance/dashboard/backend/tests`: 13 passed

---

## V9 裁决门状态

| 候选 | 门禁 | 状态 |
|------|------|------|
| **DAgger 微调 (`chase_dqn_dagger_s40.pt`)** | **92.5% (37/40)** | ✅ **新部署候选 (超越教师)** |
| 教师 BC (`chase_teacher_bc_s38_v2.pt`) | 90% (36/40) | ✅ |
| nano (任意温度) | 87.5% (35/40) | ✅ 过门 (泛化差距未闭) |
| S39 SkillProtected | 60% (24/40) | ❌ 归档 |

**部署推荐**: DAgger 微调模型 92.5% > 教师 90% → **替换教师为部署轨道**。

---

## Sprint 41 建议

1. **defensive 6/8** 仍低于其余策略 8/8 — 定向提升 defensive 表现
2. `dagger_lambda` 恒 1.0 未随 β 退火 — 后期可能过度拉向教师，探索 lambda 退火
3. 更长 β 退火窗口或分阶段退火
4. nano 泛化差距（6/8 vs 教师 7/8）继续在数据/架构方向闭合

---

## 工作文件

- 新增: `simulation/training/finetune_dqn_s40.py`, 模型 `models/chase_dqn_dagger_s40.pt`(+.best)
- 治理: `governance/meta_harness/failure_analysis.md` (S40 记录), `sprint40_execution_report.md`
