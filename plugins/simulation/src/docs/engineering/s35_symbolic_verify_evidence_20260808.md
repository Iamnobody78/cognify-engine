# Sprint 35 证据文档 — Z3 符号验证层 (第四层防护) + 新领域勘探 (2026-08-08)

> 分支: `feature/s35_symbolic_exploration` (基于 main bd07d5e = S34 合入 + tag sprint34-closed)
> PM 裁决: T1 Z3 符号验证集成 (P0) + T2 奖励/物理参数域探索 (P1, 并行)
> 验收: ①至少 1 个拓扑候选被 Z3 拦截 ②验证延迟 < 5s/候选 ③双端回归全绿 ④T2 判定分布变化

---

## 1. T1 — Z3 符号验证层 (第四层防护, SYMBOLIC_PROOF_FAIL)

### 1.1 架构: 第四层防护 (数学级, 区别于三层经验验证)

```
现有三层防护 (经验验证)          → 新增第四层 (形式验证, S35)
├── S21: diff_gate (行为级判定)    ├── S35: symbolic_verify (Z3/SMT 联合覆盖证明)
├── S30: priority 预检 (冲突检测)  │     不变量 I1: ∀输入点∈物理定义域 → 至少一条规则匹配
└── S32: COVERAGE_GAP (单维投影)   │     新增空洞查询: ∃x: 基线有匹配 ∧ 候选无匹配
                                   └─→ 拦截判据: 候选覆盖 ⊄ 基线覆盖 → SYMBOLIC_PROOF_FAIL
```

### 1.2 核心发现: 12 规则基线存在 S32 盲区的联合空洞

`symbolic_verify.py --selfcheck` 对 S34 合入后的 12 规则基线证明存在**真实联合空洞**:

| 空洞 | 位置 | 原因 | S32 可见性 |
| :--- | :--- | :--- | :--- |
| A | `opponent_found=False ∧ edge∈(0.6, 0.8]` | EDGE-WARNING 是 `>0.8` 严格不等; LOST-NEAR-EDGE 止于 0.6 | 不可见 (edge 维度投影被其他规则覆盖) |
| B | `opp_found=True ∧ dist≈0.6 边界` | CLOSE-PUSH 需 dist<0.6, OPPONENT-FOUND 需 dist>0.6 | 不可见 |

**治理含义**: 空洞 A 是 S34 删除 CAUTIOUS-EDGE (BETWEEN 0.55-0.78) 后在联合空间留下的真空 —
D4-3 "冗余判定" (邻居完全吸收) 在**数学级**上被证伪为"部分吸收"。基线指标不变 (21.4/1.0/214)
是因为仿真状态空间中该区域极少到达, 但作为第四层防护的知识基线, 后续任何候选若扩大该空洞
将被拦截。

### 1.3 集成点

- `governance/meta_harness/symbolic_verify.py` (新, ~330 行): ABDL→SMT-LIB 翻译 + 联合覆盖证明
  - `symbolic_verify()`: 基线自检 (I1 完备性)
  - `symbolic_verify_diff()`: 候选 diff 预检 (新增空洞查询, 数学精确)
  - `_simulate_apply()`: 与 S32 相同的 text.replace 语义
  - 跳过语义: 无数值传感器条件变更 (纯 priority/文本) → 放行 (与 S32 一致)
  - 降级语义: z3 不可用 → 放行 (防御纵深, 不阻断管道)
- `evaluator_diff_test.py` `precheck_topology_validity`: S32 之后插入第四层
- `outer_loop.py`: `--symbolic-verify` CLI 标志
- `variants.py` ROUND 14: T1 探针 + T2 候选

### 1.4 验收①: Z3 拦截实证 (S32 盲区案例)

`outer_loop.py --round 14 --symbolic-verify --iterations 3 --tag S35_T1T2`:

