# Meta-Harness 学术对齐差距分析与增强方案 (MHA-ARCH v1.0 执行记录)

> 日期: 2026-08-06 ｜ 依据: PM 指令 (TASK-007 签署前置任务) + MHA-ARCH v1.0 元提示词
> 协议: A.C.Q.U.I.R.E. ｜ 状态: ✅ **I(集成) 阶段完成** — P0-V1/P0-V2 落地并验证, R(复盘) 进行中

## 1. A(Assess) — P1 引擎 vs 斯坦福原版差距量化

| 差距 | 当前 P1 | 斯坦福原版 | 影响 |
| :--- | :--- | :--- | :--- |
| **G1 Proposer** | `variants.py` 规则模板生成器 (verified 串匹配, 3 层固定工厂) | **编码代理** (读取全部历史候选源码/分数/执行轨迹, 自由生成) | 核心差距: 7.7pp 提升来源 |
| **G2 元认知** | 无 (评估后仅追加 failure_analysis.md) | advanced-reasoning MCP: 置信度追踪/假设检验/推理链验证 | 搜索盲目性 |
| **G3 记忆** | 静态文件 (harness_candidates.json/pareto_frontier.md) | MemEvolve 经验知识共同进化, 经验→能力积累 | 无跨轮学习 |
| **G4 自指** | 无 (proposer 不能改自身) | Gödel Agent 递归自我改进 | 无更高层优化 |
| **G5 评估** | v9_gate_evaluator 10 局确定性种子 | 文本分类/Terminal-Bench 2 有 held-out test set | 泄漏风险 (已知, 可接受) |

## 2. C(Cite) — 理论锚定

- **Meta-Harness (arXiv:2603.28052)** — 编码代理 proposer + 文件系统血缘搜索 (G1 直接理论)
- **Self-Improvements Survey** — 自改进代理 = 经验→能力积累 (G3)
- **Gödel Agent** — 递归自我改进, 消除人类设计先验 (G4)
- **MetaAgent** — 工具元学习, 不改模型参数 (整体原则: 冻结模型进化外壳)
- **MemEvolve/EvolveLab** — 记忆-经验共同进化 (G3 设计参考)

## 3. Q(Query) — 开源生态检索结果

| 仓库 | 状态 | 价值 |
| :--- | :--- | :--- |
| stanford-iris-lab/meta-harness | ✅ 已克隆 .aionui/reference/ (104 文件) | 官方框架, ONBOARDING.md, claude_wrapper.py proposer 契约 |
| angrysky56/meta-harness | ✅ 已克隆 (87 文件) | Hermes Agent 替换 Claude Code, **Ollama 本地支持** |
| SuperagenticAI/metaharness | 可达 (未克隆) | Codex 优化器参考 |
| 本地 Ollama | ✅ 6 模型就绪 | qwen2.5:7b (proposer 引擎) + bge-m3 (经验检索) |

**关键契约发现** (官方 claude_wrapper.py): proposer wrapper 核心职责 = 记录 SessionResult
(prompt/text/tool_calls/files_read/files_written/token_usage/duration/model/exit_code/cost/raw_events)。
社区 EvolutionEngine: Candidate(name/hypothesis/axis/components/metadata) + Evaluator protocol。

## 4. U(Unify) — 增强方案 (帕累托: 核心差距优先, 不破坏现有测试)

