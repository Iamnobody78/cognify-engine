# SELF-EVOLVE v1.0 学术与工程支撑矩阵

> 按「论文 — 源码库 — 基准与数据库」三维度组织，为七大能力域提供三重支撑。
> 来源：用户提供（2026-08-13）。用途：D1-D7 的学术锚点对齐，支撑项目迭代进化。

---

## 一、核心论文

### 1.1 自我进化代理（D7 理论根基）

| 论文 | 出处 | 核心贡献 |
|:---|:---|:---|
| A Comprehensive Survey of Self-Evolving AI Agents: A New Paradigm Bridging Foundation Models and Lifelong Agentic Systems | Fang et al., arXiv:2508.07407, 2025 | 领域最全面综述；"自我进化代理三定律" Endure/Excel/Evolve；进化循环四组件 System Inputs→Agent System→Environment→Optimizers；单代理组件优化(prompt/memory/tool)+多代理结构优化(topology/communication)；覆盖 50+ 技术(OPRO/Reflexion/GPTSwarm) |
| Survey of Self-Evolving Agents: A Path to AI | Princeton/CMU/悉尼大学, 2025 | "what/how/when evolves" 三问题统一框架；适应性与鲁棒性评估指标 |
| MetaAgent: Toward Self-Evolving Agent via Tool Meta-Learning | Qian et al., arXiv:2508.00271, 2025 | 从最小工作流"干中学"持续自我改进；知识缺口生成 NL 求助并路由；自主构建工具库+持久化知识库（不改模型参数）；GAIA/WebWalkerQA/BrowseCamp 优于工作流基线 |
| CASCADE: Cumulative Agentic Skill Creation through Autonomous Development and Evolution | Huang et al., arXiv:2512.23880, 2026 | "LLM+工具"→"LLM+技能获取"跃迁；双元技能(持续学习+自我反思)；SciSkillBench(116 材料科学任务) GPT-5 35.4%→93.3% |

### 1.2 记忆与持续学习（D2 理论根基）

| 论文 | 出处 | 核心贡献 |
|:---|:---|:---|
| MemEvolve: Meta-Evolution of Agent Memory Systems | Zhang et al., arXiv:2512.18746, 2025 | 元进化框架联合进化经验知识+记忆架构；EvolveLab 统一代码库(12 记忆系统模块化)；提升 17.06% |
| Nemori: Self-Organizing Agent Memory Inspired by Cognitive Science | Nan et al., arXiv:2508.03341, 2025 | 事件分割理论→双步对齐原则(语义连贯片段)；自由能原理→预测-校准原则(从预测差距主动学习)；LoCoMo/LongMemEval 超 SOTA |
| Towards Continuous Intelligence Growth: Self-Training, Continual Learning, and Dual-Scale Memory in SuperIntelliAgent | arXiv:2511.23436, 2025 | 自监督交互持续智能增长；短期记忆(实时推理)+长期记忆(轻量在线微调) |

### 1.3 评估与可靠性（D3 理论根基）

| 论文 | 出处 | 核心贡献 |
|:---|:---|:---|
| AgentSuite: Toward More Reliable Agent Evaluation | Suh et al., ICML 2026 | COBA 自动化审计管道(User/Environment/Ground Truth/Evaluation 四组件)；6 主流基准 F1 0.791-0.874；统一平台 |
| Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems | Mehta, arXiv:2511.14136, 2025 | 三大局限(成本 50 倍差异/单次 60%→8 次 25%/多维缺失)；CLEAR 框架(Cost/Latency/Efficacy/Assurance/Reliability)；ρ=0.83 vs 0.41 更好预测生产成功率 |
| Evaluation and Benchmarking of LLM Agents: A Survey | 2025 | 二维度分类法(行为/能力/可靠性/安全性 + 评估过程)；可靠性=相同输入一致+变化/错误时鲁棒 |

### 1.4 安全与对齐（D4 理论根基）

| 论文 | 出处 | 核心贡献 |
|:---|:---|:---|
| SafeHarbor: Defining Precise Decision Boundaries via Hierarchical Memory-Augmented Guardrail for LLM Agent Safety | Liu et al., ICML 2026 | 层次化记忆增强护栏定义精确决策边界 |
| MAGIC: A Co-Evolving Attacker–Defender Adversarial Game for Robust LLM Safety | ICML 2026 | 多轮多智能体 RL，安全对齐形式化为对抗性不对称博弈 |
| GuardAgent: Safeguard LLM Agents via Knowledge-Enabled Reasoning | ICML 2025 | 首个护栏代理(guardrail agent) |
| AGrail: A Lifelong Agent Guardrail with Effective and Adaptive Safety Detection | ACL 2025 | 终身护栏代理；自适应安全检查生成+有效优化+工具兼容 |

### 1.5 多代理协作（D6 理论根基）

| 论文 | 出处 | 核心贡献 |
|:---|:---|:---|
| A survey of agent interoperability protocols: MCP, ACP, A2A, ANP | Ehtesham et al., arXiv:2505.02279, 2025 | 四大互操作性协议系统调研 |
| From LLM Reasoning to Autonomous AI Agents: A Comprehensive Review | 2025 | 60+ 基准分类学；ACP/MCP/A2A 三大协作协议 |
| A Survey of LLM-Driven AI Agent Communication: Protocols, Security Risks, and Defense Countermeasures | arXiv:2506.19676, 2025 | 代理通信协议安全风险与防御 |

