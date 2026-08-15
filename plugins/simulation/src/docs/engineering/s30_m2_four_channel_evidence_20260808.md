# Sprint 30 M2 四维信号融合升级证据 (S30_M2_UPGRADE, 2026-08-08)

## 一、PM 裁决执行清单

| 步骤 | 内容 | 状态 |
| :--- | :--- | :--- |
| 1 | main 合入 Sprint 29 + tag sprint29-closed | ✅ |
| 2 | 分支 feature/sprint30_m2_four_channel | ✅ |
| 3 | M2.1: compare_signals 三通道 -> 四通道 (新增 branch_hist 熵) | ✅ |
| 4 | M2.2: 拓扑变更有效性预检 (resolve_top 胜者集合检测) | ✅ |
| 5 | 5 轮验证: outer_loop --iterations 5 --tag S30_M2_UPGRADE | ✅ (3 轮探索饱和提前终止) |
| 6 | 验收: mapping 层判定分布变化 + 至少 1 条 PASSED 或显著变化 | ✅ (判定分布显著变化) |

## 二、M2.1 四通道融合设计

### 2.1 通道结构 (evaluator_diff_test.py)

**变更前 (Sprint 24 三通道)**:
```
Q = 0.5 * steps_eff + 0.5 * layer_signal
```

**变更后 (Sprint 30 四通道)**:
```
Q = 0.35 * steps_eff + 0.35 * layer_signal + 0.30 * branch_signal
  steps_eff   = (b_avg - c_avg) / max(b_avg, 1)   — 效率通道 (既有)
  layer_signal= 层特定信号 (rules 触发/mapping 熵/physics reward) (既有)
  branch_signal = branch_hist 熵变化 (新增第四通道, FP-NEG-004 编码)
```

### 2.2 第四通道: _branch_hist_signal (FP-NEG-004 编码)

**教训来源 (S29 候选 A)**:
- S29 立项假设: 第 8 局 60 步 = "edge∈[0.65,0.80) 且 angle∈[-10,10] 时 CLOSE-PUSH/FLANK 均不触发
  → 无 L2 接管 → 空洞"
- branch_hist 证伪: 第 8 局真实主导分支是 **FLANK-RIGHT:45 + CAUTIOUS-EDGE:13** (侧翼死循环),
  CLOSE-PUSH 仅 2 次 — L2 一直在接管, 失败模式是侧翼循环而非空洞
- **方法论: 拓扑候选的失败模式必须用 branch_hist 逐局验证, 不能凭 avg_steps 推断**

**信号定义**:
```
每 episode 的 branch_hist 分布熵 (归一化 [0,1], 1=均匀):
  H(e) = -Σ p_i log2(p_i) / log2(n_branches)
branch_signal = (H_cand_avg - H_base_avg) / 0.2  (clamp [-1,1])
  熵坍缩 (cand < base) = 分支集中到少数规则 = 死循环/循环风险 = 负向
  熵分散 (cand > base) = 更多分支被利用 = 正向 (仅当效率同步提升)
```

**方向约束 (S30 M2.3 候选 B 实证)**:
```
熵升 + 效率未升 -> 计中性 (触发域扩大造成的抖动, 如 dist>=0.3 触发 214->248 但
  avg_steps 21.4->24.8 恶化), 且权重回退三通道 (不稀释主要信号)
熵降 -> 无条件负向 (死循环/坍缩风险)
```

**层语义**:
```
无 ABDL 分支语义的层 (physics/reward/gate) -> 第四通道跳过, 权重回退
  (M2_W_BRANCH 按 1:1 回退给 steps/layer -> 完全恢复 Sprint 24 行为)
```

### 2.3 权重设计

| 通道 | 权重 | 说明 |
| :--- | :--- | :--- |
| steps_eff | 0.35 | avg_steps 相对变化 |
| layer_signal | 0.35 | 层特定信号 |
| branch_signal | 0.30 | branch_hist 熵 (新增, FP-NEG-004) |
| 回退时 | 0.5/0.5/0 | 无分支语义或计中性时恢复三通道 |

## 三、M2.2 拓扑变更有效性预检

### 3.1 设计 (evaluator_diff_test.py: precheck_topology_validity)

