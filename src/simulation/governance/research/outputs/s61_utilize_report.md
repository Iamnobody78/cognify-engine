# S.A.M.U.E.L. Utilize Report — 论文洞见 → 代码变更

**Sprint**: 61 | **日期**: 2026-08-10
**R-gate**: experiment phase PASS (2/2) — 见 `s61_utilize_report.json`

---

## 1. 代码变更清单

### I1: 干预标记蒸馏 (TORL-VLA intervention-censored) → `simulation/training/distill_s60_heuristic.py`

| 变更 | 文件 | 说明 |
|------|------|------|
| `GUARD_BRANCHES` 常量 | distill_s60_heuristic.py | SR-001 edge escapes + TR-004 vectored curves 标记为教师"干预" |
| `collect_demos` 打标 | 同上 | 改用 `select_action_traced()`（返回 branch），逐样本记录 `guard_mask` |
| `train()` 降权 | 同上 | `intervention_weight`（默认 0.25）加权 BC 损失：守卫样本损失权重 < 1 |
| CLI `--intervention-weight` | 同上 | 1.0 = 纯 S60 BC（控制基线）；0.25 = 干预审查版 |

### I2: 残差注入守卫 (MoDE-VLA residual injection) → `simulation/v9_gate_evaluator.py`

| 变更 | 文件 | 说明 |
|------|------|------|
| `ResidualGuardAgent` 类 | v9_gate_evaluator.py | 学生 MLP 主干 + S59 守卫残差；`_danger()` 仅当任一 edge < `edge_critical` 激活守卫（与 SR-001 触发线一致） |
| `_create_agent` 分支 | 同上 | `--agent residual --model <student.pt>` 接入 |
| CLI choices | 同上 | `--agent` 增加 `residual` |

## 2. 单元测试（`simulation/training/test_s61_research_r0.py` — 7/7 PASS）

| 测试 | 验证点 |
|------|--------|
| `test_guard_branches_are_tracked_by_teacher` | 教师 traced action 报告守卫 branch |
| `test_collect_demos_marks_guard_mask` | 采集产 guard_mask，守卫占比 ∈ (0,1) |
| `test_intervention_weight_lowers_guard_loss_contribution` | 同批次加权损失 < 未加权 |
| `test_train_accepts_intervention_weight` | train() 端到端 + 降权 |
| `test_residual_guard_dangerous_state_activates_guard` | 危险 obs → residual-guard 模式 |
| `test_residual_guard_safe_state_uses_student` | 安全 obs → residual-student 模式 |
| `test_residual_guard_activation_rare_in_nominal_play` | 名义对局守卫激活 < 0.5（主干保持）|

## 3. 设计决策记录

- **激活线选择**：`ResidualGuardAgent._danger()` 用 `edge_critical`（SR-001 实际触发线），**不用** `edge_danger_f`（仅告警带不触发动作）——首次实现误用 danger 线导致守卫过度激活，测试暴露后修正。对应 RULE-DI-008。
- **守卫复用**：零参数——复用单一 `V9RuleAgent(force_heuristic=True)` 实例，教师代码零改动。
- **采集标记**：`select_action_traced()` 的 branch 字段是 S59 已存在的接口，零侵入接入。

## 4. 边界

- I1 权重在 13-slot/200eps 课程上调优；更大课程需重标定
- I2 守卫是规则式（S59）；未来有风险度量时可换学习式残差