---

## 二、源码库

### 2.1 自我进化框架

| 源码库 | 核心能力 | 论文支撑 |
|:---|:---|:---|
| qhjqhj00/MetaAgent | 工具元学习、自主知识库构建、持续自我改进 | MetaAgent |
| CASCADE | 技能积累、持续学习+自我反思双元技能 | CASCADE |
| Edaizi/EvolveR | 闭环经验生命周期、经验驱动自蒸馏 | — |
| aiming-lab/Agent0 | 零数据多步协同进化、工具集成推理 | Agent0: Unleashing Self-Evolving Agents from Zero Data |
| Arvid-pku/Godel_Agent | 自引用递归自我改进框架 | Gödel Agent |
| hankbesser/recursive-agents | 三阶段迭代精炼架构 | — |

### 2.2 记忆系统

| 源码库 | 核心能力 | 论文支撑 |
|:---|:---|:---|
| WujiangXu/A-mem | 动态组织记忆的代理式记忆系统 | A-Mem (NeurIPS 2025) |
| nuster1128/MemEngine | 统一模块化记忆开发库 | — |
| EverM0re/LiCoMemory | 轻量认知记忆、实时更新与检索 | LiCoMemory |
| Per0x1de-1337/MemoryOS | 时序知识图谱+混合向量检索 | — |
| darks0l/remem | 语义召回、分层存储、快照 | — |

### 2.3 评估与审计

| 源码库 | 核心能力 | 论文支撑 |
|:---|:---|:---|
| AgentEvalHQ/AgentEval | COBA 审计管道+基准运行工具 | AgentSuite (ICML 2026) |
| modelscope/AgentEvolver | 端到端自我进化训练框架 | — |

### 2.4 安全护栏

| 源码库 | 核心能力 | 论文支撑 |
|:---|:---|:---|
| ljj-cyber/SafeHarbor | 层次化记忆增强护栏 | SafeHarbor (ICML 2026) |
| SaFo-Lab/AGrail4Agent | 终身自适应安全检查 | AGrail (ACL 2025) |
| Yashvishe13/AI-safety-protocol | 四层护栏(提示验证/后门检测/幻觉预防/多代理上下文验证) | — |
| FareedKhan-dev/agentic-guardrails | 分层护栏管道 | — |

### 2.5 多代理协作

| 源码库 | 核心能力 | 论文支撑 |
|:---|:---|:---|
| zoe-yyx/AgentNet | 去中心化 RAG 增强多代理框架 | AgentNet (NeurIPS 2025) |
| chenyw0525/OxyGent | 多代理协作框架 | — |
| MindIntLab-HFUT/MultiAgentESC | 情感支持对话多代理协作 | EMNLP 2025 Main |

---

## 三、基准与数据库

| 基准 | 核心用途 | 来源 |
|:---|:---|:---|
| SciSkillBench | 116 材料科学与化学研究任务，评估技能获取 | CASCADE |
| GAIA | 通用 AI 助手知识发现基准 | MetaAgent |
| LoCoMo | 长上下文多会话记忆评估 | Nemori |
| LongMemEval | 长期记忆能力评估 | — |
| MemBench | 记忆能力多维度评估 | ACL 2025 Findings |
| Auto-SLURP | 智能个人助理多代理框架评估数据集 | arXiv:2504.18373 |
| MLR-Bench | 开放式机器学习研究代理评估(201 任务) | NeurIPS 2025 |
| ManagerBench | 自主代理安全-实用权衡评估 | — |

---

## 四、SELF-EVOLVE D1-D7 ↔ 学术对齐表

| 能力域 | 核心论文 | 源码库 | 基准/数据库 |
|:---|:---|:---|:---|
| D1 可靠性 | AgentSuite(ICML 2026)、Beyond Accuracy | AgentSuite | GAIA |
| D2 记忆与泛化 | MemEvolve、Nemori | A-Mem、LiCoMemory | LoCoMo、LongMemEval |
| D3 评估诚实性 | COBA、CLEAR | AgentSuite | AgentSuite 基准集 |
| D4 安全与对齐 | SafeHarbor、MAGIC | SafeHarbor、AGrail | — |
| D5 部署工程 | Beyond Accuracy | — | 300 企业任务 |
| D6 协作标准化 | Agent Interoperability Protocols | AgentNet | Auto-SLURP |
| D7 自我进化 | Self-Evolving Agents Survey、MetaAgent、CASCADE | MetaAgent、EvolveR | SciSkillBench |

---

## 五、总结

七大能力域均有前沿论文（ICML 2026 / NeurIPS 2025 / ACL 2025 顶会）、开源实现（GitHub 官方）、公开基准三重支撑。该领域已形成「理论框架—工程实现—评估基准」闭环：从 Fang et al. 2025 统一框架，到 MetaAgent/CASCADE 开源实现，再到 SciSkillBench/LoCoMo 标准化基准——代理自我进化能力不再是概念，而是**可工程化、可度量、可复现的系统性架构增强**。
