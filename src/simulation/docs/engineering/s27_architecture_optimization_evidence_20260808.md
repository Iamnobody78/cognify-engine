# Sprint 27 架构优化证据矩阵 — 归档

> **Sprint**：27（评估器信号融合 / 代理蒸馏 / MCP 生态 / 种子生成锚点 四维学术对齐）
> **日期**：2026-08-08
> **依据**：PM Sprint 27 裁决附带的资源矩阵归档请求
> **状态**：COMPLETE（归档 + 与 Sprint 27 实证的映射关系）

---

## 一、评估器信号融合（M2 方向深化）

### 核心论文
| 论文 | 关键洞察 | 与本项目映射 |
| :--- | :--- | :--- |
| **Meta-Harness**（arXiv:2603.28052） | 现有文本优化器"无状态、仅依赖标量分数、反馈压缩激进"是根本缺陷 | M2 多信号融合（winrate+steps+layer_signal→Q 三档）的理论根基 |
| **Weak-for-Strong (W4S)**（arXiv:2504.04785） | 7B 元智能体调度强模型（RLAO），超越基线 2.9%~24.6%，仅 1 GPU 小时 | 与"用弱信号融合替代单一大模型判定"一致 |
| **Better Harnesses, Smaller Models**（arXiv:2607.08938） | SLM 在适配 harness 下匹配 LLM，成本降 90% | 失败轨迹自动发现 harness 适配策略 |
| **SEAL**（arXiv:2605.30104） | LLM-as-Meta-Judge 从饱和基准提取排序信号（0.83-1.00 Spearman） | **饱和不是任务固有属性，是评估分辨率局限**——S25/S26 mapping winrate 恒 1.00 失敏的解法参照 |

### 源码库
- stanford-iris-lab/meta-harness（Evaluator 协议；`evaluator_diff_test.py` 是其增强版）
- angrysky56/meta-harness（Hermes/Ollama 本地部署，与本项目一致）
- canvas-org/meta-agent（评估器 harness 调优：tau-bench v3 67%→87%）
- meta-harness-tbench2-artifact（Terminal-Bench 2.0 76.4%）

### 基准
- **Agent Island**（arXiv:2605.04312）：999 场动态游戏规避静态基准饱和——mapping/physics winrate 恒 1.00 饱和失敏根因参照
- SEAL 基准套件

### Sprint 27 实证映射
- **SUSPICIOUS 三档细化（S24）** 已落实 Meta-Harness "多信号替代标量"；
- **S25/S26 阶梯 Q=0.02→0.04 的可解析性** 证明 M2 能感知 0.01 级差异（SEAL 饱和判据）——但 mapping 层行为影响力饱和需换轴（已实证）

## 二、代理蒸馏（B 方向）

### 核心论文
| 论文 | 关键洞察 | 与本项目映射 |
| :--- | :--- | :--- |
| **EvolveR**（ICML 2026） | 经验驱动自蒸馏：成功/失败轨迹→简洁策略原则→检索指导 | 与 CELL 学习闭环（失败→engineering_rules）架构一致 |
| **Knowledge-Centric Self-Improvement**（arXiv:2607.19592） | 知识跨智能体/任务分布迁移 | M2 判定蒸馏为持久规则（不依赖特定智能体） |
| **Inference-Time Distillation** | ALFWorld 2.5 倍低成本匹配教师 | 轻量级蒸馏工程范式 |
| **OPD-Evolver**（arXiv:2606.20475） | 慢-快协同进化（记忆层次+on-policy 自蒸馏） | P2 蒸馏管道设计参照 |

### 源码库
- Edaizi/EvolveR、shidingz/EDV（Execute-Distill-Verify）、AgentArk

### Sprint 27 实证映射
- B 方向（M2 判定纳入蒸馏管道）仍延后——A（mapping 换锚点）未产生 PASSED，蒸馏缺正样本。
  Sprint 27 的 FP-NEG-002（死代码扰动）可作为 **EvolveR 负样本**（失败轨迹→原则："mapping 扰动须检查规则前提可达性"）

