# Sprint 39 执行报告 — DQN 微调修复 (FP-RL-005) + nano 温度扫描

**日期**: 2026-08-08
**分支**: `feature/s39_dqn_fix`（基于 main + sprint38-closed tag）
**PM 裁决**: P0 = T1 DQN 微调修复 (FP-RL-005) | P1 = T2 nano 温度调优 | Hermes B2 顺延 S40

---

## 结果摘要

| 任务 | 验收标准 | 实测 | 判定 |
|------|----------|------|------|
| **T1** 微调门禁 | ≥90.0% (36/40) | **60.0% (24/40)** | ❌ FAIL |
| T1 双端回归 | 220+1 全绿 | 220 passed + 1 skipped | ✅ PASS |
| **T2** nano 门禁 | ≥87.5% (35/40) | 35/40 (三温度全同) | ✅ PASS（空结果） |
| T2 random 泛化 | ≥ 教师 7/8 | **6/8**（三温度全同） | ❌ FAIL |

**总体裁决: T1 FAIL, T2 门禁达标但泛化差距未闭合（null result）。Sprint 39 未达成全部验收 → FP-RL-005 转入 Sprint 40 继续。**

---

## T1: SkillProtectedAgent 微调 — 详细数据

**实现**（`simulation/training/finetune_dqn_s39.py`, 新增）:
- 冻结 `net.0` (fc1, 32×32+32) 保持 BC 感知表征
- L2 技能保护正则 `skill_lambda=1e-3` 约束可训参数
- 低 epsilon: 0.05 → 0.01 线性衰减（2000 步）
- 13-slot 轮转课程（GATE_BEHAVIORS + defensive scale 0.40）, buffer 20000, batch 64
- BC warm-start: `chase_teacher_bc_s38_v2.pt`（教师 90%）

**训练曲线**（1000ep 后台完成）:
- 训练内最终评估 WR=97.8% (88/90) — **假阳性，不可信**（见协议缺陷）
- 输出模型: `models/chase_dqn_finetune_s39.pt` (2069 params, 架构与教师一致)

**门禁 40ep**（`v9_gate_evaluator --agent rl --model ... --episodes 40 --ci-check`）:

| 策略 | 教师 (90%) | 微调 (60%) | Δ |
|------|-----------|-----------|----|
| random | 7/8 | 6/8 | -1 |
| aggressive | 8/8 | 4/8 | **-4** |
| defensive | 5/8 | 4/8 | -1 |
| circler | 8/8 | 3/8 | **-5** |
| counter | 8/8 | 7/8 | -1 |
| **合计** | **36/40** | **24/40** | **-12** |

**根因: Q 值完全塌缩**
- 微调模型 309/309 决策步动作 = **5 (FW_MAX 全速直冲)**
- 教师动作集 {5, 15, 19, 20} = FW_MAX + FW_LEFT_HARD + FW_LEFT_FAST + FW_RIGHT_FAST（追踪技能：直冲+转向）
- 微调抹除全部转向动作 → 无法追踪 circler（3/8），对 aggressive 对冲劣势（4/8）
- 60% > 40%（FP-RL-005 原态恒定 40%）：SkillProtected 部分缓解，但**未消除塌缩**

**训练内评估协议缺陷（S39 新发现，根因之一）**:
- `finetune_dqn_s39.py` eval_env 固定 `opponent_profile="aggressive"` + 固定种子
- 97.8% 是对单一对手的过拟合指标；门禁混合 5 策略下 aggressive 仅 4/8
- **教训：所有微调/训练脚本的训练内评估必须使用 GATE_BEHAVIORS 混合协议**（5 策略 × 稳定种子），否则误判成功

**架构一致性已验证**: 微调模型 2069 params（net.0/2/4 同教师），门禁 agent_mode="rl" 真实加载非降级，排除错位加载假象。

---

## T2: nano 蒸馏温度扫描 — 详细数据

**实现**: `distill_chase_s38.py` 新增 `--temp` 参数（软目标 KL 蒸馏 `F.kl_div × T²`; temp=0 回退硬标签 CE），`_load_teacher_qnet()` 复用 BC 教师权重。

**三温度蒸馏结果**:

| 模型 | 蒸馏 acc | 门禁 | random 胜率 |
|------|---------|------|------------|
| nano_s39_t050.pt | 94.0% | 35/40 (87.5%) | 6/8 |
| nano_s39_t100.pt | 93.0% | 35/40 (87.5%) | 6/8 |
| nano_s39_t200.pt | 88.5% | 35/40 (87.5%) | 6/8 |

**判定: 门禁 ✓ / 泛化 ✗ / 空结果 (null)**:
- **argmax 表面收敛**: 不同温度 → 不同权重 → 逐动作完全相同的离散策略（35/40 三温度全同，随机 6/8 三温度全同）
- 温度只平滑 soft-target 分布，**不移动 21 离散动作的 argmax 表面** → 对泛化差距无杠杆
- nano 泛化差距（6/8 < 教师 7/8）需别处闭合：数据多样性 / 架构 / 奖励，而非蒸馏温度

---

## 回归状态

**双端全绿**: 220 passed + 1 skipped
- `simulation/tests`: 73 passed
- `governance/meta_harness/tests` + `evaluator_diff_test.py`: 134 passed + 1 skipped
- `governance/dashboard/backend/tests`: 13 passed
- `a1_warmup_test.py` 独立（vision_proxy 模块，非主套件）

注: 需在 `bottlesumo_pi/` 目录内运行 pytest（`simulation` 包相对导入）；从仓库根运行报 ModuleNotFoundError。

---

## V9 裁决门状态

| 候选 | 门禁 | 状态 |
|------|------|------|
| 教师 BC (`chase_teacher_bc_s38_v2.pt`) | 90% (36/40) | ✅ 部署轨道达标 |
| nano (任意温度) | 87.5% (35/40) | ✅ 过门（泛化差距未闭） |
| 微调 DQN (`chase_dqn_finetune_s39.pt`) | 60% (24/40) | ❌ 未过门（非部署候选） |

**部署推荐: 维持教师 BC 直投**（90% 已过门，微调修复未达 90% 前不替换）。

---

## Sprint 40 建议

1. **FP-RL-005 剩余候选路径**（按 PM 技术路径清单）:
   - **DAgger 在线纠正**: 交互式演示纠正保留时序一致追踪行为，正面应对"混合 replay + epsilon 打断数十步一致轨迹"根因
   - per-profile Q 集成: 各策略独立 Q 头
   - 或**维持 BC 直投**（教师 90% 已达标，微调收益未验证）
2. **必改**: 训练内评估协议统一为 GATE_BEHAVIORS 混合（本报告协议缺陷）
3. **T2 归档**: 温度扫描 null 结果入库，泛化差距转向数据/架构方向

---

## 工作文件

- 新增: `simulation/training/finetune_dqn_s39.py`, 模型 `models/chase_dqn_finetune_s39.pt`(+.best), `nano_s39_t{050,100,200}.pt`
- 修改: `simulation/training/distill_chase_s38.py` (--temp), `simulation/training/train.py` (defensive scale 0.40)
- 治理: `governance/meta_harness/failure_analysis.md` (S39 记录)
