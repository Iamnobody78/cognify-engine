# Sprint 17 评估器差分测试 — 证据链归档

> **Sprint**：17（评估器差分测试，P0，FP-MC-014/015 对策）
> **分支**：`feature/sprint17_evaluator_diff_test`（提交 bca55b7）
> **日期**：2026-08-08
> **验收**：PM 签收（Sprint 17 已由 7 篇核心论文、11 个源码库、4 个基准测试三重支撑，完整对齐 AI 代理差分测试与回归检测的学术与工程标准）

---

## 〇、本地实现摘要（证据主体）

| 交付物 | 路径 | 作用 |
| :--- | :--- | :--- |
| 差分框架 | `governance/meta_harness/evaluator_diff_test.py` | `baseline`/`diff`/`snapshot` 三子命令；判定四态 |
| 评估器增强 | `simulation/v9_gate_evaluator.py` | episode_results 增加 `action_hist`/`branch_hist` 决策指纹 |
| 评估器集成 | `governance/meta_harness/evaluator_v9.py` | `--diff-baseline` 参数，评估后自动对照输出 diff_test verdict |
| 回归测试 | `governance/meta_harness/tests/test_evaluator_diff_test.py` | 8 用例：判定四态 + patch 解析 + JSON 往返稳定性 |

**复现性地基**：V9GateEvaluator 确定性种子（hashlib `_stable_seed`）——同种子两次评估 **bit-identical**（实测验证）。
**判定四态**：`PASSED`（winrate 提升）/ `REGRESSION`（winrate 下降）/ `SUSPICIOUS`（行为指纹变化但 winrate 不变 → 人工审查）/ `INCONCLUSIVE`（全部一致 → no-op）。

**回归用例（真实历史候选）**：
| 用例 | 场景 | 判定 |
| :--- | :--- | :--- |
| ca_mapping_001 013047 | 注释改动（no-op） | INCONCLUSIVE ✅ |
| ca_mapping_001 014750 | `dist < dist` 逻辑损坏 | SUSPICIOUS ✅ |
| ca_reward_001 004104 | EDGE_* 未消费（no-op） | INCONCLUSIVE ✅ |
| 端到端集成 | evaluator_v9.py --diff-baseline | 当前=INCONCLUSIVE / 014750 快照=SUSPICIOUS ✅ |

**回归**：Windows 57/57 + WSL 73/73 + meta_harness 24/24 全绿。

---

## 一、核心论文（理论锚定）

| 论文 | 核心贡献 | 与差分测试的关联 |
| :--- | :--- | :--- |
| **AIProbe: Black-box Differential Testing for Autonomous Agents**（AAAI 2025） | 黑盒差分测试框架，在多样环境配置下验证自主代理，**显著优于SOTA技术**，适用于离散/连续域的model-free与model-based代理 | 为“基线对照差分”提供理论基础：**同一输入，两套实现，比较输出** |
| **Differential Testing for Reliable Language Model Updates（DT4LM）** | 针对分类任务的LM更新差分测试框架，引入**动态适应模型行为的goal function** | 动态阈值策略（threshold 0.5→0.9阶梯上升）的理论参照 |
| **AutoTestForge**（ACM TOSEM 2025） | 多维自动化NLP测试框架，**基于差分测试的多模型投票机制**验证测试用例标签质量 | 多信号交叉验证（决策指纹 + winrate + 步数）的设计参照 |
| **LLMs in Differential Testing: Medical Rule Engine Case Study** | GPT-3.5在差分测试中发现**22条实现不一致的医疗规则** | 证明差分测试能发现“实现与规格不一致”的缺陷——与ca_mapping_001 `dist < dist` 恒False案例同构 |
| **Agent-Diff: Benchmarking LLM Agents via State-Diff-Based Evaluation** | 将评估**重构为状态变更契约（state change contracts）**，而非轨迹匹配 | 决策指纹（action_hist/branch_hist）替代轨迹匹配的设计参照 |
| **Survey on Evaluation of LLM-based Agents**（arXiv 2025） | **首个LLM代理评估方法综合综述**，涵盖**测试自动化金字塔、回归测试、测试驱动开发** | 将差分测试定位为代理评估体系中的**回归测试层** |
| **An Empirical Study of Testing Practices in Open Source AI Agent Frameworks**（2025） | 实证研究揭示：**框架开发者应改进对新型测试方法的支持，应用开发者必须采用prompt回归测试** | 为将差分测试集成至CI/CD提供实证依据 |

