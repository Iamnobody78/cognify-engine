# Sprint 33 证据：候选 G CAUTIOUS-EDGE 移除评估 + D5 置信度校准

- 日期：2026-08-08
- 分支：`feature/s33_candidate_g_distill`（基于 main 31fb72e = S32 合入 + tag sprint32-closed）
- 目标：P0 候选 G CAUTIOUS-EDGE 移除评估（D4-3 依据）；P1 D1/D2 自蒸馏迭代（D5 置信度校准）
- 测试：**134/134 全绿**

---

## P0：候选 G CAUTIOUS-EDGE 移除评估

### 依据（D4-3 冗余分支识别，S31 topo_A 回放实证）
S31 topo_A（CLOSE-PUSH edge 0.65→0.80 对齐）回放显示：CAUTIOUS-EDGE 13→0 触发完全
消失但步数仅 -1（60→59）→ CAUTIOUS-EDGE 触发域 ⊆ CLOSE-PUSH/FLANK 触发域，可无损
替代。PM 裁决 S33 P0 批准移除评估（预检层 S32 已稳定，三层防护覆盖副作用）。

### 实施（variants.py）
- `mh_rules_topo_G`（候选 C 后追加）：注释化 `SIM-HEUR-CAUTIOUS-EDGE` 整条规则块
  （拓扑级文本变更，非参数 bump，S29 禁令合规；含移除原因注释）
- ROUND 13 分支：topo_G + topo_A 回放（冗余证据源）+ mapping_001（交叉验证）

### 预检（_tmp/s33_precheck.py）
- ROUND 13 池 = {topo_G, topo_A, mapping_001} ✅
- G 锚点（CAUTIOUS-EDGE 块）唯一存在 ✅
- **覆盖预检放行**：移除后 edge 维度无空洞（0.55-0.78 区间被 CLOSE-PUSH <0.65 +
  FLANK <0.80 覆盖）✅ —— S32 COVERAGE_GAP 预检确认移除安全

### 验证（outer_loop --iterations 3 --round 13 --tag S33_CAND_G，3 轮一致）

| 候选 | 判定 | avg_steps | rules 触发 | 关键信号 |
|------|------|-----------|------------|----------|
| **mh_rules_topo_G** | **INCONCLUSIVE (Q=0.00)** | 21.4→21.4（**0 变化**） | 214→214 | CAUTIOUS-EDGE 13 次触发被 CLOSE-PUSH/FLANK 无损吸收；熵 0.648→0.651（Δ+0.002） |
| mh_rules_topo_A（回放） | SUSPICIOUS (Q=0.02) | 60→59 | 213 | 复现 S31 |
| mh_mapping_001（回放） | REGRESSION (Q=-0.17) | 21.4→29.3 | — | 第四次复现 |

**结论**：候选 G 步数变化 0（≤1 达标），无新增 REGRESSION，通过三层防护
（diff_gate INCONCLUSIVE + priority 预检放行 + COVERAGE_GAP 预检放行）——
**CAUTIOUS-EDGE 冗余判定实证成立**，可安全移除（S34 合入主规则）。

## P1：D5 置信度校准（--recalibrate）

### 设计（distill_loop.py）
`recalibrate_rules(dg)`：基于 M2 四通道信号对 D1/D2 规则置信度校准：
- `|Q|` 越大 → 行为影响越确定 → 置信度越高
- branch_hist 熵响应 `|Δ熵|` 越大 → 拓扑级变化越显著 → 加分
- winrate 饱和（失敏）→ 置信度 ×0.6 降级
- 同 variant 多条记录（重复 id）按最强信号聚合
- 输出：每条规则附带 `confidence` + `signal_components`，按置信度降序

CLI 新增 `--recalibrate`（run() 挂载 D5，meta.sprint = "S33-M1 (候选 G 后自蒸馏迭代,
D5 置信度校准)"）。

### 输出（experience/distill_rules_20260808_192416.json）
- diff_gate_total: **349**（含 S33 候选 G 记录）
- **D1 排序（按置信度）**：
  - `D1-mh_rules_topo_B` conf=0.48（|Δ熵|=0.024，S29 REGRESSION 最强信号）
  - `D1-mh_mapping_001` conf=0.30（|Δ熵|=0.015，S31 第四次复现）
  - `D1-mh_rules_topo_A` conf=0.26（|Δ熵|=0.013，M2 捕获微号）
  - mapping_002 / physics_seed_002 conf=0.05（低信号）
- **D2 含候选 G**（conf=0.05，INCONCLUSIVE 中性 → 低信息量，符合 no-op 预期）
- D3 分布（349 记录）：mapping 54 INC/45 SUS/27 REG；physics 78 INC/21 SUS/48 REG；
  action_map 9 REG（S33 候选 G 入池后 REGRESSION 计数更新）

### 校准有效性验证
- D1 降序排列正确 ✓
- 熵响应强度与置信度单调对应（0.024→0.48 > 0.015→0.30 > 0.013→0.26）✓
- no-op 候选（G, seed_002 等）置信度地板 0.05 ✓

## 验收核对

| 验收项 | 状态 |
|--------|------|
| 候选 G 通过三层防护 | ✅ diff_gate INCONCLUSIVE + priority 放行 + COVERAGE_GAP 放行 |
| 步数变化 ≤1 且无新增 REGRESSION | ✅ 变化 0（21.4→21.4） |
| 自蒸馏输出精炼规则（D5 校准） | ✅ distill_rules_20260808_192416.json |
| 双端回归全绿 | ✅ 134/134 pytest |

## 治理产出

1. **CAUTIOUS-EDGE 冗余判定闭环**：D4-3 预测（13→0 消失步数 -1）→ 候选 G 实测
   （移除后步数 0 变化）→ 判定成立，S34 可合入主规则（净减 1 规则）。
2. **D5 校准机制**：M2 四通道信号 → 蒸馏规则置信度排序，后续蒸馏可筛选
   conf≥0.3 的高价值规则（当前 topo_B/mapping_001/topo_A 三强）。
3. **评估预算再优化**：S31 浪费在 topo_D 的评估（34.1 步灾难）现被三层防护拦截；
   S33 候选 G 的 INCONCLUSIVE 判定证明冗余规则不再消耗信号带宽。

## 文件

- `governance/meta_harness/variants.py`：mh_rules_topo_G + ROUND 13 分支
- `governance/meta_harness/distill_loop.py`：recalibrate_rules（D5）+ --recalibrate CLI + re 导入
- `governance/meta_harness/experience/distill_rules_20260808_192416.json`：D5 校准输出
- `_tmp/s33_precheck.py` / `_tmp/s33_verify_d5.py` / `_tmp/s33_inspect_structure.py`（工作文件）
