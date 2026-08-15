# Sprint 59 — Design Proposal（设计方案）

**目标**: 消除 heuristic 对 defensive 对手的拉锯死循环（50% → 100%，步数 334 → ≤200）
**分支**: `feature/sprint59_learning_path`
**日期**: 2026-08-10
**状态**: PROPOSED → 待实现

---

## 1. 设计原则

1. **最小改动面**：只动 `_heuristic_v9`（v9_gate_evaluator.py:389-453）决策逻辑 +
   `heuristic_config.yaml` 新增阈值。不改 env、不改对手、不改其他代理。
2. **不破坏既有测试**：现有 `test_heuristic_branch_choices_unchanged` 的 9 个用例
   输入输出全部保持（见 §5 兼容性分析）。
3. **配置化**：所有新魔数进 `heuristic_config.yaml` + `_HEURISTIC_RULES_DEFAULT` 同步。
4. **确定性**：不用随机数；用边缘余量/奇偶计数做方向选择（可复现、可测试）。

## 2. 根因回顾（specification §3 摘要）

defensive 对手行为: 驻守中心 → 对手接近 `opp_dist<0.4` 时直线反冲 → 我方被推至边缘 →
`SR-001/edge_f` REV_SLOW 直线后退（朝向不变）→ 退出危险区后 TR-002/TR-001 再次直线
接近 → 无限拉锯 → 500 步超时（实测 291/500 步耗在 edge_f 规避）。

**三个结构性缺陷**:
| # | 缺陷 | 位置 | 后果 |
|---|------|------|------|
| D1 | charge 直线冲锋无反冲回避 | `TR-001/charge`（行 432-436）| 正面冲击反冲区 |
| D2 | edge_f 规避只有直线后退 | `SR-001/edge_f`（行 417-419）| 朝向不变 → 再入死循环 |
| D3 | 反冲区（0.4-0.5）无中间策略 | TR-001/TR-002 之间 | 0.5 直线推进直接进 0.4 反冲区 |

## 3. 方案设计（三处修改）

### 3.1 新增 L1.5 反冲回避规则 `TR-004/vectored`（修复 D1+D3）

在 L1 TR-001 之前插入：

```
if opp_dist < shove_dist(0.45) and abs(opp_angle) < opp_angle_tol(0.3):
    # 反冲区边缘正面对峙 → 侧向曲线绕行（不直线冲锋）
    if edge_l > edge_r:   # 向左更开阔 → FW_LEFT_MILD(13)
        branch = "TR-004/vectored_l"; action = 13
    else:                 # 向右更开阔 → FW_RIGHT_MILD(16)
        branch = "TR-004/vectored_r"; action = 16
```

- **物理意义**: defensive 反冲是直线向前（HARD_FORWARD）。我方在 0.4-0.45 边缘
  转用侧向曲线切入其侧面 → 反冲扑空 → 我方绕到侧后。
- **方向选择**: 用 `edge_l`/`edge_r` 余量比较（确定性），同时天然规避即将靠近的
  边缘——一举两得。
- **D3 修复**: 0.4-0.5 区间不再有"直线推进"选项（TR-002 的 `advance_dist=0.8`
  下界被 TR-004 截断）。

### 3.2 SR-001/edge_f 连续规避转向（修复 D2）

在 `_heuristic_v9` 前增加实例状态（`__init__` 中 `self._edge_f_streak = 0`）：

```
if edge_f < edge_critical:
    self._edge_f_streak += 1
    if self._edge_f_streak >= 3:
        # 连续 3+ 步直线后退无改善 → 强制横向脱离（改变朝向）
        self._last_heuristic_branch = "SR-001/edge_f_turn"
        self._edge_f_streak = 0          # 重置, 避免永久锁定转向
        return 10 if edge_r >= edge_l else 7   # 向更开阔侧转向 (TURN_R/L_MILD)
    self._last_heuristic_branch = "SR-001/edge_f"
    return 6                              # REV_SLOW（前 2 步保持原行为）
```

- **物理意义**: 前 2 步仍 REV_SLOW（与原行为一致，兼容既有测试）；第 3 步起
  REV 无法改善时强制转向，改变退避方向 → 打破"直线后退-直线接近"固定循环。
- **方向选择**: `TURN_R_MILD(10)` 若右侧更开阔（edge_r >= edge_l），否则
  `TURN_L_MILD(7)`。确定性、可测试。
- **既有测试兼容**: `test_heuristic_branch_choices_unchanged` 每次新建 agent
  （streak=0），单次调用 streak=1 < 3 → 仍返回 6 + `SR-001/edge_f` ✓

### 3.3 收紧 TR-001/charge 触发距离（配合 3.1）

```
if opp_dist < opp_detect_dist:
    if abs(opp_angle) < opp_angle_tol and opp_dist < charge_dist(0.35):
        # 已深入反冲区以内 (0.35 < 0.4) → 直线冲锋速度优势成立
        branch = "TR-001/charge"; action = 5
    elif abs(opp_angle) < opp_angle_tol:
        branch = "TR-004/vectored_*"; action = 13/16   # 0.35-0.5 区间走曲线
    elif opp_angle < 0:
        ...TR-001/right 不变
    else:
        ...TR-001/left 不变
```

