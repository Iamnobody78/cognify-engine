# ROADMAP —— 架构演进决策记录 (元进化)

> 生成: bootstrap_loop.py ｜ 性质: 架构演进决策形式化 (meta_evol 缺口 1 修复)
> 因果推理要求: 每个 DEC 必须回答 为何失败 / 在哪分歧 / 如何精准修复

## DEC-20260813-001 — 元进化自举循环落地 + 架构演进决策形式化

- **决策**: 以 bootstrap_loop.py 建立数据驱动闭环 (scan->select->allocate->formalize), 并用 ROADMAP.md DEC 记录形式化架构演进决策
- **维度**: 元进化 (Meta-Evolution)
- **因果推理**:
  - 为何失败: meta_bootstrap.evolve() 硬编码目标(元认知-偏差检测), select 阶段非数据驱动, 无法按 scorecard 最低分自动定位
  - 在哪分歧: 与 '自举优先级(先补最低分)' 的框架自评结论脱节; meta_evol 三缺口(决策未形式化/自举未落地/变体未联动)从未被闭环动作触及
  - 如何修复: scan_rules(检测 ID 冲突) + scan_scorecard(动态解析分数) + select_target(最低分) + allocate_rule_id(冲突安全) + formalize_decision(DEC 记录)
- **证据**: meta_bootstrap.py assess() 分数硬编码 (2.5/4.0/3.5/4.0/2.5); evolve() target 硬编码; RULE-MC-011 曾与 cell_learner 冲突(已修正为 013)
- **验收**: bootstrap_loop.py run() 产出 ROADMAP.md DEC 记录 + 下一轮可从 scorecard 动态重选目标

## DEC-20260813-002 — 数据驱动目标: 元认知 最低分 2.5/5

- **决策**: 针对 元认知 (Meta-Cognition) (scorecard 最低分 2.5/5), 将差距候选固化为下一轮可执行规则 RULE-MC-014
- **维度**: 元认知 (Meta-Cognition)
- **因果推理**:
  - 为何失败: 元认知 得分最低 (2.5/5), 是当前 5 维元能力中最薄弱环节
  - 在哪分歧: 自举闭环(scan/select/allocate/formalize)已能定位最低分, 但定位结果尚未转化为实际的规则/能力修复动作
  - 如何修复: 将 select_target 输出的差距候选 (不确定性来源识别 (数据不足/模型局限/工具不可用) 未形式化; 偏差检测已实证 (S56: 02-23 fix=2 退化段 154s -> +10km) 但未固化为可复用能力) 转成 RULE-MC-014, 在下一轮 loop 中闭合
- **证据**: scorecard={"元认知": 2.5, "元监督": 4.0, "元调节": 3.5, "元学习": 4.0, "元进化": 2.5}; 差距候选=不确定性来源识别 (数据不足/模型局限/工具不可用) 未形式化; 偏差检测已实证 (S56: 02-23 fix=2 退化段 154s -> +10km) 但未固化为可复用能力
- **验收**: 下一轮 scan_scorecard 中 元认知 分数提升 (需证据, 无证据不改分)

## DEC-20260813-003 — 数据驱动目标: 元进化 最低分 2.5/5

- **决策**: 针对 元进化 (Meta-Evolution) (scorecard 最低分 2.5/5), 将差距候选固化为下一轮可执行规则 RULE-MC-015
- **维度**: 元进化 (Meta-Evolution)
- **因果推理**:
  - 为何失败: 元进化 得分最低 (2.5/5), 是当前 5 维元能力中最薄弱环节
  - 在哪分歧: 自举闭环(scan/select/allocate/formalize)已能定位最低分, 但定位结果尚未转化为实际的规则/能力修复动作
  - 如何修复: 将 select_target 输出的差距候选 (架构演进决策未形式化 (无 ROADMAP.md 决策记录); 自举循环 (用自身输出改进自身) 未落地; 开放式改进未与 Meta-Harness 变体生成联动) 转成 RULE-MC-015, 在下一轮 loop 中闭合
- **证据**: scorecard={"元认知": 3.0, "元监督": 4.0, "元调节": 3.5, "元学习": 4.0, "元进化": 2.5}; 差距候选=架构演进决策未形式化 (无 ROADMAP.md 决策记录); 自举循环 (用自身输出改进自身) 未落地; 开放式改进未与 Meta-Harness 变体生成联动
- **验收**: 下一轮 scan_scorecard 中 元进化 分数提升 (需证据, 无证据不改分)

