# Sprint 41 执行报告 — defensive 定向提升 + lambda 退火

**日期**: 2026-08-09
**分支**: `feature/s41_defensive_dagger`（基于 main + sprint40-closed tag）
**PM 裁决**: P0 = defensive 定向提升 (6/8→8/8) | P1 = lambda 退火 (1.0→0.2) | β 窗口延长延后

---

## 结果摘要

| 任务 | 验收标准 | 实测 | 判定 |
|------|----------|------|------|
| **T1** defensive 定向提升 | defensive 8/8 + 门禁 ≥ 92.5% | defensive 5/8, 门禁 90% | ❌ FAIL |
| **T2** lambda 退火 | 门禁 ≥ 92.5% + 防御无退化 | 门禁 87.5%, random 退化 | ❌ FAIL |
| **T3** 回归验证 | 门 ≥ 92.5% + 220+1 全绿 | 220 passed + 1 skipped | ✅ (回归部分) |

**Sprint 41 总体: T1/T2 均未达验收 → defensive 困难局突破需新路径。S40 DAgger (92.5%) 保持部署最优。**

---

## T1: defensive 采样加权 (Exp-A) — FAIL

**实现**: `finetune_dqn_s41.py`（S40 参数化扩展）`--defensive-weight 4`（课程池 defensive 2→4 slots）+ lambda 固定 1.0，1000ep 训练。

**门禁结果**:

| 策略 | S40 DAgger | Exp-A | Δ |
|------|-----------|-------|---|
| random | 7/8 | 7/8 | = |
| aggressive | 8/8 | 8/8 | = |
| **defensive** | **6/8** | **5/8** | **-1** |
| circler | 8/8 | 8/8 | = |
| counter | 8/8 | 8/8 | = |
| **合计** | **92.5%** | **90%** | **-2.5pp** |

**矛盾现象**: 训练内 defensive 3/6→4/6（提升 ✅）但门禁 defensive 5/8（反降 ❌）
- 训练内 6 局与门禁 8 局的种子集不同 → 训练内 4/6 的 2 失败局 ≠ 门禁的 3 失败局
- ep0/ep5 仍是教师同款失败（{15:12,19:12} 纯左转 / {20:24} 纯右转），ep7 新增失败
- **根因**: 加权只增加 exposure，无法改变 dagger_buffer CE 监督**复制教师失败模式**的本质 —— ep0/ep5 是教师 5/8 也输的困难局（教师监督上界）

## T2: lambda 退火 (Exp-B) — FAIL

**实现**: `--lambda-decay 0.2`（dagger_lambda 1.0→0.2 线性退火，与 β 同步）+ defensive-weight 2，1000ep。

**门禁结果**: **87.5% (35/40)**，random 6/8 退化（S40: 7/8）
- 训练曲线: 早期 83.3% → 后期 **63.3%**（退火后期失去教师约束，自主探索失控）
- `.best` (83.3%) 高于 final (63.3%) → 退火后期明确破坏
- **根因**: 1.0→0.2 释放自主探索过猛。DAgger 的 dagger_lambda 是"技能保持"的锚，
  退火太快导致 Q 值漂移重现（FP-RL-005 残余）

---

## 核心洞察: 教师监督上界 (90%)

- ep0/ep5 是**稳定种子协议下的教师级困难局**（教师 5/8 也输）
- DAgger 继承教师失败模式（dagger_buffer CE 监督逐字复制 {15:14,19:11} / {20:24}）
- 采样加权 + lambda 退火都无法突破 —— 因为**教师自己也不知道怎么赢这两局**

**S42 候选路径**:
1. **纯 RL 阶段**: β 退火后延长完全自主探索（β=0.1 保持更久），让 DQN 用 TD 学习教师不会的 FW_MAX 推进
2. **定向奖励塑形**: defensive 场景对"直线推进接近"给正奖励（修改奖励函数）
3. **接受上界**: S40 DAgger 92.5% 已超教师 90%，defensive 6/8 已是超越

---

## 回归状态

**双端全绿: 220 passed + 1 skipped**（simulation 73 + meta_harness 134 + dashboard 13）— s41 脚本 + 新模型未破坏任何测试。

---

## V9 裁决门状态（不变）

| 候选 | 门禁 | 部署 |
|------|------|------|
| **S40 DAgger (`chase_dqn_dagger_s40.pt`)** | **92.5% (37/40)** | ✅ **部署中 (线上策略)** |
| 教师 BC | 90% (36/40) | 已部署 |
| S41 Exp-A / Exp-B | 90% / 87.5% | ❌ 不部署 |
| nano | 87.5% | 过门 |

**部署保持 S40 DAgger 92.5% 不变。**

---

## 工作文件

- 新增: `simulation/training/finetune_dqn_s41.py`, 模型 `chase_dqn_s41_t1_defw4.pt(+.best)`, `chase_dqn_s41_t2_lam02.pt(+.best)`
- 治理: `governance/meta_harness/failure_analysis.md` (S41 记录), `sprint41_execution_report.md`
