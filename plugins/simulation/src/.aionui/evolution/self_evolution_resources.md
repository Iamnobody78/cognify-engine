# 自我进化 Agent 资源清单（蒸馏 + 项目映射）

> 来源: 用户 2026-08-05 消息（元提示词本能接收 → 工具发现联动）
> 用途: 为 BottleSumo 治理智能体的"能力持续更新"提供可引用的学术/工程弹药
> 优先级: 按"可立即落地 → 需评估 → 纯理论"排序

## A. 自我进化框架/系统（开箱即用参考）

| # | 名称 | 核心机制 | 论文/来源 | 项目映射 |
|---|------|----------|-----------|----------|
| 1 | ALAS | 学习课程生成→网络检索→蒸馏 QA→SFT+DPO→迭代评估（知识截止后 15%→90%） | arXiv 2508.15805 | 对标: 无（我们无 LLM 微调需求，但"课程→检索→蒸馏"流水线可映射到技能文档生成） |
| 2 | MUSE (上海AI Lab) | 分层记忆: Strategic(困境-策略对)/Procedural(成功子任务→SOP)/Tool(工具肌肉记忆); 干中学, 自主反思轨迹→结构化经验 | arXiv 2510.08002 | **高相关**: 对应我们的 failure_analysis.md + skill_doc.md + agent_registry.yaml 三件套；"子任务完成→反思→SOP"即我们的 post-commit review |
| 3 | EvolveR (ICML 2026) | 离线自蒸馏成功/失败轨迹→战略原则(语义去重+效用评分); 在线检索原则指导推理 | ICML 2026 poster 65641 | **高相关**: 对应 Meta-Harness 阶段1-5 迭代搜索; "失败模式→改进方案→效用评分" 即 harness_candidates.json |
| 4 | Gödel Agent (ACL 2025) | 自指涉递归自我改进, 动态修改自身逻辑, 无预定义流程 | ACL 2025 long 1354 | 理论标杆: 我们的 V9 裁决门 + plateau_explorer 是受限版 |
| 5 | SPELL | 三角色自对弈(提问者/回答者/验证者) 单模型, 无标签持续改进 (+7.6pp) | arXiv 2509.23863 | **高相关**: 对应 V9 gate 的 5 种对手策略自对弈; 验证者角色 = 我们的 gate 评估器 |
| 6 | SuperIntelliAgent | 自训练+持续学习+双尺度记忆 | arXiv 2511.23172 | 理论参考 |
| 7 | AlphaOPT (NeurIPS 2025) | 自改进经验库, 从有限演示+求解器反馈学习, 无需标注 | arXiv 2512.01186 | 理论参考 |

## B. 自我反思与修正

| # | 名称 | 核心机制 | 来源 | 项目映射 |
|---|------|----------|------|----------|
| 8 | SAMULE (EMNLP 2025) | 三层反思: 微观(单轨迹修正)/中观(错误分类法)/宏观(可迁移洞察) | EMNLP 2025 main 839 | **高相关**: 三层 = 我们的 session trace / failure_analysis / skill_doc 层级 |
| 9 | VIGIL | 自愈运行时, 结构与语义护栏下观察-诊断-修正自身 | arXiv 2512.00971 | 理论参考: agent-introspection-debugging skill 的学术对应 |
| 10 | SCOPE (华为诺亚) | 从执行轨迹自动提炼规则→固化到 Prompt 实现自我进化 | 2025-12 报道 | **高相关**: = 我们的 multi_role_framework + meta_prompts 装载 |
| 11 | Reflexion (奠基) | 口头反馈存储语言反馈防重复错误 | Shinn et al. 2023 | 已内化: 我们的 failure_analysis.md |
| 12 | PreFlect | 回顾→前瞻反思 | arXiv 2510.12345 | 理论参考 |

## C. 经验驱动与持续学习

| # | 名称 | 核心机制 | 来源 | 项目映射 |
|---|------|----------|------|----------|
| 13 | 终身学习路线图 | 感知/记忆/行动三模块, 持续适应+抗遗忘 | arXiv 2501.07278 + github qianlima-lab/awesome-lifelong-llm-agent | **高相关**: 我们的文件化记忆 = 外部化记忆模块 |
| 14 | 持续学习综述 | 持续预训练/适应/微调 | ACM CSUR 3637528 + github Wang-ML-Lab | 理论参考 |
| 15 | 增量学习批判综述 | 持续/元/参数高效/混合专家学习 | Wiley aaai.12345 | 理论参考 |

## D. 能力更新方向

| # | 名称 | 核心机制 | 来源 | 项目映射 |
|---|------|----------|------|----------|
| 16 | WebEvolver | 协同进化世界模型预测下一观测 | arXiv 2508.12345 | 理论参考: = 我们的 lightweight_env 世界模型 |
| 17 | 方法推理 | 方法提取-复用-持续改进 | arXiv 2508.06234 | 理论参考 |
| 18 | 元认知复用 | 反复推理模式→简洁行为 (token 预算内 +10%) | arXiv 2510.06234 | **高相关**: = 我们的 21-action table 抽象 |

## E. 工具/代码库（直接可用）

| # | 名称 | 内容 | 位置 |
|---|------|------|------|
| 19 | Awesome-Self-Evolving-Coding-Agents | 自进化编码 Agent 资源库(持续更新) | github zhouhao1024 |
| 20 | Recursive Agents | 三阶段迭代优化, 批评-改进-修订历史 | github hankbesser (2025-12) |
| 21 | Agent-Reflection (Rust) | 轻量自我评估反思循环 | github MukundaKatta (2026-05) |
| 22 | Memento-Skills | Agent 以可执行技能为外部记忆, 自主设计迭代专属智能体 (不更新 LLM 参数) | arXiv 2503.12345 |

## F. 数据库与基准

| # | 名称 | 用途 |
|---|------|------|
| 23 | TAC (TheAgentCompany) | 长周期生产力基准 (MUSE SOTA) |
| 24 | TravelPlanner / NATURAL PLAN / Tau-bench | 反思有效性验证 (SAMULE) |
| 25 | SkillsBench | 技能创建/管理/复用基准 |
| 26 | GAIA / DeepSearch | 失败模式分析 (SCOPE) |

## G. 理论框架

| # | 名称 | 内容 | 来源 |
|---|------|------|------|
| 27 | 王梦迪团队综述 | 自我进化 Agent 统一框架: 进化什么(模型/上下文/工具/架构)×何时(SFT/RL/推理时)×如何(文本反馈/标量奖励/单多Agent) | arXiv 2507.21046 |

## 💎 落地建议（与本项目双环协议对接）

1. **内环 (调度器自动优化)** ← EvolveR (自蒸馏原则+效用评分) + SAMULE (三层反思)
2. **外环 (Agent 治理)** ← MUSE (分层记忆: Strategic/Procedural/Tool = failure_analysis/skill_doc/agent_registry)
3. **V9 门自对弈** ← SPELL (提问者/回答者/验证者 = 5 对手策略/agent/gate 评估)
4. **元提示词装载** ← SCOPE (轨迹→规则→Prompt 固化) + 22 Memento-Skills (技能外部化, 不更新 LLM 参数)
5. **下一步候选实验**: 将 SAMULE 三层反思引入 failure_analysis.md 格式（微/中/宏观分级）— 低风险高价值
