# 元能力五维评估表 (META-CAPABILITY SCORECARD)

> 生成: 2026-08-13 (20260813_164739) | 工具: META-BOOTSTRAP v1.0 | 标签: META_SCORECARD
> 依据: meta_decisions.jsonl / pareto_frontier.md / failure_analysis.md /
> meta_engineering_rules.md / experience/hypotheses.jsonl / sprint 报告

## 总分与成熟度

| 维度 | 分数 (0-5) | 成熟度 | 关键证据 | 主要差距 |
| :--- | :---: | :---: | :--- | :--- |
| 元认知 (Meta-Cognition) | 3.0 | L3 | hypotheses_jsonl_lines=63; reasoning_chain=sprint 报告 + failure_analysis 记录; bias_detection_formalized=S56 fix=2 退化段已固化 (RULE-MC-013); META-THINK v1.0 已形式化 (强制反思 T.H.I.N.K. 五步, 未在真实运行 exercise) | 偏差检测 jump 排除未固化 (S56 进行中) |
| 元监督 (Meta-Supervision) | 4.0 | L4 | meta_decisions_jsonl=1542; pareto_frontier_lines=548; gate_progress=V9 门 10% -> 90% (S38, chase-BC 直投 + defensive 审计) | HONEST-BOUNDARY 边界感知已设计未全量落地 |
| 元调节 (Meta-Regulation) | 3.5 | L3~L4 | param_bounds_updates=88; meta_config=temperature/retrieval_threshold/target_priority 自适应 (stagnation 触发); target_priority_rotation=physics->reward->mapping 轮换 | 资源分配未与 SRS 联动 |
| 元学习 (Meta-Learning) | 4.0 | L4 | rules_entries=19; cell_learning_events=169; failure_analysis_lines=1813 | 知识迁移跨领域形式化 (NCLT 教训 -> 其他传感器融合域) 未沉淀 |
| 元进化 (Meta-Evolution) | 3.5 | L3~L4 | sprint_reports=11; code_agent_proposer=存在 (56KB); candidates_dir=53; architecture_decisions=DEC-001..007; EVOLVE-SAFE v1.0 落地 (R1-R5 红线); RULE-MC-019 反退化守卫已演示; RULE-MC-020 决策漂移回写; variants.py cp950 + 陈旧 assert 已修 (--self-test 实测通过); harness 文件已确认全部在 bottlesumo_pi (simulation_rules.abdl/abdl_action_bridge.py/lightweight_env.py/wheel_to_discrete.py) | variants 生成能力已落地但未在真实 Renode 运行中证明改进胜率 (L4 缺口) |

**综合元能力指数 (MCI)**: 3.60/5.0 (L3 主导)

## 逐维度详情

### 元认知 (Meta-Cognition) — L3 (3.0/5)

**证据**:
- hypotheses_jsonl_lines: 63
- reasoning_chain: sprint 报告 + failure_analysis 记录
- bias_detection_formalized: S56 fix=2 退化段已固化 (RULE-MC-013); jump 排除仍进行中
- uncertainty_source_id: 已形式化 (uncertainty_source.py 三通道 + RULE-MC-014), 待真实运行积累标注
- meta_think_formalized: META-THINK v1.0 落地 (T.H.I.N.K. 五步强制反思), 已形式化但未在真实运行 exercise

**差距 (改进候选)**:
- 偏差检测 jump 排除未固化 (S56 进行中)
- 不确定性标注机制已建 (uncertainty_source.py) 但未在真实运行中 exercise

### 元监督 (Meta-Supervision) — L4 (4.0/5)

**证据**:
- meta_decisions_jsonl: 1542
- pareto_frontier_lines: 548
- gate_progress: V9 门 10% -> 90% (S38, chase-BC 直投 + defensive 审计)
- monitor: meta_monitor.py (stagnation/loop/latency_anomaly)

**差距 (改进候选)**:
- HONEST-BOUNDARY 边界感知已设计未全量落地

### 元调节 (Meta-Regulation) — L3~L4 (3.5/5)

**证据**:
- param_bounds_updates: 88
- meta_config: temperature/retrieval_threshold/target_priority 自适应 (stagnation 触发)
- target_priority_rotation: physics->reward->mapping 轮换