- **D1 修复**: charge 只在 `opp_dist < 0.35`（已穿透反冲区）时触发；0.35-0.5
  的"正面对峙"移交 TR-004 曲线。
- **既有测试兼容**: `([0.9,0.9,0.9,0.9,0.3,0.0], "TR-001/charge", 5)` —
  opp_dist=0.3 < 0.35 ✓ 仍 charge。

## 4. 新增/修改配置项（heuristic_config.yaml）

```yaml
l1_tactical:
  opp_detect_dist: 0.5        # (不变)
  opp_angle_tol: 0.3          # (不变)
  shove_dist: 0.45            # NEW: 反冲回避触发距离 (defensive 反冲 0.4 之上留余量)
  charge_dist: 0.35           # NEW: 直线冲锋距离 (须小于反冲区 0.4)
l0_safety:
  edge_f_turn_streak: 3       # NEW: 连续 edge_f 规避次数阈值 → 强制转向
```

`_HEURISTIC_RULES_DEFAULT` 同步（保持 `test_defaults_identical_to_loaded` 契约）。

## 5. 测试计划

### 5.1 既有测试兼容性（test_heuristic_rules.py — 9 用例全保持）

| 用例 | obs | 新逻辑判定 | 结果 |
|------|-----|-----------|------|
| SR-001/edge_f | edge_f=0.05 | streak=1 < 3 | 6 ✓ |
| SR-001/edge_l | edge_l=0.05 | 不变 | 10 ✓ |
| SR-001/edge_r | edge_r=0.05 | 不变 | 7 ✓ |
| SR-001/edge_b | edge_b=0.05 | 不变 | 5 ✓ |
| TR-001/charge | opp=0.3, ang=0.0 | 0.3<0.35 charge | 5 ✓ |
| TR-001/right | opp=0.3, ang=-0.5 | 0.3<0.35 但 |ang|≥tol → right | 16 ✓ |
| TR-001/left | opp=0.3, ang=0.5 | 同上 → left | 13 ✓ |
| TR-002/advance | opp=0.6 | 0.45≤0.6<0.8 → advance | 3 ✓ |
| TR-003/search | opp=0.9 | 不变 | ✓ |

### 5.2 新增测试用例

```
TR-004/vectored_l:  [0.9,0.9,0.7,0.4,0.42,0.0] → 13 (edge_l>edge_r, 反冲区边缘正对)
TR-004/vectored_r:  [0.9,0.9,0.4,0.7,0.42,0.0] → 16
TR-001/charge 收紧: [0.9,0.9,0.9,0.9,0.30,0.0] → 5  (charge)
                   [0.9,0.9,0.9,0.9,0.40,0.0] → 13/16 (vectored, 不再 charge)
SR-001/edge_f streak: 新建 agent, 连续 3 次 [0.05,...] → 第3次返回转向动作,
                       分支 = "SR-001/edge_f_turn"
配置等价: loaded["l1_tactical"]["shove_dist"] == 0.45,
          loaded["l1_tactical"]["charge_dist"] == 0.35,
          loaded["l0_safety"]["edge_f_turn_streak"] == 3
```

### 5.3 门回归（必需验收）

```
heuristic: 10 episodes → 总分 ≥ 92.5%（当前 90%）, defensive 2/2, avg_steps ≤ 200
abdl:      10 episodes → 零回归（全对手胜率不下降）
v11:       10 episodes → 零回归
```

## 6. 风险分析

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| TR-004 降低对 aggressive 推进效率 | 中 | 中 | 门回归观察 aggressive 对手；charge 仍在 0.35 内保留直线 |
| SR-001 转向可能导致撞另一边缘 | 低 | 中 | 转向选更开阔侧（edge_r/edge_l 比较）|
| TR-004 与 TR-002 顺序依赖 | 低 | 低 | 明确规则优先级: L0 > L1.5(TR-004) > L1(TR-001) > L2(TR-002) |
| 配置契约测试失败 | 中 | 低 | 同步更新 `_HEURISTIC_RULES_DEFAULT` |

## 7. S.E.E.D. 循环映射（Sprint 59 学习路径 Phase 4）

| S.E.E.D. | 对应活动 |
|----------|----------|
| **S**can | 诊断脚本 s59_diag_defensive.py → 58% 步数耗在 edge_f（specification §3）|
| **E**xplore | 本设计方案（3.1 反冲回避 + 3.2 横向脱离 + 3.3 charge 收紧）|
| **E**xecute | 实现 + 单元测试 + 门回归（§5）|
| **D**ebrief | engineering_rules.md + pattern_library/defensive_stalemate/ 归档 + META-EDU |

**审批要点**: 方案最小改动 heuristic 决策层，确定性、可测试、零 env 侵入。
请 PM 评审后进入实现。
