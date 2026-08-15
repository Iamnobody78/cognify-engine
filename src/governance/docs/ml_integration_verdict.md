# ML/CV/DL 能力集成提案 — 事实核查与 Meta-Harness 裁决

> 版本: v1.0 · 2026-08-04 · 对应提案: 三场景集成 (SIREN/CodeAstra/SingGuard/RL)
> 裁决者: agent-governance-v2 治理智能体 (Meta-Harness 双环融合)

## 一、事实核查结果（逐项验证，非盲从）

### 资源清单验证

| 提案资源 | 验证方法 | 结果 | 备注 |
|----------|----------|------|------|
| SIREN (ACL 2026) | arXiv API + HF API + PyPI API | ✅ 真实 | arXiv 2604.18519, HF UofTCSSLab/SIREN-Qwen3-0.6B, PyPI llm-siren 0.1.1; **但 HF 路径应为 UofTCSSLab/ 而非提案写的 CSSLab/** |
| CodeAstra-500M | HF API + GitHub API | ✅ 真实但极冷门 | rootxhacker/codeastra-500M, apache-2.0, downloads=26/likes=0 — 未经验证的新模型 |
| SingGuard | HF API | ✅ 真实 | inclusionAI/SingGuard-2b/4b/8b |
| wolf-defender-prompt-injection | HF API | ✅ 真实 | patronus-studio 系列 |
| verl-agent | GitHub API | ✅ 真实 | 存在仓库 |
| MicroSafe-RL | GitHub API | ✅ 真实 | 存在仓库 |
| GiGPO | arXiv API | ⚠️ 无法确认 | arXiv 无结果 — 疑似笔误/幻觉 |
| **FireRL** | arXiv + GitHub API | ⛔ **不存在** | 两源均无结果 — **幻觉资源, 不得引用** |

### 提案关键论断核查（对照项目真实状态）

| 论断 | 项目真实状态 | 结论 |
|------|-------------|------|
| "基线 606 passed / v1.27.0-sql" | **809+ passed / v1.35.0-persist** | ⛔ 基线过期（提案数据来自旧快照） |
| "Base64 绕过是当前硬伤" | test_ast_guard_bypass.py + probe_base64_bypass.py **实证 6/6 BLOCK**（含拼接形态 getattr('ev'+'al')/下标形态） | ⛔ 已闭合（批判审计 2026-08-04 修复 + taint.py 折叠） |
| "AST 无语义之实" | src/semantic_hook.py + judge/llm_judge.py (TASK-REAL-009) 已有 Ollama 语义旁路, 判定后升级钩子, fail-soft | ⚠️ 部分成立 — 已有后置钩子, 但无前置语义筛查 |
| "SIREN 可检测 Base64 恶意代码" | SIREN 是 **LLM 内容有害性检测器**（prompt/response 有害性打分 [0,1]）, 训练目标是自然语言有害性, **非代码安全** | ⛔ **用途错配** — 模型能力与提案用法不符 |
| "语义检测延迟 50-200ms, 需两级架构" | 提案自述 | ✅ 合理 — 但本项目 ast_guard.analyze() 是**同步纯函数**, LLM 旁路必须置于钩子层 (main.py intercept 链), 架构约束 |

## 二、Meta-Harness 裁决

### 裁决 1: Phase 1 语义检测 — 有条件批准（重定义）

**不采纳**提案的"SIREN 集成"路径（用途错配 + torch≥2.0 重依赖 + HF 路径错误）。
**采纳**其方向（语义意图理解是 AST 的合理补充），但执行路径改为：

```
现有资产复用: judge/llm_judge.py (Ollama qwen2.5:7b 本地判定, 零-key)
            + src/semantic_hook.py (判定后升级钩子, 已有 fail-soft/阈值 0.85)
升级方向: 从"判定后升级" → "判定前语义预筛" (semantic_hook 前移)
约束: analyze() 保持纯函数 (同步), LLM 旁路在 main.py 拦截链异步调用
依赖: 零新增 (Ollama 已有), 不引入 torch/transformers
```

验收: 新语义预筛可识别当前 AST 盲区形态 (跨函数参数数据流等), 全量测试 ≥809 零回归。

### 裁决 2: Phase 2 多模态 — 推迟

网关当前无多模态输入通道（纯文本/JSON 工具调用）。为不存在的输入面建检测器是过度工程。
**条件**: 当 Agent 生态引入图像输入时再启动（可复用 SingGuard 调研结论）。

### 裁决 3: Phase 3 RL 策略优化 — 推迟 + 剔除幻觉资源

- FireRL **不存在**（幻觉），不得引用；GiGPO 无法确认。
- 更深层: RL 自动调策略与"确定性治理"原则冲突（微软 Agent Governance Toolkit 明确
  "治理 Agent 的行动, 而非推理"）。治理判定必须是确定性的、可审计的。
- **替代路径**: 策略优化先走"数据驱动的手动调参闭环" — 拦截数据 → 误报分析 →
  规则改进 (当前 ROADMAP 已覆盖), RL 留待远期评估。

## 三、诚实边界

1. 本核查基于公开 API (arXiv/HF/GitHub/PyPI) 实时验证, 2026-08-04 当日有效。
2. CodeAstra-500M 真实但极冷门 (26 downloads) — 生产采用前需独立评估。
3. SIREN 作为内容护栏有真实价值 (LLM 输出有害性检测), 但那是**另一个场景**
   (治理 LLM 输出而非代码输入), 与本提案的 Base64 场景无关。
4. 本裁决不否定 ML 集成的长期价值 — 它否定的是"基于错误事实的盲目执行"。

## 四、决策记录

| 提案项 | 裁定 | 依据 |
|--------|------|------|
| SIREN 集成 (Phase 1) | ⛔ 重定义 | 用途错配 (内容检测≠代码检测) + HF 路径错误 |
| 语义预筛升级 (Phase 1') | ✅ 批准 | 复用现有 Ollama 资产, 零新增依赖, 补 AST 盲区 |
| 多模态治理 (Phase 2) | ⏸ 推迟 | 无多模态输入面 |
| RL 策略优化 (Phase 3) | ⏸ 推迟 | FireRL 幻觉 + 确定性治理原则冲突 |
| 元提示词基线 | ⛔ 拒绝 | 606/v1.27.0-sql 过期, 实际 809+/v1.35.0-persist |
