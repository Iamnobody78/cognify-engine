# Sprint 29 规则拓扑探索证据 (S29_RULE_TOPOLOGY_DISTILL, 2026-08-08)

## 一、PM 裁决执行清单

| 步骤 | 内容 | 状态 |
| :--- | :--- | :--- |
| 1 | main 合入 Sprint 28 (ff42e5d) + tag sprint28-closed | ✅ |
| 2 | 分支 feature/sprint29_rule_topology_distill | ✅ |
| 3 | 规则拓扑探索：3 个候选 (A/B/C) 实现于 variants.py `_gen("rules")` + ROUND 11 分支 | ✅ |
| 4 | 并行自蒸馏：distill_loop.py → distill_rules_20260808_170729.json | ✅ |
| 5 | 5 轮验证：outer_loop --iterations 5 --round 11 --meta-config | ✅ (3 轮探索饱和提前终止) |
| 6 | 验收报告：判定分布 + 自蒸馏摘要 | ✅ (本文档) |

## 二、规则拓扑候选设计（拓扑级文本变更，规避 FP-MC-020 参数级 bump 根因）

| 候选 | 变更（old → new） | 拓扑意图 | ABDL 锚点 | FP-NEG-002 可达性 |
| :--- | :--- | :--- | :--- | :--- |
| mh_rules_topo_A | CLOSE-PUSH `sensor(edge_proximity) < 0.65` → `< 0.80` | 填充 L2 空洞（60 步贴边对局） | simulation_rules.abdl L99 | ✅ 无死路径 |
| mh_rules_topo_B | OPPONENT-FOUND `sensor(opponent_dist) > 0.6` → `>= 0.3` | 触发域重组（近距离接管） | simulation_rules.abdl L68 | ✅ |
| mh_rules_topo_C | SPEED-ADAPT `priority: 300` → `priority: 350` | 优先级重排（时间压力优先） | simulation_rules.abdl L132 | ✅ |

## 三、验证结果（outer_loop --iterations 5 --tag S29_RULE_TOPOLOGY_DISTILL --round 11 --meta-config）

### 3.1 判定分布（3 轮探索饱和提前终止，确定性可复现：3 轮判定完全一致）

| 候选 | 判定 | Q | winrate | avg_steps | rules 触发 | 逐局 steps |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| mh_rules_topo_A | **INCONCLUSIVE** | 0.00 | 1.00 | 21.4→21.3 | 214→213 | [6,8,7,19,42,49,12,**59**,5,6] |
| mh_rules_topo_B | **REGRESSION** | -0.16 | 1.00 | 21.4→24.8 | 214→248 | [6,8,7,19,**52,73**,12,60,5,6] |
| mh_rules_topo_C | **INCONCLUSIVE (no-op)** | — | 1.00 | 21.4→21.4 | 无变化 | identical（逐位相同） |
| mh_mapping_001 | **REGRESSION** | -0.17 | 1.00 | 21.4→29.3 | — | [6,12,10,29,41,47,**74**,57,11,6] |

基线：steps=[6,8,7,19,42,49,12,60,5,6]，avg=21.4，winrate=1.0（10/10）
基线第 8 局（60 步，circler）branch_hist：**FLANK-RIGHT:45 + CAUTIOUS-EDGE:13 + CLOSE-PUSH:2**

### 3.2 因果推理

1. **候选 A 假设证伪（空洞假设不成立）**：S29 立项假设"第 8 局 60 步 = edge∈[0.65,0.80) 且
   angle∈[-10,10] 时 CLOSE-PUSH/FLANK 均不触发 → 无 L2 接管 → 落回 L3 减速"。但 branch_hist 显示
   第 8 局主导分支是 **FLANK-RIGHT 45 次（侧翼死循环）** + CAUTIOUS-EDGE 13 次，CLOSE-PUSH 仅 2 次——
   L2 一直在接管，失败模式是 FLANK 侧翼追不上 circler 而非空洞。edge 0.65→0.80 只增加 1 次
   CLOSE-PUSH 触发（60→59 步），净行为影响近零 → INCONCLUSIVE。
   **方法论教训：拓扑候选的动机假设必须用 branch_hist 逐局验证，不能凭 avg_steps 推断失败模式。**

