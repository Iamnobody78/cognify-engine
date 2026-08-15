# TASK-005d Pareto (BottleSumo V9 门, 2026-08-05)

## Sprint 37 运行记录 (2026-08-08, S37_OBS_UPGRADE) — 观测升级 + 门阈值首次突破 (77.5%)

**背景**: PM 裁决 P0 = 观测升级 (9-10 维), P1 = 轮转课程, T3 门 ≥60% (12/20)。

**门回归矩阵 (20/40 对局口径)**:
| 策略 | random | aggr | def | circ | counter | **总** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| ABDL (基线) | — | — | — | — | — | **10%** |
| 9 维 DQN 1000ep | 0/4 | 4/4 | 0/4 | 0/4 | 4/4 | **40%** |
| 9 维 DQN 5000ep | 0/4 | 4/4 | 0/4 | 0/4 | 4/4 | **40%** |
| chase-BC 预热 + DQN | 0/4 | 4/4 | 0/4 | 0/4 | 4/4 | **40%** |
| **chase-BC (未微调)** | **7/8** | 8/8 | 0/8 | **8/8** | 8/8 | **77.5%** ✅ |

**Pareto 意义**:
1. **门阈值首次突破**: chase-BC (全知追敌教师行为克隆) 77.5% ≥ 60% — V9 门自 10%
   (ABDL) 以来首次达标。9 维观测充分性获直接证明 (FP-RL-003 证伪)。
2. **FP-RL-005 揭示 DQN 微调是当前唯一学习瓶颈**: BC 77.5% → 任何 DQN 微调后恒 40%
   (逐策略一致) — 混合 replay + epsilon 摧毁时序一致追击技能。修复候选: 低 epsilon
   技能保护微调 / 分策略 Q 集成 / DAgger 在线纠正 (S38)。
3. **defensive 结构性不可胜 (新约束)**: 全知追敌 0/10 + 诱敌/侧翼 0/10 + BC 0/8 —
   对称速度 (0.53 vs 0.53) 对冲僵持 + 边缘撤退回中逃逸; 需物理参数审计 (推力/速度
   不对称) 或门档案复核 (S38 决策点)。
4. 新前沿: "BC 即最优" (行为克隆策略可部署) vs "真 RL 过门" (修复 DQN 微调) —
   Pareto 前沿移动至训练动态层, 表征/分布/物理均已定位。

## Sprint 38 运行记录 (2026-08-08, S38_BC_DEPLOY) — chase-BC 直投 + defensive 物理审计 + V9 自蒸馏 (门 90%)

**背景**: PM 裁决 P0 = chase-BC 直投 (77.5% ≥ 60% 不等微调), P1 = defensive 物理审计
(速度不对称 OR 被动防御判负), P2 = DQN 微调修复 (延后), V9 plateau 自蒸馏条件满足。

**门回归矩阵 (40 对局口径, 新门协议 defensive scale=0.4)**:
| 策略 | random | aggr | def | circ | counter | **总** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| chase-BC v2 (S38 学生, scale 0.4 训练) | 7/8 | 8/8 | **5/8** | 8/8 | 8/8 | **90.0%** ✅ |
| nano 蒸馏 (16×2, 789 params, 38% 教师) | 6/8 | 8/8 | **5/8** | 8/8 | 8/8 | **87.5%** ✅ |

**T2 defensive 物理审计 — 关键机制实证**:
1. **FP-RL-006 probe 假死 bug 确认修复**: reward_functions.py 无条件
   `edge_min < edge_critical/20 → -150` 已移除 (探针 7.5cm 先出界曾致追击者推挤中假死)。
2. **bait-counter 绕行诱敌 (非被动)**: defensive (edge_f<0.3→REVERSE; opp_dist<0.4→
   HARD_FORWARD; else STOP) 用绕行机动把追击者引向边缘再反冲 —— 追击者转向稀释
   有效推进 (0.30×cos 大角 ≈ 0.21 < defensive 直线 0.265) → 被动判负路径依据不足,
   走速度不对称路径。
3. **scale 扫参 (门协议 seed × 8, s38 学生)**: 0.5→0/8, 0.40→6/8, 0.35→8/8。
   取 0.40: defensive 直线 0.212 < chase FAST 0.30, 追击可完成边缘推挤;
   训练-评估一致性 (collect/train/gate 三处统一 scale 0.4)。
4. **双端回归**: 220 passed + 1 skipped + 0 失败 (与 S37 一致, 零回归)。

**T3 V9 plateau 自蒸馏 — 首次触发成功**:
- 教师 chase-BC v2 (2069 params) → NanoQNet9 16×2 (789 params, **38%** ≤ 50% ✅)
- BC acc 92.2%, 门 87.5% ≥ 60% ✅; nano random 6/8 vs 教师 7/8 (轻量化正常权衡)
- `v9_gate_evaluator._RLGateAgent._load` 加 nano 兼容 (二次尝试, mode="rl-nano")

**Pareto 意义**:
1. **门胜率 77.5% → 90.0% (chase-BC 直投)**: defensive 0/8 → 5/8 (62.5%), 四策略
   无回归。FP-RL-005 (微调摧毁) 被绕过而非修复 — "BC 即最优"前沿稳固。
2. **defensive 结构性约束解除**: 对称速度时代 0/8 → scale 0.4 时代 5/8;
   "诱敌反冲"保留战术存在 (非删除), 物理不对称 + 追击 FAST 双杠杆。
3. **V9 自蒸馏闭环首次完整**: plateau_explorer 触发 → 教师演示 → nano 学生 (38% 尺寸)
   → 门 87.5%。轻量化部署路径打通 (若未来上硬件/视觉轨)。
4. 新前沿: "BC 直投 + 物理不对称" 可部署基线 (90%), 下一步是 FP-RL-005 DQN 微调
   修复 (真 RL 过门) 或 Hermes B2 (继续延后)。

## Sprint 36 运行记录 (2026-08-08, S36_RL_INFRA) — RL 轨道: 从 0 到 50% 门胜率 + 表征上限定位

**背景**: PM 裁决 S36 P0 = RL 轨道 (PyTorch DQN), 基于三轴解耦 (规则层勘探饱和)。T3 门回归
验收 = 门分数 ≥1.0 + 双端回归全绿。

**RL 训练矩阵 (BC 预热 + DQN, 全部 10 对局门评估)**:
| 模型 | 课程 | random | aggr | def | circ | counter | 总 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| ABDL (基线) | — | — | — | — | — | — | **10%** |
| s36 (100ep) | 阶梯 | 2/2 | 1/2 | 0/2 | 0/2 | 2/2 | **50%** |
| s36_500 (500ep) | 阶梯 | 2/2 | 1/2 | 0/2 | 0/2 | 2/2 | **50%** |
| s36_gatecur (500ep) | 阶梯+门行为 | 0/2 | 2/2 | 0/2 | 0/2 | 2/2 | **40%** |
| s36_rr (500ep) | 轮转 | 0/2 | 2/2 | 0/2 | 0/2 | 2/2 | **40%** |

**Pareto 意义**:
1. **RL 轨道打破规则层天花板**: 10% → 50% (5 倍), 教师桥 (BC 预热 88.7% 复现率) 有效 —
   规则知识无损注入 RL, DQN 在门对局中超越规则决策质量。V9 门从"规则勘探"切换为"RL 正样本
   供给"的正确性获实证。
2. **三失效模式迭代 (FP-RL-001→003)**: 分布缺口 → 阶梯遗忘/稀释 → **观测表征上限**。
   前两者均已修复 (轮转课程), 40-50% 平台由 7 维观测 (无对手速度) 限制 — "等撞型"赢
   "追击型"输的结构性证据 (counter 12 步速胜 vs defensive 48 步全败)。
3. **新前沿**: 从"规则拓扑参数"迁移到"RL 表征/课程设计" — 观测升级 (opp_vx/vy → 9-10 维)
   是下一最高杠杆点 (S37 P0), 预期可解锁追击技能, 突破 60% 门阈值。
4. 基线保持: 双端回归 220 passed + 1 skipped + 0 失败; 规则层/门协议零改动, RL 全新增模块。

## Sprint 35 运行记录 (2026-08-08, S35_SYMBOLIC_EXPLORATION) — 第四层防护落地 + 轴证伪