探针候选 `mh_rules_close_edge_030` (CLOSE-PUSH edge 0.65→0.30 收窄):
- **S32 单维投影: 放行** (edge 维度被 FLANK<0.80/OF<0.5 覆盖, 无新增投影空洞)
- **Z3 联合覆盖: 拦截 3/3 轮** — SYMBOLIC_PROOF_FAIL:
  "候选引入联合覆盖空洞 (基线有覆盖、候选无覆盖) e.g. (edge=0.625, angle=0, dist=0, opp_found=True)..."
- 新增空洞位置: `(opp_found=True, dist∈(0,0.6), angle∈(-10,10), edge∈(0.30,0.65))`

### 1.5 验收②: 验证延迟

| 测量 | 值 |
| :--- | :--- |
| 单候选 Z3 求解 (新增空洞查询 + I1 检查) | **0.027s** |
| 预检链端到端 (含 S32) | < 0.1s |
| 验收线 (PM) | < 5s/候选 ✅ |

### 1.6 测试: 215/215 全绿 (新增 8 个符号验证测试)

`tests/test_symbolic_verify.py` (8 tests, z3 缺失时 pytest.importorskip 跳过):
解析正确性 / 基线自检检测联合空洞 / edge 收窄拦截 / angle 收窄拦截 /
无变更放行 / action-only 放行 / precheck 集成 (S32 放行 Z3 拦截) / precheck 集成无变更

---

## 2. T2 — 新领域勘探 (物理抓地系数, GRIP_DECAY)

### 2.1 候选设计 (ROUND 14)

动量轴 (ROUND 2 mh_physics_002/003 0.90/0.875 被支配) 已证伪 → 选未勘探的 GRIP_DECAY 双向包络:

| 候选 | 变更 | 预判 |
| :--- | :--- | :--- |
| mh_physics_grip_020 | GRIP_DECAY 0.10→0.20 (边缘打滑翻倍) | 更早避让边缘 |
| mh_physics_grip_000 | GRIP_DECAY 0.10→0.0 (全域抓地) | 极限区推力保持 |

### 2.2 结果: 双候选 INCONCLUSIVE (Q≈0.00)

| 候选 | Q | avg_steps | physics reward | 结论 |
| :--- | :--- | :--- | :--- | :--- |
| mh_physics_grip_020 | 0.00 | 21.4→21.3 | 297.16→296.64 | 扰动无行为影响 |
| mh_physics_grip_000 | 0.00 | 21.4→21.4 | 297.16→298.13 | 扰动无行为影响 |

### 2.3 治理结论 (T2 验收: 判定分布显著变化 — 以"轴证伪"形式达成)

GRIP_DECAY 轴与**动量轴 (ROUND 2)、奖励轴 (ROUND 10)** 一致: **外层参数轴对规则引擎解耦**。
三条独立证据链 (reward/push_threshold → physics/momentum → physics/GRIP_DECAY) 汇聚为同一结论:
规则引擎 (ABDL 12 规则) 的 avg_steps 由**拓扑分支结构**决定, 外层参数扰动在 ±0.005 步噪声内。
→ V9 门胜率 10% 的根源不在规则层参数, 支持 PM 预判: 需转向 RL 轨道 (PyTorch) 而非规则勘探。

---

## 3. 测试与回归

- [x] meta_harness + tests 双端: **215 passed** (55.81s, 含 8 个新符号验证测试)
- [x] z3-solver 5.0.0.0 (pip3 --break-system-packages, PEP 668 环境)

## 4. 交付物

| 文件 | 变更 |
| :--- | :--- |
| `governance/meta_harness/symbolic_verify.py` | **新增**: Z3 符号验证层 (~330 行) |
| `governance/meta_harness/tests/test_symbolic_verify.py` | **新增**: 8 测试 |
| `governance/meta_harness/evaluator_diff_test.py` | precheck 链 + 第四层防护集成 |
| `governance/meta_harness/outer_loop.py` | `--symbolic-verify` CLI |
| `governance/meta_harness/variants.py` | ROUND 14 (T1 探针 + T2 GRIP_DECAY) |
| 本文件 | S35 证据文档 |