## 三、MCP 生态与工具调用（架构对齐）

### 核心论文
| 论文 | 关键洞察 | 与本项目映射 |
| :--- | :--- | :--- |
| **MCP-AgentBench**（AAAI 2026） | SOTA 模型 MCP 工具调用性能局限 | 验证 `--mcp-integration` 默认启用决策 |
| **OSWorld-MCP** | MCP 工具通常提升任务成功率 | MCP 服务器集成实证 |
| **ETOM**（EACL 2026 Findings） | 五级多跳端到端工具编排基准 | 评估 MCP 调用质量 |
| **DynamicMCPBench**（arXiv:2607.20531） | 轨迹锚定+效果评分实时基准 | 对应 `mcp_usage_report.jsonl` 监控 |
| **MCP Ecosystem Measurement** | 2024/11-2026/02 监测 177,436 个 MCP 工具 | 生态规模实证 |

### 源码库
- MCP-Universe、MCPToolBench++（4,000+ 服务器）、LiveMCPBench（KDD 2026）

## 四、种子生成与锚点修复（A 方向支撑）

### 核心论文
| 论文 | 关键洞察 | 与本项目映射 |
| :--- | :--- | :--- |
| **ANCHOR**（arXiv:2602.07153） | 轨迹扩展：已验证种子演示→可扩展监督 | `_seed_variants` 种子生成一致 |
| **StaAgent** | 缺陷检测规则→诱发缺陷的种子程序 | 动态锚点机制 |
| **AgentGA** | 智能体-种子空间进化 | agent-seed optimization 实用设计点 |
| **InfCode** | 对抗性多智能体 79.4% 解决率 | 种子生成→验证闭环 |

### Sprint 27 实证映射
- **FP-NEG-002 教训**（规则前提可达性检查）是 StaAgent/ANCHOR 思想的补强：种子扰动前须验证目标分支的可达性（前提不互斥）

## 五、对齐总结（Sprint 27 → Sprint 28 行动）

| 维度 | 理论锚定 | Sprint 28 行动 |
| :--- | :--- | :--- |
| 评估器信号融合 | SEAL（饱和分辨率）+ Meta-Harness（多信号） | 保持 M2 三档；mapping 层换轴后重测 |
| 代理蒸馏 | EvolveR + EDV | B 解锁条件：A 产生 PASSED 或 V9 门触发 |
| MCP 生态 | MCP-AgentBench + DynamicMCPBench | 维持 `--mcp-integration` 监控 |
| 种子生成/锚点 | ANCHOR + StaAgent + **FP-NEG-002** | 第三轴 TURN_*_MED 轮速增益（跨层联动锚点）前做可达性检查 |

**关键洞察（与 Sprint 27 实证直接相关）**：
1. SEAL 证明"饱和是评估分辨率局限"——S25/S26 的 mapping 角度轴饱和（0.005 Q/度）正是分辨率局限，换轴（flank 距离→转向增益）是正确响应
2. EvolveR 经验闭环与 CELL 一致——FP-NEG-002 死代码扰动应沉淀为 engineering_rules："mapping 层候选锚点必须通过规则前提可达性检查"
3. MCP-AgentBench 验证 `--mcp-integration` 默认启用的必要性
4. Agent Island 的 winner-take-all 动态游戏与 BottleSumo 竞技场同构——winrate 恒 1.00 的失敏需多信号融合（M2 已落地）

## 关联归档
| 文档 | 路径 |
| :--- | :--- |
| 帕累托前沿 | `governance/meta_harness/pareto_frontier.md`（Sprint 27 三轴图谱） |
| 失败分析 | `governance/meta_harness/failure_analysis.md`（FP-NEG-002 + flank 双侧 REGRESSION） |
| 路线图 | `docs/architecture/ROADMAP_v2.md`（11.22 Sprint 27） |
| 跨领域证据 | `docs/engineering/s18_s26_cross_domain_evidence_20260808.md` |
