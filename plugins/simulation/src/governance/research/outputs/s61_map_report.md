# S.A.M.U.E.L. Map Report — 洞见 → Harness 文件映射

**Sprint**: 61 | **分支**: `feature/s61_research_r0` | **日期**: 2026-08-10
**输入**: `s61_assess_report.md`（I1 干预标记蒸馏 + I2 残差注入守卫）

---

## 1. 映射矩阵

### I1: 干预标记蒸馏 (TORL-VLA intervention-censored)

| 维度 | 映射 |
|------|------|
| **洞见** | intervention-censored critic：防止干预后成功被错误归因给干预前策略动作 → 蒸馏中教师守卫样本与策略样本需区分 |
| **目标文件** | `simulation/training/distill_s60_heuristic.py`（采集循环） |
| **具体改动** | `collect_demos` 增加守卫标记：逐帧记录 `is_guard`（当 `_last_heuristic_branch` ∈ {SR-001/*, TR-004/vectored_*} 时打标）；返回 `X, Y, guard_mask`；`train()` 增加 `--intervention_weight` 参数，守卫样本损失降权（默认 0.25，模拟 TORL-VLA 的 critic 审查） |
| **教师接口** | `V9RuleAgent.select_action_traced()` 已返回 `trace["branch"]`（line 275）——零成本接入 |
| **单元测试** | `scripts/s61/`：断言守卫样本占比 > 0；断言降权后 val_acc 不低于原版（同 seed） |
| **风险** | 低——仅影响训练采样权重，不动推理 |

### I2: 残差注入安全守卫 (MoDE-VLA residual injection + ReTouch 闭环精化)

| 维度 | 映射 |
|------|------|
| **洞见** | 残差注入机制：接触感知精化不损害预训练主干知识 → 学生 MLP 预训练主干 + 危险态守卫残差覆盖 |
| **目标文件** | `simulation/v9_gate_evaluator.py`（`_RLGateAgent` 或新 wrapper）|
| **具体改动** | 新增 `ResidualGuardAgent` wrapper：`select_action` 先跑学生 MLP；若 obs 处于危险态（`edge_f < edge_danger_f` 或任一 edge < critical，S59 守卫的激活条件），改由教师 heuristic 守卫接管（复用一个 V9RuleAgent 实例） |
| **接入点** | `v9_gate_evaluator.py` CLI：`--agent rl --model <student> --guard` 或单独 `--agent residual` |
| **单元测试** | `scripts/s61/`：危险态注入测试——构造 edge_f=0.05 的 obs，断言返回守卫动作；安全态断言返回学生 MLP 动作 |
| **风险** | 中——需确保守卫激活频率低（只覆盖 S59 已证明正确的行为），不损害学生 100% 门分数 |

### I3: 特权预训练同构确认 (VITaL) — P1，无需代码

S60 结果（学生 100%）已实证 VITaL 核心命题：特权信息（教师完整规则）预训练提升无特权推理（学生 9 维 obs）。作为方法论确认记录到 learn_report。

---

## 2. 接入点审计（与现有接口的兼容性）

| 现有接入点 | I1 影响 | I2 影响 |
|-----------|---------|---------|
| `--policy nano --model`（S45） | 无（训练侧改动） | 无（新增 `--guard` 标志，默认关闭） |
| `--agent heuristic`（S59 教师） | 无 | 无（仅复用其守卫逻辑，教师代码零改动） |
| `eval_s60_nano.py` | 无 | 可扩展 `--guard` 对比 |

## 3. 验收标准（Evaluate 阶段）

| 标准 | I1 | I2 |
|------|----|----|
| 门分数 ≥ 90% | 学生（干预降权版）≥ 90% | residual student ≥ 90% |
| 教师零回归 | heuristic 100% | heuristic 100% |
| 延迟不退化 | — | residual student 延迟 ≤ 10x 教师（守卫激活仅在危险帧）|
| 新能力 | 守卫样本占比报告 | 危险态守卫接管正确（单测）|

## 4. 结论

两个 P0 洞见均映射到明确文件与改动点，接入点审计无冲突。进入 Utilize 阶段。