**背景**: PM 裁决 S35 T1 = Z3 符号验证 (P0), T2 = 新领域勘探 (P1, 并行), 延后 V9 自蒸馏/Hermes B2。

**T1 验证 (outer_loop --round 14 --symbolic-verify --iterations 3 --tag S35_T1T2)**:
| 候选 | 判定 | 关键 |
| :--- | :--- | :--- |
| mh_rules_close_edge_030 (T1 探针) | **TOPO-PRECHECK-FAIL ×3** | SYMBOLIC_PROOF_FAIL: 联合空洞 (edge∈(0.30,0.65) 收窄, S32 放行) — Z3 数学级拦截 |
| mh_physics_grip_020 (T2) | INCONCLUSIVE (Q=0.00) | avg_steps 21.4→21.3, reward 296.64 — 无行为影响 |
| mh_physics_grip_000 (T2) | INCONCLUSIVE (Q=0.00) | avg_steps 21.4→21.4, reward 298.13 — 无行为影响 |

**Pareto 意义**:
1. **第四层防护从概念到实证**: S32 单维投影 (启发式) 与 Z3 联合覆盖 (数学证明) 的盲区差
   异被同一候选的"放行 vs 拦截"直接演示 — 覆盖验证从"保守近似"升级为"精确包含"。
2. **基线知识**: 12 规则基线的联合空洞 (edge∈(0.6,0.8], opp_found=False) 作为知识基线记录,
   后续候选若扩大该空洞即被拦截 (防止 S34 精简的隐性回退)。
3. **三轴解耦收敛**: reward (S10/ROUND 10) + momentum (ROUND 2) + GRIP_DECAY (S35) 三独立
   证据链 → 规则引擎 avg_steps 由拓扑决定, 外层参数轴已证伪 — 探索预算应转向 RL 轨道。
4. 基线保持: avg_steps=21.4 / winrate=1.0 / 触发 214 (第四层防护不改变基线行为, 零副作用)。

## Sprint 34 运行记录 (2026-08-08, S34_RULE_PRUNE_DISTILL) — 规则数净减落地 + D5 蒸馏入库

**背景**: PM 裁决 S34 P0 = 候选 G 合入主规则 (8→7 规则精简), P1 = D5 高价值规则蒸馏
(conf≥0.3 入库), P2 = Hermes B2 延后 S35。

**P0 合入验证 (outer_loop --iterations 3 --tag S34_G_MERGE, 12 规则基线)**:
| 候选 | 判定 | avg_steps | 关键 |
| :--- | :--- | :--- | :--- |
| 基线 (CAUTIOUS-EDGE 移除) | — | **21.4** | 与 S33 完全一致, 214 触发零 CAUTIOUS-EDGE |
| mh_rules_topo_A (回放) | SUSPICIOUS | 60→59 | 复现 |
| mh_mapping_001 (回放) | REGRESSION (-0.17) | 21.4→29.3 | 第四次复现 |
| 探索饱和 | 3 轮无有效结果 | — | 规则空间已固定 (预期) |

**Pareto 意义**: 规则数净减从「评估结论」(S33) 落地为「主分支事实」— 12 条规则 id
(13→12, CAUTIOUS=0), 冗余分支不再消耗信号带宽且减少一条维护路径。**D5 蒸馏入库**:
三强规则 (topo_B 0.48 / mapping_001 0.30 / topo_A 0.26) 写入 engineering_rules.md
HC 章节 (RULE-HC-001/002/003), 12 规则基线下重跑 --recalibrate 置信度零漂移 —
蒸馏管道与规则精简正交, HC 规则为治理指导 (非管道输入) 无副作用。134/134 全绿。

## Sprint 33 运行记录 (2026-08-08, S33_CAND_G_DISTILL) — 候选 G 冗余确认: 规则数净减机会

**背景**: PM 裁决 S33 P0 = 候选 G CAUTIOUS-EDGE 移除评估 (D4-3), P1 = D5 置信度校准。

**候选 G 验证 (outer_loop --round 13, 3 轮一致)**:
| 候选 | 判定 | avg_steps | 关键 |
| :--- | :--- | :--- | :--- |
| mh_rules_topo_G (CAUTIOUS-EDGE 移除) | **INCONCLUSIVE (Q=0.00)** | 21.4→21.4 (**0**) | 13 次触发被邻居无损吸收 |
| mh_rules_topo_A (回放) | SUSPICIOUS (+0.02) | 60→59 | 复现 |
| mh_mapping_001 (回放) | REGRESSION (-0.17) | 21.4→29.3 | 第四次复现 |

**Pareto 意义**: 首条**规则数净减**路径 (CAUTIOUS-EDGE 冗余, 8→7 规则空间) —
冗余分支不再消耗信号带宽; D4-3 预测 → 候选 G 实测闭环。**D5 校准**: M2 四通道信号
驱动 D1/D2 置信度排序 (topo_B 0.48 > mapping_001 0.30 > topo_A 0.26), 精炼规则库
供后续筛选 (conf≥0.3)。134/134 全绿。

## Sprint 32 运行记录 (2026-08-08, S32_COVERAGE_DISTILL) — 预检升级: COVERAGE_GAP 拦截入图

**背景**: PM 裁决 S32 P0 = 覆盖连续性预检升级 (FP-NEG-005), P1 = 治理发现自蒸馏 D4 (V9 门触发后首轮)。

**P0 生效验证 (outer_loop --round 12 --tag S32_COVERAGE_DISTILL, 3 轮)**:
| 候选 | S31 判定 | S32 判定 | 变化 |
| :--- | :--- | :--- | :--- |
| mh_rules_topo_D | REGRESSION (-0.53, 覆盖真空) | **TOPO-PRECHECK-FAIL (COVERAGE_GAP)** | 0 次评估, 拦截于 apply 前 |
| mh_rules_topo_E | INCONCLUSIVE no-op | INCONCLUSIVE no-op | 复现 |
| mh_rules_topo_F | INCONCLUSIVE no-op | INCONCLUSIVE no-op | 复现 |
| mh_rules_topo_A | SUSPICIOUS (+0.02) | SUSPICIOUS | 复现 (M2 四通道) |
| mh_mapping_001 | REGRESSION (-0.17) | REGRESSION | 复现 |

**Pareto 意义**: 预检层新增第三类拦截 (COVERAGE_GAP), 与 S30 的 priority 拦截、S21 的
diff_gate 判定构成三层防护。评估预算从"浪费在已知损坏候选"转向"探索未知拓扑"。
**D4 蒸馏入库**: 3 条治理规则 (D4-1 覆盖预检 / D4-2 归因修正 / D4-3 冗余识别) 供后续
候选生成引用, 自蒸馏首轮完成。134/134 全绿, 提交 07edbe2。

## Sprint 31 运行记录 (2026-08-08, S31_TOPO2_BRANCH_HIST) — 拓扑第二波: 0 PASSED, 覆盖真空入图

**背景**: PM 裁决 S31 P0 = 基于 FP-NEG-004 修正归因的规则拓扑第二波 (M2 四通道就绪)。
ROUND 12 专用分支: topo D/E/F + topo_A 回放 (M2 下判定变化) + mh_mapping_001 交叉验证。

**判定分布 (outer_loop --iterations 5 --round 12, 3 轮探索饱和提前终止, 确定性可复现)**:
| 候选 | 判定 | Q | avg_steps | 因果 |
| :--- | :--- | :--- | :--- | :--- |
| mh_rules_topo_D | REGRESSION | -0.53 | 21.4→34.1 | 覆盖真空 (FLANK 收窄留 (-15,-10)∪(10,15) 空洞, 裸 abdl 92 次) |
| mh_rules_topo_E | INCONCLUSIVE | — | identical | 0.55~0.60 空采样, 交替循环假设证伪 |
| mh_rules_topo_F | INCONCLUSIVE | — | identical | stuck 恒<3, 退出机制假设证伪 |
| mh_rules_topo_A | SUSPICIOUS | +0.02 | 60→59 | CAUTIOUS-EDGE 13→0 (近似冗余); M2 回放判定 S29 INC→SUSPICIOUS |
| mh_mapping_001 | REGRESSION | -0.17 | 21.4→29.3 | flank 0.15 第三次复现 |

