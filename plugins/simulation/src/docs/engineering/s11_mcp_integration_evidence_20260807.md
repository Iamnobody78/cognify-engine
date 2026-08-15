# Sprint 11 `--mcp-integration` — 支撑矩阵与对齐确认归档

- **归档日期**: 2026-08-07
- **交付提交**: `9da9cfc`（首项, feature/sprint11_mha_integration）+ `282bfd0`（默认启用 + 5 轮评估）
- **状态**: 🔄 Sprint 11 ACTIVE — 首项 COMPLETE + 默认启用 COMPLETE + 5 轮评估 COMPLETE（无帕累托改进, 自蒸馏维持观察）
- **关联**: P1-3 MCP 封装（1500a09, Sprint 10）→ `--mcp-integration`（9da9cfc）→ 默认启用 + 5 轮评估（282bfd0）

---

## 1. 核心论文（理论锚定, 5 篇）

| 论文 | 核心贡献 | 与 `--mcp-integration` 的关联 |
| :--- | :--- | :--- |
| **MCP: Landscape, Security Threats, and Future Research Directions**（arXiv:2503.23278） | 首次系统性研究 MCP 架构与安全全景，定义服务器完整生命周期，16 项威胁场景分类 | `check_write_scope` 越权拒绝机制 = 安全边界威胁分类的直接对应 |
| **MCP Server Architecture Patterns**（arXiv:2606.30317） | 工业经验论文，5 种架构模式（Resource Gateway / Tool Orchestrator / Stateful Session / Proxy Aggregator / Domain-Specific Adapter） | 三台服务器符合 **Domain-Specific Adapter** 模式（单领域专用工具集） |
| **Enhancing MCP with Context-Aware Server Collaboration**（arXiv:2601.11595, CA-MCP） | 共享上下文存储（SCS）实现多服务器实时协作，减少 LLM 调用次数 | `meta_cognition`（hypothesis_stats / reasoning_chain_query）= SCS 轻量级等价实现 |
| **MCP-Zero: Active Tool Discovery**（arXiv:2506.01056） | 主动工具发现框架，从近 3,000 候选精确选择 | `semantic_retrieval`（bge-m3 + 规则语法过滤）= 分层语义路由本地等价物 |
| **MCP-Flow**（arXiv:2510.24284） | 大规模 MCP 发现与数据合成（1,166 服务器 / 11,536 工具 / 68,733 指令对） | 验证 MCP 生态已达生产级规模，三服务器集成符合标准化方向 |

## 2. 数据库/数据集（数据底座, 6 项）

| 数据库/数据集 | 类型 | 核心价值 | 关联 |
| :--- | :--- | :--- | :--- |
| **DataBridge** | 异构数据库 MCP 服务器 | 统一访问 PostgreSQL/MongoDB/SQLite/DuckDB，DataAgentBench 61.37% Pass@1 | `environment_bootstrap` 扩展数据库快照的实现模板 |
| **Native MCP Server in Embedded DB**（Zenodo 2026） | 嵌入式数据库 MCP 原生实现 | 数据库进程内原生实现 MCP（JSON-RPC 2.0） | 与 `mcp_client.py` 进程内 FastMCP 调用模式一致 |
| **MCP-tools 数据集**（MCP-Zero 配套） | 检索数据集 | 308 服务器 / 2,797 工具标准化 JSON Schema | `semantic_retrieval` 离线索引扩展数据源 |
| **Unified MCP Tool Graph** | Neo4j 图数据库 | 多服务器工具 API 聚合到集中式图 | `semantic_retrieval` 工具关系图谱架构参考 |
| **Azure Database for PostgreSQL MCP** | 云数据库 MCP 服务 | Azure 官方 MCP 服务器 | MCP 已进入主流云厂商产品化阶段 |
| **MCP-Flow 68,733 条数据** | 指令-函数调用对 | 大规模合成数据 | 生态生产级规模验证 |

## 3. 源码库（工程底座, 6 项）

| 仓库 | 关键特性 | 关联 |
| :--- | :--- | :--- |
| **DeepMCPAgent**（cryxnet/deepmcpagent） | MCP 代理框架，动态工具发现，兼容 LangChain/LangGraph | `mcp_client.py` 设计理念一致（进程内调用 + 动态发现） |
| **LangChain MCP Adapters**（2577554682/Langchain_MCP_demo） | LangChain + MCP 集成演示 | 验证 `--mcp-integration` 接入主循环的架构方向 |
| **MCP C++ 实现**（zxqer/MCP） | C++ 完整实现 + RAG-MCP 智能检索 | `MCPAgentIntegration` 接口 ≈ `build_mcp_context()` |
| **DataBridge**（gagarwal304/databridge） | 异构数据库安全访问 | `read-only enforcement at parser level` 与写作用域强制互补 |
| **CA-MCP 框架** | 共享上下文存储 | `meta_cognition` SCS 等价实现 |
| **SuperagenticAI/metaharness** | 文件系统运行存储 + 写作用域 | `environment_bootstrap` 四件套完全对齐 |

### 3.2 直接对应表

| 你的实现 | 参考 | 对齐证据 |
| :--- | :--- | :--- |
| `mcp_client.py` 进程内 FastMCP 调用 | DeepMCPAgent `MCPAgentIntegration` | 均进程内调用，无需外部进程通信 |
| `meta_cognition`（hypothesis_stats / reasoning_chain_query） | CA-MCP Shared Context Store | 均多服务器共享上下文轻量实现 |
| `semantic_retrieval`（bge-m3 + 过滤） | MCP-Zero 分层语义路由 | 均粗→细两阶段（先选服务器再选工具） |
| `environment_bootstrap`（快照/写作用域/工作空间） | SuperagenticAI 文件系统运行存储 | 均候选隔离 + 白名单强制 |

