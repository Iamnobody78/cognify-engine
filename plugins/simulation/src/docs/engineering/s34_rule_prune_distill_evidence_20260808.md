# Sprint 34 证据文档 — 候选 G 合入主规则 + D5 蒸馏入库 (2026-08-08)

> 分支: `feature/s34_rule_prune_distill` (基于 main 4a2e8bc = S33 合入 + tag sprint33-closed)
> 执行指令: PM Sprint 34 裁决 (P0 候选 G 合入 8→7 / P1 D5 高价值规则蒸馏 / P2 Hermes B2 延后 S35)

---

## 1. P0 — 候选 G 合入主规则 (CAUTIOUS-EDGE 物理删除)

### 1.1 变更内容

`governance/meta_language/simulation_rules.abdl` 中 SIM-HEUR-CAUTIOUS-EDGE 块物理删除:

| 项 | 值 |
| :--- | :--- |
| 删除块 | `SIM-HEUR-CAUTIOUS-EDGE` / level 3 / `BETWEEN(edge_proximity), 0.55, 0.78)` / PolicyCautiousEdge / priority 250 (原 L137-144) |
| 规则 id 数 | 13 → **12** |
| CAUTIOUS 出现次数 | **0** |
| git diff | 9 行纯删除, 无行尾污染 (字节级 WSL python3 编辑, CRLF 保持) |

### 1.2 基线验证 (outer_loop --iterations 3 --tag S34_G_MERGE)

| 指标 | S33 (13 规则) | S34 (12 规则) | 一致性 |
| :--- | :--- | :--- | :--- |
| avg_steps | 21.4 | **21.4** | ✅ 一致 |
| winrate | 1.0 | **1.0** | ✅ 一致 |
| rules 触发 | 214 | **214** (零 CAUTIOUS-EDGE) | ✅ 一致 |

**判定复现** (全部与 S33 一致, 无锚点崩溃无预检混淆):
- mh_rules_topo_A → SUSPICIOUS (复现)
- mh_rules_topo_B → REGRESSION (-0.16, 复现)
- 候选 C → TOPO-PRECHECK-FAIL (复现)
- mh_mapping_001 → REGRESSION (-0.17, 复现)
- mh_mapping_002 → INCONCLUSIVE (复现)
- mh_physics_seed_001 → REGRESSION / seed_002, seed_003 → INCONCLUSIVE (复现)
- mh_action_map_001 → REGRESSION (复现)
- 探索饱和: 3 轮无有效结果 (规则空间已固定, 预期)

**结论**: D4-3 冗余判定 (S33) 在物理删除后成立 — CAUTIOUS-EDGE 的 13 次触发被邻居
(CLOSE-PUSH <0.65 + FLANK <0.80) 无损吸收。PM 预期 "步数 214, 分数 1.0" 满足。

---

## 2. P1 — D5 蒸馏规则入库 (engineering_rules.md)

### 2.1 HC 章节写入

`governance/dashboard/engineering_rules.md` 新增「高置信度规则 (HC) — D5 蒸馏入库 (Sprint 34)」章节,
位于流程规则 (PR) 与分隔线之间, 字节级插入 (CRLF 保持, git diff 13 行纯新增):

| ID | 规则 | 来源 |
| :--- | :--- | :--- |
| RULE-HC-001 | FLANK 阈值收窄 ±10→±15 为 REGRESSION 方向 (topo_B, conf=0.48): avg_steps +3.4、熵 Δ+0.024 (S29 最强信号); 候选生成禁止沿 FLANK 收窄方向 | D5 校准 (S33) |
| RULE-HC-002 | flank dist 0.15 截止为 REGRESSION 方向 (mapping_001, conf=0.30): avg_steps +7.9, 4 次复现 (S27v3/S29/S31/S33); 特征已解决, 保持锁定 | D5 校准 (S33) |
| RULE-HC-003 | CLOSE-PUSH edge 0.65→0.80 对齐为 SUSPICIOUS 边界 (topo_A, conf=0.26): Q=+0.02、熵 Δ+0.013, CAUTIOUS-EDGE 触发域被吸收 (13→0); M2 捕获微信号 | D5 校准 (S33) |

### 2.2 副作用验证 (distill_loop --recalibrate, 12 规则基线)

| 规则 | S33 conf | S34 重跑 conf | 漂移 |
| :--- | :--- | :--- | :--- |
| topo_B (D1-mh_rules_topo_B) | 0.48 | **0.48** | 0.00 ✅ |
| mapping_001 (D1-mh_mapping_001) | 0.30 | **0.30** | 0.00 ✅ |
| topo_A (D1-mh_rules_topo_A) | 0.26 | **0.26** | 0.00 ✅ |

**副作用路径确认**: `distill_loop.py` 不消费 `engineering_rules.md` (HC 规则为后续候选
生成的治理指导, 非管道输入); `cell_learner` 写 `meta_engineering_rules.md` 为另一文件 —
治理规则库与蒸馏管道零耦合。蒸馏入库无副作用 ✅

---

## 3. 测试与回归

- [ ] meta_harness 134/134 (候选 G 合入后全量回归, 待执行确认)

## 4. 交付物

| 文件 | 变更 |
| :--- | :--- |
| `governance/meta_language/simulation_rules.abdl` | CAUTIOUS-EDGE 物理删除 (13→12 规则) |
| `governance/dashboard/engineering_rules.md` | HC 章节 (RULE-HC-001/002/003) + footer 更新 |
| `governance/meta_harness/failure_analysis.md` | S34 记录 |
| `governance/meta_harness/pareto_frontier.md` | S34 运行记录 |
| `_tmp/s34_remove_cautious_edge.py` | P0 删除脚本 (交付物留存) |
| `_tmp/s34_verify_recal.py` | P1 副作用验证脚本 (交付物留存) |
| `_tmp/s34_distill_rules_md.py` | HC 章节写入脚本 (交付物留存) |
| 本文件 | S34 证据文档 |