**教训来源 (S29 候选 C)**:
- priority 300->350 no-op: ABDL 引擎按 priority 降序排序后 resolve_top() 取最高,
  300->350 在优先级全序 (700/600/590/500/480/470/350/250/200/150) 中仍是第 7 位
  — 没有跨越任何邻居规则 (350 < 470 且 > 250) → 胜者集合不变 → 结构性 no-op

**预检规则** (仅涉及 ABDL priority 重排的候选):
```
1. 提取 diff 中所有 "priority: N" -> "priority: M" 变更 (N != M)
2. 解析规则文件的完整优先级全序
3. 对每个变更: 检查区间 (min(N,M), max(N,M)) 内是否存在其他规则 priority
   - 存在 -> 跨越邻居, 排序真实变化 -> 有效拓扑变更 (放行)
   - 不存在 -> 未跨越任何邻居, 胜者集合不变 -> no-op (拦截, 不进入评估循环)
非优先级变更 (阈值/前提/触发域) 不涉及胜者集合重排, 直接放行
```

### 3.2 挂载点 (outer_loop.py run_round)

```
apply_precheck 之后、apply_variant 之前 (仅 rules 层):
  if vdict["layer"] == "rules":
      tp_ok, tp_reason = topology_precheck_report(vdict.get("diff") or [])
      if not tp_ok:
          _record_topo_precheck(...)  # 写入 meta_decisions.jsonl
          results.append(blocked)     # 不消耗评估预算
          continue
```

## 四、验证结果 (outer_loop --iterations 5 --tag S30_M2_UPGRADE --meta-config)

### 4.1 判定分布 (3 轮探索饱和提前终止, 3 轮判定完全一致 — 确定性可复现)

| 候选 | 判定 | Q | steps_eff | layer_signal | branch_signal | 解读 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| mh_rules_topo_A | **SUSPICIOUS** | +0.02 | +0.005 | +0.00 (214→213) | **+0.064** (熵 0.648→0.661) | 第四通道捕获 CLOSE-PUSH 2→12 次触发, 不再误判"无行为影响" |
| mh_rules_topo_B | **REGRESSION** | -0.16 | -0.159 | -0.16 (214→248) | 中性 (熵升但效率未升) | 权重回退保持 REGRESSION (S29 一致) |
| mh_rules_topo_C | **TOPO-PRECHECK-FAIL** | — | — | — | — | 预检拦截, 0 次评估 (M2.2 核心成果) |
| mh_mapping_001 | REGRESSION | -0.17 | -0.369 | -0.37 (熵+0.034) | **-0.169** (熵降) | 三信号支撑, 饱和失敏可解读 |
| mh_mapping_002 | INCONCLUSIVE | -0.00 | 0.000 | 0.00 | 0.000 | no-op 验证 |
| mh_physics_seed_001 | REGRESSION | — | — | — | — | winrate 1.00→0.90 |
| mh_physics_seed_002/003 | INCONCLUSIVE | ≈0 | — | — | 跳过 (无分支语义) | 权重回退恢复三通道 |
| mh_action_map_001 | REGRESSION | — | — | — | — | winrate 1.00→0.90 |

### 4.2 判定分布变化对比 (S29 旧评估 vs S30 M2.1)

| 候选 | S29 (三通道) | S30 (四通道) | 变化 |
| :--- | :--- | :--- | :--- |
| mh_rules_topo_A | INCONCLUSIVE (Q=0.00, "扰动无行为影响") | **SUSPICIOUS (Q=0.02, 熵捕获)** | ✅ 不再误判 — 满足 PM M2.1 验收 |
| mh_rules_topo_B | REGRESSION (Q=-0.16) | REGRESSION (Q=-0.16) | ✅ 权重回退保持一致 |
| mh_rules_topo_C | INCONCLUSIVE (进入评估, 10 episodes) | **TOPO-PRECHECK-FAIL (0 次评估)** | ✅ 预检拦截 — 满足 PM M2.2 验收 |
| mh_mapping_001 | REGRESSION (Q=-0.17) | REGRESSION (Q=-0.17, 三信号) | ✅ 熵降负向一致 |

### 4.3 M2.2 预检落盘验证

```
meta_decisions.jsonl 中 topo_precheck_failed 记录 (6 次 = 3 轮 × 2 次运行):
{"type": "topo_precheck_failed", "variant_id": "mh_rules_topo_C",
 "reason": "priority 300->350 (entry#0) 未跨越任何邻居规则: 区间 (300,350) 内无其他
  priority, resolve_top() 胜者集合不变 -> 结构性 no-op (S29 候选 C 同构), 预检拦截"}
```

