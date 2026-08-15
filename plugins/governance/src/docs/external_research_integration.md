# 外部研究整合分析 — 学术论文部分

> 版本: v1.0 · 2026-08-04 · 对应元提示词任务 1
> 方法: arXiv API 实时验证（2026-08-04 当日），每篇论文逐条核实存在性

## ⚠️ 事实核查：提案列出的 3 篇论文全部无法验证

| 提案论文 | arXiv 验证 | 判定 |
|----------|-----------|------|
| 《Anchor: A Federated Governance Engine for Secure and Compliant Agentic AI Systems》 | `all:"federated governance engine"` → 0 结果；`all:"Anchor" AND all:"agentic"` → 仅返回无关论文（Artifact Drift / Noise Creation / Alignment Auditing） | ⛔ **疑似幻觉** — 不得引用 |
| 《Execution Governance for Agentic AI》 | `all:"execution governance" AND all:"agentic"` → 无此标题 | ⛔ **疑似幻觉** — 不得引用 |
| 《Deterministic Dual-Gate Governance for Agentic AI》(Chimera) | `all:"dual-gate" AND all:"agent"` → 仅返回无关论文（MARL 时间膨胀） | ⛔ **疑似幻觉** — 不得引用 |

**结论**: 与上一轮 FireRL 同款 — 提案资源清单含幻觉论文。**学术支撑必须建立在可验证来源上**，本文件改用 arXiv 实测存在的同领域论文。

## ✅ 实测存在的同领域论文（2026-08-04 arXiv 验证）

### 1. SafeAgent: A Runtime Protection Architecture for Agentic Systems
- **核心**: Agent 运行时保护架构 — 在 Agent 执行链中插入保护层
- **与项目对应**: 我们的 `main.py` 拦截链 (intercept) + `semantic_hook.py` 判定后升级
- **可整合**: 运行时保护的分层理念 — 验证我们拦截链是否覆盖"执行前/执行后"两阶段

### 2. Executable Governance for AI: Translating Policies into Rules Using LLMs
- **核心**: 用 LLM 把自然语言策略翻译成可执行规则
- **与项目对应**: 我们的 `policies.yaml` 规则 + `knowledge_distill.py` 蒸馏模式
- **可整合**: LLM→规则翻译的验证方法（我们已有 YAML 策略, 可借鉴其翻译评测基准）

### 3. POLARIS: Typed Planning and Governed Execution for Agentic AI
- **核心**: 类型化规划 + 受治理执行 — 规划与执行分离, 执行受治理约束
- **与项目对应**: 我们的五级裁决 (ALLOW→DENY) + trace 因果链
- **可整合**: 类型化执行约束 — 我们的 tool_lethality 权重可视为轻量类型化

### 4. Deontic Policies for Runtime Governance of Agentic AI Systems
- **核心**: 道义逻辑 (义务/禁止/许可) 的运行时治理策略
- **与项目对应**: 我们的 ALLOW/ESCALATE/DENY/SUSPEND 五级判定
- **可整合**: 道义逻辑形式化 — 验证我们判定语义是否与义务/禁止逻辑一致

### 5. CAVA: Canonical Action Verification and Attestation for Runtime Governance
- **核心**: 动作规范化验证 + 证明 (attestation) — 运行时治理的可验证性
- **与项目对应**: 我们的 `context_hmac.py` (HMAC 签名) + `storage.py` 审计
- **可整合**: **审计链升级的直接依据** — CAVA 的 attestation 理念 = 我们的签名 + 链式哈希

### 6. Governed Auditable Decisioning Under Uncertainty
- **核心**: 不确定条件下的可审计决策
- **与项目对应**: 我们的 DecisionRecord + rationale 13 列审计
- **可整合**: 不确定性标注 — 我们的概率判定 (semantic score) 可加置信度审计

## 整合建议优先级（基于真实论文）

| 优先级 | 整合项 | 真实论文依据 | 对应项目模块 |
|--------|--------|-------------|-------------|
| P0 | **审计链升级** (父决策哈希 + verify) | CAVA attestation + Governed Auditable Decisioning | storage.py + context_hmac.py |
| P1 | **执行边界验证** (不可绕过审计) | SafeAgent 运行时保护 | main.py 拦截链 |
| P2 | **道义逻辑语义对齐** | Deontic Policies | policy.py 五级判定 |
| P3 | **LLM→规则翻译评测** | Executable Governance | knowledge_distill + policies.yaml |

## 诚实边界

1. 本文件仅整合**已验证**论文；提案 3 篇幻觉论文已剔除并记录在案（防再次引用）。
2. 论文核心概念基于摘要提取, 未全文精读 — 整合前如需深度引用应下载原文。
3. 学术验证价值: 本文件证明项目方向与 2026 年真实研究趋势一致 (运行时治理/可审计决策/道义策略)。
