# Sprint 31 证据：规则拓扑第二波探索（branch_hist 修正归因）

- 日期：2026-08-08
- 分支：`feature/sprint31_topo2_branch_hist`（基于 main=63b6565 = S30 合入 + tag sprint30-closed）
- 目标：基于 FP-NEG-004 的 branch_hist 修正归因，执行规则拓扑第二波探索
- 验证命令：`outer_loop.py --iterations 5 --round 12 --tag S31_TOPO2 --meta-config`（显式 --round 12）
- 快照：`variants/_snapshots/20260808_184101/`
- 测试：**128/128 全绿**（含 9 个 M2 四通道测试）

---

## 1. T1：FP-NEG-004 branch_hist 修正归因（候选设计前置分析）

基线（S29/S31 共享，10 episodes）branch_hist 逐局分析：

| 指标 | 值 |
|------|-----|
| 基线 avg_steps | 21.4（steps=[6,8,7,19,42,49,12,60,5,6]） |
| FLANK 全局占比 | **67.3%**（144/214 触发；LEFT 84 + RIGHT 60） |
| CLOSE-PUSH | 57（26.6%） |
| CAUTIOUS-EDGE | 13（6.1%） |
| 慢局（>30 步）| 3 局：42 / 49 / 60 步，全部 FLANK 主导 |
| ep7（60 步死循环）| FLANK-RIGHT:45 + CAUTIOUS-EDGE:13 交替让路 |

**修正归因结论**（FP-NEG-004 要求逐局验证，不凭 avg_steps 推断）：
1. 慢局元凶不是单一分支，而是 **FLANK（edge<0.80）与 CAUTIOUS-EDGE（BETWEEN 0.55-0.78）条件重叠区的交替让路**（ep7 = 45+13 次）。
2. FLANK 高占比（67.3%）本身是"正常路径"，真正的问题是**无退出机制**（45 次侧翼校准不收敛）与**边缘让路竞争**。
3. 由此设计三个正交拓扑候选：触发域收窄（D）/ 循环打断（E）/ 退出机制（F）。

## 2. T2：三个拓扑候选设计与实施（variants.py, ROUND 12 分支）

| 候选 | 变更（拓扑级，无参数 bump） | branch_hist 预期变化 |
|------|------------------------------|----------------------|
| mh_rules_topo_D | FLANK 角度阈值 ±10°→±15°（`sensor(opponent_angle) < -10`→`< -15`；`> 10`→`> 15`） | FLANK 触发域收窄，-10°~-15° 区间改由其他分支接管；预期 FLANK 计数下降、部分局转入 CLOSE-PUSH 对齐窗 |
| mh_rules_topo_E | CAUTIOUS-EDGE 下界 0.55→0.60（`BETWEEN(sensor(edge_proximity), 0.55, 0.78)`→`0.60`） | 0.55~0.60 区间不再触发 CAUTIOUS-EDGE，与 FLANK 的重叠区收窄 → 预期 ep7 交替死循环打断、步数下降 |
| mh_rules_topo_F | FLANK 条件追加 `AND sensor(stuck_counter) < 3`（左右各一处） | stuck≥3 时 FLANK 让路 → 预期 45 次无收敛侧翼校准被上限截断 |

交叉验证池（ROUND 12 全部 5 候选）：D + E + F + topo_A 回放（M2 四通道下判定变化）+ mh_mapping_001 回放（S29 REGRESSION 复现）。

**预检**（`_tmp/s31_precheck.py`）：
- 候选池 = {D, E, F, A, mapping_001} ✅
- 全部锚点 expected 与实际 text.count 唯一匹配 ✅（F 的完整条件串 `... AND sensor(opponent_dist) < 0.6 AND sensor(edge_proximity) < 0.80` 精确存在）
- M2.2 拓扑预检：D/E/F 均无 priority 变更 → 全部放行 ✅

## 3. T2 验证结果：判定分布（ROUND 12, S31_TOPO2）

3 轮探索饱和（P2-V4 门）提前终止，判定确定性可复现：

| 候选 | 判定 | Q | winrate | avg_steps | rules 触发 | 关键信号 |
|------|------|---|---------|-----------|------------|----------|
| mh_rules_topo_D | **REGRESSION** | **-0.53** | 1.00 | 21.4→**34.1** | 214→341 (+59%) | 裸 `abdl` 分支 92 次（覆盖真空）；熵 0.648→0.571（-0.078 坍缩） |
| mh_rules_topo_E | INCONCLUSIVE (no-op) | — | 1.00 | 21.4→21.4 | 无变化 | 逐位 identical（FP-MC-014 类） |
| mh_rules_topo_F | INCONCLUSIVE (no-op) | — | 1.00 | 21.4→21.4 | 无变化 | 逐位 identical（FP-MC-014 类） |
| mh_rules_topo_A（回放）| **SUSPICIOUS** | +0.02 | 1.00 | 21.4→21.3 | 214→213 | CAUTIOUS-EDGE 13→0 消失；熵 +0.013；60→59 步 |
| mh_mapping_001（回放）| **REGRESSION** | -0.17 | 1.00 | 21.4→29.3 | — | 与 S29 完全复现（第三次确认） |

### 3.1 topo_D：覆盖真空（REGRESSION, Q=-0.53, 新失败机制）