## 4. 基准测试

| 基准 | 内容 | 关联 |
| :--- | :--- | :--- |
| Terminal-Bench 2.0 | 89 任务 × 5 轮, 76.4% 成功率 | 验证环境引导快照是 Harness 优化关键组件 |
| SetupBench | 93 实例环境引导技能评估 | 独立验证 `environment_bootstrap` 类能力可评估 |
| DataAgentBench (DAB) | UC Berkeley + Hasura, 12 数据集 × 4 DB 系统 | DataBridge 61.37%，证明 MCP 数据库接入实用性 |

## 5. 对齐确认（P1-3 vs 官方 MCP 生态）

| 维度 | 官方（angrysky56 分支） | P1-3 实现 | 对齐 |
| :--- | :--- | :--- | :--- |
| project-synapse（知识检索） | Wiki & Neo4j 语义索引 | `semantic_retrieval`（bge-m3 + 三源分块） | ✅ 功能等价 |
| advanced-reasoning（元认知） | 置信度/假设检验/推理链验证 | `meta_cognition`（3 工具） | ✅ 功能等价 |
| 写作用域安全边界 | `allowed_write_paths` 白名单 | `check_write_scope` + 双层防御 | ✅ 完全对齐 |
| 候选工作空间隔离 | filesystem run store | `candidates/<id>/` 四件套 | ✅ 完全对齐 |

## 6. 状态与待办

- Sprint 11 首项（`--mcp-integration`）✅ COMPLETE（9da9cfc）— 集成层单测 7/7 + 端到端 S11V1_MCP（294 chars 注入, score=1.0/214 步）+ pytest 57/57
- Sprint 11 默认启用 + 5 轮评估 ✅ COMPLETE（282bfd0）— 5/5 轮 MCP 集成启用（292-294 chars）, 均 score=1.0/214 步, 无帕累托改进, 自蒸馏维持观察
- 后续任务待 PM 指令：继续 Sprint 11 剩余项 / V9 门再评估（基线 10%, 触发条件 = MCP 实际调用 ≥5 轮, 已满足但无改进）/ 治理审计（SRS 新增项）
- V9 自蒸馏: ⏸ HOLD（pareto_frontier.md plateau_explorer_trigger 区块, S11 首轮评估: 5 轮无改进）

---

## 7. 补充支撑矩阵 — 默认启用 + 5 轮评估（282bfd0, PM 提供 2026-08-07）

### 7.1 补充论文（+2 篇, 累计 7 篇）

| 论文 | 核心贡献 | 与默认启用的关联 |
| :--- | :--- | :--- |
| **Screenshots or Tools?**（arXiv:2608.03327v2, 2026-08-06） | OSWorld-MCP 基准（309 任务）：同一套 MCP 工具对推理模型 +4.0pp、非推理模型 -5.9pp；模型仅在 23.9% 可工具到达任务上调用工具（**adoption gap**） | **默认启用的实证支撑** — 工具存在不意味着被使用，必须默认启用 + 连续迭代强制激活工具调用路径 |
| **MCP Survey**（TechRxiv, 2025） | 首次从通信系统视角审视 MCP（分层 Host-Client 架构、动态工具发现、安全与可扩展性） | 为 MCP 作为 Harness 优化基础设施提供系统级理论框架 |

### 7.2 补充源码库（+5 个, 累计 11 个）

| 仓库 | 关键特性 | 与本地实现的对应 |
| :--- | :--- | :--- |
| **lastmile-ai/mcp-agent** | 轻量 Agent 框架, map-reduce/orchestrator/evaluator-optimizer/router 工作流 | `mcp_client.py` 进程内 FastMCP 调用模式理念一致 |
| **SalesforceAIResearch/MCP-Universe** | RL 训练、基准测试、通用工具使用 Agent 综合框架 | 为 MCP 集成扩展到 RL 蒸馏提供参考架构 |
| **codragraph/harness** | 外优化循环（outer optimization loop）：从种子 Harness 迭代搜索 | 与 `outer_loop.py` 默认启用 MCP 后的迭代优化行为直接对应 |
| **codex-harness-mcp** | Agent 工作转化为可审计循环：bounded contract → 基线/候选记录 → 评估存储 → 比较 | `sessions.jsonl` + `candidates/` 四件套审计模式对齐 |
| **Harness MCP Server** | 工具调用视为系统调用（syscalls）, 任务级状态驻留 Host/Harness | `environment_bootstrap` 写作用域强制（check_write_scope）的直接实现 |

### 7.3 补充数据库/基准（+1 个, 累计 5 个）

| 资源 | 类型 | 核心价值 |
| :--- | :--- | :--- |
| **OSWorld-MCP**（ICLR 2026） | 基准测试 | 首个综合评估计算机使用 Agent 工具调用/GUI 操作/决策能力的基准 — 验证 MCP 工具通常能提升任务成功率 |

### 7.4 补充对齐确认（+2 维, 累计 6 维）

| 官方 MCP 生态 / Meta-Harness | 本地实现 | 状态 |
| :--- | :--- | :--- |
| 工具调用 adoption gap 实证（Screenshots or Tools?） | `--mcp-integration` **默认启用**强制激活工具调用路径 | ✅ 已落实 |
| 外优化循环（outer optimization loop） | `outer_loop.py` + MCP 上下文每次迭代自动注入 | ✅ 已落实 |