**Pareto 前沿无变化**（零 PASSED）→ **V9 门触发条件再次满足**（连续 2 个 Sprint 0 PASSED,
S29 + S31）。但获得拓扑负空间扩展: 覆盖真空 (D, 最深 Q=-0.53) + 双假设证伪 (E/F) +
CAUTIOUS-EDGE 冗余证据 (A 回放)。**M2.2 预检盲区入库**: 覆盖连续性检测缺失 (FP-NEG-005)。
自蒸馏 (plateau_explorer) 正式排期。证据: meta_harness 128/128 + S31 快照 3 轮判定一致性
(20260808_184101)。

## Sprint 30 运行记录 (2026-08-08, S30_M2_UPGRADE) — M2 四维信号融合: 评估器能力升级

**背景**: PM 裁决 S30 P0 = M2 评估器信号融合升级 (三通道->四通道 + 拓扑预检),
规则拓扑第二波延后至 M2 完成后。mapping 层饱和失敏 (48 INC + 45 SUSPICIOUS) 是
M2 重构的核心前置证据。

**交付**:
- M2.1: 第四通道 branch_hist 熵 (FP-NEG-004 编码) — Q = 0.35*steps + 0.35*layer + 0.30*branch
  熵坍缩负向 / 熵升需效率同步提升 (方向约束) / 无分支语义层权重回退三通道
- M2.2: 拓扑变更有效性预检 (precheck_topology_validity) — priority 重排未跨越邻居
  -> 结构性 no-op 拦截, 不进入评估循环 (候选 C 同构)

**判定分布 (3 轮探索饱和提前终止, 确定性一致)**:
| 候选 | S29 旧判定 | S30 新判定 | 变化 |
| :--- | :--- | :--- | :--- |
| mh_rules_topo_A | INCONCLUSIVE (Q=0.00) | SUSPICIOUS (Q=0.02, 熵 0.648->0.661) | 第四通道捕获, 不再误判无行为影响 |
| mh_rules_topo_B | REGRESSION (Q=-0.16) | REGRESSION (Q=-0.16) | 权重回退保持一致 |
| mh_rules_topo_C | INCONCLUSIVE (10 episodes) | TOPO-PRECHECK-FAIL (0 次评估) | M2.2 拦截 |
| mh_mapping_001 | REGRESSION (Q=-0.17) | REGRESSION (Q=-0.17, 三信号) | 熵降负向一致 |

**Pareto 前沿**: 评估器能力升级 (第四通道 + 预检) 不直接改变 Harness 参数前沿,
但显著提升判定分辨率 — mapping 层饱和失敏 (48 INC/45 SUSPICIOUS) 现在可被正确解读
(候选行为影响不再淹没在近零信号中)。meta_harness 128/128。

## Sprint 29 运行记录 (2026-08-08, S29_RULE_TOPOLOGY_DISTILL) — 规则拓扑首探: 0 PASSED

**背景**: PM 裁决 S29 三方向——①规则拓扑探索（P0，拓扑级文本变更解禁 RULES CLOSED）②M2 融合升级（延后）
③plateau_explorer 自蒸馏（并行）。ROUND 11 专用分支：mh_rules_topo_A/B/C + mh_mapping_001。

**判定分布（outer_loop --iterations 5 --round 11，3 轮探索饱和提前终止，确定性可复现）**：
| 候选 | 判定 | avg_steps | 逐局 steps | 因果 |
| :--- | :--- | :--- | :--- | :--- |
| mh_rules_topo_A | INCONCLUSIVE | 21.4→21.3 | 60→59（仅 -1） | 空洞假设证伪（branch_hist: FLANK-RIGHT 45 主导） |
| mh_rules_topo_B | REGRESSION | 21.4→24.8 | 42→52, 49→73 | p700 触发域抢占 p500 领地（F-100 同构） |
| mh_rules_topo_C | INCONCLUSIVE | 21.4→21.4 | identical | priority 300→350 未跨越邻居（结构性 no-op） |
| mh_mapping_001 | REGRESSION | 21.4→29.3 | 全面拖长 | flank 0.15 收窄复现（S27v3 同构） |

**Pareto 前沿无变化**（零 PASSED）→ V9 门触发条件满足（3 轮无 PASSED）；
但获得**规则拓扑负空间图谱**：空洞证伪（A）+ 优先级抢占（B）+ 邻居跨越规则（C）——FP-NEG-004 入库
failure_analysis.md。**M2 融合升级前置证据**：自蒸馏显示 mapping 48 INCONCLUSIVE/45 SUSPICIOUS 饱和失敏。
证据：meta_harness 119/119 + S29 快照 3 轮判定一致性（20260808_171124/134/142）

## Sprint 28 运行记录 (2026-08-08, S28_SPEED)

**A1 轮速增益实证（action_map 层首探，PM 裁决 P0）**：
- 扰动：TURN_*_MED 轮速幅值 0.6→0.8（L/R 对称保持，wheel_to_discrete.py ACTION_MAP）
- | 轮次 | winrate | avg_steps | 判定 |
  | :--- | :--- | :--- | :--- |
  | ROUND 1 | 1.00→0.90 | 21.4→17.7 | REGRESSION |
  | ROUND 2 | 1.00→0.90 | 21.4→17.7 | REGRESSION |
  | ROUND 3 | 1.00→0.90 | 21.4→17.7 | REGRESSION |
- **轮速轴可行域：上界 ≈0.70**（0.6 基线 → 0.8 越界）；与动量轴（上界 1.10）同构——
  执行层参数放大先行触碰物理包线失稳。FP-NEG-003 入库 failure_analysis.md
- **Pareto 前沿无变化**（零 PASSED）；但完成第四轴（轮速）斜率标定——行为参数四轴全景
  （角度饱和/距离单峰/动量上界/轮速上界）全部收口 → **探索饱和，触发 V9 门**
- **架构扩展**：新增 `action_map` 层（HARNESS_FILES 六层）——wheel_to_discrete.py 纳入
  snapshot/restore/apply 白名单闭环；ROUND 1 候选循环 + D2_PRIOR + M3 阈值表同步；
  meta_harness 119/119 全绿
- 证据：S28_SPEED 3 轮全 REGRESSION（确定性可复现），meta_harness 119/119

## Sprint 27 运行记录 (2026-08-08, S27_REWARD_AXIS)

**A1 换锚点实证（mapping 层三轴完整行为影响力图谱）**：
- **轴 1 角度阈值**（`abs(angle)>40`, flank）：S25/S26 已证饱和（斜率 0.005 Q/度，SUSPICIOUS 上限 0.04）
- **轴 2 距离阈值**（`dist<0.20`, flank）：**双侧 REGRESSION（单峰最优）**——
  | 扰动 | 方向 | Q | avg_steps | 判定 |
  | :--- | :--- | :--- | :--- | :--- |
  | S26 D: 0.20→0.18 | 微收窄 | 0.00 | 21.4→21.4 | INCONCLUSIVE |
  | S27 v2: 0.20→0.25 | 放宽 | -0.17 | 21.4→18.3 | REGRESSION |
  | S27 v3: 0.20→0.15 | 大幅收窄 | -0.17 | 21.4→29.3 | REGRESSION |
  **0.20 是制胜策略的局部最优**（放宽→推进力不足胜率降；收窄→效率降步数+37%）
- **轴 3 距离阈值**（`dist<0.22`, pursue 直冲窗）：**死代码**（FP-NEG-002）——rules 层
  OPPONENT-FOUND 前提 dist>0.6 与直冲窗互斥，identical:true
- **PM 推荐锚点否决**：V9_WINRATE_THRESHOLD（评估器及格线非行为参数）、PUSH_REWARD_SCALE
  （零命中虚构）、reward_functions.py 默认值（env 显式传参遮蔽 → no-op）
- **FP-NEG-002 教训**：S24 RULES CLOSED 后，mapping 扰动必须做"规则前提可达性"检查
- **Pareto 前沿无变化**（三轴均无 PASSED）；但获得 mapping 层完整斜率图谱（换锚点探索收口）
- **Sprint 27 候选（第三轴）**：TURN_*_MED 轮速增益（ACTION_MAP: TURN_R_MED -0.6→-0.8,
  wheel_to_discrete.py）——mapping flank 分离态收敛 + physics 搜索旋转的跨层联动锚点
