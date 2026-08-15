# Meta-Harness 融合报告

> **日期**: 2026-08-03 · **版本**: v1.22.0 · **审计**: AUDIT-0042
> **仓库**: https://github.com/Iamnobody78/agent-governance-v2（提交链：MH-1 → MH-2 → MH-3，均已 push origin/main）
> **基线**: 斯坦福 IRIS Lab Meta-Harness（arXiv:2603.28052）——"冻结模型、进化 harness"

---

## 1. 融合前差距（为什么需要三阶段）

L5（meta-harness 层）此前只是**策略建议生成器**：`adapter.generate_policy_suggestions()` +
`sandbox.evaluate_candidate_in_sandbox()`，具备单候选验证能力，但缺少 Meta-Harness 的四个核心机制：

| 斯坦福原则 | 融合前 L5 | 缺口 |
|-----------|-----------|------|
| 冻结模型，进化 harness | 模型与 harness 耦合在建议里 | 无独立 harness 版本管理 |
| 完整执行轨迹作为反馈（≤10M token） | 仅 decisions 记录，无步骤级轨迹 | **无 trace 捕获层** |
| 文件系统作为唯一真实来源 | 状态散落 DB/内存 | 无 traces/、candidates/ 目录 |
| Pareto frontier（质量 vs 成本） | 单维度阈值比较 | **无多目标决策** |
| 提议者 = 变异算子 | 建议是文本，非可运行候选 | 候选非完整文件树 |

## 2. 三阶段融合交付

### MH-1 — 执行轨迹捕获（`src/trace/`）

**交付**: `store.py` + `capture.py` + 15 tests
- `TraceStore`: `traces/{trace_id}/manifest.json` + `steps/NNN_*.json`（**每步增量落盘，崩溃不丢**）+ `artifacts/`
- `TraceCapture`: 上下文管理器——异常自动 `failed`；`fail()` 显式标记；`capture_run` 函数包装；`traced` 装饰器
- `token_estimate`: 4 字符 ≈ 1 token（10M 反馈预算裁剪输入）
- schema `mh-trace/v1`，路径越界防护

### MH-2 — 提议器（`src/proposer/`）

**交付**: `reader.py` + `writer.py` + 14 tests
- `TraceReader`（只读）: `read_trace` / `search_traces`（子串）/ `grep_traces`（正则）/ `cat_trace`（LLM 可消费全文）/ `feedback_budget`（10M 预算统计）
- `CandidateWriter`（变异算子）: `candidates/{candidate_id}/src/` **完整 harness 文件树（非补丁）** + `candidate.json` 血缘（parent_trace_id + 变异说明）+ 父轨迹产物导入 + 整树复制

### MH-3 — Pareto 前沿 + 迭代循环（`src/pareto/`）

**交付**: `frontier.py` + `loop.py` + 11 tests
- `ParetoFrontier`: (quality↑, cost↓) 双目标非支配集——**不被单一维度绑架**
- `EvolutionLoop`: propose → score → merge **≥3 轮**，每轮轨迹落盘（反馈闭环）；严格裁决门（被支配候选拒绝合并）
- 裁决规则：新候选 3 轮迭代内优于当前最优才允许写入主分支

## 3. 融合演示（真实执行，非模拟）

```
$ python -c "...EvolutionLoop(max_rounds=3)..."
rounds: 3                          # ≥3 轮迭代 ✅
merged: 2                          # 3 候选 → 2 进入前沿（1 被支配拒绝）✅
frontier: [(candidate_A, 0.79, 44.6), (candidate_C, 0.66, 31.2)]
traces: 3 条                       # 每轮完整轨迹落盘（反馈闭环）✅
candidates: 3 个                   # candidates/{id}/src/ 完整 harness ✅
```

> **⚠️ 状态更正（AUDIT-0059, 2026-08-04, docs/meta_harness_verification.md）**：本段"完整的 Harness 工程自动化系统"为 v1.22.0 时期**旧宣称**，与 2026-08-03 L5 元批判后修正的诚实边界冲突。源码核查结论：本项目实现的是 Meta-Harness 概念的**确定性基础设施**（轨迹库/变异算子/循环引擎/沙箱），**不含斯坦福原版核心的"编码 Agent 提议器"**（无 LLM 调用, propose_fn 外部注入）；"完整 Harness 工程自动化"列为 v2 方向。原文保留作审计轨迹。

证明 L5 已从"策略建议生成器"进化为**完整的 Harness 工程自动化系统**：
`traces/` 是进化反馈库（唯一真相）、`candidates/` 是变异算子产物库、
`pareto/` 是决策层（质量 vs 成本）、`loop.py` 是自动化迭代引擎。

## 4. 与既有 L5 的协同（非推翻）

| 新层 | 复用/被复用 |
|------|------------|
| MH-1 trace | 被 bootstrap.sensor（critic/debt 读取）、loop（每轮落盘）复用 |
| MH-2 proposer | 候选评分可接 `sandbox.evaluate_candidate_in_sandbox`（生产注入） |
| MH-3 pareto | 被 L4 critic / 自进化引擎裁决门复用 |
| P12 bootstrap | sensor/diagnoser 提供"漂移信号"作为提议者的失败样本来源 |

## 5. 验收矩阵

| AC | 内容 | 结果 |
|----|------|------|
| AC1 | MH-1 trace 完整执行轨迹 | ✅ manifest+steps+artifacts 增量落盘 |
| AC2 | MH-2 proposer reader+writer | ✅ 检索/搜索/grep/cat + 完整候选 harness |
| AC3 | MH-3 Pareto+loop ≥3 轮 | ✅ 11 tests，融合演示 3 轮 |
| AC4 | ≥488 tests | ✅ **542 passed**（502 基线 + 40 新增） |
| AC5 | 每阶段独立提交 | ✅ MH-1/MH-2/MH-3 三个独立提交 |
| AC6 | 本报告含 GitHub 链接 | ✅ 见文首 |
| AC7 | v1.22.0 快照 | ✅ snapshot + AUDIT-0042 + GATE 7 断言 |

## 6. 后续（供裁决）

- **P13 认证/授权**: 下一步候选——审计与 P6 外部评审缺口 #1（认证）/ P8（ED25519）重叠；P13-P19 路线图裁决
- **生产评分接线**: `EvolutionLoop.score_fn` 接入 `sandbox.evaluate_candidate_in_sandbox`（当前测试用假评分）
- **10M 预算裁剪**: `TraceReader.feedback_budget` 已就绪，待接提议者 top-k 选择