- **diff 重放验证**（`_tmp/s31_replay_D.py`）：apply 产物精确——`< -10`→`< -15`、`> 10`→`> 15` 各 1 处替换，BETWEEN(-10,10) 未污染，无残留。
- **行为归因**：收窄后角度区间 **(-15,-10)∪(10,15) 无任何规则覆盖** → ABDL 落入无命名默认分支（ep1 出现裸键 `'abdl': 16`）→ 平均步数 21.4→34.1（+59%），触发总数 214→341（规则空转）。
- **治理发现**：topo_D 通过 M2.2 预检（无 priority 跨越）却制造了**覆盖连续性断裂** —— M2.2 只检测 priority 重排的胜者集合变化，**不检测条件域收窄后的覆盖空洞**。这是 M2.2 预检的盲区，纳入 failure_analysis（下轮升级方向：覆盖连续性检测）。
- **对照 S29 深度**：S29 最深 REGRESSION 为 -0.16/-0.17；S31 topo_D 达 **-0.53**，为迄今最深负向信号。

### 3.2 topo_E / topo_F：双 no-op —— 交替死循环假设证伪

- E（CAUTIOUS-EDGE 下界 0.55→0.60）逐位无变化：**0.55~0.60 区间在 10-episode 分布中从未被采样到**（CAUTIOUS-EDGE 触发时 edge_proximity 均 ≥0.60 或由其他条件先行），故循环打断无对象。
- F（FLANK + stuck_counter<3）逐位无变化：**stuck_counter 传感器在 FLANK 触发场景恒 <3**（45 次侧翼校准并非 stuck 死锁，而是正常追踪路径上的高频重复触发）。
- **归因修正**（FP-NEG-004 闭环）：ep7 的 45+13 交替并非"CAUTIOUS-EDGE 主动让路"或"stuck 卡死"，而是 **FLANK 自身在 edge∈[0.60,0.80) 且角度校准未收敛时的正常反复选择**。真正干预点应是对 FLANK 触发次数设上限（非 stuck 传感器），或扩大 CLOSE-PUSH 接管域。

### 3.3 topo_A 回放：INCONCLUSIVE → SUSPICIOUS（M2 四通道升级直接验证）

- 同一候选（CLOSE-PUSH edge 0.65→0.80）在 S29（三通道）判 INCONCLUSIVE (Q=0.00)，S31（M2 四通道）判 **SUSPICIOUS (Q=0.02)**：第四通道 `_branch_hist_signal` 捕获熵微升（0.648→0.661, Δ=+0.013），方向约束放行（效率同步 +0.005）。
- **结构发现**：CLOSE-PUSH 上界对齐后 **CAUTIOUS-EDGE 13→0 完全消失**（CLOSE-PUSH 接管其触发域），但步数仅 -1（60→59）→ **CAUTIOUS-EDGE 是近似冗余分支**（其行为可被 CLOSE-PUSH 无损替代）。此发现对后续拓扑精简（S32 候选 G：CAUTIOUS-EDGE 移除评估）提供依据。

## 4. T3 / V9 门状态

- 判定分布：**0 PASSED**（D REGRESSION / E-F no-op / A SUSPICIOUS / mapping REGRESSION）。
- 3 轮无 PASSED → **V9 门触发条件满足**（plateau_explorer 自蒸馏正式启动；P2-V4 探索饱和门按设计 3/5 轮提前终止）。
- 自蒸馏为 Sprint 31 延后项，正式排期为 V9 门触发后的下一个执行块。

## 5. 验收核对

| 验收项 | 状态 |
|--------|------|
| ① 3 个候选各带 branch_hist 预期变化 | ✅ variants.py D/E/F 均含 hypothesis + expected |
| ② 至少 1 PASSED **或** 判定分布显著变化 | ✅ 0 PASSED，但分布显著：D 覆盖真空 -0.53（新机制）；A 回放 INCONCLUSIVE→SUSPICIOUS（M2 捕获）；E/F 双 no-op 证伪 |
| ③ 128/128 全绿 | ✅ 128 passed in 6.69s |

## 6. 治理产出

1. **M2.2 预检盲区（P0）**：priority 跨越检测不覆盖"条件域收窄导致的覆盖空洞" → 升级方向：解析邻居规则触发域并检测收窄后空洞区间。
2. **CAUTIOUS-EDGE 近似冗余（P1）**：S32 候选 G = CAUTIOUS-EDGE 移除评估（用 M2 四通道验证零损失）。
3. **FLANK 退出机制修正（P1）**：stuck_counter 传感器无效（恒<3）；改为 FLANK 触发次数上限或 CLOSE-PUSH 域扩大。
4. **FP-NEG-004 闭环**：交替死循环归因修正为"FLANK 高频正常重复"，非 stuck 死锁。
5. **mh_mapping_001 第三次 REGRESSION 复现（-0.17）**：flank dist 0.15 收窄确认负向，维持 S27v3 结论。

## 7. 文件

- `governance/meta_harness/variants.py`：topo D/E/F + ROUND 12 分支
- `_tmp/s31_precheck.py` / `_tmp/s31_replay_D.py` / `_tmp/s31_result_analysis.py` / `_tmp/s31_deep_check.py` / `_tmp/s31_verify_EF_A.py` / `_tmp/s31_inspect_keys.py`（工作文件）
- 快照：`variants/_snapshots/20260808_184101/`
