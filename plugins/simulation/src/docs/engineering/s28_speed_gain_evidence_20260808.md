# Sprint 28 轮速增益实证 + action_map 层建立 + V9 门触发（2026-08-08）

> 交付摘要：Sprint 28（PM 裁决 A1 P0：TURN_*_MED 轮速增益 0.6→0.8）已执行完毕。
> **结论：3 轮全 REGRESSION（确定性可复现）→ 按 PM 验收条件触发 V9 门。**
> 配套：新增 `action_map` 层（HARNESS_FILES 第六层）、FP-NEG-003 负样本入库、meta_harness 119/119 全绿。

## 1. 执行指令对照（PM Sprint 28 裁决）

| # | PM 指令 | 执行状态 | 结果 |
| :-- | :-- | :-- | :-- |
| ① | 轮速增益 TURN_*_MED 0.6→0.8（P0 优先） | ✅ 完成 | 3 轮全 REGRESSION（winrate 1.00→0.90） |
| ② | V9 门（条件触发：3 轮无 PASSED） | ✅ 触发 | 内环探索饱和，外部 mujoco 实机 winrate=1.0 基线稳定 |
| ③ | 蒸馏管道（并行启动） | ✅ 完成 | FP-NEG-003 入库 failure_analysis.md 负样本库 |

## 2. 架构前置：action_map 层建立（关键治理动作）

**问题**：`simulation/wheel_to_discrete.py`（PM 指令目标）不在 `HARNESS_FILES` 五层
（rules/mapping/physics/reward/gate）内——meta_harness 的 snapshot/restore/apply 白名单
（`allowed = set(HARNESS_FILES.values())`）会以"作用域越界"拒绝任何针对该文件的扰动。

**解法**：新增第六层 `action_map`，双端同步（variants.py + outer_loop.py 各有一份 HARNESS_FILES）：
```python
"action_map": "simulation/wheel_to_discrete.py",
```
机制自动覆盖（无需改动快照/回滚/白名单代码——全部按 HARNESS_FILES 展开）：
- `snapshot_harness` 遍历 HARNESS_FILES.items() → 新层自动入快照
- `restore_harness(layers=[layer])` → 新层自动回滚
- `apply_precheck` 白名单 → 新层自动放行

**同步扩展**（一致性要求）：
- `variants.py`：`_gen("action_map")` 分支（mh_action_map_001 变体）+ `_SEED_PARAMS["action_map"]`
  降级种子（2 条：R/L 对称）+ `SEED_PERTURBATION_THRESHOLDS["action_map"]`（abs 0.20）
- `variants.py` ROUND 1 候选循环：`("rules", "mapping", "physics", "action_map")`（动态过滤
  HARNESS_FILES 存在性，兼容测试 fixture patch）
- `distill_loop.py` `D2_PRIOR`：新增 `"action_map"` 条目（对齐测试
  `test_thresholds_align_distill_d2_prior`）
- `variants._self_test`：断言更新（mapping/physics/action_map 3 个；rules 被 RULES CLOSED 排除）

**治理教训（沉淀）**：凡 PM 指令指向的文件，先确认是否在 HARNESS_FILES 内；不在则需
**先建层再扰动**（否则 apply_precheck 白名单拒绝 = 作用域越界，S26 已见同类问题）。

## 3. 可达性检查（FP-NEG-002 新规则，PM 明确要求）

TURN_*_MED 的调用点全部在评估路径上（非死代码）：

| 动作 | 调用点 | 层 | 状态 |
| :-- | :-- | :-- | :-- |
| TURN_R_MED | abdl_action_bridge.py:217（mapping flank 分离态） | mapping | 活路径（S27 实证） |
| TURN_R_MED | wheel_to_discrete.py:198（heuristic fallback） | physics | 活路径 |
| TURN_L_MED | abdl_action_bridge.py:225（mapping flank 分离态） | mapping | 活路径 |
| TURN_L_MED | wheel_to_discrete.py:162/196（搜索旋转/回退） | physics | 活路径 |

无 FP-NEG-002 式互斥（对比 S27 直冲窗 dist>0.6 与 dist<0.22 的死代码）。
diff 锚点 `Action.TURN_*_MED: (0.0, ±0.6)` 唯一匹配 ACTION_MAP 实际生效值
（枚举注释行不含 `Action.` 前缀，不会误匹配）。

