# Sprint 20 P2 plateau_explorer 自蒸馏 — 设计文档（2026-08-08）

> 触发依据（PM Sprint 20 指令 5）：**"若 5 轮全部门禁拦截且无 PASSED → 启动 P2 自蒸馏设计（参考 EvolveR 闭环）"**
> 触发证据：S20_P2DATA（5 轮请求，3 轮后探索饱和停止）——9 次评估 **全部被门禁拦截**（6 SUSPICIOUS + 3 INCONCLUSIVE，无 PASSED）；S19_VERIFY 同构（9/9 全拦截）。连续两轮 18 次评估零 PASSED，**探索饿死状态确认**。
> 学术基线：EvolveR（ICML 2026 闭环经验生命周期）、Mem²Evolve（协同进化）、OPD-Evolver（慢-快双速）、Skill-SD（技能条件自蒸馏）、EDV（Execute-Distill-Verify 防 Self-Confirmation Trap）、AgentArk（多代理蒸馏到权重）、**Why Does FADS Fail?（decoding collapse 警示，arXiv 2607.17558）**

---

## 1. 问题诊断：门禁在保护什么，饿死在哪个环节

```
候选生成 → [P1 恒 False 拦截] → apply_precheck → apply → [S18 差分门禁] → Pareto
                                            ↓ 100% 成功          ↓ 9/9 全拦截
                                      干净 apply            SUSPICIOUS 6 + INCONCLUSIVE 3
```

**门禁语义正确性已实证**（S18/S19/S20 三轮一致）：候选行为变化全部被拦截，说明门禁在**正确拒绝**——但探索被饿死说明：

| 判定 | 次数 | 语义 | 根因（指纹+winrate 交叉分析） |
|------|------|------|------|
| SUSPICIOUS | 6+6 | 行为指纹变化但 winrate 不变 | **评估失敏**：基线 winrate=1.0 饱和，行为变化无法映射到质量信号 |
| INCONCLUSIVE | 3+3 | 信号相同（行为指纹不变） | **扰动幅度过小**：候选修改未跨越行为感知阈值（如 `BETWEEN(-15,15)`→`(-8,8)` 在饱和策略下动作直方图不变） |

**结论**：饿死的不是"生成质量"而是**两个信息缺口**——(a) 评估信号对行为变化失敏（无法区分好坏）；(b) 候选扰动与行为变化之间缺乏映射先验（不知道多大幅度才算"有意义的变化"）。

## 2. 蒸馏目标：不是蒸馏"答案"，而是蒸馏"失敏诊断与扰动映射"

**防 decoding collapse 的根本设计**（对齐 Why Does FADS Fail?）：不蒸馏 LLM 候选输出（重复模板风险），而是蒸馏**结构化判定语义**——每条被拦截候选都是带标签的训练信号：

```
蒸馏数据集条目（每候选 1 条，源: meta_decisions.jsonl + 行为指纹快照）:
{
  "diff_verdict": "SUSPICIOUS" | "INCONCLUSIVE",
  "diff_reason": 门禁 reason,
  "fingerprint_delta": action_hist/branch_hist 变化摘要（from select_action_traced）,
  "winrate_saturated": true（基线 1.0 饱和标志）,
  "layer": rules/mapping/physics,  "anchor_type": BETWEEN/direct/const,
  "perturbation": 具体改动（如 BETWEEN(-15,15)->(-8,8), 幅度 7°）,
  "verdict_signal": 该条应蒸馏出的规则（人工/自动标注）
}
```

## 3. 三类可蒸馏资产（蒸馏管道输出）

### D1：失敏检测规则（SUSPICIOUS → 评估层）
- **规则**：`winrate==1.0 饱和时，行为指纹变化 → 评估失敏，需降级到次级信号（steps/动作熵/对抗配置）`
- **落点**：v9_gate_evaluator 增加"饱和感知"标志；meta_config 增加 `saturation_fallback` 配置
- **闭环验证**：蒸馏后重跑 SUSPICIOUS 案例，若次级信号能区分（steps 变化）→ D1 有效

### D2：扰动-行为映射先验（INCONCLUSIVE → 生成层）
- **规则**：`扰动幅度必须超过行为感知阈值：角度锚点 ≥10° 变化、阈值锚点 ≥20% 变化、动量系数 ≥0.2 变化`（从 S19/S20 案例归纳）
- **落点**：`_seed_variants` 增加扰动幅度校验；LLM prompt 注入"最小有意义扰动"先验（对齐 EvolveR 经验检索）
- **闭环验证**：蒸馏后生成候选的 INCONCLUSIVE 比例应显著下降

### D3：候选多样性度量（跨轮诊断）
- **规则**：`连续 N 轮全拦截 → 输出多样性诊断：锚点类别分布（BETWEEN/常量/阈值）、层分布、扰动幅度直方图`
- **落点**：outer_loop stagnation 报告增强（S20 已有 stagnation@3 轮，增强为含多样性归因）
- **闭环验证**：S21 运行报告中出现多样性统计