2. **候选 B 优先级抢占（REGRESSION 机制，FP-NEG-004）**：OPPONENT-FOUND（p700）触发域从 dist>0.6
   扩至 >=0.3 后，在 dist∈[0.3,0.6) 区间与 CLOSE-PUSH（p500）/FLANK（p480/470）领地重叠——
   **p700 > p500，ABDL 按 priority 降序 resolve_top() 优先选 OPPONENT-FOUND → `_pursue_opponent`
   （≤0.38 m/s）替代 CLOSE-PUSH 直推（FW_MAX）→ 近距离推挤效率下降** → defensive 对局
   42→52、49→73 步拖长，触发总数 214→248（+34）。
   这是 **F-100（p700 遮蔽近战规则）被拓扑级变更重新触发**的教科书案例——F-100 修复是
   OPPONENT-FOUND 增加 `AND opponent_dist > 0.6` 约束，候选 B 正好反向撤销该约束。

3. **候选 C no-op（priority 重排需跨越邻居）**：SPEED-ADAPT priority 300→350 在优先级全序中
   仍是第 7 位（700/600/590/500/480/470/350/250/200/150）——350 仍 > 250（CAUTIOUS-EDGE）且
   < 470（FLANK-LEFT），**没有跨越任何邻居规则** → resolve_top() 的胜者集合完全不变 → identical:true。
   **拓扑规则：priority 数值变更必须跨越至少一个其他规则的优先级才构成真实拓扑变更；同序位内
   数值微调是结构性 no-op（FP-MC-014 同根，但这里是确定性结构，非评估盲区）。**

4. **mh_mapping_001 交叉验证（REGRESSION 复现）**：flank dist 0.20→0.15 大幅收窄 → 动作熵
   0.831→0.865，步数 +37%（21.4→29.3，S27 v3 完全同构）——mapping 层距离轴 0.20 单峰最优
   第三次确认（S26D 0.18 INCONCLUSIVE / S27v2 0.25 REGRESSION / S27v3 0.15 REGRESSION / S29 0.15 REGRESSION）。

## 四、自蒸馏产物（plateau_explorer 并行触发，步骤 4）

- 文件：`experience/distill_rules_20260808_170729.json`
- 摘要：**D1 去敏化 66 条**（全部 winrate 饱和）、**D2 扰动先验 124 条**、**D3 多样性被阻止 253 条**
- 分维度判定分布：
  | 层 | INCONCLUSIVE | REGRESSION | SUSPICIOUS |
  | :--- | :--- | :--- | :--- |
  | action_map（新增） | 3 | 3 | 0 |
  | mapping | 48 | 9 | 45 |
  | physics | 66 | 42 | 21 |
  | rules | 10 | 9 | 0 |
- **M2 融合升级前置证据**：mapping 层 48 INCONCLUSIVE + 45 SUSPICIOUS 的饱和失敏分布，是
  PM 裁决"评估器信号融合升级（M2）"的核心数据依据（OmniPlay 融合机制脆弱论点的本地实证）。

## 五、验收结论

1. **规则拓扑探索：0 PASSED / 1 INCONCLUSIVE（假设证伪）/ 1 REGRESSION / 1 no-op**——
   获得拓扑负空间图谱（FP-NEG-004 三条因果入库 failure_analysis.md）
2. **自蒸馏：产物完整**（66 D1 / 124 D2 / 253 blocked），判定分布呈现层间结构性差异
3. **V9 门触发条件满足**（3 轮无 PASSED）；P2-V4 探索饱和门按设计提前终止（3/5 轮）
4. **下一步（待 PM 裁决）**：M2 评估器信号融合升级（mapping 饱和失敏证据已备）；
   或规则拓扑第二波候选（基于 branch_hist 修正的失败模式归因，如 FLANK-RIGHT 侧翼收敛）

## 六、证据链

- 快照：`variants/_snapshots/20260808_171124/`、`171134/`、`171142/`（3 轮判定一致性）
- 蒸馏产物：`experience/distill_rules_20260808_170729.json`
- 测试：meta_harness 119/119 全绿
- 分支：feature/sprint29_rule_topology_distill（基于 main ff42e5d = S28 合入）