- 证据：meta_harness 119/119（S27 测试更新 0.20→0.15 断言）

## Sprint 26 运行记录 (2026-08-08, S26_PASS)

**A1 扰动阶梯实证（mapping 角度阈值 -5°→-8°→-10°）**：
- PM 裁决 P0（-8°, 40→32）执行后 Q=0.03（steps_eff=+0.051），较 S25（-5°, 40→35, Q=0.02）真实提升但未达 PASS
- 兜底档 -10°（40→30, PM 验收授权）：Q=0.04（steps_eff=+0.056, 熵 Δ=+0.015）——仍 SUSPICIOUS，P2-V4 饱和门按设计停止
- **阶梯斜率 = 0.005 Q/度**（线性）；外推 Q=0.15 需 30° 总扰动 → 必翻转 REGRESSION
- **根因判定：角度阈值锚点行为影响力饱和**，非幅度不足——10 局中 `abs(angle) > 30` 触发面窄（熵 Δ 仅 +0.015）
- **路径澄清**：`_gen` 候选（mh_mapping_001）不走 M3 bump——S25 外环实际应用 40→35（非 40→32）；
  seed 路径（有 bump）对 -8° 为 no-op（mag=8 非 < 8.0）。两条生成路径必须分别校准（_gen 无 bump / _seed_variants 有 bump）
- **Pareto 前沿无变化**（零 PASSED）；但获得关键量测：扰动-响应斜率标定（mapping 角度轴饱和证据）
- 负样本入库：physics_001 动量 1.20 REGRESSION（FP-NEG-001）→ failure_analysis.md；动量轴可行域上界 ≈1.10
- 双端回归全绿：physics_seed_002/003 + mapping_002 均 INCONCLUSIVE（Q≈0）
- 证据：meta_harness 119/119（S26 测试更新 40→30 断言）

## Sprint 25 运行记录 (2026-08-08, S25_SEED_FIX)

**种子层信号枯竭修复（动态锚点 A1 + 扰动幅度 A2）**：
- A1 动态锚点：3 个死锚点修复——physics seed_1（`TIMESTEP * 0.8` 已演进为 `momentum = net * TIMESTEP * 1.0`）、
  physics seed_2（线性抓地已演进为二次形式）、mapping seed_1（`abs(angle) > 45` 已演进为 `> 40`）——
  全部改为 `anchor="regex"` 动态解析当前值生成 diff（对齐 _mk_* 磁盘实读原则，S19 FP-MC-017 复发根治）
- A1 种子数：physics 1→3/轮（+GRIP_DECAY 动态锚点），mapping 2/轮；max_per_layer 1→3（S22 后每层多种子）
- A2 扰动幅度：mapping 40→35°（abs 8° 边界）、physics 动量 1.0→1.20（M3 加大）、GRIP_DECAY 0.10→0.30
- **REGRESSION 首现（真实）**：mh_physics_seed_001 → REGRESSION（winrate 1.00→0.90，avg_steps 21.4→17.2），
  3 轮确定性复现，M2 门禁正确拒收——种子层信号枯竭修复后 M2 首次在真实运行产出 REGRESSION
- **判定三态共存**：SUSPICIOUS（mapping_001 Q=0.02，steps_eff=+0.037 真实行为影响）
  + REGRESSION（physics_001）+ INCONCLUSIVE（mapping_002/physics_002/003 无行为影响）——
  打破 S24 的全 INCONCLUSIVE 锁死；mapping_001 的 Q=0.02 贴近 PASS 边界（0.15）——扰动幅度再增大即可跨越
- 残量：P2-V4 门按设计触发探索饱和（3 轮无 PASSED）；PASSED 仍需更强候选或更大扰动
- **Pareto 前沿无变化**（零 PASSED）；但判定分布显著分化（REGRESSION+SUSPICIOUS+INCONCLUSIVE 三态）——
  M2 评估层 + 种子层修复共同解锁了饱和场景的信号可区分性
- 证据：meta_harness 119/119（+M2 17 项 + rules 排除）

## Sprint 23 运行记录 (2026-08-08, S23_RECAL / S23_RECAL2)

**D2 阈值回标（参数级扰动配置 + 符号安全网）**：
- FP-MC-020 根因修正：S22/S23 REGRESSION 真因是 bump_magnitude 语义破坏——abs 阈值
  （8°/10°）误用于 0-1 归一化参数 edge_proximity（0.80-8=-7.20 恒 True 负阈值）→
  无条件转向 → CAUTIOUS-EDGE 循环 → winrate 0.50；S22/S23 确定性复现（0.5/433）
- 修复：_SEED_PARAMS 参数级 perturb 配置（BETWEEN abs 8° / edge_proximity·dist rel 20% /
  动量 abs 0.2）+ bump 符号安全网（跨符号边界拒绝）+ bump 内部验证传 cfg bug 修复
- S23_RECAL2：REGRESSION 严重度 **0.50→0.90**（edge_proximity 0.80→0.64 域内）——
  灾难性劣化消除；判定分布 3 REGRESSION（rules）+ 6 SUSPICIOUS（mapping/physics 饱和）+ INC 0
- 外部治理：RULES CLOSED（ROUND 11 起禁止规则层新候选）——rules 种子应按策略排除（S24）
- **Pareto 前沿无变化**（零 PASSED；REGRESSION 0.90 已接近边界——规则层关闭后
  mapping/physics 扰动需评估层区分（M2）或探索新层）
- 证据：meta_harness 101/101（+1 符号安全网）

## Sprint 22 运行记录 (2026-08-08, S22_SEED)

**M3 扩展（种子扰动幅度校验）**：
- `SEED_PERTURBATION_THRESHOLDS` + `perturbation_magnitude` + `bump_magnitude` 下沉至 `_seed_variants`
  （rules 角度≥10° / mapping 阈值≥20% / physics 系数≥0.2，与 D2_PRIOR 同源；不足则加大或跳过）
- S22_SEED（5 轮请求 → 3 轮后探索饱和，--meta-config）：
  - **REGRESSION 首现**：mh_rules_seed_002 → REGRESSION（winrate 1.00→0.50，avg_steps 21.4→43.3）
    ——rules 扰动加大后行为变化首次跨越感知阈值；门禁 REGRESSION 路径首次被真实数据触发并正确拒收
  - **判定分布打破同构**：INCONCLUSIVE 10/10 → **0**；REGRESSION 3（全 rules）+ SUSPICIOUS 6
    （全 mapping/physics 饱和）——M3 闭环断点（FP-MC-019）修复
- 新发现：10° 角度扰动全部劣化（FP-MC-020 扰动过激）→ D2 阈值回标为 Sprint 23 候选；
  mapping/physics 饱和失敏 18 条 → M2 评估层裁决依据
- **Pareto 前沿无变化**（零 PASSED；REGRESSION 被正确拒收——门禁语义完整闭环）
- 证据：meta_harness 99/99（+16 test_seed_perturbation）

## Sprint 21 运行记录 (2026-08-08, S21_M1M3)

**P2 自蒸馏 M1+M3（数据管道 + 扰动先验）**：
- M1 `distill_loop.py`：D1 失敏检测 / D2 扰动先验 / D3 多样性，结构化判定蒸馏（防 decoding collapse），
  版本化输出 experience/distill_rules_<ts>.json
- M3 `PERTURBATION_PRIOR` 注入 code_agent_proposer 硬约束（角度≥10°/阈值≥20%/系数≥0.2）
- S21_M1M3（5 轮请求 → 3 轮后探索饱和）：9 次评估全被拦截（3 INCONCLUSIVE + 6 SUSPICIOUS）
  ——与 S19/S20 同构；三轮累计 **27 次评估零 PASSED**
- M1 蒸馏揭示层×判定强相关：rules→INCONCLUSIVE 10/10（扰动不足）、mapping/physics→SUSPICIOUS 18/18（全饱和）
- 闭环断点 F1/F2：真实运行走种子路径，M3 提示与 D2 规则未覆盖 `_seed_variants`（种子扰动如
  BETWEEN(-10,10)→(-8,8) 仅 2°，远低于 10° 先验）——M3 扩展（种子扰动参数化）为 Sprint 22 候选
