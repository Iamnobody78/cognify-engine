# Sprint 32 证据：覆盖连续性预检升级（FP-NEG-005）+ 治理发现自蒸馏

- 日期：2026-08-08
- 分支：`feature/sprint32_coverage_distill`（基于 main 5931458 = S31 合入 + tag sprint31-closed）
- 目标：P0 M2.2 覆盖连续性预检升级；P1 基于 S31 三大治理发现的自蒸馏迭代
- 测试：**134/134 全绿**（原 128 + 新增 6 覆盖连续性测试，集成测试适配扩宽语义）

---

## P0：覆盖连续性预检升级（FP-NEG-005）

### 问题回顾
S31 topo_D（FLANK ±10→±15）通过 M2.2 priority 预检（无 priority 变更）却制造覆盖断裂：
(-15,-10)∪(10,15) 无任何规则匹配 → ABDL 落入无命名默认分支（裸 `abdl` 键 92 次）→
avg_steps 21.4→34.1（+59%）。**M2.2 只查 priority 重排的胜者集合变化，不查条件域收窄的覆盖连续性**。

### 实现（evaluator_diff_test.py）
新增 `coverage_continuity_check(entries, rules_text)` + 辅助函数：

| 函数 | 职责 |
|------|------|
| `_parse_dim_intervals` | 解析规则文本中某数值维度（angle/dist/edge）的全部触发闭区间（`<`/`<=`/`>`/`>=`/`BETWEEN`） |
| `_merge_intervals` | 合并重叠/相邻区间 → 覆盖并集 |
| `_coverage_gaps` | 返回维度上未被任何规则覆盖的连续区间（维度投影） |
| `coverage_continuity_check` | ① 找 entries 涉及的数值维度 ② 模拟应用全部 diff ③ 对比基线 vs 候选的覆盖空洞 → 新增空洞标 `COVERAGE_GAP` 拦截 |

串联进 `precheck_topology_validity` 第 0 步（priority 检查之前）：条件域收窄/迁移类变更
先过覆盖检查，防止 topo_D 同构损坏放行进入评估循环。

### 判别验证（_tmp/s32_coverage_smoke.py，S31 真实候选）

| 候选 | 变更 | 判别 | 依据 |
|------|------|------|------|
| topo_D | FLANK ±10→±15 收窄 | **拦截 COVERAGE_GAP** | angle 维度新增空洞 (-15,-10)∪(10,15) |
| topo_E | CAUTIOUS-EDGE 0.55→0.60 | 放行 | (0.55,0.60) 仍被 CLOSE-PUSH <0.65 覆盖，无新增空洞（与 S31 实测 no-op 一致） |
| topo_F | FLANK + stuck_counter<3 | 放行 | stuck 不在投影维度，无数值收窄 |
| topo_A | CLOSE-PUSH 0.65→0.80 扩宽 | 放行 | 扩宽不产生空洞 |
| priority-only | 800→850 无跨越 | 覆盖检查跳过 → priority 判定 | involved 为空 |

### 新增测试（tests/test_m2_fused_signals.py，+6）
`test_coverage_gap_angle_narrow_blocked` / `test_coverage_gap_edge_narrow_covered_by_neighbor` /
`test_coverage_gap_append_and_condition_passthrough` / `test_coverage_gap_widen_passthrough` /
`test_coverage_gap_anchor_mismatch_blocked` / `test_coverage_gap_no_numeric_dim_skips`

### 集成测试适配
`test_diff_gate_integration.py` mock_1 由 `< -10`→`< -12`（收窄，在真实规则文件上制造
(-12,-10) 空洞 → 被新预检正确拦截）改为 `< -10`→`< -8`（扩宽，放行）——保留"rules 层
候选进入门禁"的测试意图，同时与新预检语义一致。

## P1：治理发现自蒸馏（D4 通道）

### 设计
distill_loop.py 新增 `distill_d4(discoveries=None)`：将 Sprint 31 三大治理发现编码为
结构化可复用规则（anti-collapse 原则：非 LLM 自由文本，全部来自 S31 实证数据）。
`run()` 挂载 D4，meta.sprint 更新为 "S32-M1 (V9 门触发后首轮自蒸馏)"。

### 输出（experience/distill_rules_20260808_190458.json）
- `diff_gate_total`: 328（20260808 起全量）
- **D4-1 覆盖连续性预检**：条件域收窄/迁移类变更 apply 前验证邻居覆盖，否则 COVERAGE_GAP 拦截（源 FP-NEG-005）
- **D4-2 慢局归因修正**：FLANK 高频重复触发时先验证 stuck_counter 是否真达阈值，恒<3 则干预点应为触发次数上限（源 FP-NEG-006 + topo_E/F 双 no-op）
- **D4-3 冗余分支识别**：分支触发域 ⊆ 邻居触发域且移除步数变化 ≤1 → 冗余候选（S32 候选 G）（源 topo_A 回放）
- D1 desensitization: 78（全部饱和失敏 = M2 四通道前的失敏信号基线）
- D2 perturbation_prior: 154

### D3 分布洞察（S32 视角）
- mapping 层：54 INC / 45 SUSPICIOUS / 21 REGRESSION —— 失敏集中层（M2 四通道修复目标）
- rules 层：22 INC / 12 SUSPICIOUS / 18 REGRESSION —— 拓扑扰动感知
- physics 层：78 INC / 21 SUSPICIOUS / 48 REGRESSION

## 验收核对

| 验收项 | 状态 |
|--------|------|
| 覆盖预检拦截（D 收窄 → COVERAGE_GAP）| ✅ 单元测试 + 真实候选冒烟双验证 |
| 自蒸馏输出（D4 三条治理规则）| ✅ distill_rules_20260808_190458.json |
| 双端回归全绿 | ✅ 134/134 pytest + outer_loop 正常加载 |

## 文件

- `governance/meta_harness/evaluator_diff_test.py`：coverage_continuity_check + 串联
- `governance/meta_harness/distill_loop.py`：distill_d4 + run() 挂载
- `governance/meta_harness/tests/test_m2_fused_signals.py`：+6 测试
- `governance/meta_harness/tests/test_diff_gate_integration.py`：mock_1 扩宽适配
- `governance/meta_harness/experience/distill_rules_20260808_190458.json`：D4 输出
- `_tmp/s32_coverage_smoke.py` / `_tmp/s32_check_decisions.py` / `_tmp/s32_verify_d4.py`（工作文件）