---

## 二、源码库（工程实现底座）

### 2.1 差分/回归测试框架（与 `evaluator_diff_test.py` 直接对应）

| 源码库 | 核心能力 | 与本地实现的对应 |
| :--- | :--- | :--- |
| **evalview**（npm/PyPI） | **黄金基线diff + CI/CD集成**，支持LangGraph、CrewAI、OpenAI、Claude、Ollama、MCP | `baseline/diff/snapshot` 三子命令架构的直接参照 |
| **agentsnap**（@mukundakatta） | **工具调用轨迹快照测试**：记录agent运行轨迹→与基线diff→CI失败回归，**零运行时依赖** | 快照→diff→CI gate 模式与你的设计完全一致 |
| **agent-replay**（clay-good） | SQLite驱动的**时间旅行调试**：重放执行轨迹、diff行为变化、fork运行测试修复 | `diff` 命令将两轮运行并排对比，“哪一步 diverged”的定位能力 |
| **kalibra**（PyPI） | **回归检测与CI质量门**：`kalibra compare baseline.jsonl current.jsonl` | `--diff-baseline` 自动判定的直接参照 |
| **DProvenanceKit** | 本地优先的**回归与溯源SDK**：记录agent行为、比较运行、追踪输出到源、检测推理漂移 | 决策指纹 + 行为溯源的设计参照 |
| **agent-evals-workbench** | 轻量级评估工作台：**按运行目录存储输出和分数，支持case级diff** | 候选工作空间（`candidates/<candidate_id>/`）的diff存储模式 |
| **agent-diff-bench** | **交互式沙箱**：在第三方API副本（Slack、Linear、Box）上评估agent与RL训练 | 状态变更契约评估的工程化实现 |

### 2.2 CI/CD 集成与质量门（对应“接入 outer_loop 自动判定”）

| 源码库 | 核心能力 |
| :--- | :--- |
| **ciagent**（PyPI） | **CI for AI Agents**：pytest原生回归测试，捕获路由变化、工具调用漂移、成本峰值 |
| **Assay CI Gate** | 专为AI代理设计的CI回归门：处理**慢（30s-3min/测试）、贵（$0.10-$1.00/次）、flaky（5-20%失败率）** 特性 |
| **maida AgentDbg** | 三个CLI命令将追踪运行转为轻量级回归测试：**baseline、assert、diff** |

### 2.3 评估器增强（对应 FP-MC-014/015 对策）

| 源码库 | 核心能力 |
| :--- | :--- |
| **agent-eval**（Tlahey） | 零依赖测试框架：**Git隔离执行 + LLM-as-judge + SQLite仪表板** |
| **claude-code-harness evaluator-agent** | **对抗性质量评估**：读取plan、git diff、源码→运行build和test→报告分级发现（hard blocks vs advisory） |
| **AgentEval BiasMetric** | 通过**反事实测试**测量跨人口统计组的差异对待 |

---

## 三、数据库与基准测试

| 资源 | 类型 | 核心价值 |
| :--- | :--- | :--- |
| **MCPEval**（EMNLP 2025） | 评估框架 | 基于MCP的深度评估框架，在**5个真实世界领域**验证 |
| **litebench**（PyPI） | 基准运行器 | **5分钟到首次评估**，支持HumanEval/GSM8K/MMLU/MATH等 |
| **Agent-Diff Benchmark** | 基准 | 基于**状态变更契约**评估企业API任务上的LLM代理 |
| **Survey on Evaluation of LLM-based Agents** | 综述 | 首个LLM代理评估方法综合综述 |

---

## 四、差分测试四态判定与学术/工程对齐

