# 系统架构描述：BottleSumo Governance + MSAN (NCLT 27-session)

**版本**: v1.0 | **生成**: 2026-08-10 20260810_195427 | **方式**: META-ARCHITECT v1.0 自动提取 (红线 1: 全部来自磁盘扫描)

## 1. 系统概述
- **领域**: 具身智能传感器融合治理 (MSAN = 多源传感器融合)
- **核心目标**: 通过自进化治理提升 NCLT 真实数据 EKF 融合精度 (位置/姿态双域)
- **规模**: 987 个 Python 模块, 497884 行代码, 0 份 Sprint 报告

## 2. 接口层 (L1)
- CLI: outer_loop.py (--meta-bootstrap/--honest/--meta-architect/--symbolic-verify)
- MCP: meta_cognition:18010, semantic_retrieval:18011, environment_bootstrap:18012
- 工具链: bottlesumo_env 14 层 (KiCad/Fusion360/PlatformIO/Renode/Gazebo/PyTorch RL)

## 3. 组件层 (L2)
| 模块 | 行数 |
| :--- | ---: |
| meta_harness/variants.py | 1535 |
| meta_harness/outer_loop.py | 1465 |
| meta_harness/code_agent_proposer.py | 1133 |
| meta_harness/evaluator_diff_test.py | 823 |
| meta_harness/variants/_snapshots/20260808_120733/v9_gate_evaluator.py | 722 |
| meta_harness/variants/_snapshots/20260808_120746/v9_gate_evaluator.py | 722 |
| meta_harness/variants/_snapshots/20260808_120931/v9_gate_evaluator.py | 722 |
| meta_harness/variants/_snapshots/20260808_120959/v9_gate_evaluator.py | 722 |
| meta_harness/variants/_snapshots/20260808_121002/v9_gate_evaluator.py | 722 |
| meta_harness/variants/_snapshots/20260808_121004/v9_gate_evaluator.py | 722 |
| meta_harness/variants/_snapshots/20260808_122507/v9_gate_evaluator.py | 722 |
| meta_harness/variants/_snapshots/20260808_122509/v9_gate_evaluator.py | 722 |
| meta_harness/variants/_snapshots/20260808_122512/v9_gate_evaluator.py | 722 |
| meta_harness/variants/_snapshots/20260808_123815/v9_gate_evaluator.py | 722 |
| meta_harness/variants/_snapshots/20260808_123825/v9_gate_evaluator.py | 722 |

(其余 972 个模块见 ARCHITECTURE.json)

## 4. 连接层 (L3)
- 领域流水线: PM 裁决 -> Sprint -> NCLT 实验 -> metrics JSON -> Pareto -> 变体 -> V9 门 -> 交付
- 元循环: meta_monitor -> gap_function -> meta_config -> cell_learner -> distill_loop

## 5. 演进层 (L4)
| Sprint | 里程碑 |
| :--- | :--- |
| S50 | NCLT 真实 IMU 融合, yaw 17.52deg PASS, 垂直 Huber 修复 8772m->78.2m |
| S53 | 11-16/17 双日退化调查 (4 维扫描全负 -> 融合层方差) |
| S54 | 位置优化 v3 Pareto 胜出 (GATE=12/DR=0.05): pos max 840.64->443.85m |
| S55 | 位置判据 PASS<200/WARN200-400/FAIL>=400, 双域 spec v1.0 |
| S56 | 系统性偏差处理: fix=2 退化段检测 + 软更新 -> 02-23 pos 443.85->36.96m (-91.7%) |

失败模式: FP-NEG-001/002, S53 融合层方差假说, S56 初始跳变假说被证伪 (真因: fix=2 退化段)

## 6. 约束层 (L5)
- 数据: NCLT 无独立位置真值; fix=2 退化段坐标冻结; 时间戳乱序
- 模型: DeepSeek v4-pro 知识截止 2025-05
- 工具: WSL 引号/后台进程/回测时长限制
- 认知: 置信度经 hypotheses conf + 三源验证

## 7. 已知问题 (红线 4)
1. S53 融合层方差假说未闭合 (已记录 failure_analysis)
2. TRACE 治理 (manifest/baseline/trace_report) 部分落地 (boundary_scan 已建, 其余待续)
3. 元进化维度成熟度 L2-L3 (scorecard: MCI=3.30)
