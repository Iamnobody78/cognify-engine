# SELF-EVOLVE D1-D7 ↔ MCI 五维 映射与整合 (v1.0)

> 日期: 2026-08-13 ｜ 目的: 把 SELF-EVOLVE v1.0 七大能力域（1-10 分）与既有 MCI 五维（0-5, L0-L5）建立**因果映射**，双尺度并行评估，不破坏既有系统。
> 协议联动: HONESTY-PERMANENT / META-BOOTSTRAP / MAINTENANCE-GATE / TRACE-AGENT / META-EDU

---

## 1. 映射总表（主锚点 + 次锚点）

| SELF-EVOLVE 能力域 | 主锚点 (MCI 维) | 次锚点 | 现有成熟度 | 关键证据 |
|:---|:---|:---|:---:|:---|
| **D1 可靠性** | 元监督 (L4) | 元认知 | ★★★★ | V9 门 gate_progress 10%→90%; meta_monitor.py (stagnation/loop/latency) |
| **D2 记忆与泛化** | 元学习 (L4) | 元认知 | ★★★★ | rules_entries=13; cell_learning_events=169; failure_analysis=1813 行; distill_loop.py |
| **D3 评估诚实性** | 元监督 (L4) | 元认知 | ★★★☆ | HONEST-BOUNDARY 已设计; pareto_frontier=548 行; 谎报降级 ESCALATE 实证 |
| **D4 安全与对齐** | 元调节 (L3.5) | — | ★★★☆ | param_bounds=88; 越权检测 ESCALATE; CVE-S 42 协议护栏 |
| **D5 部署工程** | 元调节 (L3.5) | 元监督 | ★★★☆ | meta_config 自适应; 资源分配**未与 SRS 联动**（已知缺口） |
| **D6 协作标准化** | 元调节 (L3.5) | — | ★★☆☆ | mcp_usage_report.jsonl 已有数据; 工具选择**未与 MCP 联动**（已知缺口） |
| **D7 自我进化** | 元进化 (L2.5) | 元认知 | ★★☆☆ | code_agent_proposer=56KB; 自举循环未落地; 架构演进未形式化 |

## 2. 因果推理：为什么这样映射

- **D1/D3 → 元监督**：可靠性=长链条成功率，评估诚实=声称vs实际差距。二者都由门评估器、监控器、帕累托前沿直接量化，是元监督的核心职责。元监督 L4 是最成熟维度 → **D1/D3 是 SELF-EVOLVE 里最稳的两维**。
- **D2 → 元学习**：跨会话记忆=经验→能力积累（rules/cell/failure/distill），正是元学习 L4 的定义。元学习同样成熟 → **D2 稳**。
- **D4/D5/D6 → 元调节**：安全护栏、资源成本、MCP 协作都是"调节/配置"层职责。元调节 L3.5 中等，且 scorecard 已记录**两个未落地缺口**——恰好对应 **D5（资源未联 SRS）与 D6（工具未联 MCP）**。
- **D7 → 元进化 + 元认知**：自我进化需要"自举循环 + 架构演进决策"（元进化）与"主动评估反思自身学习过程"（元认知）。二者都是 L2~L2.5 最弱维度 → **D7 是 SELF-EVOLVE 里最弱的一维**。

## 3. 关键收敛点（SELF-EVOLVE 精准命中 MCI 已记录的缺口）

MCI scorecard 里"元调节"的差距候选，与 SELF-EVOLVE 的 D5/D6 **逐字对应**：

| MCI 差距候选（已记录） | SELF-EVOLVE 能力域 | 状态 |
|:---|:---|:---|
| "资源分配未与 SRS 联动" | **D5 部署工程** | 待落地 |
| "工具选择未与 MCP 联动 (mcp_usage_report.jsonl 已有数据)" | **D6 协作标准化** | 待落地 |

→ SELF-EVOLVE 为这两个已知缺口提供了**外部学术锚点**（D5↔Beyond Accuracy CLEAR 框架, D6↔MCP/A2A/ACP/ANP 互操作协议调研），使"缺口"从项目内自评升级为**可度量的能力域**。

## 4. 双尺度评估规范

| 尺度 | 维度 | 刻度 | 用途 |
|:---|:---|:---|:---|
| **MCI 五维** (L-scale) | 元认知/元监督/元调节/元学习/元进化 | 0-5 (L0-L5) | 内部引擎成熟度，驱动 meta_bootstrap 自举 |
| **SELF-EVOLVE 七维** (D-scale) | D1-D7 | 1-10 | 外部能力自评，驱动 S.E.L.F. 四相循环 + 月度报告 |

换算（近似，供交叉校验，非硬映射）：D-scale ≈ L-scale × 2（如 L4=8/10, L2.5=5/10）。

## 5. 整合落地文件

| 文件 | 角色 |
|:---|:---|
| `meta_prompts/SELF-EVOLVE_v1.0.md` | 完整元提示词（身份/七维/S.E.L.F./月度/红线） |
| `meta_prompts/SELF-EVOLVE_v1.0_academic_matrix.md` | 论文/源码/基准三维支撑矩阵 |
| `meta_harness/self_evolve.py` | S.E.L.F. 四相循环引擎（Scan/Evaluate/Learn/Fix） |
| `meta_harness/meta_capability_scorecard.md` | 既有 MCI 五维（不变，作为 L-scale 事实源） |

## 6. 演进顺序（SELF 循环的优先级）

依据映射，S.E.L.F. 循环应优先攻击**最低分维度**：
1. **D7 自我进化**（最弱，映射 L2~L2.5）→ 自举循环 + 架构演进决策形式化
2. **D6 协作标准化**（MCP 未联动）→ mcp_usage_report.jsonl 已备数据，接入工具选择
3. **D5 部署工程**（SRS 未联动）→ 资源分配接 SRS
4. D1/D2/D3 已稳（L4）→ 仅维护，不做无证据改动