| 判定 | 条件 | 学术支撑 | 工程支撑 |
| :--- | :--- | :--- | :--- |
| **INCONCLUSIVE** | 全部信号一致（no-op） | AIProbe“同一输入→两套实现→比较输出” | evalview黄金基线diff |
| **SUSPICIOUS** | 行为指纹变 + winrate不变 | Agent-Diff“状态变更契约” | agent-replay diff行为变化 |
| PASSED | winrate提升 | 传统回归测试通过 | kalibra质量门 |
| REGRESSION | winrate下降 | 传统回归测试失败 | Assay CI Gate |

---

## 五、对齐确认

| 维度 | 学术/工程标准 | Sprint 17 实现 | 状态 |
| :--- | :--- | :--- | :--- |
| **差分测试核心** | 同一输入→两套实现→比较输出 | `baseline` + `diff` 子命令 | ✅ |
| **黄金基线** | 记录已知良好行为作为参照 | `evaluator_v9.py --diff-baseline` | ✅ |
| **CI/CD 质量门** | 回归检测集成至CI | 判定四态（INCONCLUSIVE/SUSPICIOUS/PASSED/REGRESSION） | ✅ |
| **行为指纹** | 轨迹diff替代纯分数对比 | `action_hist`/`branch_hist` 决策指纹 | ✅ |
| **状态变更契约** | 评估基于状态变化而非轨迹匹配 | 决策指纹 + winrate 双信号 | ✅ |

---

## 六、Sprint 18 候选（依赖本证据链）

1. **差分测试接入 outer_loop 自动判定**——候选评估强制 diff 对照，SUSPICIOUS 不入 Pareto（对应 ciagent / Assay CI Gate 的 CI/CD 质量门定位）
2. resolve_diff 恒 False 启发式
3. plateau_explorer 自蒸馏（依赖评估器已修复）

---

## 七、Sprint 18 落地实证（2026-08-08, outer_loop 差分门禁集成）

Sprint 18 将四态判定接入 outer_loop 候选评估流程，作为 **Pareto 保留前强制质量门**。实证如下：

### 7.1 回归用例拦截（真实评估, WSL）

| 候选 | 注入缺陷 | diff_verdict | 门禁动作 |
|---|---|---|---|
| ca_reward_001 | EDGE_* 常量 no-op（未消费, FP-MC-014 类） | **INCONCLUSIVE**（信号与基线一致） | ✅ BLOCKED，不入 Pareto |
| ca_mapping_001 | `dist < dist` 链式比较恒 False（FP-MC-015 类） | **SUSPICIOUS**（winrate 1.0 但 avg_steps 21.4→29.3） | ✅ BLOCKED，转人工 |
| s18_e2e_rules_001 | E2E 构造候选（真实链路） | **INCONCLUSIVE** | ✅ BLOCKED，meta_decisions 记录 |

### 7.2 与学术/工程对齐更新

- **ciagent / Assay CI Gate 定位**：差分门禁 = 候选合并前的 CI 质量门，S18 落地为该门禁的强制执行点（此前仅有判定能力、无强制拦截）
- **Agent-Diff / agent-evals-workbench**：S18 将"差分判定"从离线工具（S17 CLI）升级为在线评估管线（evaluator_v9 `--diff-baseline` 内嵌）
- **AIProbe / DT4LM 行为指纹**：`action_hist`/`branch_hist` 决策指纹在 SUSPICIOUS 判定中起决定性作用（winrate 饱和时唯一分辨信号）

### 7.3 验收对照（PM 裁决约束）

| 验收标准 | 结果 |
|---|---|
| ① ca_reward_001/ca_mapping_001 回归拦截 | ✅ 双用例均 BLOCKED（见 7.1） |
| ② 双端回归全绿 | ✅ Windows 57/57 + WSL 73/73 + meta_harness 38/38（16+8+14） |
| ③ meta_decisions.jsonl 含 diff_verdict/diff_blocked | ✅ `type=diff_gate, diff_verdict=INCONCLUSIVE, diff_blocked=true`（s18_e2e_rules_001） |

### 7.4 新增缺陷沉淀

- **FP-MC-016（测试隔离缺陷）**：run_round 集成测试未 mock `_record_diff_decision`，导致 mock 记录污染运行时审计日志（27 条）→ fixture 统一隔离 + 清理脚本。规则沉淀：凡测试涉及写持久化文件的辅助函数，一律在 fixture 层隔离。