## 4. S28_SPEED 验证结果（--iterations 5 --tag S28_SPEED --meta-config）

### 判定分布（3 轮完全一致，确定性可复现）

| 候选 | 层 | 扰动 | 判定 | 关键信号 |
| :-- | :-- | :-- | :-- | :-- |
| **mh_action_map_001** | **action_map** | TURN_*_MED 0.6→0.8 | **REGRESSION** | winrate 1.00→0.90；avg_steps 21.4→17.7（-17.3%） |
| mh_mapping_001 | mapping | flank 0.20→0.15 | REGRESSION | Q=-0.17（S27 已知） |
| mh_mapping_002 | mapping | flank 0.20→0.18 | INCONCLUSIVE | no-op（S26 已知） |
| mh_physics_seed_001 | physics | 动量 +0.05 | REGRESSION | winrate 1.00→0.90（S25 已知） |
| mh_physics_seed_002/003 | physics | 抓地/其他 | INCONCLUSIVE | no-op |

### 行为级证据（逐局步数）

基线 steps：`[6, 8, 7, 19, 42, 49, 12, 60, 5, 6]`（avg 21.4, winrate 1.0）
变体 steps：`[6, 8, 7, 19, 41, 45, 12, 28, 5, 6]`（avg 17.7, winrate 0.9）

- 第 6 局 49→45（-8%）、第 8 局 60→28（-53%）：**贴边极限对局提前结束**
- 第 8 局从胜（60 步推胜）转负（28 步坠落）：**轮速 +33% 弧线过冲越过最佳推力角**
- `behavior_changed: true, identical: false` → 扰动有真实行为影响（非 no-op）

## 5. FP-NEG-003 负样本（入库 failure_analysis.md）

- **模式**：执行层参数放大（动量 1.20 / 轮速 0.80）同构失败——物理包线失稳
- **轮速轴可行域**：上界 ≈0.70（0.6 基线 → 0.8 越界）；建议 clamp ≤ 0.70
- **与 FP-NEG-001 联动**：动量轴（上界 1.10）+ 轮速轴（上界 0.70）合并为
  "执行层包线约束"治理规则——M3 bump 放大执行层参数时须检查物理包线
- **复用价值**：轮速类扰动锚点模板（ACTION_MAP 精确锚点）、action_map 层基建

## 6. V9 门触发（PM 验收条件满足）

- **内环（meta-harness）**：S25-S28 行为参数四轴全景收口——角度饱和（S25/S26）、
  距离单峰（S27）、动量上界（S25/FP-NEG-001）、轮速上界（S28/FP-NEG-003）
  → **行为参数正扰动空间耗尽，探索饱和**
- **外环（mujoco 实机 V9 门）**：`v9_gate_report.json` winrate=1.0 passed=True
  → 基线稳定，无回归（S28 未合入任何 REGRESSION 变体）
- **plateau_explorer 自蒸馏**：按治理协议待触发（V9 门裁决路径）

## 7. 质量门

| 项 | 结果 |
| :-- | :-- |
| meta_harness 测试套件 | 119/119 全绿（含新增 action_map 层一致性） |
| variants._self_test | 通过（mapping/physics/action_map 3 候选） |
| wheel_to_discrete.py 工作树 | 未修改（REGRESSION 不归档行为变更，仅保留变体定义） |
| 快照/回滚闭环 | 3 轮 × 6 候选全部正确 restore（含 action_map 层） |

## 8. 关联文件

- `governance/meta_harness/variants.py`（HARNESS_FILES 六层 + _gen action_map 分支 + 种子/阈值）
- `governance/meta_harness/outer_loop.py`（HARNESS_FILES 六层同步）
- `governance/meta_harness/distill_loop.py`（D2_PRIOR 新增 action_map）
- `governance/meta_harness/failure_analysis.md`（FP-NEG-003）
- `governance/meta_harness/pareto_frontier.md`（S28 轮速轴实证）
- `docs/architecture/ROADMAP_v2.md`（11.23 节）
- 运行数据：`governance/meta_harness/variants/_snapshots/20260808_1647*`（不提交，RL-4）