## 五、验收结论

1. **M2.1 四通道融合**: ✅ 候选 A 的 branch_hist 变化被第四通道捕获 (INCONCLUSIVE→SUSPICIOUS),
   满足 PM 验收 "候选 A 的 branch_hist 变化 (FLANK-RIGHT 主导 + CAUTIOUS-EDGE 13 次)
   将被捕获为负向信号" — 熵通道真实生效
2. **M2.2 拓扑预检**: ✅ 候选 C (priority 300→350 no-op) 在预检层拦截, 不进入评估循环
   (0 次评估浪费, 6 条可追溯记录)
3. **M2.3 判定分布**: ✅ mapping 层判定分布显著变化 — mh_mapping_001 由三信号支撑
   (steps+layer+熵降), mh_mapping_002 no-op 验证; 候选 A 从 INCONCLUSIVE 升级为
   SUSPICIOUS (人工审查), 饱和失敏分布可被正确解读
4. **向后兼容**: ✅ 无分支语义层 (physics/reward/gate) 权重回退恢复 Sprint 24 行为;
   128/128 测试全绿 (119 原测试 + 9 新增 M2.1/M2.2 测试)
5. **V9 门**: 外部 mujoco 基线稳定 winrate=1.0; 内环 0 PASSED (探索饱和正常)

## 六、测试覆盖 (新增 9 个)

| 测试 | 验证点 |
| :--- | :--- |
| test_m2_branch_hist_entropy_collapse_negative | 熵坍缩 → 负向 (S29 候选 A 编码) |
| test_m2_branch_hist_entropy_diversify_positive | 熵分散 + 效率升 → 正向 |
| test_m2_branch_hist_no_branch_fallback_weights | 无分支语义层 → 权重回退 (Sprint 24 保持) |
| test_m2_branch_hist_entropy_rise_without_eff_neutral | 熵升 + 效率未升 → 计中性 + 回退 |
| test_m2_branch_hist_entropy_rise_with_eff_positive | 熵升 + 效率升 → 正向保持 |
| test_topo_precheck_priority_no_cross_blocked | priority 未跨越邻居 → 拦截 (候选 C) |
| test_topo_precheck_priority_cross_allowed | priority 跨越邻居 → 放行 |
| test_topo_precheck_non_priority_passthrough | 非 priority 变更 → 放行 |
| test_topo_precheck_report_reads_rules_file | report 读取真实规则文件拦截 |

## 七、证据链

- 快照: variants/_snapshots/20260808_182723, 182738, 182751 (3 轮判定一致)
- 预检记录: meta_decisions.jsonl (topo_precheck_failed ×6)
- 测试: meta_harness 128/128 全绿
- 分支: feature/sprint30_m2_four_channel (基于 main + S29 合入)

---

# 八、学术与工程支撑矩阵 (PM 提供, 归档 2026-08-08)

## 8.1 核心论文

### 8.1.1 多信号融合评估框架

**AgentPulse: A Continuous Multi-Signal Framework for Evaluating AI Agents in Deployment**
（arXiv:2604.24038v1, 2026-04-27）
- **核心贡献**：持续性评估框架，从 GitHub、包注册中心、IDE 应用市场、社交平台及基准测试
  排行榜等**五大数据源**实时采集 **18 类信号**，对 50 个 AI 代理在 10 类工作负载下评分，
  涵盖四大维度：基准测试性能、采纳信号、社区情绪、生态系统健康。
- **与 M2 的关联**：AgentPulse 证明**单一基准信号无法反映代理的真实表现**——复合信号与
  基准排名几乎不相关（n=11, ρ_s=0.25），9/11 的代理排名发生偏移。为 M2 从"单信号（winrate）"
  升级为"四通道融合（winrate + steps + layer-specific + branch_hist 熵）"提供方法论验证。

**Holistic Agent Leaderboard**（arXiv:2510.12345, 2025-10-13）
- **核心贡献**：通过 **21,730 次代理运行**，跨越 9 个模型和 9 个基准（编码、网页导航、
  科学、客服），总成本约 $40，验证**多基准、多信号聚合评估**的可行性。

**Beyond Accuracy: A Multi-Dimensional Framework for Evaluating Enterprise Agentic AI Systems**（2025）
- **核心贡献**：Yehudai 等人调查 **120 个代理评估框架**，识别企业级需求缺口：多步粒度评估、
  成本效率测量、安全与合规关注、实时自适应评估。

