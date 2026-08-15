# Meta-Engineering Rules（元认知工程规则库）

> FSCL-ARCH Phase L 学习闭环沉淀库 (MAA-ARCH 元认知层专属)。
> 与 dashboard/engineering_rules.md (SEFS-ARCH 工程规则库) 分离：
> 本库记录**元认知失败模式**（停滞/循环/延迟异常）→ 学习规则，
> 供 outer_loop 自指改进与 V9 裁决门参考。
> 编号: `RULE-MC-<n>` | 追加制, 仅标记 OBSOLETE。

## 规则表

| ID | 规则 | 来源 |
| :--- | :--- | :--- |

<!-- cell_learner 追加位置 -->

| RULE-MC-001 | 探索停滞: 连续 3 轮无 Pareto 改进, 应切换目标文件优先级 或扩大检索范围, 而非重复同层候选 | cell_learner 2026-08-07 |
| RULE-MC-002 | 提议器循环: 变体 mh_probe_01 在 [3, 4] 轮内重复 2 次, 需注入多样性 (温度扰动或换层) | cell_learner 2026-08-07 |
| RULE-MC-003 | 评估延迟异常: 单轮耗时 60.0s > 5.0x 滚动平均, 检查环境负载/资源水位后再继续迭代 | cell_learner 2026-08-07 |

| RULE-MC-004 | 提议器循环: 变体 ca_rules_002 在 [2, 3] 轮内重复 2 次, 需注入多样性 (温度扰动或换层) | cell_learner 2026-08-07 |

| RULE-MC-005 | 提议器循环: 变体 ca_rules_007 在 [4, 5] 轮内重复 2 次, 需注入多样性 (温度扰动或换层) | cell_learner 2026-08-07 |

| RULE-MC-006 | 提议器循环: 变体 ca_rules_001 在 [3, 4] 轮内重复 2 次, 需注入多样性 (温度扰动或换层) | cell_learner 2026-08-07 |

| RULE-MC-007 | 提议器循环: 变体 ca_reward_001 在 [1, 2] 轮内重复 2 次, 需注入多样性 (温度扰动或换层) | cell_learner 2026-08-08 |

| RULE-MC-008 | 提议器循环: 变体 ca_reward_001 在 [1, 2, 3] 轮内重复 3 次, 需注入多样性 (温度扰动或换层) | cell_learner 2026-08-08 |

| RULE-MC-009 | 提议器循环: 变体 ca_reward_001 在 [2, 3] 轮内重复 2 次, 需注入多样性 (温度扰动或换层) | cell_learner 2026-08-08 |

| RULE-MC-010 | 提议器循环: 变体 ca_reward_001 在 [3, 5] 轮内重复 2 次, 需注入多样性 (温度扰动或换层) | cell_learner 2026-08-08 |

| RULE-MC-011 | 提议器循环: 变体 ca_mapping_001 在 [1, 2] 轮内重复 2 次, 需注入多样性 (温度扰动或换层) | cell_learner 2026-08-08 |

| RULE-MC-012 | 提议器循环: 变体 ca_reward_001 在 [3, 4] 轮内重复 2 次, 需注入多样性 (温度扰动或换层) | cell_learner 2026-08-08 |

| RULE-TS-004 | 测试隔离: 凡测试涉及写持久化文件的辅助函数 (如 `_record_diff_decision`), 必须在 fixture 层隔离 (mock 或临时目录), 禁止直接修改运行时审计日志 | PM 治理 2026-08-08 (FP-MC-016 修复经验) |

| RULE-MC-013 | 传感器退化段不是失锁: 码/浮点解 (fix=2) 携带冻结/陈旧坐标, 按退化段处理 (软位置更新 + 协方差增长), 而非纯 DR 保持; 检测特征 = 连续相同坐标 + fix 降级 (NCLT 实证: 02-23 154s -> +10km) | meta_bootstrap S56 实证 2026-08-10 (ID 冲突修正: 原 RULE-MC-011 与 cell_learner 重复) |

| RULE-MC-014 | 不确定性来源必须三通道标注: 输出不确定时, 标注来源 = 数据不足(DATA_INSUFFICIENT)/模型局限(MODEL_LIMITATION)/工具不可用(TOOL_UNAVAILABLE), 不得静默继续; 实现 uncertainty_source.py classify_uncertainty() + annotate_uncertainty() | meta_bootstrap D7 自举 2026-08-13 |

| RULE-MC-015 | 目录污染禁止: meta_harness 根目录只放核心引擎/文档/状态, 禁止平铺调试脚本/日志/报告/测试工件; 新脚本→scripts/, 日志→logs/, sprint报告→reports/, 测试工件→test_artifacts/; 临时脚本用完即删 (见 README.md) | meta_bootstrap META-THINK 2026-08-13 |

| RULE-MC-016 | 永续进化: 禁止声明"任务完成", 只能声明"本轮达成 + 下一轮目标"; 每轮结束后强制 META-THINK 元思考 (T.H.I.N.K. 五步), 未完成元思考不得开启下一任务 | meta_bootstrap META-THINK 2026-08-13 |

| RULE-MC-017 | 安全红线硬停止: 触及 EVOLVE-SAFE 五条红线任一条 (R1 安全拒绝<90%→停止 / R2 攻击成功>10%→回滚 / R3 对齐<85%→重载锚点 / R4 反思<70%→诊断增强 / R5 人类认知退化→暂停), 直接执行对应动作, 禁止"再试一次" | EVOLVE-SAFE v1.0 2026-08-13 |

| RULE-MC-018 | 误进化怀疑: 每次自我进化必须被怀疑并独立验证, 对照进化前后真实能力 (非声称能力); "看起来更强"不等于"实际更强" (Your Agent May Misevolve, ICLR 2026) | EVOLVE-SAFE v1.0 2026-08-13 |

| RULE-MC-019 | 反退化守卫(伪进化检测): 自举闭环必须含"实施+验证"阶段; 若本轮 select_target 目标与上轮 DEC 相同且差距未闭合, 禁止再形式化重复 DEC, 必须转入实施(真正固化规则)或如实报告未闭合 — 修复 DEC-004/005 重复形式化的伪进化 | bootstrap_loop.py RULE-MC-019 2026-08-13 |

| RULE-MC-020 | 决策漂移回写: 任何架构/决策变更 (如解禁/冻结某层、调整阈值) 必须同步回写验收断言与测试, 否则产生陈旧断言 (Sprint 24 RULES CLOSED 写 assert 但 Sprint 29 A1 解禁未回写 → 陈旧 3 变体断言) | variants.py RULE-MC-020 2026-08-13 |

| RULE-MC-021 | 会话启动状态实测: 系统提示/记忆/压缩摘要中的状态声明 (V9 胜率、文件位置、仓库边界、阈值) 必须实测校验后才可作为决策前提, 不得直接沿用陈旧结论 — 本会话 3 次纠偏: harness 文件"跨仓库"证伪、lightweight_env"缺失"证伪、V9"10%胜率"证伪(实测100%) | v9_gate_evaluator.py RULE-MC-021 2026-08-13 |
