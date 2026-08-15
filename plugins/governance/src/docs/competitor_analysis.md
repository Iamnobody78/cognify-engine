# 竞品分析 — 开源项目对比 (agent-governance-v2)

> 版本: v1.0 · 2026-08-04 · 对应元提示词任务 2
> 方法: GitHub API 实时验证（2026-08-04 当日），star 数与归属逐项核实

## ⚠️ 事实核查: 提案清单 5 项目中 1 个名称不实

| 提案项目 | 验证结果 | 判定 |
|----------|----------|------|
| Omnigent | ✅ omnigent-ai/omnigent, 8085★, 2026-06 创建 — **但归属非 Databricks 官方组织** (owner=omnigent-ai, 提案称"Databricks 开源"不准确) | ✅ 真实 |
| Microsoft Agent Governance Toolkit | ✅ microsoft/agent-governance-toolkit, 5603★, 2026-03 创建, OWASP Agentic Top 10 10/10 | ✅ 真实 |
| metaharness (ruvnet) | ✅ ruvnet/metaharness, 544★, 2026-06 创建 | ✅ 真实 |
| agent-governance-research | ⚠️ 精确名不存在 — 找到 WooyoohL/Research-Agent-Governance 等**不同**仓库 | ⛔ 名称不实 |
| Stronghold | ✅ Agent-StrongHold/stronghold — **但仅 1★, 极冷门** | ✅ 真实但未经验证 |

## 对比分析

### 1. Omnigent (8085★) — 元框架/沙箱治理
- **能力**: 编排 Claude Code/Codex/Cursor/Pi/自定义 Agent; 不重写 harness 即切换; 策略执行 + 沙箱; 实时协作
- **与 agent-governance-v2 对比**:
  - 相同: 外部包装治理（非侵入）、策略执行、沙箱理念
  - 差异: Omnigent 是**面向编码 Agent 的编排框架** (meta-harness 层), 我们是**网关层** (拦截+判定+审计); Omnigent 无 AST 分析, 我们已有多语言 tree-sitter ASTGuard
- **可借鉴**: 多 Agent 编排的 harness 抽象 — 我们的 agent_registry.yaml 可扩展为 harness 注册

### 2. Microsoft Agent Governance Toolkit (5603★) — 工业级参考
- **能力**: 运行时策略执行、零信任身份、执行沙箱、可靠性工程; OWASP Agentic Top 10 全覆盖; "治理行动而非推理"
- **与 agent-governance-v2 对比**:
  - 相同: 策略执行/审计/确定性治理原则 (与我们裁决方向一致 — 印证我们推迟 RL 决策正确)
  - 差异: 微软是完整 SDK+生态, 我们是轻量自研网关; 微软 6100+ 测试 vs 我们 ~880
- **可借鉴**: OWASP Agentic Top 10 对照表 — 验证我们覆盖缺口; 测试规模差距 (我们零依赖轻量)

### 3. metaharness (ruvnet) (544★) — 自我进化参考
- **能力**: 为代码库"铸造"定制 Agent 框架; Darwin Mode (自我变异+测试进化)
- **与 agent-governance-v2 对比**:
  - 相同: 自进化理念 — 我们已有 Meta-Harness (adapter/sandbox/proposer/pareto/trace)
  - 差异: metaharness 变异的是**框架代码**, 我们变异的是**策略候选** (更安全 — 不碰代码)
- **可借鉴**: Darwin Mode 的"变异→测试"循环 → 我们的 proposer 已生成候选, 缺的是**候选自动 pytest 验证**

### 4. Stronghold (1★) — 不成熟, 仅记录
- **能力**: 零信任执行框架 + 威胁检测 + 自改进记忆
- **判定**: 1★ 未经验证, 不作为整合依据; 其"自改进记忆"我们已有 (memory/ + knowledge/ 闭环)

### 5. agent-governance-research — 名称不实, 剔除

## 差距与整合决策

| 维度 | agent-governance-v2 | 行业参考 | 差距 | 决策 |
|------|--------------------|----------|------|------|
| AST 语义分析 | ✅ 多语言 tree-sitter + taint + semantic_hook | 未见同类 (Omnigent/微软均无) | **领先** | 保持 |
| 审计链 | ⚠️ parent_span_id 因果 + HMAC 单记录签名 | CAVA 论文 attestation | 缺链式哈希 | **P0 升级** |
| 策略自动验证 | ⚠️ proposer 生成候选, 无自动测试 | metaharness Darwin (变异+测试) | 缺候选 pytest | **P1 补** |
| OWASP Agentic Top 10 | 未系统对照 | 微软 10/10 | 需对照表 | P2 |
| 多 Agent 治理 | agent_registry.yaml (单项目) | Omnigent harness 编排 | 未扩展 | P3 |

## 诚实边界

1. star 数仅反映关注度, 非质量指标 (Stronghold 1★ ≠ 无用, 但不可作生产依据)。
2. Omnigent 归属"Databricks 开源"需更正 — owner 是 omnigent-ai 组织。
3. 对比基于 README/描述, 未深读源码; 深度整合前应下载分析。
4. 微软 6100+ 测试的规模差距是**架构选择** (我们零依赖轻量) 而非缺陷 — 但 OWASP 对照值得补齐。
