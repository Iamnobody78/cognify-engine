# Meta-Harness 执行状态报告

> 核查依据：斯坦福 Meta-Harness 元提示词（2026-08-04）· 强制规则：源码交叉验证 / 不得模糊 / 区分概念与实现
> 核查对象：`agent-governance-v2`（v1.37.0-toolargs, commit 7423348）· 核查编号：AUDIT-0059
> 证据采集：src/ 全量源码逐文件读取 + grep 交叉验证（未依赖 README 宣称）

## 结论

- **总体判定**：⚠️ **部分执行** —— 基础设施（trace/proposer/pareto/sandbox）真实存在且测试覆盖，但**核心能力"编码 Agent 提议器"未实现**：循环引擎为确定性注入式（propose_fn 外部提供），无自主"读取 10M 轨迹 → 诊断 → 重写 Harness"闭环。
- **与斯坦福原版对标**：**概念借用 + 适配层实现，差距显著**。README 已诚实声明（"理念源自 Meta-Harness 研究框架，但仅实现适配层能力"），本项目自己的能力边界文档（architecture_narrative §L5 诚实边界）也明确"完整 Harness 工程自动化不在当前能力内，列为 v2 方向"。
- **额外发现**：3 处文档-源码漂移（融合报告旧宣称 + 2 处 BottleSumo 内容污染），本报告附修正。

---

## 各维度核查结果

| 维度 | 状态 | 证据 |
|------|------|------|
| 1. 外循环存在性 | ✅ 存在（基础设施） | `src/pareto/loop.py` EvolutionLoop（propose→score→merge→log, max_rounds=3, 非支配集裁决门）；`src/proposer/writer.py` CandidateWriter 写**完整 harness 文件树**（非补丁）+ candidate.json 血缘；`src/proposer/reader.py` TraceReader 文件系统只读访问；`src/meta_harness/adapter.py` 策略建议器（DENY 日志扫描→YAML 候选→3 层门控）；`src/meta_harness/sandbox.py` 候选沙箱 + `run_pytest_regression`（subprocess 真跑 pytest） |
| 2. 完整轨迹访问 | ✅ 存在（能力/上限） | `src/trace/store.py` 文件系统唯一真相（traces/{id}/manifest.json + steps/NNN_*.json + artifacts/ 增量落盘、崩溃可恢复、total_tokens 记账, 4 字符≈1 token 估算）；`reader.py` grep_traces（正则）/cat_trace（全量展开）/search_traces（子串）检索 API；`feedback_budget = 10_000_000`（10M token 预算常量 ✅）。**边界**：预算为能力上限+估算记账，无真实 10M 规模运行证据 |
| 3. Proposer 能力 | ⚠️ 部分（确定性模块, 非编码 Agent） | Writer 具备文件系统写能力 ✅；但 **proposer/pareto/meta_harness 全模块无任何 LLM 调用**（grep 验证：无 ollama/deepseek/openai/requests；仅 sandbox 用 subprocess 跑 pytest）。循环的 propose_fn/score_fn **由外部注入**（测试注入 fake 函数），无生产驱动脚本。自主"读轨迹→诊断→重写"闭环**不存在**——这就是斯坦福原版的核心，本项目未实现 |
| 4. 与原版差距 | ⚠️ 概念对齐, 实现差距显著 | 对齐：轨迹中心文件系统循环 / 变异算子（整树非补丁）/ Pareto 质量vs成本 / ≥3 轮裁决门 / 10M 预算设计 / grep/cat 检索。差距：①**Proposer 非编码 Agent**（核心差距）；②优化对象偏窄（实际产出=策略候选 YAML, 未对 harness 代码/提示词/重试逻辑做自动化变异）；③无持续驱动（融合演示 3 轮 2 候选为一次性 demo, 无 CI/调度器接入）；④10M 预算未实战；⑤候选自动 pytest（sandbox 已有能力）未接为默认合并门槛 |

---

## 证据链（源码定位）