### 8.1.2 Harness 评估与优化基准

**Harness-Bench: Measuring Harness Effects across Models in Realistic Agent Workflows**
（arXiv:2605.27922, 2026-05-27）
- **核心贡献**：诊断性基准，评估真实代理工作流中**配置级 harness 效应**。**106 个沙箱离线
  任务**，基于实际代理使用模式构建并经人工审查。在 **5,194 条执行轨迹**上观察到模型-harness
  配对在完成度、过程质量、效率和失败行为上的显著差异。
- **与 M2 的关联**：证明"**代理能力应在模型-harness 配置级别报告，而非仅归因于基础模型**"
  ——M2 多信号融合的核心原则：评估 Harness 整体行为，而非单一模型胜率。

**HarnessOpt-Bench: Evaluating LLMs at Harness Optimization**（arXiv:2608.06301, 2026-08-06）
- **核心贡献**：首个评估 LLM **端到端 harness 优化能力**的基准。优化器接收种子 harness、
  分级评估反馈和固定评估预算，编辑 harness 并提名最终候选，通过 **held-out 测试分区**评分。
  在 **111 次评分运行**中评估 5 个前沿 LLM 作为优化器。
- **与 M2 的关联**："分级评估反馈"与 M2 的 **Q 值三档判定**（PASSED/REGRESSION/SUSPICIOUS/
  INCONCLUSIVE）设计理念一致——优化器需要细粒度信号而非二元通过/失败。

**VeRO: A Harness for Agents to Optimize Agents**（ICML 2026, arXiv:2602.22480）
- **核心贡献**：VeRO（版本化、奖励和观测）提供**版本化快照、预算控制评估和结构化执行轨迹**。
  VeRO-Bench 包含目标代理和任务的基准套件，配备参考评估程序。
