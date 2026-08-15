# Sprint 60 — Specification（需求分析）

**目标**: 轻量级蒸馏策略验证 — 以 S59 最优 heuristic（100%，216 步）为教师，
蒸馏 MLP 小模型策略，保持门分数 ≥ 90% 且推理延迟降低 10 倍
**分支**: `feature/sprint60_distill_lightweight`
**日期**: 2026-08-10
**状态**: DRAFT → 待设计评审

---

## 1. 问题陈述与立项背景

PM 立项（Sprint 59 签收后）:
> "用当前最优 heuristic Harness（100%，216 步）作为教师，蒸馏一个 MLP 或小模型
> 策略，目标是保持门分数 ≥ 90% 且推理延迟降低 10 倍。"

动机:
1. **推理成本压缩**: heuristic 是规则链（分支判断 × 多），MLP 是单次前向传播。
   部署到边缘设备（STM32/Cortex-M）时，MLP 的固定延迟可预测且远低于规则链。
2. **数据质量已达上限**: S59 后 heuristic 门分数 100%（10/10），defensive 已修复，
   教师数据质量足够高，蒸馏的上界（teacher ceiling）从 S44 时代的 92.5% 提升到 100%。
3. **S40-S42 DAgger 路线延续**: 历史已验证 92.5% 上界（chase_dqn_dagger_s40），
   但**那些学生模型的教师是旧版规则/网络，不是 S59 升级后的 heuristic**——
   S59 的 TR-004/vectored + edge_f_turn 三层防御未进入任何学生模型。

## 2. 现状盘点（基础设施审计）

| 组件 | 状态 | 说明 |
|------|------|------|
| `NanoQNet9`（S44）| ✅ 可用 | 9→24→24→21 MLP，1365 params，BC 交叉熵训练 |
| `collect_chase`（S37）| ⚠️ 教师过时 | 教师是 `chase_action`（S38 全知追敌启发式），**非** V9 heuristic |
| `collect_chase_net`（S45）| ⚠️ 教师过时 | 教师是 `chase_dqn_dagger_s40.pt`（92.5% 上限时代）|
| `v9_gate_evaluator.py --policy nano` | ✅ 可用 | S45 双轨部署，自动加载 NanoQNet9 权重，obs9→action21 |
| `heuristic_config.yaml`（S59）| ✅ 最新 | 含 shove_dist/charge_dist/edge_f_turn_streak |

**关键差距**: 现存学生模型（nano_s44.pt / nano_v2/v3）的教师均未包含 S59 的
defensive 反冲回避逻辑。S60 必须**用 `V9RuleAgent(force_heuristic=True)`（当前代码，
含 S59 修复）作为教师重新采集**。

## 3. 目标（可量化）

| 指标 | 当前值 | 目标 | 验收判据 |
|------|--------|------|----------|
| 学生门分数 | nano_s44 未知（92.5% 时代）| **≥ 90%** | `--policy nano` 10 局 ≥ 9 胜 |
| 推理延迟 | heuristic 规则链（基线测量）| **≤ 1/10** | 单次 select_action 耗时比 |
| 学生 vs defensive | — | ≥ 50%（不弱于旧学生）| defensive 2 局 ≥ 1 胜 |
| 零回归 | — | heuristic/abdl/v11 不变 | 门分数不下降 |

**范围边界**:
- IN: 新蒸馏脚本（教师 = V9RuleAgent 当前代码）、NanoQNet9 训练、延迟基准
- IN: `--policy nano` 接入验证（S45 已支持，确认即可）
- OUT: 不改 env 物理、不改教师决策、不改 S45 双轨部署架构
- OUT: 不做真机 HIL（本次仅仿真验证）

## 4. 风险与对策

| 风险 | 对策 |
|------|------|
| BC 学生无法复现 streak 类时序逻辑（edge_f_turn 依赖历史帧）| 教师动作在单帧 obs 下大部分可复现；时序分支（streak≥3）占少数，接受概率损失（门评估验证实际影响）|
| defensive 反冲回避（TR-004）需要精确距离阈值 | BC 会学习到近似边界（0.35-0.45），若门评估 defensive 退化则回退到 hidden_dim=24 大模型 |
| 训练数据不足（200ep ≈ 数千样本）| 扩到 400ep；13-slot 课程含 random 2/13 |
| 延迟测量不稳定 | 1000 次 select_action 取中位数，双方同环境 |

## 5. 验收流程

1. 采集教师演示（V9RuleAgent force_heuristic, 400ep, 13-slot 课程）
2. 训练 NanoQNet9（hidden_dim 16/24 两档）→ BC 交叉熵
3. 门评估: `v9_gate_evaluator.py --policy nano --model models/nano_s60.pt` × 10 局
4. 延迟基准: heuristic 规则链 vs MLP 前向（1000 次中位数）
5. 零回归: heuristic/abdl/v11 门分数复核
6. 知识固化: engineering_rules + pattern_library + META-EDU

## 6. 交付物清单

- [ ] `simulation/training/distill_s60_heuristic.py`（新蒸馏脚本）
- [ ] `models/nano_s60.pt`（学生权重）
- [ ] 门回归报告（`s60_gate_report.md`）
- [ ] 延迟基准数据（`s60_latency_report.md`）
- [ ] engineering_rules / pattern_library 更新
- [ ] META-EDU 学习记录