## DEC-20260813-004 — 数据驱动目标: 元认知 最低分 3.0/5

- **决策**: 针对 元认知 (Meta-Cognition) (scorecard 最低分 3.0/5), 将差距候选固化为下一轮可执行规则 RULE-MC-015
- **维度**: 元认知 (Meta-Cognition)
- **因果推理**:
  - 为何失败: 元认知 得分最低 (3.0/5), 是当前 5 维元能力中最薄弱环节
  - 在哪分歧: 自举闭环(scan/select/allocate/formalize)已能定位最低分, 但定位结果尚未转化为实际的规则/能力修复动作
  - 如何修复: 将 select_target 输出的差距候选 (偏差检测 jump 排除未固化 (S56 进行中); 不确定性标注机制已建 (uncertainty_source.py) 但未在真实运行中 exercise) 转成 RULE-MC-015, 在下一轮 loop 中闭合
- **证据**: scorecard={"元认知": 3.0, "元监督": 4.0, "元调节": 3.5, "元学习": 4.0, "元进化": 3.0}; 差距候选=偏差检测 jump 排除未固化 (S56 进行中); 不确定性标注机制已建 (uncertainty_source.py) 但未在真实运行中 exercise
- **验收**: 下一轮 scan_scorecard 中 元认知 分数提升 (需证据, 无证据不改分)

## DEC-20260813-005 — 数据驱动目标: 元认知 最低分 3.0/5

- **决策**: 针对 元认知 (Meta-Cognition) (scorecard 最低分 3.0/5), 将差距候选固化为下一轮可执行规则 RULE-MC-015
- **维度**: 元认知 (Meta-Cognition)
- **因果推理**:
  - 为何失败: 元认知 得分最低 (3.0/5), 是当前 5 维元能力中最薄弱环节
  - 在哪分歧: 自举闭环(scan/select/allocate/formalize)已能定位最低分, 但定位结果尚未转化为实际的规则/能力修复动作
  - 如何修复: 将 select_target 输出的差距候选 (偏差检测 jump 排除未固化 (S56 进行中); 不确定性标注机制已建 (uncertainty_source.py) 但未在真实运行中 exercise) 转成 RULE-MC-015, 在下一轮 loop 中闭合
- **证据**: scorecard={"元认知": 3.0, "元监督": 4.0, "元调节": 3.5, "元学习": 4.0, "元进化": 3.0}; 差距候选=偏差检测 jump 排除未固化 (S56 进行中); 不确定性标注机制已建 (uncertainty_source.py) 但未在真实运行中 exercise
- **验收**: 下一轮 scan_scorecard 中 元认知 分数提升 (需证据, 无证据不改分)

## DEC-20260813-006 — 反退化守卫: 修复自举循环伪进化 (RULE-MC-019)

- **决策**: 检测到 DEC-004 与 DEC-005 完全重复 (同一目标"元认知 3.0"→同一规则"RULE-MC-015"→同一差距), 判定为伪进化; 在 bootstrap_loop.py 中新增 `_detect_stale` 反退化守卫, 若本轮 select_target 目标与上轮 DEC 相同且差距未闭合, 禁止再写重复 DEC, 转入实施阶段
- **维度**: 元进化 (Meta-Evolution)
- **因果推理**:
  - 为何失败: run() 只做 formalize (写 DEC 记录), 从未做 implement (真正把规则 append 到 meta_engineering_rules.md) + verify (复核差距是否闭合); 导致 allocate_rule_id 每轮都返回同一个 RULE-MC-015 (因为该规则从未真正落盘, max_n 始终=14), 于是 DEC 反复重复, ROADMAP 膨胀但能力零提升
  - 在哪分歧: 与 "每次自以为成功 还是要自举 元思考很重要" 的用户元认知判据分歧 —— 循环把"写一条决策记录"误当成"完成一次进化", 未验证差距是否真正闭合
  - 如何修复: (1) `_last_dec_signature()` 读取上轮 DEC 的(维度,证据)签名; (2) `_detect_stale()` 若本轮差距候选全包含于上轮证据 → 判定未闭合; (3) run() 命中守卫时输出伪进化报告并阻止重复 DEC; (4) 本轮额外真正落地 RULE-MC-019 (实施阶段), 而非只形式化