| 声明 | 源码位置 | 核查结论 |
|------|----------|----------|
| 循环结构存在 | `src/pareto/loop.py:EvolutionLoop`（propose→score→merge, max_rounds=3） | ✅ 真实 |
| 完整候选树写入 | `src/proposer/writer.py:CandidateWriter`（candidates/{id}/src/ 整树 + candidate.json） | ✅ 真实 |
| 轨迹检索+grep/cat | `src/proposer/reader.py:grep_traces/cat_trace/search_traces` + `feedback_budget=10_000_000` | ✅ 真实（10M 为预算常量） |
| 轨迹文件系统唯一真相 | `src/trace/store.py`（manifest+steps 增量落盘+artifacts+token 记账） | ✅ 真实 |
| 策略建议器（只读） | `src/meta_harness/adapter.py`（generate_policy_suggestions + validate_candidate 3 层门控） | ✅ 真实（**确定性规则引擎, 无 LLM**） |
| 候选沙箱+pytest 回归 | `src/meta_harness/sandbox.py`（evaluate_candidate_in_sandbox + run_pytest_regression subprocess） | ✅ 真实（AC5 部分能力已存在） |
| **"完整的 Harness 工程自动化系统"** | `docs/META_HARNESS_FUSION_REPORT.md`（v1.22.0 旧宣称） | ⛔ **与 README/architecture_narrative 诚实边界冲突**（见 §文档漂移） |
| **"Meta-Scheduler（6 层总线+优先级队列+无锁+心跳）"** | `docs/wiki/Releases.md` v1.20.0 + `architecture_narrative.md` | ⛔ **src/ 无 meta_scheduler.py**（BottleSumo 内容污染） |
| **"调度器执行器 28+, meta-layer 审计 14 层"** | `docs/wiki/Architecture.md` | ⛔ **本仓库无此规模**（BottleSumo v11.23 内容污染） |

---

## 文档-源码漂移（本核查新增发现）

1. **docs/META_HARNESS_FUSION_REPORT.md** 结尾声称 L5"进化为**完整的 Harness 工程自动化系统**"——这是 v1.22.0 时期的旧宣称，未随 2026-08-03 L5 元批判修正（README/architecture_narrative 已改为"策略建议器+诚实边界"）。**修正**：加状态横幅，保留原文作审计轨迹。
2. **docs/wiki/Releases.md** v1.20.0 与 **architecture_narrative.md** 声称"Meta-Scheduler（6 层总线+优先级队列+无锁+心跳）"——src/ 仅有 `src/task_scheduler.py`（任务调度）与 `src/bootstrap/scheduler.py`（P12 确定性调度器），**无 meta_scheduler.py**；该描述源自 BottleSumo v11.20 记忆污染。**修正**：加更正横幅。
3. **docs/wiki/Architecture.md** "调度器执行器 28+、meta-layer 审计 14 层"——本仓库当前 src 共 ~45 个模块，无"28+ 执行器/14 层审计"实体；同属 BottleSumo v11.23 内容污染。**修正**：加更正横幅。

---

## 概念 vs 实现区分（强制规则 3）

- **概念对齐**：Meta-Harness 的"冻结模型、进化 harness"思想、轨迹中心循环、变异算子、Pareto 裁决——本项目在**概念层**完整吸收，并落地为可测试的适配层。
- **实现差距**：斯坦福原版的核心是"**编码 Agent 提议器**"（Claude Code/Opus 级 LLM Agent 读取 10M token 轨迹、自主诊断、重写提示词/工具/重试/上下文/子代理协调），Terminal-Bench 2.0 76.4% 的成绩来自该 Agent 闭环。本项目实现的是该闭环的**确定性基础设施**（读取/写入/循环/沙箱），"脑"由外部（人/会话级 LLM）注入——是"工具"而非"自主体"。

---

## 建议

| 优先级 | 建议 | 状态 |
|--------|------|------|
| P0 | 修正 3 处文档-源码漂移（融合报告旧宣称 + 2 处 BottleSumo 污染） | ✅ 本报告随附修正 |
| P1 | AC5 候选自动 pytest：把 sandbox.run_pytest_regression 接为候选合并默认门槛（能力已存在, 缺接线） | 保留设计（.aionui/design/ac5_harness_pytest.md） |
| P1 | 若目标为对齐斯坦福：以 LLM Agent（本会话即实例）为 Proposer, 驱动 EvolutionLoop 产出真实 harness 候选, 记录 10M 规模运行证据 | 触发条件：v2.0 决策 |
| P2 | wiki 页面引入"源码引用校验"（引用文件必须存在）防再污染 | backlog |
| — | 维持 README/architecture_narrative 诚实边界表述（不升级为"完整 Harness 工程自动化"宣称） | 持续 |

---
*核查方法：src/ 全量文件逐一读取（trace/store.py, trace/capture.py, proposer/reader.py, proposer/writer.py, pareto/loop.py, pareto/frontier.py, meta_harness/adapter.py, meta_harness/sandbox.py）+ grep 交叉验证（LLM 调用/子进程）+ git ls-files 验证 .aionui 跟踪状态 + docs/README/wiki 全量交叉核对。核查时间 2026-08-04。*