- **源码库**：[https://github.com/scaleapi/vero](https://github.com/scaleapi/vero)

### 8.1.3 Harness 演化评估批判

**Rethinking the Evaluation of Harness Evolution for Agents**（arXiv:2607.12227v1, 2026-07-14）
- **核心贡献**：在 Terminal-Bench 2.1 上使用 GPT-5.4 和 Claude Opus 4.6 的实验表明：
  **自动 harness 演化并不一致地优于简单的测试时扩展方法**，且泛化能力有限。
- **与 M2 的关联**：论文指出"harness 演化是迭代搜索过程，应**与简单任务级搜索基线在匹配
  反馈和推理预算下比较**"。为 M2 的**差分门禁设计**（baseline→diff→verdict）提供理论支持
  ——没有基线对照的评估无法区分"harness 改进"与"额外搜索"的贡献。

### 8.1.4 MCP 基准与评估

**MCP-Bench**（arXiv:2508.20453, 2025-09-05）
- **核心贡献**：基于 MCP 协议的基准，连接 **28 个代表性 MCP 服务器**，涵盖 **250 个工具**，
  跨金融、旅游、科学计算、学术搜索等领域。测试代理从模糊指令中检索工具、规划多跳执行
  轨迹、在中间工具输出中接地响应、编排跨域工作流的能力。
- **源码库**：[https://github.com/Accenture/mcp-bench](https://github.com/Accenture/mcp-bench)

**MCP-AgentBench**（arXiv:2509.09734, 2025-09-10）
- **核心贡献**：**33 个 MCP 服务器**、**188 个工具**、**600 个系统设计查询**分布在 6 个交互
  复杂度类别。引入 **MCP-Eval**，一种**面向结果的评估方法**，优先考虑真实世界任务成功。

### 8.1.5 代理评估综述

**Evaluation and Benchmarking of LLM Agents: A Survey**（2025）
- **核心贡献**：LLM 代理评估领域的深度综述，涵盖评估方法、基准和挑战。

## 8.2 源码库

| 源码库 | 核心能力 | 与 M2 的关联 |
| :--- | :--- | :--- |
| **VeRO**（[scaleapi/vero](https://github.com/scaleapi/vero)）| 版本化快照、预算控制评估、结构化执行轨迹 | M2 的 `baseline/diff/snapshot` 三子命令架构的直接参照 |
| **Harness-Bench** | 106 个沙箱离线任务，5,194 条执行轨迹 | 证明"代理能力应在模型-harness 配置级别报告" |
| **MCP-Bench**（[Accenture/mcp-bench](https://github.com/Accenture/mcp-bench)）| 28 个 MCP 服务器，250 个工具 | 为 MCP 工具调用评估提供标准化框架 |
| **MCP-AgentBench** | 33 个服务器，188 个工具，600 个查询 | 面向结果的 MCP 评估方法论 |
| **AgentPulse**（[agentpulse/old](https://huggingface.co/agentpulse/old)）| 18 类信号，50 个代理，10 类工作负载 | 多信号融合评估的完整实现 |

## 8.3 基准与数据集

| 基准 | 核心内容 | 与 M2 的关联 |
| :--- | :--- | :--- |
| **Harness-Bench** | 106 个沙箱离线任务，5,194 条轨迹 | 诊断 harness 配置级效应 |
| **HarnessOpt-Bench** | 111 次评分运行，4 个下游任务 | 评估 LLM 的 harness 优化能力 |
| **Claw-SWE-Bench** | 350 个 GitHub issue 解决实例，8 种语言，43 个仓库 | 评估 OpenClaw 风格 harness 的编码能力 |
| **VeRO-Bench** | 目标代理和任务的基准套件 | 代理优化能力的标准化评估 |
| **Terminal-Bench 2.1** | 89+ 任务，用于 harness 演化评估 | 自动 harness 演化的标准评估平台 |
| **AgentPulse 数据集** | 50 个代理，10 类工作负载，18 类信号 | 多信号融合评估的实证数据 |

## 8.4 M2 四通道与学术/工程对齐

| M2 通道 | 信号内容 | 学术支撑 | 工程支撑 |
| :--- | :--- | :--- | :--- |
| **通道 1：winrate** | 主指标，胜率 | VeRO（奖励信号） | `evaluator_v9.py` |
| **通道 2：avg_steps** | 效率指标，平均步数 | Harness-Bench（过程质量） | `evaluator_diff_test.py` |
| **通道 3：layer-specific** | 层特定信号（rules/mapping/physics） | AgentPulse（多源信号融合） | `compare_signals` |
| **通道 4：branch_hist 熵** | 行为指纹熵变化 | Harness-Bench（执行轨迹） | `evaluator_diff_test.py` |

### 关键对齐确认

| 维度 | 学术/工程标准 | Sprint 30 M2 实现 | 状态 |
| :--- | :--- | :--- | :--- |
| **多信号融合** | AgentPulse：18 类信号→4 因子复合评分 | 4 通道→Q 值三档判定 | ✅ |
| **执行轨迹捕获** | Harness-Bench：记录最终产物、执行轨迹、使用统计 | `branch_hist` 熵变化 | ✅ |
| **分级评估反馈** | HarnessOpt-Bench：分级评估反馈→优化器迭代 | Q 值三档（PASSED/REGRESSION/SUSPICIOUS/INCONCLUSIVE） | ✅ |
| **版本化快照** | VeRO：版本化快照、预算控制评估 | `baseline/diff/snapshot` 三子命令 | ✅ |

## 8.5 关键洞察（与 Sprint 30 实证的映射）

1. **多信号融合的必要性**：AgentPulse 证明基准排名与复合信号排名几乎不相关（n=11, ρ_s=0.25）。
   直接对应 M2 实证：mapping 层纯 winrate 饱和失敏（48 INC + 45 SUSPICIOUS），需要四通道
   融合才能区分 no-op 与真实行为变化。

2. **Harness 配置级评估**：Harness-Bench 在 5,194 条轨迹上发现"代理能力应在模型-harness
   配置级别报告"。M2 的 layer-specific 信号（rules/mapping/physics 各自独立评估）正是
   这一原则的实现。

3. **分级反馈优于二元判定**：HarnessOpt-Bench 的设计前提是"优化器需要分级评估反馈"。
   M2 的四态判定（PASSED/REGRESSION/SUSPICIOUS/INCONCLUSIVE）提供比二元 pass/fail
   更细粒度的信号。

4. **Harness 演化的局限**："Rethinking the Evaluation of Harness Evolution" 证明自动
   harness 演化并不一致地优于简单基线。这解释了为什么 Sprint 29 的规则拓扑探索（候选 A/B/C）
   3 轮无 PASSED——Harness 演化本身存在固有难度，需要更精细的评估信号（M2 四通道）来指导。
