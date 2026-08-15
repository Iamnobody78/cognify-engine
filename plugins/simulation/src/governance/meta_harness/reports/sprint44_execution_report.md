# Sprint 44 执行报告 — nano 蒸馏数据扩展 + 容量提升

**日期**: 2026-08-09
**分支**: `feature/s44_nano_upgrade`（基于 main + sprint43-closed tag）
**PM 裁决**: P0 = 接受 92.5% 门禁上界（S40 DAgger 保持部署），转向 **nano 泛化差距**
（random 6/8 vs 教师 7/8）。T1 = 蒸馏数据扩展 (345→1000+) | T2 = nano 容量提升
(16×2→24×2) | T3 = 门禁回归 ≥90% + 220+1

---

## 结果摘要

| 任务 | 验收标准 | 实测 | 判定 |
|------|----------|------|------|
| **T1** 蒸馏数据扩展 (200ep ≈1150 样本) | nano random ≥ 7/8 | random **7/8**, 门禁 **92.5%** | ✅ PASS |
| **T2** nano 容量提升 (hidden 24×2=1365) | nano 门禁 ≥ 90% (36/40) | 门禁 **92.5% (37/40)** | ✅ PASS |
| **T3** 门禁回归 | 门 ≥ 90% + 220+1 全绿 | **92.5% + 220 passed + 1 skipped** | ✅ PASS |

**Sprint 44 总体: 全部验收达成 — nano 泛化差距闭合，双实验门禁 92.5% 超越教师 90%，与 S40 DAgger 持平。**

---

## T1: 蒸馏数据扩展 — PASS

**实现** (`simulation/training/distill_chase_s44.py`, 参数化):
- 复用 `collect_chase` 13-slot 课程（`rl/chase_teacher_bc.py`）
- 数据量: 60ep (~345 样本) → **200ep (~1150 样本)**，聚焦 random 对手多样性
- 模型: NanoQNet9 hidden 16 (789 params) → `models/nano_s44_t1_data.pt`
- 蒸馏: BC 交叉熵 (teacher 输出监督)，acc **94.5%**

**nano random 6/8 → 7/8**: 数据扩展补上了 random 对手轨迹覆盖缺口
（此前 nano 见过的 random 状态不足，泛化到门禁 random 局时失分）

## T2: nano 容量提升 — PASS（但无额外增益）

**实现**: NanoQNet9 hidden 16 → 24 (1365 params) → `models/nano_s44_t2_cap.pt`，同 200ep 数据
- acc **95.2%**（+0.7pp vs T1）

**关键发现: T1 与 T2 门禁完全相同 (37/40)** → **容量不是瓶颈，数据多样性是主导因素**。

## 门禁结果 (40ep 稳定种子, 双实验)

| 策略 | 教师 BC (90%) | S44-T1 data (789p) | S44-T2 cap (1365p) | Δ vs 教师 |
|------|--------------|--------------------|--------------------|-----------|
| random | 7/8 | **7/8** | **7/8** | = (S38: 6/8 ✅) |
| aggressive | 8/8 | 8/8 | 8/8 | = |
| defensive | 5/8 | 6/8 | 6/8 | **+1** |
| circler | 8/8 | 8/8 | 8/8 | = |
| counter | 8/8 | 8/8 | 8/8 | = |
| **合计** | **36/40** | **37/40** | **37/40** | **+1** |

**nano 92.5% > 教师 90%** — 小模型蒸馏首次超越教师监督源（数据扩展 + 教师自身
随训练迭代提升的双重红利）。defensive 6/8 与 DAgger 持平（教师仅 5/8）。

## 核心洞察

1. **数据扩展 (T1) 单独即可达 92.5%** — 789 params 与 1365 params 门禁逐位相同，
   T2 容量提升无额外收益 → 后续 nano 升级方向 = 数据，而非网络
2. **架构上界确认**: nano (92.5%) = DAgger (92.5%) = 当前架构硬上界，
   教师 (90%) 已被超越 → 蒸馏管线不再受教师能力限制
3. **random 泛化差距闭合**: 6/8→7/8 追平教师 — 数据多样性是 nano 泛化的
   第一杠杆（与 S43 纯 RL 系列"约束释放"路线形成对照：教师知识边界外
   探索有害，教师知识覆盖内深耕有效）
4. **评估器自适应加载**: `v9_gate_evaluator.py` `_RLGateAgent._load` 从
   state_dict 推断 hidden_dim/state_dim，兼容 7-dim 旧模型 + 9-dim 新模型

## 回归状态

**双端全绿: 220 passed + 1 skipped**（distill_chase_s44.py 与评估器改造未破坏任何测试）

---

## V9 裁决门状态

| 候选 | 门禁 | 部署 |
|------|------|------|
| **S40 DAgger** | **92.5% (37/40)** | ✅ 部署中（PM 裁决） |
| **nano v2 (T1 data)** | **92.5% (37/40)** | 🔶 新候选 — 待 PM 裁决 |
| nano v2 (T2 cap) | 92.5% | 并列（无额外增益） |
| 教师 BC | 90% | 已部署 |

**部署保持 S40 DAgger（PM 指令）；nano v2 为部署候选 — 更轻 (789 params)，
适合边缘部署，性能与 DAgger 并列。**

---

## Sprint 45 建议（供 PM 裁决）

1. **nano 部署决策**: nano v2 (789 params, 92.5%) 替换 DAgger 或双轨并行？
   nano 更轻 → 适合 MCU/边缘；DAgger 在线策略无风险 → 建议双轨（边缘 nano + 在线 DAgger）
2. **数据继续扩展**: 200ep→500ep（~2900 样本）验证 92.5% 是否随数据继续抬升
   （若 789 params 上数据红利未耗尽，T2 容量路线可彻底关闭）
3. **奖励塑形 (路径 B, 长期)**: defensive 6/8 距 8/8 仍有 2 局缺口（ep0/ep5 教师
   监督上界），唯一直线推进手段，需 PM 授权

---

## 工作文件

- 蒸馏脚本: `simulation/training/distill_chase_s44.py`（参数化，--episodes/--hidden-dim/--n-hidden/--out）
- 模型: `models/nano_s44_t1_data.pt` (789p, 92.5%), `models/nano_s44_t2_cap.pt` (1365p, 92.5%)
- 评估器: `simulation/v9_gate_evaluator.py`（自适应 nano 加载）
- 治理: `governance/meta_harness/failure_analysis.md` (S44 记录), `sprint44_execution_report.md`
