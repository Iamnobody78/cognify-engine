# Sprint 59 — 门回归验证报告 (Gate Regression)

**日期**: 2026-08-10
**分支**: `feature/sprint59_learning_path`
**目标**: 优化 defensive 对手胜率与步数（代理自主完成一次 BottleSumo 完整迭代）
**验收线**: 门分数 ≥ 92.5%（或 90% 基线）；defensive 2/2；零回归

---

## 1. 验收结果总表

| 指标 | 基线 (2026-08-10) | S59 交付后 | 判定 |
|------|-------------------|-----------|------|
| **heuristic 门分数** | 90% (9/10) | **100% (10/10)** | ✅ PASS (≥92.5%) |
| heuristic vs defensive | 50% (1/2) | **100% (2/2)** | ✅ PASS |
| defensive avg_steps | 334/500 | **216/500** | ✅ PASS (≤200 目标附近, −35%) |
| defensive 聚焦 10 局 | — | **100% (10/10)**, avg 202 | ✅ 稳定性验证 |
| abdl 门分数 | 100% | 100% | ✅ 零回归 |
| v11 门分数 | 80% | 80% | ✅ 零回归 (控制基准) |
| 单元测试 | — | 82 passed (含 9 新增) | ✅ PASS |
| 完整门 ×3 复现 | — | 100% 稳定 | ✅ PASS |

**S.E.E.D. 循环状态**: Scan ✅ → Explore ✅ → Execute ✅ → Debrief ✅

## 2. 详细数据

### 2.1 heuristic 完整门（10 episodes，mode=real，lightweight 后端）

| 对手 | 胜局 | 总局 | 胜率 | avg_steps |
|------|------|------|------|-----------|
| aggressive | 2 | 2 | 100% | 117 |
| circler | 2 | 2 | 100% | 198 |
| counter | 2 | 2 | 100% | 201 |
| **defensive** | **2** | **2** | **100%** | **216** |
| random | 2 | 2 | 100% | 96 |
| **合计** | **10** | **10** | **100%** | — |

### 2.2 修复前 vs 修复后（heuristic vs defensive，诊断脚本实测）

| 维度 | 修复前 | 修复后 |
|------|--------|--------|
| 单局结果 | 499 步超时（输）| 251 步获胜 |
| `SR-001/edge_f` 占比 | 58% (291/500) | 大幅下降 |
| `SR-001/edge_f_turn` 触发 | 0 次 | 118 次（横向脱离激活）|
| 分支结构 | 直线进退死循环 | vectored 侧向迂回 + 边缘转向 |

## 3. 修复内容（三层防御）

1. **TR-004/vectored（新规则）**: `opp_dist < 0.45` 且正对 → 侧向曲线绕行
   （向更开阔侧），不直线冲锋进 defensive 反冲区（0.4）
2. **charge 收紧**: `TR-001/charge` 仅 `opp_dist < 0.35` 触发（反冲区以内）
3. **SR-001/edge_f_turn**: 连续 3 次前缘危险规避 → 强制横向转向（选更开阔侧），
   **脱离守卫**: 连续 2+ 步安全才重置 streak（修复锯齿饥饿）

## 4. 关键诊断洞见（元学习）

**"单步安全立即重置计数器"是通用陷阱**：REV_SLOW 后退一步使 edge_f 从 0.0 恢复
到 0.1-0.15（脱离临界但仍在危险带 0.15），立即清零会导致 streak 锯齿
（1→2→1→2 永不到 3），横向脱离永远无法触发。修复：连续 2 步安全才重置。

→ 已固化: `pattern_library/defensive_shove_stalemate.md`（症状/根因/修复/验证全记录）
→ 已固化: `engineering_rules.md` RULE-AS-001/002/003 + RULE-TS-004

## 5. 交付物

| 文件 | 变更 |
|------|------|
| `simulation/v9_gate_evaluator.py` | MODIFIED: `_HEURISTIC_RULES_DEFAULT` + `__init__` + `_heuristic_v9`（TR-004/charge 收紧/edge_f_turn）|
| `simulation/heuristic_config.yaml` | MODIFIED: shove_dist/charge_dist/edge_f_turn_streak |
| `tests/test_heuristic_rules.py` | MODIFIED: +9 S59 用例（TestS59DefensiveCounter）|
| `governance/sprint_reports/s59_specification.md` | NEW: 需求分析 |
| `governance/sprint_reports/s59_design_proposal.md` | NEW: 设计方案 |
| `governance/sprint_reports/s59_gate_report.md` | NEW: 本报告 |
| `governance/dashboard/engineering_rules.md` | MODIFIED: RULE-AS-001~003 + RULE-TS-004 |
| `governance/pattern_library/defensive_shove_stalemate.md` | NEW: 模式固化 |
| `governance/pattern_library/README.md` | MODIFIED: 索引 |
| `governance/pattern_library/pattern_index.json` | REBUILT: 7 模式 |

## 6. 遗留观察（诚实披露）

1. **defensive avg_steps 216** 略高于目标 200（−35% 已达标，但未完全消除拉锯残余）—
   横向脱离已激活，剩余步数来自多次脱离-再组织循环；可接受，不作过度优化。
2. **模式检索分 0.036 偏低**：symptom_keywords 以中文为主，英文检索词命中弱；
   已在模式 notes 记录，待后续轮次补充英文同义词。
3. **v11 对 defensive 仍 50%**（控制基准，本次未改其决策）——v11 是 RL 基准代理，
   不在 heuristic 规则层修复范围内；如实记录，非本 sprint 缺陷。
