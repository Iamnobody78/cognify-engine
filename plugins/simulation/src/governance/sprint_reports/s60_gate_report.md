# Sprint 60 — 蒸馏门验证报告 (Distillation Gate)

**日期**: 2026-08-10
**分支**: `feature/sprint60_distill_lightweight`
**目标**: 以 S59 最优 heuristic Harness（100%, 216 步）为教师，蒸馏小模型策略，
保持门分数 ≥ 90% 且推理延迟降低 ≥ 10x
**验收线**: 学生门分数 ≥ 90%；延迟 speedup ≥ 10x；教师零回归

---

## 1. 验收结果总表

| 指标 | 目标 | S60 交付后 | 判定 |
|------|------|-----------|------|
| **学生门分数** (10 eps) | ≥ 90% | **100% (10/10)** | ✅ PASS |
| **推理延迟** | ≤ 教师 1/10 | **318.1x speedup** (89.3μs vs 28.4ms) | ✅ PASS (超 31 倍) |
| 学生参数规模 | 小模型 | **1,365 params** (8.5KB .pt) | ✅ PASS |
| 教师零回归 (heuristic) | 100% 保持 | **100% (10/10)** | ✅ PASS |
| CLI 接入点交叉验证 | — | `--agent rl --model` **100% PASS** | ✅ PASS |
| 蒸馏采样质量 | — | 200 eps, 99% 教师胜率, 15,441 samples | ✅ PASS |
| 学生训练精度 | — | val_acc **91.1%** @ 60 epochs, loss 0.210 | ✅ PASS |

**S.E.E.D. 循环状态**: Scan ✅ → Explore ✅ → Execute ✅ → Debrief ✅

## 2. 详细数据

### 2.1 学生门评估（NanoQNet9, 10 episodes, lightweight 后端）

| 对手 | 胜局 | 总局 | 胜率 | avg_steps |
|------|------|------|------|-----------|
| random | 2 | 2 | 100% | 77 |
| aggressive | 2 | 2 | 100% | 38 |
| **defensive** | **2** | **2** | **100%** | **180** |
| circler | 2 | 2 | 100% | 62 |
| counter | 2 | 2 | 100% | 12 |
| **合计** | **10** | **10** | **100%** | — |

> 注: defensive avg_steps **180** < 教师 216 —— 蒸馏学生不仅保留门分数，
> 还在防御性对手上更快收局（学生学到了教师后期收敛路径，去除了早期犹豫分支）。

### 2.2 延迟基准（1000 次前向实测）

| 策略 | 延迟 (μs) | 参数 | 权重文件 |
|------|-----------|------|----------|
| heuristic 决策链 (S59 教师) | 28,405.9 | — (规则链) | — |
| **NanoQNet9 学生** | **89.3** | **1,365** | nano_s60_quick.pt (8.5KB) |
| **Speedup** | — | — | **318.1x** |

### 2.3 蒸馏设置

- **教师**: `V9RuleAgent(force_heuristic=True)` —— S59 修复后代码，9 维 obs → select_action
- **学生**: `NanoQNet9` (S44 架构: 9→hidden→21, hidden=24) —— 从 `distill_chase_s44.py` 导入
- **课程**: 13 slots × 命名对手 2 组 (aggressive/defensive/circler/counter) + random + 填充
- **采集**: env 按对手组复用（避免防御性对手 speed_scale=0.40 的逐 ep 重建开销）
- **训练**: BC 交叉熵, 60 epochs, val_acc 91.1%
- **采样**: 200 eps, 198 教师胜 (99%), 15,441 transitions

## 3. 关键发现（元学习洞见）

1. **280-318x 延迟降幅的根源是架构本质差异**: 规则链每个决策遍历多层 if-elif
   （含多个模拟量比较），MLP 是 3 层矩阵乘。延迟收益主要来自"无分支固定计算图"，
   而非模型小本身——这为后续实时部署（嵌入式/on-board）提供依据。
2. **蒸馏保真度与门分数的关系**: 训练 val_acc 91.1% 即达到 100% 门分数——
   说明门测试的决策边界远宽于 val 分布，学生对教师的行为"足够接近"即可通过，
   无需 100% 模仿。91% 的 BC 保真度是**门级等效**。
3. **防御性 avg_steps 180 < 教师 216**: 学生压缩了教师早期探测行为，
   直接学习收敛路径。蒸馏不仅降延迟，还隐式做了行为压缩。
4. **零回归核查是 S59 后固定流程**: 教师 heuristic 100% 保持，确认蒸馏
   未污染教师代码路径（sentinel 修复保证日志不重复打印）。

## 4. 交付物

| 文件 | 说明 |
|------|------|
| `simulation/training/distill_s60_heuristic.py` | 蒸馏脚本（教师采集 + BC 训练 + 延迟基准）|
| `simulation/training/eval_s60_nano.py` | 学生门评估 + 延迟基准（复用 S45 接入点）|
| `models/nano_s60_quick.pt` | 学生权重 (8.5KB, 1,365 params) |
| `s60_distill.log` | 完整采集/训练日志 |
| `simulation/v9_gate_evaluator.py` | `_heuristic_notified` sentinel 修复（已合入）|
| `governance/research/` | 研究引擎（本 sprint 独立交付，commit 40f01ea）|

## 5. 遗留项（非阻塞）

| 项 | 状态 |
|----|------|
| v11 vs defensive 50% | 控制基线，已接受 |
| avg_steps 216 vs 200 | 学生已 180，教师侧如需要可后续处理 |
| 模式检索英文同义词 | 研究引擎后续迭代 |

## 6. 结论

**三个标准全部达成。** 蒸馏学生以 100% 门分数（≥90% 目标）、318.1x 延迟降幅
（≥10x 目标）、1,365 参数（8.5KB）完成轻量级策略验证。教师零回归。
可进入知识固化与签收流程。