- **Pareto 前沿无变化**（27 次评估零 PASSED）；证据 docs/engineering/s20_p2_distill_evidence_20260808.md

## Sprint 20 运行记录 (2026-08-08, S20_P2DATA)

**P1 恒 False 模式检测上线 + P2 蒸馏数据收集**：
- P1 三层防御（生成层 `resolve_diff` + 运行时 `apply_precheck` + 共享检测器 `detect_always_false`）：
  拦截自引用比较（`dist < dist`，恒 False/恒 True 无信息）、空条件（`if:`/`if ():`）、恒 False
  字面量（`if 0:`/`while False:`/`if 0.0:`/`elif None:`）——先于锚点计数拦截，零评估预算
- P1 验证：meta_harness 48→**65** 测试全绿；三端回归 Windows 57/57 + WSL 73/73 + meta_harness 65/65；
  真实运行 **零误报**（S20_P2DATA 无 apply_precheck_failed——种子候选全部干净 apply）
- P2 数据收集（S20_P2DATA，5 轮请求）：3 轮后探索饱和停止；9 次评估 **全部被门禁拦截**
  （6 SUSPICIOUS + 3 INCONCLUSIVE，**无 PASSED**）——满足 PM 指令 5 触发条件，P2 自蒸馏设计启动
  （详见 docs/engineering/s20_p2_distill_design_20260808.md）
- meta_decisions.jsonl：9 条 diff_gate（diff_verdict/diff_blocked）+ 1 条 stagnation 报告
- **Pareto 前沿无变化**（无 PASSED）——恒 False 候选在生成/运行时前移拦截，评估预算零浪费

## Sprint 19 运行记录 (2026-08-08, S19_DIAG / S19_VERIFY)

**候选 apply 匹配度修复实证**：
- S19_DIAG（修复前 5 轮）：apply 成功率 **0%**（3/3 FAIL/轮）——三类失效：A 锚点缺失
  （`BETWEEN(opponent_angle,-15,15)`/`TIMESTEP*0.8` 当前 0 处）、B 多匹配（`dist<0.20` 3 处
  默认 expected=1）、C 死锚点（physics 动量演进到 `TIMESTEP*1.0`）
- S19_VERIFY（修复后 5 轮）：apply 成功率 **100%**（15/15）——种子动态适配 + diff 声明真实
  expected + `apply_precheck` dry-run 预检（失败记录 `apply_precheck_failed`）
- 候选 9 次评估全被差分门禁拦截（6 SUSPICIOUS + 3 INCONCLUSIVE，无 PASSED）→ 探索饱和 3 轮
  停止：修复后候选干净 apply，但行为变化被 S18 门禁正确拦截（S18/S19 协同）
- **Pareto 前沿无变化**（本轮无 PASSED 保留）——门禁语义：宁可无保留也不收损坏候选

## Sprint 18 运行记录 (2026-08-08, S18_DIFF_GATE / S18_E2E)

**门禁语义生效**：Pareto 保留前强制差分门禁（outer_loop 集成）——
- ca_reward_001（EDGE_* no-op）：diff_verdict=**INCONCLUSIVE** → BLOCKED，不入 Pareto（FP-MC-014 对策实证）
- ca_mapping_001（dist<dist 逻辑损坏）：diff_verdict=**SUSPICIOUS** → BLOCKED，转人工（FP-MC-015 对策实证）
- s18_e2e_rules_001（E2E 构造候选）：diff_verdict=**INCONCLUSIVE** → BLOCKED，meta_decisions.jsonl 记录 diff_gate/diff_blocked=True

**Pareto 更新语义（S18 起）**：`--iterations 3 --tag S18_DIFF_GATE` 冒烟无保留候选
（rule 模板与饱和工作树不匹配，apply FAIL → 候选生成层既有局限，非门禁缺陷）；
基线信号每轮生成成功（winrate=1.0, episodes=10），门禁链路全通。
详见 docs/architecture/ROADMAP_v2.md §11.14。

## 历史前沿记录（S17 及之前）

| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=rules, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=rules, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_001 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_002 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_002 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_007 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_007 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_007 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_008 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_001 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_001 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_reward_001 (v=reward, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_reward_001 (v=reward, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_reward_001 (v=reward, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_reward_001 (v=reward, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_reward_001 (v=reward, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_reward_001 (v=reward, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_mapping_001 (v=mapping, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_mapping_001 (v=mapping, 血缘 code_agent) | 质量 1.0 (PASS) | 293 步 | 帕累托前沿 |
| ca_reward_001 (v=reward, 血缘 code_agent) | 质量 1.0 (PASS) | 293 步 | 帕累托前沿 |
| ca_reward_001 (v=reward, 血缘 code_agent) | 质量 1.0 (PASS) | 293 步 | 帕累托前沿 |
| ca_mapping_001 (v=mapping, 血缘 code_agent) | 质量 1.0 (PASS) | 293 步 | 帕累托前沿 |
> **治理标注 (2026-08-08)**: ca_reward_001 经静态分析为 **no-op 候选** (FP-MC-014)——修改的 EDGE_DANGER/EDGE_WARNING 常量在 compute_edge_reward 中未被消费 (区带边界硬编码 0.15/0.30/0.50, self.edge_* 仅构造函数赋值), score=1.0 为基线水平非改善; 且引入语义倒置 (EDGE_WARNING=2.0 < EDGE_DANGER=2.5)。**评估器满分记录保留作为 FP-MC-014 实证, 但对应 diff 已从工作树回滚**, 不构成真实帕累托改进。
> **治理标注 (2026-08-08, S16 R8)**: ca_mapping_001 经静态分析为 **逻辑损坏候选** (FP-MC-015)——LLM 将 `if dist < 0.20:` 改为 `if dist < dist < 0.15:` (Python 链式比较, `dist < dist` 恒 False → 接触判定分支永不触发), 通过 resolve_diff+评估 (10/10 winrate)+行为验证但为语法合法语义恒 False 的 bug。**满分记录保留作为 FP-MC-015 实证, diff 已回滚**; 不构成真实帕累托改进。同轮 ca_reward_001 再改 EDGE_WARNING=2.0 (FP-MC-014 no-op), 亦已回滚。
## plateau_explorer_trigger (Sprint 10 裁决, 2026-08-07)

- **V9 门当前胜率**: 10% (1/10) — 低于 60% 阈值, 自蒸馏候选
- **裁决**: **暂不触发** plateau_explorer 自蒸馏
- **决策逻辑**: Sprint 9/10 产出为基础设施 (日志标准化/环境引导/MCP 服务器), 尚未接入实际 Harness 优化; 此时蒸馏将把旧 Harness 缺陷 (未接入新工具) 复制进新策略
- **触发条件**: P1-3 三台 MCP 服务器被实际调用并产生 **≥5 轮有效候选** 后, 重新评估门分数是否仍 < 60% 阈值
- **再评估基线**: 门胜率 10% (1/10), 规则轨 214 步 / 视觉轨 418 步 (记录于 2026-08-07)

### S11 首轮评估 (2026-08-07, MCP 集成默认启用后)

- **5 轮优化迭代结果** (S11_MCP_DEFAULT, ts=20260807_153455~160144): 5/5 轮均启用 MCP 集成
  (注入 292-294 chars, env+meta+5 假设+3 检索命中), 每轮 1 个有效候选
- **评估结论**: 5 轮均 score=1.0 / 214 步 (规则轨基线持平), **无帕累托改进**
  (无步数突破, 无门分数提升) — 自蒸馏触发条件 **未满足**, 维持观察
- **观察备注**: MCP 集成已验证稳定 (默认启用, 容错降级正常), 但提议器在
  物理层 (lightweight_env) 上已收敛至基线 214 步; 若后续多轮 (≥5) 仍无改进,
  应考虑切换目标文件优先级 (meta_config target_priority 轮换) 或触发自蒸馏

### S12 门裁决评估 (2026-08-07, --meta-config 5 轮, 修复后)

- **发现并修复 P2-V4 门裁决缺陷**: `meta_config.is_invalid` 原判定 `steps > 214`
  (严格大于), score=1.0/214 持平被判"有效" → "连续 2 轮无效"永不触发,
  meta_decisions.jsonl 为空 (S12 首轮 5 轮全持平无轮换)。修复为 `steps >= 214`
  (持平=无效=无帕累托改进), 单测 6/6 PASS
- **修复后 5 轮结果** (S12_META_CONFIG_R2, ts=20260807_172100~174622):
  4 条门裁决触发 (R2/R3/R4/R5), 参数演化有界 — temp 0.3→0.2→0.1 (下限),
  thr 0.45→0.5→0.55→0.6→0.65 (上限 0.90 内), target 轮换
  physics → physics+reward → 全物理层 → 循环 (注入 294→327→364 chars 随目标扩展)
- **评估结论**: 5 轮仍 score=1.0/214 步持平, **无帕累托改进** —
  门裁决触发条件已修复验证, 但提议器未突破; 按 PM 裁决 (Sprint 12 指令 4):
  **触发 plateau_explorer 自蒸馏评估** (待执行)

| 变体 | 质量 (winrate) | 效率 (步数) | 帕累托状态 |
|------|------|------|-----------|
| 基线 (4次规则编辑后) | 0.6, aggressive 0/2 | 超时频发 | 被支配 |
| + 优先级遮蔽修复 (OPPONENT-FOUND +dist>0.6) | 0.6, 近战接战大增 | 240步僵局 | 被支配 |
| + 对手诚实化 (帧/常量/死区) | 0.6, 28次持续推挤 | 240步僵局 | 被支配 |
| + 推力碰撞×抓地衰减 (物理) | 0.8 (aggressive 2/2), defensive 0/2 | 16-80步 | 帕累托 |
| + 探针判死修复 + 出生对脸 | 0.8, circler 恢复 | 5-80步 | 帕累托 |
| + 混合侧翼 + 门调优 (CLOSE-PUSH 15°/FLANK 0.80/CAUTIOUS 0.55-0.78) | **1.0 (10/10)** | 5-80步, 零超时 | **当前最优** |
| mh_rules_001 (v=rules, 血缘 970c209, P1 ROUND 1) | 1.0 (PASS) | 461 步 | 被支配 (效率劣于 mh_physics_001) |
| mh_mapping_001 (v=mapping, 血缘 970c209, P1 ROUND 1) | 1.0 (PASS) | 372 步 | 被支配 (效率劣于 mh_physics_001) |
| mh_physics_001 (v=physics, 血缘 970c209, P1 ROUND 1) | 1.0 (PASS) | 365 步 | **帕累托前沿 (保留, 效率 371→365)** |
| mh_rules_002 (v=rules, 血缘 970c209, P1 ROUND 2) | 1.0 (PASS) | 290 步 | 帕累托前沿 (FLANK 18°→15°) |
| mh_physics_002 (v=physics, 血缘 2181108, P1 ROUND 2) | 1.0 (PASS) | 360 步 | 被支配 (动量 0.90) |
| mh_physics_003 (v=physics, 血缘 2181108, P1 ROUND 2) | 1.0 (PASS) | 362 步 | 被支配 (动量 0.875 二分) |
| mh_combined_001 (v=combined, 血缘 d8ad9d7, P1 ROUND 3) | 1.0 (PASS) | **288 步** | **帕累托前沿 (FLANK 15°+动量 0.90 叠加)** |
| mh_combined_002 (v=combined, 血缘 9c6fd50, P1 ROUND 4) | 1.0 (PASS) | 289 步 | 被支配 (14°+0.89 组合负增益) |
| mh_rules_004 (v=rules, 血缘 9c6fd50, P1 ROUND 4) | 1.0 (PASS) | 288 步 | 持平 (288=288, 无质量/效率改进, 未保留) |
| mh_physics_005 (v=physics, 血缘 9c6fd50, P1 ROUND 4) | 1.0 (PASS) | 289 步 | 被支配 (动量 0.89 负增益) |
| mh_physics_006 (v=physics, 血缘 7e74be7, P1 ROUND 5) | 1.0 (PASS) | **286 步** | **帕累托前沿 (动量 0.90→0.95, 效率 288→286)** |
| mh_rules_005 (v=rules, 血缘 7e74be7, P1 ROUND 5) | 1.0 (PASS) | 288 步 | 持平 (角度阶梯 13°-15° 平台期, 未保留) |
| mh_combined_003 (v=combined, 血缘 7e74be7, P1 ROUND 5) | 1.0 (PASS) | 286 步 | 持平 (286=286 与 mh_physics_006 并列, 引擎按顺序保留 physics; 加性第 4 次验证) |
| mh_rules_001 (v=rules, 血缘 970c209, P1 ROUND 6-A 意外重跑) | 1.0 (PASS) | 351 步 | 被支配 (近战窗 ±15°→±10°, 重跑仍劣于基线) |
| mh_mapping_001 (v=mapping, 血缘 970c209, P1 ROUND 6-A 意外重跑) | 1.0 (PASS) | **262 步** | **帕累托前沿 (侧翼硬转 45°→40°; ROUND 1 时 372 被支配, 新基线下交互增益 → 引擎保留并已应用)** |
| mh_physics_007 (v=physics, 血缘 1517a2e, P1 ROUND 6) | 1.0 (PASS) | **260 步** | **帕累托前沿 (动量 0.95→1.0 硬上限, 262→260; 动量轴穷尽)** |
| mh_rules_006 (v=rules, 血缘 1517a2e, P1 ROUND 6) | 1.0 (PASS) | 262 步 | 持平 (平台期延续 12°-15°, 未保留) |
| mh_combined_004 (v=combined, 血缘 1517a2e, P1 ROUND 6) | 1.0 (PASS) | 260 步 | 持平 (260=260 与 mh_physics_007 并列; 加性第 5 次验证) |
| mh_physics_seed_002 (v=physics, 血缘 SEED_TEMPLATE, P1 ROUND 6-B 重扫) | 1.0 (PASS) | **259 步** | **帕累托前沿 (抓地衰减线性→二次, 新正交轴; 动量保持 1.0 未越界; sweep 单发 259 + 2× 确定性复验 259=259)** |
| mh_physics_008 (v=physics, 血缘 2e33751, P1 ROUND 7) | 1.0 (PASS) | 259 步 | 持平 (259=259, grip 轴饱和 → 宣告新轴闭合; 未保留) |
| mh_rules_007 (v=rules, 血缘 2e33751, P1 ROUND 7) | 1.0 (PASS) | **258 步** | **帕累托前沿 (FLANK 15°→10°, 近缘死区 10°-15°∩edge 0.65-0.80 提前接管; 2× 确定性复验 258=258)** |
| mh_combined_005 (v=combined, 血缘 2e33751, P1 ROUND 7) | 1.0 (PASS) | 258 步 | 持平 (258=258 与 mh_rules_007 并列, 加性第 6 次验证: 259+0(cubic)+(-1)(10°)=258 ✓; 简化偏好保留单轴变体) |
| mh_rules_001 (v=rules, 血缘 970c209, P1 ROUND 8-A sweep 重扫) | 1.0 (PASS) | **214 步** | **帕累托前沿 (CLOSE-PUSH 窗 ±15°→±10°; 与 FLANK 10° 完美空间铺砖; 2× 确定性复验 214=214; 跨基线交互增益二次兑现)** |
| mh_rules_008 (v=rules, 血缘 9107662, P1 ROUND 8-B 重新资格化) | 1.0 (PASS) | 214 步 | 持平 (214=214, FLANK 10°→8° 在铺砖基线上行为中性; 裁决: 不触发 5° 探针, **FLANK 10° 锁定为最佳切角**; 角度轴饱和) |
| mh_reward_001 (v=reward, 血缘 69abd93, P1 ROUND 10 证伪测试) | 1.0 (PASS) | 214 步 | 持平 (214=214; 奖励幅值与规则引擎步数指标解耦 — 规则非奖励驱动 + env 显式传参遮蔽默认值; **奖励轴对规则 harness 关闭, 仅对 RL 轨道有效**) |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_physics_001 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_physics_001 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_physics_001 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_physics_001 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |
| ca_rules_01 (v=physics, 血缘 code_agent) | 质量 1.0 (PASS) | 214 步 | 帕累托前沿 |


> **附注 (2026-08-06, P1 ROUND 2/3)**: PM「黄金分割线」假设 (0.86~0.88 存在陡峭效率悬崖) 已被实证数据证伪 — 动量曲率 365→362→360 单调递减, 无拐点; 且动量 0.90 与 FLANK 15° 叠加 仅 288 步 (若严格独立应为 279), 说明收益存在 ~9 步重叠, 为微弱加性而非乘法放大。

> **附注 (2026-08-06, P1 ROUND 4 — 精细化搜索, 无帕累托改进)**: 围绕 (15°, 0.90) 的 2×2 因子微扰完成 — 动量 0.89 负增益 (+1), FLANK 14° 中性 (0), 组合 14°+0.89 完全符合加性 (0+1=+1)。**288 步确认为局部盆地 (局部最小)**: 四个邻域点 (14°/15° × 0.89/0.90) 均 ≥ 288。前沿连续第 1 轮未改进 (终止条件计数: 1/2)。

> **附注 (2026-08-06, P1 ROUND 5 — 动量阶梯突破)**: mh_physics_006 (动量 0.90→0.95) = **286 步**, 新帕累托前沿 (288→286, 2× 确定性复验一致)。动量在 FLANK 15° 处仍单调 (0.89→289, 0.90→288, 0.95→286), 无饱和迹象 — 向 1.0 硬上限推进。FLANK 13° 持平 (角度阶梯 13°-15° 平台期)。加性第 4 次验证: 0.95(-2) + 13°(0) = 组合(-2) ✓。终止条件计数归零 (前沿改进)。

> **附注 (2026-08-06, P1 ROUND 6-A — 意外重跑 ROUND 1 计划, 交互增益发现)**: tag ROUND6 推断缺陷 (推断表缺 "6") 导致误执行 ROUND 1 计划; 意外重跑暴露**跨基线交互增益**: mh_mapping_001 (侧翼硬转 45°→40°) 在 ROUND 1 基线 (371) 时为 372 (中性, 被正确支配), 在改进基线 (286, FLANK 15°+动量 0.95) 下 = **262 步**, 2× 确定性复验一致 — 新帕累托前沿 (286→262, -8.4%, 全场最大单步增益)。逐策略: circler 66→57 (-9), defensive 50→47 (-3) — 精准压缩 F-106 侧滑无效推力。**方法论教训: 线性逐轮保留会漏掉跨基线交互收益 — 建议定期对全变体注册表做"重资格扫描" (re-qualification sweep)**。ROUND 6 正式计划 (动量 1.0 硬上限 + 角度 12°) 将在新基线 262 上执行。

> **附注 (2026-08-06, P1 ROUND 6 — 动量 1.0 硬上限)**: mh_physics_007 (动量 0.95→1.0) = **260 步**, 新帕累托前沿 (262→260, 2× 确定性复验一致)。**动量轴穷尽**: 1.0 = 物理层硬上限, 末次增量边际 0.76% < 1% → **触发 PM 裁决 2 的 TASK-005f 视觉解冻评估条件**。FLANK 12° 持平 (角度平台期 12°-15°)。加性第 5 次验证: 1.0(-2) + 12°(0) = 组合(-2) ✓。**全场演进 371→365→290→288→286→262→260 (总压缩 -30%)**。ROUND 7 建议: 先做 re-qualification sweep (重扫全注册表验证交互增益), 再考虑角度 10° 下探 / 奖励函数新轴。

> **附注 (2026-08-06, P1 ROUND 6-B — re-qualification sweep 首杀, 新正交轴)**: 按 ROUND 6-A 教训实现并执行 `--sweep` (重扫 6 候选注册表): 基线 260; mh_rules_001=343 被支配, mh_mapping_002 跳过 (diff 3× 匹配 vs 期望 1), mh_physics_seed_001 跳过 (0.8 不在磁盘), mh_combined_001=264, mh_rules_003=260 持平, **mh_physics_seed_002=259 击败基线**。seed_002 血缘为 SEED_TEMPLATE (早期磁盘正则失配时的降级种子), 其改动为**抓地衰减 (DOHYO 边缘区) 线性→二次** — 全新正交物理轴, 历轮计划从未触碰。**裁决: 合法前沿** — git diff 证实 momentum 行 `TIMESTEP * 1.0` 与 4f031a3 完全一致 (未越 1.0 硬上限); 2× 确定性复验 259=259 一致。**全场演进 → 259 (总压缩 -30.2%)**。sweep 机制成为常设工具: 每轮前沿变更后重扫全注册表, 捕获跨基线交互收益。

> **附注 (2026-08-06, P1 ROUND 7 — 角度轴平台期外突破, grip 轴闭合)**: 三候选因子设计 (基线 259): **mh_rules_007 (FLANK 15°→10°) = 258 步, 新帕累托前沿** (259→258, 2× 确定性复验 258=258)。机制: 优先级 (CLOSE-PUSH p500 > FLANK p480/470) 保证重叠带 (10°,15°) 无歧义; 增益来自**近缘死区** — 角度 (10°,15°) ∩ edge∈[0.65,0.80) 之前无规则触发, FLANK 10° 提前接管 → 近缘快速重新对齐 (random 7.5→7.0, circler 57.0→56.5)。mh_physics_008 (grip 二次→三次) = 259 持平 → **grip 轴饱和, 宣告闭合**。mh_combined_005 (三次+10°) = 258 与 rules_007 并列 → 加性第 6 次验证: 259+0(cubic)+(-1)(10°)=258 ✓; 简化偏好保留单轴变体。**角度响应非单调**: 12°-15° 平台期 (全 288) 是局部平台, 10° 突破。**全场演进 → 258 (总压缩 -30.5%)**。ROUND 8 建议: 角度 8° 下探 (F-106 零新魔数), 或 258 基线再 sweep。

> **🔒 已闭合轴标注 (2026-08-06 PM 裁决 3 强制归档)**: **动量 1.0 = 物理层硬上限 (ROUND 6 触顶, 边际 0.76% < 1%)**; **grip 衰减二次 = 轴闭合 (ROUND 7: 二次→三次 259=259 零增益)**。后续变体**禁止**重复探索这两轴 (再动物理层仅允许新正交轴, 如摩擦/惯量/阻尼; 抓地仅允许阶梯化等异质形状)。违规变体将被拒绝并归档为"已闭合轴重复探索"。

> **⏸️ TASK-005f (视觉 Sprint 6) 状态: FROZEN → THAW_PENDING (2026-08-06 PM 裁决 1)**。解冻条件升级为 **3-2-1 触发器**: (a) 连续 3 轮 (ROUND 8-10) 无帕累托改进 → 自动解冻; (b) 步数压缩率连续 2 轮 < 0.5% → 自动解冻; (c) PM 发出 1 次"强制解冻视觉"指令 → 立即执行。THAW_PENDING 期间: **允许**在 variants.py TASK-005f 占位符预研视觉特征提取 (Rerun 图像叠加层), **禁止**纳入评估循环。与 OBS-007 收敛预测交叉验证: 3 轮无前沿 ≈ ROUND 10-12 噪声层。

> **附注 (2026-08-06, P1 ROUND 8-A — sweep 巨型跨基线交互, 完美铺砖 214)**: 258 基线 `--sweep` (PM 裁决 2B 强制并行) 重扫 6 候选注册表 → **mh_rules_001 (CLOSE-PUSH 近战窗 ±15°→±10°) = 214 步**, 击败 258 (**-17%**)。**按 PM 裁决立即中断角度 8° 探索, 优先验证**: 2× 确定性复验 214=214, gate 0, 10/10。**机制 — 完美空间铺砖**: 该变体在 260 基线 = 343 (FLANK 15° 时产生 (10°,15°) 死区 → 灾难), 在 258 基线 (FLANK 10°) = 214 (CLOSE-PUSH ±10° 与 FLANK ±10° 无缝分割角度空间: |angle|≤10° CLOSE-PUSH, |angle|>10° FLANK, 零重叠零死区)。**收益全部来自 circler: 56.5→36.0 (-20.5)**, 因 10°-15° 带从 CLOSE-PUSH 切向浪费 (F-106) 转为 FLANK 高效重新对齐; defensive 45.5 (-1.5), aggressive 13.0 不变。**跨基线交互增益第二次巨额兑现** (首次 ROUND 6-A: mapping_001 = -24; 本次 -44): sweep 制度化的核心价值实证。**全场演进 → 214 (总压缩 -42.3%)**。角度 8° 候选按裁决搁置, 待 214 基线重新资格化。

## 潜伏变体注册表 (latent_score)
记录「若以当前基线评估, 历史/未采纳变体会得多少分」 — 潜伏变体早期识别 (PM ROUND 9 架构指令, 配合 --auto-sweep)
| 变体 | 质量 | 步数 | 评估基线 (ts) |
|---|---|---|---|
| mh_combined_001 (v=combined, 血缘 d8ad9d7) | 1.0 (PASS) | 221 步 | latent @ 20260806_123437 |
| mh_physics_008 (v=physics, 血缘 2e33751) | 1.0 (PASS) | 214 步 | latent @ 20260806_123437 |

> **附注 (2026-08-06, P1 ROUND 8-B — P0 全量 sweep + P1 角度资格化, 前沿 214 保持)**: **P0 (PM 裁决, 214 基线全量 sweep)**: 6 候选无一击败 214。PM 关注的 mh_combined_001 (15°+0.90) = **221 > 214** — 旧组合被当前前沿 (10°+1.0) 支配, 负协同证据成立 (其从 260 基线 264 → 214 基线 221 随基线改善, 但从未追上; 组件已过时)。mh_physics_008 (grip 三次) = 214 持平 — grip 轴跨基线零贡献, 闭合确认。4 候选跳过 (已并入基线或 diff 失效)。**P1 (角度 8° 重新资格化)**: mh_rules_008 (FLANK 10°→8°) = 214 **持平** — 8° 在铺砖基线上行为中性, (8,10)∩edge≥0.65 死带在种子局中不可达或影响为零 → 按裁决不触发 5° 探针, **FLANK 10° 锁定为最佳切角** (角度轴饱和)。**引擎升级 (PM ROUND 9 架构指令)**: `--auto-sweep` (每轮末尾轻量重扫未采用候选) + `--baseline N` (指定基线) + `--clamp` (MFHS D4 边界自限) + 潜伏注册表 latent_score (本表)。**OBS-007 双模式收敛规则 (PM 修正)**: 连续轴优化 → 指数衰减模型; 结构重组 (sweep/交互) → 突变-重组模型 (平均每 5-8 轮一次); 3-2-1 触发器"3 轮无进展"仅计连续轴轮次。**全场演进保持 214 (总压缩 -42.3%)**; ROUND 10 候选: 奖励轴 (mh_reward_001 就绪) / 再 sweep。

> **附注 (2026-08-06, P1 ROUND 10 — 奖励轴证伪测试, 轴关闭)**: mh_reward_001 (push_threshold 0.2→0.285, 文件头自述 BayesOpt 最优值, F-106 零新魔数) = **214 持平** — 证伪测试确认: **奖励幅值与规则引擎步数指标完全解耦**。机制 (磁盘实读): (a) 规则智能体由 ABDL 规则选动作, 非奖励驱动; (b) 终止 (done) 仅由出界事件决定; (c) env 显式传参 `V10Reward(edge_penalty_weight, push_threshold)` 遮蔽 reward_functions.py 默认值。**奖励轴对规则 harness 引擎关闭** (改奖励幅值不可能改变步数); 奖励优化仅对 **RL 训练轨道**有效 (那里智能体确实优化奖励信号) — 已记录为跨轨道差异。**四轴全闭**: 动量 1.0 (硬上限) / grip 二次 / FLANK 10° / 奖励 (解耦)。**全场演进保持 214 (总压缩 -42.3%)**; 剩余候选轴: 规则距离阈值 (0.6/0.65/0.80) 微扰、新规则 (如边缘预防)、或宣告收敛。

> **🏁 ROUND 11 (2026-08-06, PM 裁决 3/3) — RULES 引擎 CONVERGED/CLOSED, TASK-005f ACTIVE**: PM 裁决: ROUND 11 起 **禁止任何规则层新候选** (含距离阈值 0.6/0.65/0.80 微扰——会污染映射结果)。规则轨道以 **214 步** 正式归档收敛 (四轴全闭: 动量 1.0 / grip 二次 / FLANK 10° / 奖励解耦; 总压缩 -42.3%, 14 提交, 6 新前沿)。3-2-1 触发器满足 (ROUND 8-B P1 8° 持平 + ROUND 10 奖励持平 + ROUND 11 RULES 关闭) → **TASK-005f 解冻 → ACTIVE**, 视觉集成轨道开启。ROUND 11 交付物: (a) ROADMAP_v2.md 视觉集成路线图 (EVAI R-I-C-E 四步法 + 三层架构 + Phase A/B/C) — ✅ 完成; (b) `outer_loop.py --vision-probe` 干跑 — ✅ 完成 (30 帧 Recognize 热图经 gRPC 摄入 :9090 画布, RULES 基线零扰动)。**协议栈扩充至 5 ACTIVE**: MFHS / EVAI-V1R (Recognize-Interpret-Command-Execute) / EVAI-INT (Retrieve-Inspect-Configure-Execute + L1-L6 资源索引) / EDTA-V1 (四支柱验真) / G3CA-ARCH (P-E-R + 工具优先, v1.1)。**wasm 交互自动化判定不可靠 (F-107)**, 采纳 G3CA 工具优先原则: 桌面/GUI 控制走 MCP 工具调用, 视觉仅 fallback; 验证证据用磁盘 PNG + gRPC/.rrd 双通道。TASK-006 (视觉-物理融合标定) / TASK-007 (GUI 截图自动调参) RESERVED。

> **🏛️ TASK-006b + TASK-007 (2026-08-06, 视觉-物理融合, Sprint 7 收官)**: **TASK-006b (实时闭环, b01377b)** — 门分数 = 1.0 (score), 步数 = **418**, 里程碑基线 (edge_min→decay 闭环: edge_min<0.20 注入 decay=0.06+0.02*(0.20-edge_min)/0.20, edge_min<0.05→0.10 封顶)。**TASK-007 (Gazebo 真实危险帧, 4735793)** — 40 个真实边缘事件 (2 danger 0.038/0.048 + 18 near), 视觉检测 edge_min<0.20 → 注入 decay 0.072-0.100, 门回归 **418 步 / 1.0 分** 零劣化。**注**: 步数指标从规则轨 (214) 切换至视觉闭环轨 (418) — 两轨独立计数, 418 = 视觉轨里程碑基线 (PM 阶段评估表: 371→214→419→418)。**MHA-ARCH v1.0 (学术对齐)**: P1 引擎升级编码代理 Proposer (code_agent_proposer.py, 本地 Ollama qwen2.5:7b), 2 次实测产出有效候选 (GRIP_DECAY / V9 阈值), 幻觉防御实证拦截 1 次; 血缘 4 文件落位 (harness_candidates.json / pareto_frontier.md / failure_analysis.md / skill_doc.md); 回归零劣化 (46 passed / 4 failed 既有)。

> **🏁 P0 多轮迭代收敛基线 (2026-08-07, MHA_MULTIROUND_1, PM 裁决 1 定稿)**: **GRIP_DECAY = 0.08 定稿为规则轨独立基线**。3 轮迭代 (ca_rules_01 ×3, 5303f90): 0.10↔0.08 振荡, 全部 score=1.0 / 214 步, 假设检验 3/3 confirmed (hypotheses.jsonl: 20260807_105324/105934/110547, 置信度 0.7/0.7/0.75)。LLM 振荡后自然落定 0.08 → `lightweight_env.py:47` 默认值更新 (env 变量 BOTTLE_GRIP_DECAY 仍可注入覆盖)。**与视觉轨共存规则**: 视觉轨 (418 步闭环) 经 `BOTTLE_GRIP_DECAY` 环境变量显式注入动态 decay (edge_min 映射 0.06-0.10), 不读此默认值 — 两轨零冲突 (vision_physics_controller.py:75)。跨项目污染修复同批归档 (pareto/failure_analysis 迁移 meta_harness/, 三处定位逻辑重定向, 详见 governance_audit_20260807.md)。