## 4. 管道设计（EDV 范式映射：Execute→Distill→Verify）

```
[Execute] 已有: P1 拦截 + apply_precheck + 差分门禁 = 干净候选与判定数据
    ↓
[Distill] 新增 distill_loop.py:
   1. 读取 meta_decisions.jsonl（--since S19_VERIFY）
   2. 过滤: diff_gate 记录（SUSPICIOUS/INCONCLUSIVE）+ apply 成功
   3. 关联指纹: variants/_snapshots/<ts>/ 下的候选 diff + 基线信号
   4. 规则提取: D1/D2/D3 三管道并行（规则模板 + 数值归纳 + 分布统计）
   5. 输出: rules/experience/ 下蒸馏规则文件（版本化, 供种子化）
    ↓
[Verify] 闭环验证（防 Self-Confirmation Trap, EDV 核心）:
   1. 蒸馏规则 → 转 _seed_variants 种子（apply_precheck + 恒 False 检测全过）
   2. 重跑 5 轮: 若 PASSED 出现 → 蒸馏有效; 若仍全拦截 → 记录失败并触发
      评估层 D1 降级信号（次级评估配置）
   3. 关键防线: 蒸馏规则本身必须通过 S18 门禁——坏规则与坏候选同等待遇
```

## 5. 防 decoding collapse 三道闸（对齐 Why Does FADS Fail?）

1. **不蒸馏自由文本**：规则从结构化字段（verdict/reason/fingerprint_delta/perturbation）归纳，不走 LLM 模板重复
2. **EMA 教师语义**：不引入"教师模型"，而是以**门禁判定**（确定性标签）为教师——判定稳定，无教师漂移
3. **验证门**：蒸馏规则进入种子管道前必须过 P1 恒 False 检测 + apply_precheck + diff 门禁（与候选同等待遇），坏规则不产生种子

## 6. 里程碑与验收标准（Sprint 21 候选）

| 里程碑 | 内容 | 验收 |
|--------|------|------|
| M1 | distill_loop.py（数据管道 + D1/D2/D3 提取） | 从 S19+S20 数据集提取 ≥3 条规则，快照可审计 |
| M2 | D1 落点：饱和感知评估标志 + 次级信号 | SUSPICIOUS 案例次级信号可区分（steps Δ≠0） |
| M3 | D2 落点：种子扰动幅度校验 | 蒸馏后种子 INCONCLUSIVE 比例下降（对比 S20 基线 33%） |
| M4 | 闭环重跑 5 轮 | 出现首个 PASSED 或明确失败归因（触发评估层重构候选） |

## 7. 风险与边界

| 风险 | 缓解 |
|------|------|
| 蒸馏规则过拟合单次运行 | 数据源跨 S19_VERIFY + S20_P2DATA 两轮 18 案例；规则带置信度 |
| 次级信号（steps）在饱和策略下也无区分度 | M2 备选：对抗配置评估（对手策略变化）——超出本设计范围时触发 V9 门裁决 |
| 规则库膨胀 | 规则版本化 + Pareto 语义：规则本身也走保留评审 |

## 8. 与 PM 学术矩阵映射

| 学术资源 | 本设计落点 |
|----------|-----------|
| EvolveR 闭环（离线自蒸馏→在线检索→策略 RL） | §4 管道；D2 扰动先验 = "可复用策略原则" |
| Why Does FADS Fail?（decoding collapse） | §5 三道闸（结构化蒸馏 + 确定性教师 + 验证门） |
| EDV（Execute-Distill-Verify） | §4 管道三阶段命名与防 Self-Confirmation Trap 验证门 |
| Skill-SD（技能条件自蒸馏 + 动态教师） | D1/D2 规则 = "成功行为/错误/工作流"技能化 |
| Mem²Evolve（经验→能力扩展） | D1 落点为评估层能力扩展（超越经验积累） |
| OPD-Evolver（慢-快双速） | 快循环 = 现有轮次；慢循环 = distill_loop（跨轮回顾） |
| AgentArk（蒸馏到权重） | 后续候选：若规则化蒸馏到达瓶颈，转策略蒸馏（Sprint 22+） |

## 9. 决策请求（待 PM 裁决）

1. **P2 实现范围**：M1-M4 全做，或先做 M1+M3（数据管道 + 生成层扰动先验）再评估 M2（评估层重构）？
2. **资源**：distill_loop.py 归入 meta_harness 现有测试体系（新增 ~15 测试），是否需要独立证据文档？
3. **V9 门联动**：若 M4 闭环仍无 PASSED，是否触发 plateau_explorer 自蒸馏 V9 门（10% 胜率 → 60% 阈值的既有路径）？