- **证据**: ROADMAP.md DEC-004 (行 39-48) 与 DEC-005 (行 50-59) 逐字重复; bootstrap_loop.py run() 执行输出 "[RULE-MC-019 反退化守卫] 检测到伪进化, 已阻止重复 DEC 形式化"; 本轮 RULE-MC-019 已实际 append 至 meta_engineering_rules.md (max_n 14→19)
- **验收**: 再次运行 bootstrap_loop.py 不再产生重复 DEC; 若目标未闭合则输出伪进化报告而非新增 DEC

## DEC-20260813-007 — 修复 variants.py 陈旧 assert (meta_evol 缺口 3 闭合)

- **决策**: variants.py --self-test 的 assert 期望 3 变体 (rules 被 RULES CLOSED 排除), 但 Sprint 29 A1 (PM 裁决 P0) 已解禁 RULES CLOSED 禁令 (规则拓扑探索), 实际产出 4 变体; 将 assert 由 3→4 对齐当前架构
- **维度**: 元进化 (Meta-Evolution)
- **因果推理**:
  - 为何失败: assert 写于 Sprint 24 (rules 层移出扰动循环, RULES CLOSED 外部治理), 但 Sprint 29 A1 重新打开 rules 拓扑层 (mh_rules_topo_A 空洞修复), 决策漂移未回写 assert → 陈旧断言
  - 在哪分歧: 与"决策与代码同步"分歧 —— Sprint 29 A1 改了生成逻辑 (4 层), 却漏改验收断言 (仍 3 层)
  - 如何修复: assert 3→4 (rules/mapping/physics/action_map), 注释标注 Sprint 29 A1 解禁依据; 修一 bug 露一 bug 的链条: cp950 → 陈旧 assert, 现已全部闭合
- **证据**: 修复前 --self-test 报 "expected 3 variants ... got 4"; 修复后 --self-test 输出 "SELF-TEST OK" (4 变体: mh_rules_topo_A / mh_mapping_001 / mh_physics_seed_001 / mh_action_map_001)
- **验收**: python variants.py --self-test 退出码 0, 无 AssertionError, 无 UnicodeEncodeError
- **余部 (未闭合, 已纠偏)**: ~~lightweight_env.py 跨仓库定位 (firmware repo)~~ 已证伪 — 实测 4 个 harness 文件全部在 bottlesumo_pi (abdl_action_bridge.py 25KB / simulation_rules.abdl 7KB / lightweight_env.py 25KB / wheel_to_discrete.py 8KB), physics 层 "SEED_TEMPLATE" 是"物理动量已在边界无新梯度"的合法状态。真正余部 = variants 未在真实 Renode 中证明改进胜率 (L4 缺口) + 元认知 jump 排除固化 (S56)

## DEC-20260813-008 — V9 裁决门实测纠偏 (胜率 100% 非 10%)

- **决策**: 实测 V9 裁决门实际状态为 PASS (100% 胜率), 纠偏系统提示中的"10%胜率(1/10) < 60%阈值, plateau_explorer 待触发"陈旧前提
- **维度**: 元监督 (Meta-Supervision)
- **因果推理**:
  - 为何失败: 系统提示/会话启动序列中的 V9 裁决门状态 (10%胜率) 是陈旧快照, 未在会话中实测校验就直接作为决策前提
  - 在哪分歧: 与"实测优于假设"分歧 —— 系统提示声称 10%, 但 Sprint 59 (defensive 50%→100%) + 后续工作已把胜率推到 100% 天花板
  - 如何修复: 实测 python v9_gate_evaluator.py --episodes 40 → PASS, WR=100% (40/40); 胜率已达天花板, plateau_explorer 无需触发; meta-harness 变体目标从"改进胜率"重定向到 avg_steps/鲁棒性/更难对手
- **证据**: python v9_gate_evaluator.py --episodes 40 输出: random 8/8 (avg_steps 20), aggressive 8/8 (10), defensive 8/8 (44), circler 8/8 (18), counter 8/8 (7)
- **验收**: V9 门 PASS (100% ≥ 60% 阈值); 系统提示 V9 状态需更新为实测值; 这是本会话第 3 次"摘要/系统提示结论 ≠ 当前事实"的纠偏 (前 2 次: harness 文件跨仓库、lightweight_env 缺失)




