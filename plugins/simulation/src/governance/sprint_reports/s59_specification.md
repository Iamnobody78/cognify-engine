# Sprint 59 — Specification（需求分析）

**目标**: 优化 defensive 对手胜率与步数（代理自主完成一次 BottleSumo 完整迭代）
**分支**: `feature/sprint59_learning_path`
**日期**: 2026-08-10
**状态**: DRAFT → 待设计评审

---

## 1. 问题陈述

V9 裁决门要求胜率 ≥ 60%。当前真实基线（`v9_gate_evaluator.py` lightweight 后端，
mode=real，10 episodes，2026-08-10 实测）：

| 代理 | 总胜率 | defensive 胜率 | defensive avg_steps | 门判定 |
|------|--------|----------------|---------------------|--------|
| **heuristic** | 90% (9/10) | **50% (1/2)** | **334 / 500** | PASS 但 defensive 是唯一败因 |
| **abdl** | 100% (10/10) | 100% (2/2) | 56 | PASS |
| **v11**（控制基准）| 80% (8/10) | **50% (1/2)** | **254 / 500** | PASS 但 defensive 是唯一败因 |

**关键事实**:
1. **三个代理的共同弱点是 defensive 对手**——heuristic 与 v11 均只有 50%，
   且步数异常高（334/500、254/500，接近超时上限）。
2. defensive 对手行为（`v9_gate_evaluator.py:153`）:
   - `edge_f < 0.3` → REVERSE（靠边缘后退）
   - `opp_dist < 0.4` → HARD_FORWARD（对手靠近时反冲）
   - 否则 STOP（驻守中心）
   - speed_scale = 0.40（S38 T2 已削弱物理不对称）
3. **失败 episode 根因（诊断脚本 s59_diag_defensive.py 实测）**:
   - heuristic 失败局（500 步超时）: **291/500 步（58%）耗在 `SR-001/edge_f` 规避**
     （REV_SLOW 后退），156 步 TR-002/advance（接近），53 步 TR-001/left。
   - 机制: defensive 驻守中心 → heuristic 直线接近（TR-002）→ 进入 opp_dist<0.4
     触发 defensive 反冲 → heuristic 被推至边缘 → edge_f 危险 → 无限 REV_SLOW
     后退 ↔ 再接近 的拉锯 → 500 步超时。
   - **对照**：heuristic 获胜局（169 步）主要动作是 `TR-001/left`（87 步侧向
     包围）+ `SR-001/edge_r`（58 步边缘转向调整）——侧向迂回而非直线冲击。
4. **矛盾说明**: PM 引述的"10% 胜率(1/10)"与 plateau 记录（08-05，mujoco 后端
   ABDL 40%）均早于当前代码状态；本次 specification 以 2026-08-10 实测 lightweight
   基线为准（诚实披露，基线漂移已记录）。

## 2. 目标（可量化）

| 指标 | 当前基线 | 目标 | 验收判据 |
|------|----------|------|----------|
| heuristic vs defensive 胜率 | 50% (1/2) | **100% (2/2)** | 回归 10 局中 defensive 2/2 全胜 |
| heuristic vs defensive 步数 | 334/500 | **≤ 200** | 平均步数显著下降（消除超时拉锯） |
| 门分数（heuristic 全对手） | 90% | **≥ 92.5%** | 门分数 ≥ 当前基线（PM 验收线 92.5% 或 90%） |
| 全代理回归 | — | 不退化 | abdl/v11 全对手胜率不下降，零回归 |

**范围边界**:
- IN: `heuristic` 代理策略调整（L1/L2 规则层）
- IN: defensive 专项应对（侧向迂回优先、边缘规避改进）
- OUT: 不改动 env 物理、不改对手实现、不改其他对手胜率
- OUT: 不引入新依赖（纯规则层修改）

## 3. 根因分析（诊断证据）

失败链条（heuristic vs defensive，500 步超时局）:

```
defensive 驻守中心 (STOP)
  → heuristic TR-002/advance 直线接近 (opp_dist 从 1.0 降至 <0.4)
  → defensive 反冲 (HARD_FORWARD, opp_dist<0.4)
  → heuristic 被推向边缘 (edge_f 降至 <0.15 危险区)
  → heuristic SR-001/edge_f → REV_SLOW 直线后退
  → 退至中心附近但方向未变
  → 再次 TR-002 直线接近 → 循环
```

**结构性缺陷**（heuristic L2 规则）:
1. `TR-002/advance`（直线推进）在 `opp_detect_dist=0.5` 内无条件触发——
   没有角度偏差要求，导致正面冲击 defensive 反冲区（opp_dist<0.4）。
2. `SR-001/edge_f` 规避后没有"横向脱离"——REV_SLOW 直线后退保持原朝向，
   退出危险区后立即回到 TR-002 直线接近路径，形成固定拉锯（无随机性/无侧移）。
3. 成功模式已存在但未被强化: `TR-001/left`（侧向包围，87 步获胜局主动作）
   是有效策略，但 L2 优先级低于直线 advance，且依赖随机初始朝向。

**对比 v11 失败局**: 261 步 action 6（REV_SLOW）+ 110 步 action 8——同一
"边缘规避死循环"结构，证明是策略层缺陷而非单代理偶然。

## 4. 候选方案（供设计评审）

| 方案 | 机制 | 预期收益 | 风险 |
|------|------|----------|------|
| **A. 侧向迂回优先** | L1 层: 检测到 opp_dist<0.5 且 defensive 姿态时，优先 TR-001 侧向而非 TR-002 直线 | 避免正面冲击反冲区 | 可能降低对 aggressive 对手的推进速度 |
| **B. 边缘规避横向脱离** | SR-001/edge_f 后退时叠加转向（REV + 左/右转），退出后偏航角改变 | 打破固定拉锯路径 | 可能引入新的边缘碰撞 |
| **C. 反冲区回避** | 新增 L1.5 规则: opp_dist<0.4 且对方反冲姿态 → 横向闪避（TR-001/TR-010）而非后退 | 直接避开反冲 | 需要识别反冲姿态（观测有限） |
| **D. 组合 A+B+C** | 完整应对 | 最稳 | 改动面最大，回归风险高 |

## 5. 验收标准（门回归）

1. **必需**: `v9_gate_evaluator.py` heuristic 10 局 ≥ 92.5% 门分数（当前 90%）
2. **必需**: defensive 2/2（当前 1/2）
3. **必需**: defensive avg_steps ≤ 200（当前 334）
4. **必需**: abdl/v11 零回归（全对手胜率不下降）
5. **必需**: 单元测试覆盖新规则分支（L1 侧向优先、反冲回避）
6. **流程**: S.E.E.D. 循环（Sprint 59 学习路径 Phase 4）→ 知识固化
   (`engineering_rules.md` + `pattern_library/`) → META-EDU 记录

## 6. 交付物清单

- [ ] `specification.md`（本文件）
- [ ] `design_proposal.md`（设计方案）
- [ ] 代码 PR（heuristic 规则实现）
- [ ] 单元测试（新分支覆盖）
- [ ] 门回归报告（v9_gate_evaluator 前后对比）
- [ ] `engineering_rules.md` 更新
- [ ] `pattern_library/` 更新（defensive 拉锯模式归档）
- [ ] META-EDU 学习记录