### P0-V1: 编码代理 Proposer (`code_agent_proposer.py`) — 对应 G1
- **不替换** variants.py (向后兼容, 红线#3); 通过 `--proposer code_agent` 启用, 默认规则模板
- 引擎: 本地 Ollama qwen2.5:7b (OpenAI 兼容 API), 系统提示注入 Meta-Harness 理论 + 领域知识
- 输入: harness_candidates.json + pareto_frontier.md + failure_analysis.md + 最近执行轨迹
- 输出: 与现有 Variant 同构 (id/layer/target_file/diff/hypothesis/evidence/bloodline)
- **幻觉防御**: diff 必须通过现有精确串匹配校验 (apply_variant 前原子校验), 无效 diff 丢弃并记录
- 会话日志: 参照官方 SessionResult 契约写入 experience/

### P0-V2: 元认知模块 — 对应 G2 (advanced-reasoning 轻量本地版)
- 置信度追踪: proposer 自报 confidence + 依据, 存候选 metadata
- 假设检验: "假设→评估结果"配对 JSONL, 命中率统计, 反馈注入下次提议上下文

### P1-V3: 经验记忆层 — 对应 G3 (MemEvolve 式)
- experience/ JSONL 累积 + bge-m3 语义检索相似经验 (Ollama 已就绪)
- 提议时注入 top-k 相似经验 (经验→能力积累闭环)

### P2-V4: 自指最小闭环 — 对应 G4 (Gödel Agent 式, 最小化)
- meta_config.json: proposer 可建议自身参数 (候选数/探索利用偏好), 门裁决后生效

## 5. 集成约束 (红线)
1. ✅ 不替换既有 variants.py / outer_loop.py 主路径 (默认行为零变化)
2. ✅ 新 proposer 候选必须通过现有 diff 原子校验, 否则丢弃
3. ✅ 回归: pytest + v9_gate_evaluator 全量复验 (红线#3)
4. ✅ 本地 Ollama 直连 (不新增外部依赖, 与既有 8766 vision 端口并存)

## 6. 验证计划 → ✅ 执行结果 (I 阶段实录)

### P0-V1 编码代理 Proposer — ✅ 端到端验证 PASS
- 实测 2 轮 (本地 qwen2.5:7b): 产出 2 个**有效候选**, diff 均通过精确串匹配:
  1. `ca_physics_1`: GRIP_DECAY 抓取稳定性 (conf=0.7, 239s)
  2. `ca_gate_0`: V9_WINRATE_THRESHOLD 0.60→0.70 (conf=0.8, 62s)
- **幻觉防御实证**: LLM 曾提议 `edge_min < 0.6` 改 v9_gate_evaluator.py — 该串在目标文件中 count=0,
  **被校验器正确拦截丢弃** (既有的 rule 工厂同款防线)
- 源码摘录注入: 5 文件关键符号上下文 (编码代理"文件系统访问"本地等价物), prompt 4.2KB
- 血缘加载修复: variants._find_file 的 `REPO_ROOT/../..` 基数缺陷 (越过工作区根)
  → code_agent_proposer 用 WORKSPACE_ROOT 本地修正, **未动 variants.py**

### P0-V2 元认知 — ✅ 验证 PASS
- 假设检验闭环: record_hypothesis → hypotheses.jsonl (confirmed/rejected) → load_history
  命中率统计 → 注入下次提议系统提示 (经验→能力积累成立)
- 会话契约: sessions.jsonl 记录 SessionResult (prompt/completion tokens, duration)

### 治理缺口修复 (血缘落地)
- **发现**: outer_loop 的 PARETO_FILE/FAILURE_FILE 指向工作区根, 但 4 个工作文件
  (harness_candidates.json/pareto_frontier.md/failure_analysis.md/skill_doc.md) 从未存在
  → 每轮 Pareto 写入被跳过 (WARN), WSL ~/.aionui/ 为陈旧残留 (2026-07-27, 20%胜率)
- **修复**: 4 文件全部落位工作区根 + Pareto 更新至当前真实前沿 (100% 胜率, 418 步)

### 回归 (红线 #3) — ✅ 零劣化
- pytest: 46 passed / 4 failed (既有 test_heuristic_rules, 与本次无关) / 2 collection errors (缺依赖)
  = **与基线完全一致**
- variants.py / outer_loop.py 未修改 (零侵入)

## 7. R(复盘) — 关键经验
1. 本地 7b 编码代理可行但慢 (60-240s/提议) — prompt 体积是主要杠杆 (4.2KB 平衡精度/时延)
2. 源码摘录注入大幅降低幻觉 (LLM 基于磁盘事实而非记忆编造)
3. 既有 P1 存在路径基数缺陷 + 治理文件缺失 — 学术对齐过程中自然暴露并修复
4. 未做 (待后续): P1-V3 经验检索 (bge-m3), P2-V4 自指改进 (meta_config), G5 held-out 评估

## 8. Sprint 8 P0-V1 集成 (PM 签署 2026-08-06) — ✅ 全链路 PASS
- `outer_loop.py --proposer code_agent` 接入 (默认 rule 零行为变化, 红线#3)
- **PM 验收标准达成**: MHA 候选 `ca_rules_01` (GRIP_DECAY 0.06→0.10) 通过 v9_gate
  回归 → **score=1.0, passed=True, steps=214** → Pareto 保留 (LLM 提议被门验证有效的
  首个实例; 效率提升 214 < 1e9 基线)
- 修复 2 个既有缺陷 (Sprint 8 集成暴露): ① evaluate_candidate WSL 路径转换
  (_to_wsl_path, Windows 直跑 bash cd 失败) ② outer_loop --help cp950 崩溃 (stdout reconfigure)
- MHA 提议器多轮工程迭代 (v1→v3):
  - v1 规则模板 (基线) → v2 编码代理 (LLM 生成完整 diff — 7b 幻觉率高)
  - v3 **混合架构**: LLM 只做数值决策 (anchor+value), 代码确定性构造 diff
    - auto_target: anchor 自动定位文件 (7b 顽固错配 target_file 实证)
    - 行级模糊定位: 解决 anchor 微妙改写 (0.06 vs "0.06" 引号差异)
    - 重试反馈循环: 拒绝原因反馈 LLM 修正 (原版"提议-验证-反馈"精髓)
    - max_tokens=400 + num_ctx=4096 + temperature=0.3 (时延/质量平衡)
- 回归: pytest 46 passed/4 failed 与基线一致; GRIP_DECAY=0.10 为新工作树基线 (提交固化)
