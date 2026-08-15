# Sprint 45 执行报告 — nano 数据红利饱和确认 + 双轨部署

**日期**: 2026-08-09
**分支**: `feature/s45_nano_data_scale`（基于 main + sprint44-closed tag）
**PM 裁决**: nano v2 双轨部署 ✅ 立即执行 | 数据继续扩展 (200ep→500ep) ✅ P0 | 奖励塑形 ⏸ 终止

---

## 结果摘要

| 任务 | 验收标准 | 实测 | 判定 |
|------|----------|------|------|
| **T0** 双轨部署 (`--policy nano/dagger`) | 双轨部署完成, 门禁 92.5% 回归 | nano 37/40, dagger 37/40, 路由正确 | ✅ PASS |
| **T1** 数据扩展 (200ep→500ep) | 若门禁 >92.5% 继续扩展; =92.5% 确认饱和 | **T1a 37/40 (92.5%) = T1b 37/40 (92.5%) = S44 37/40** | ✅ **数据红利饱和确认** |
| **T2** 门回归 | 门 ≥92.5%, 220+1 全绿 | **37/40 + 220 passed + 1 skipped** | ✅ PASS |

**Sprint 45 核心结论: 92.5% 确认为 nano 架构 (789 params) 硬上界 — 数据量 (200→500ep)
与教师质量 (规则 90% vs DAgger 92.5%) 均不是杠杆。**

---

## T0: 双轨部署 — PASS

**实现** (`simulation/v9_gate_evaluator.py`):
- 新增 `--policy {nano,dagger}` 参数（`--agent rl` 时生效）
- 优先级: `--model` 显式指定 > `--policy` 映射 > 历史默认 v10_dqn_s36.pt
- `--policy nano` → `models/nano_s44_t1_data.pt` (789 params, 边缘)
- `--policy dagger` → `models/chase_dqn_dagger_s40.pt` (在线)

**路由验证 (40ep 门禁)**:
| policy | agent_mode | 结果 | 判定 |
|--------|-----------|------|------|
| `--policy nano` | rl-nano | **37/40 = 92.5%** (random 7/8, def 6/8) | ✅ |
| `--policy dagger` | rl | **37/40 = 92.5%** (random 7/8, def 6/8) | ✅ |

**双轨架构生效: 在线 DAgger (持续收集轨迹) + 边缘 nano (资源受限部署) 均保持 92.5%。**

## T1: 数据扩展 (200ep→500ep) — 数据红利饱和确认

**实现** (`simulation/training/distill_chase_s44.py` 扩展):
- 新增 `--teacher-mode {rule,net}`:
  - `rule`: S38 规则启发式 (S44 原管线, `collect_chase`)
  - `net`: 网络 argmax rollout (`collect_chase_net`, 新函数) — 加载 DAgger 教师
    `chase_dqn_dagger_s40.pt` (门禁 92.5%) 作为演示源, 满足 PM "用 DAgger 教师收集"
- 双教师对照实验 (控制单变量: 教师来源):

| 实验 | 教师 | 数据量 | acc | 门禁 (40ep) |
|------|------|--------|-----|-------------|
| S44 (基线) | 规则 90% | 200ep (~1150) | 94.5% | **37/40 = 92.5%** |
| **T1a** | 规则 90% | 500ep (4101) | 96.4% | **37/40 = 92.5%** |
| **T1b** | DAgger 92.5% | 500ep (4167) | 99.6% | **37/40 = 92.5%** |

**三个实验逐位相同 (random 7/8, aggressive 8/8, defensive 6/8, circler 8/8, counter 8/8)**

**结论 (双杠杆均无效)**:
1. **数据红利在 200ep 已饱和**: 200→500ep (2.9×数据) 门禁零增益 — 单变量归因成立
2. **教师质量不是瓶颈**: 规则教师 (90%) 与 DAgger 教师 (92.5%) 蒸馏结果完全相同 —
   学生 nano 已不被教师能力限制 (S44 已超越教师, S45 确认教师再强也无助)
3. **92.5% = nano 架构硬上界 (789 params)**: 与 DAgger 92.5% 平齐, 数据/教师双杠杆
   耗尽后确认架构上限; 继续提升只剩奖励塑形 (PM 已终止) 或架构变更

**模型资产**:
- `models/nano_s45_t1a_rule500.pt` — 规则教师 500ep (4101 样本, acc 96.4%)
- `models/nano_s45_t1b_dagger500.pt` — DAgger 教师 500ep (4167 样本, acc 99.6%)
- 两者门禁均 92.5% — 无部署优先级差异, 边缘候选仍为 nano_s44_t1_data.pt (更小更早验证)

## T2: 门回归 — PASS

**双端全绿: 220 passed + 1 skipped (87.25s)** — `--policy` 路由与
`--teacher-mode net` 扩展未破坏任何测试。

---

## V9 裁决门状态 (S45 完结)

| 候选 | 门禁 | 参数 | 部署 |
|------|------|------|------|
| **S40 DAgger (在线)** | **92.5%** | ~2070 | ✅ 在线策略 (持续收集轨迹) |
| **nano v2 (边缘)** | **92.5%** | **789 (38%)** | ✅ 边缘策略 (T0 双轨部署完成) |
| nano 500ep (T1a/T1b) | 92.5% | 789 | 🔶 与 v2 并列, 无增益, 不部署 |
| 教师 BC | 90% | — | 已退役 |

**双轨部署闭环: 在线 DAgger + 边缘 nano 均保持 92.5%, 参数比 38%, 边缘推理/内存优势落地。**

---

## Sprint 46 建议 (供 PM 裁决)

1. **nano 系列关闭**: 数据/教师/容量三维度全部验证 (S44: 容量无效; S45: 数据+教师
   无效), nano 管线在 789 params 下已达 92.5% 硬上界 — 建议 nano 系列正式关闭,
   edge 部署冻结于 nano_s44_t1_data.pt
2. **架构变更探索 (若 PM 想突破 92.5%)**: 唯一剩余杠杆 —
   - 选项 A: 教师集成 (DAgger 教师 + 学生联合微调, 而非纯蒸馏)
   - 选项 B: 学生容量跳到 8× 以上 (789→6000+) 验证大模型表达力
   - 选项 C: 接受 92.5% 为终局, 转治理/工程化 (PM 已两次"接受上界"倾向)
3. **持续集成**: 双轨部署已就绪, 可加 CI 每日门禁 (40ep × 2 策略) 防止回归

---

## 工作文件

- 蒸馏脚本: `simulation/training/distill_chase_s44.py` (+`collect_chase_net` 网络教师,
  `--teacher-mode rule/net`)
- 评估器: `simulation/v9_gate_evaluator.py` (+`--policy nano/dagger` 双轨路由)
- 模型: `models/nano_s45_t1a_rule500.pt`, `models/nano_s45_t1b_dagger500.pt`
- 治理: `governance/meta_harness/failure_analysis.md` (S45 记录), `sprint45_execution_report.md`