**差距 (改进候选)**:
- 资源分配未与 SRS 联动
- 工具选择未与 MCP 联动 (mcp_usage_report.jsonl 已有数据)

### 元学习 (Meta-Learning) — L4 (4.0/5)

**证据**:
- rules_entries: 16
- cell_learning_events: 169
- failure_analysis_lines: 1813
- distill: distill_loop.py nano 蒸馏 (789 params, 87.5% 门)

**差距 (改进候选)**:
- 知识迁移跨领域形式化 (NCLT 教训 -> 其他传感器融合域) 未沉淀

### 元进化 (Meta-Evolution) — L3~L4 (3.5/5)

**证据**:
- sprint_reports: 11
- code_agent_proposer: 存在 (56KB)
- candidates_dir: 53
- architecture_decisions_formalized: ROADMAP.md DEC-001..007 (架构演进决策记录)
- self_evolve_loop: bootstrap_loop.py 数据驱动闭环 (scan->select->allocate->formalize) + RULE-MC-019 反退化守卫
- evolve_safe: EVOLVE-SAFE v1.0 落地 (D1-D7 安全维度 + G.A.P.S. + R1-R5 红线)
- variants_cp950_fixed: variants.py 增加 sys.stdout.reconfigure(encoding="utf-8"), self-test 中文血缘标题正常打印
- variants_self_test_pass: 陈旧 assert 修正 (3→4 变体, 对齐 Sprint 29 A1 rules 层解禁), --self-test 实测通过 (4 变体 rules/mapping/physics/action_map)
- harness_files_verified: 全部 4 个 harness 文件已确认在 bottlesumo_pi (core/meta_language/abdl_action_bridge.py 25KB, governance/meta_language/simulation_rules.abdl 7KB, simulation/lightweight_env.py 25KB, simulation/wheel_to_discrete.py 8KB) — 此前"跨仓库 firmware repo"前提已证伪
- v9_gate_verified: 实测 python v9_gate_evaluator.py --episodes 40 → PASS, WR=100% (40/40, 5 对手策略 random/aggressive/defensive/circler/counter, avg_steps 7-44) — 系统提示"10%胜率(1/10)"前提已证伪

**差距 (改进候选)**:
- meta-harness 变体目标重定向: V9 胜率已达 100% 天花板, "variants 改进胜率"目标已无 headroom (L4 该维度 MOOT); 应转向 avg_steps / 鲁棒性 / 更难对手套件 / HIL 真机验证
- 元认知 jump 排除固化 (S56): 偏差检测 jump 排除未固化, 待实施

## 结论与自举建议

- MCI=3.60: 元监督/元学习最成熟 (L4), 元认知 (L3, 差距未闭合) 为当前最薄弱
- **自举优先级**: 下一优先 = 元认知 (3.0, 最低分): 偏差检测 jump 排除固化 + META-THINK/uncertainty 在真实运行中 exercise; 次优先 = 元进化 (3.5): variants 在真实 Renode 中证明改进胜率 (10-episode 快速验证)
- S56 实证已为元认知-偏差检测提供现成素材: fix=2 退化段检测已固化 (RULE-MC-013), jump 排除待固化
- **反退化守卫已生效 (RULE-MC-019)**: 本轮 select_target 命中"元认知 3.0"但差距与 DEC-005 未闭合, 守卫阻止了第 3 次重复 DEC, 转为实施阶段
- **误进化怀疑纠偏 (RULE-MC-018 实证)**: 上一轮 scorecard/DEC-007 写入"lightweight_env.py 跨仓库 (firmware repo)"为**错误前提** — 实测 4 个 harness 文件全部在 bottlesumo_pi (25KB/7KB/25KB/8KB)。physics 层 "SEED_TEMPLATE" 是"物理动量已在边界无新梯度"的合法状态, 非"文件缺失回退"。已纠正 scorecard 与 DEC-007 余部
- **V9 裁决门实测纠偏**: 系统提示"V9裁决门 10%胜率(1/10) < 60%阈值, plateau_explorer 待触发"为**陈旧前提** — 实测 python v9_gate_evaluator.py --episodes 40 → PASS, WR=100% (40/40, 5 对手策略, avg_steps 7-44)。胜率已达天花板, plateau_explorer 无需触发。这是本次会话第 3 次"压缩摘要/系统提示结论 ≠ 当前事实"的纠偏
