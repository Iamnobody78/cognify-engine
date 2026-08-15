# ARCHITECTURE.md — agent-governance v2

![Tests](https://img.shields.io/badge/tests-574%20passed-green)
![GATE 8](https://img.shields.io/badge/GATE%208-5%2F5%20PASS-green)
![Snapshot](https://img.shields.io/badge/snapshot-v1.25.0-blue)
![License](https://img.shields.io/badge/license-MIT-blue)
![CI](https://img.shields.io/badge/CI-GATE%201--8-blueviolet)
![Meta](https://img.shields.io/badge/meta-5%2F7%20%CE%94%20%28%E2%9C%94+%E2%9A%A0%EF%B8%8F%29-orange)
[![行为守则](https://img.shields.io/badge/Contributor%20Covenant-2.1-4baaaa.svg)](CODE_OF_CONDUCT.md)
[![安全策略](https://img.shields.io/badge/Security-Policy-brightgreen)](SECURITY.md)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

> 本文档是 agent-governance v2 的架构设计文件。它以 v1.7.0-PoC 的自我批判为起点，定义了一个诚实的、可验证的、生产就绪的 Agent 治理框架。

> **📐 现行架构权威参考（v1.24.0, 2026-08-03）**：[docs/architecture.md](docs/architecture.md)
> **🔐 认证授权层（P13）**：[docs/AUTH.md](docs/AUTH.md) — API Key→租户映射 + Bearer/X-API-Key 双格式 + 租户隔离（AC1-AC7 全过）
> **🧬 Meta-Harness 适配层（L5 策略级自进化，能力边界明确）**：[src/trace/](src/trace/)（决策轨迹）→ [src/meta_harness/](src/meta_harness/)（adapter=确定性策略建议器：DENY 扫描→YAML 候选→3 层门控；无 meta_scheduler 模块, 更正见 docs/meta_harness_verification.md）→ [src/pareto/](src/pareto/)（质量vs成本 Pareto 前沿+≥3 轮迭代）；融合报告见 [docs/META_HARNESS_FUSION_REPORT.md](docs/META_HARNESS_FUSION_REPORT.md)。**诚实边界（2026-08-03 元批判核查后明确）**：本层为"策略建议器"——零侵入只读 storage、复用 policy.py、仅生成 YAML 候选，**不**修改 Harness 核心代码；"完整 Harness 工程自动化"（斯坦福 Meta-Harness 级：完整执行轨迹重写+跨领域验证）**不在当前能力内**，列为 v2 方向。
> **🔄 自举运行时（P12 确定性调度器）**：[src/bootstrap/](src/bootstrap/) — 感知→诊断→修复→验证→部署主循环 + `bootstrap_state.db`（SQLite）状态持久化；codegen 漂移自动修复+白名单提交，失败回滚，人类在环（`auto_push` 默认 False）；`python -c "from src.bootstrap import run_cycle; run_cycle()"` 单轮演练
> **🧬 元能力自检清单（P11 诚实声明）**：[docs/META_CAPABILITIES.md](docs/META_CAPABILITIES.md) — 自审计/自修复/自追踪/自认证/自生成 ✅ 5/7，自修改/自部署 ⚠️（人类在环，诚实边界）
> **🛡️ 高可用设计（Phase HA）**：[docs/ha_design.md](docs/ha_design.md)
> **🔏 认证层（P8 ED25519）**：[docs/CERTIFICATION.md](docs/CERTIFICATION.md) — `python -m src.certification.sign --file <f>` / `python -m src.certification.verify --file <f> --signature <sig>`
> **🔌 外部代理接入（P9 examples）**：[examples/README.md](examples/README.md) — LangChain/AutoGen 零侵入 `base_url` 接入 + 通用 Python agent_tools；`powershell -File examples/run_examples.ps1`（Windows）或 `bash examples/run_examples.sh`（Git Bash）一键验收
> **🤝 贡献指南（P10 开源就绪）**：[CONTRIBUTING.md](CONTRIBUTING.md) — GATE 1-8 + Agent 治理流程 + 提交规范；CI 见 [.github/workflows/ci.yml](.github/workflows/ci.yml)
> 本文档为 v1→v2 的演进叙事与 ADR 附录；**当前五层架构（L1-L5）、模块清单、请求生命周期、暗雷区加固点、HA 部署拓扑、认证层**以 docs/ 为准，架构变更须与该文档同提交。

---

## 第一章：为什么重来

### 1.1 v1 的问题不是"实现不到位"，是"概念与代码之间不存在对应关系"

v1.7.0-PoC 的 CRITIQUE.md 对 6 个核心模块的逐行审计揭示了一个系统性模式：

| 模块 | 宣称 | 实际代码 | 行号 |
|------|------|----------|:--:|
| GodelianBoundary | 哥德尔不完备性边界检测 | 6 个关键词正则匹配 | `godelian_boundary.py:110-117` |
| FixedPointDetector | Banach 不动点检测假收敛 | `abs(current - previous) < epsilon` | `fixed_point_detector.py:32` |
| MetaCognitiveLoop | 5 阶段元认知闭环 | 均值+多样性阈值；开发者自注"玩具算式" | `meta_cognitive_loop.py:314,504` |
| SelfCheck | 10 边界场景验证 | `len(strategy.description) < 3` | `meta_cognitive_loop.py:573` |
| AgentInterface | 零侵入 Sidecar | ABC 继承 + 4 个 @abstractmethod | `agent_interface.py:13-68` |
| 530 测试 | 治理逻辑测试 | dataclass 字段赋值验证（~70ms/test） | 全部 test_*.py |

**这不是一个可以"修复"的代码库。** 每一行代码都是为"看起来像那么回事"而写的，不是为"真正工作"而写的。在 regex 基础上补 Gödel 编号和在自行车上装火箭发动机一样——底盘不承载。

### 1.2 v1 的真正价值

v1 不是废品。它的价值不在代码而在三个层面：

| 层面 | 价值 | v2 如何使用 |
|------|------|-------------|
| **问题定义** | 4 个根本性问题（元认知缺失、无自演进、无安全边界、无自我验证）是真实存在的 | 保留为 v2 的 North Star |
| **架构草图** | 4 层架构（数据→引擎→标准化→组织）是对的 | 保留架构分层，更换每层的实现方式 |
| **教训** | v1 是"如何不做一个治理框架"的完整案例 | CRITIQUE.md 作为 v2 的开发宪法，每个 Pull Request 必须对齐宣称 |

### 1.3 v2 的铁律

从 v1 的失败中提取三条不可违反的原则：

| # | 铁律 | 检查方式 |
|:--:|------|----------|
| 1 | **每个宣称必须有可执行的代码证据** | PR Review 时用 `grep` 验证：宣称 A → 代码必须有 A 的实现（不能是空壳/正则/阈值） |
| 2 | **每个测试必须验证真实运行时行为** | 禁止 `assert obj.field == value` 式的 dataclass 字段赋值测试；断言必须验证真实运行时状态——HTTP 响应字段（`resp.status`）、函数调用结果（`engine.evaluate().action`）、状态迁移值（`flushed == 1`）。由 GATE 1（`scripts/check_test_quality.py`）静态扫描强制：豁免裸 Name 比较、HTTP 根、调用根与 Subscript 链 |
| 3 | **文档与代码同一仓库、同一提交** | 架构决策记录（ADR）与实现代码在同一 PR 中提交 |

---

## 第二章：诚实架构

### 2.1 核心定位变更

| | v1 | v2 |
|---|-----|-----|
| **定位** | "可迁移的 Agent 治理范式" | "Agent 行为的透明代理网关" |
| **侵入性** | ABC 继承（SDK 模式） | HTTP/gRPC 拦截代理（Sidecar 模式） |
| **部署方式** | `pip install` + 修改 Agent 代码 | 独立进程，与 Agent 并列运行 |
| **目标用户** | Agent 开发者 | 平台运维 / SRE |

### 2.2 物理架构

```
┌─────────────┐    HTTP/gRPC     ┌─────────────────┐    HTTP/gRPC     ┌─────────────┐
│             │ ───────────────→ │                 │ ───────────────→ │             │
│  User/API   │                  │ agent-governance│                  │  Agent      │
│  Client     │ ←─────────────── │ v2 (Sidecar)    │ ←─────────────── │  (LangChain/│
│             │                  │                 │                  │  AutoGen/   │
└─────────────┘                  │ port :9000      │                  │  CrewAI...) │
                                 └────────┬────────┘                  └─────────────┘
                                          │
                                          │ 写入
                                          ▼
                                 ┌─────────────────┐
                                 │  DecisionLog    │
                                 │  (SQLite/        │
                                 │   PostgreSQL)    │
                                 └────────┬────────┘
                                          │
                                          │ 查询
                                          ▼
                                 ┌─────────────────┐
                                 │  Dashboard      │
                                 │  (Grafana/       │
                                 │   Web UI)        │
                                 └─────────────────┘
```

**关键特性**：

- **Agent 代码零修改**：Agent 不知道治理层存在。它只看到来自治理层转发的请求。
- **独立进程**：崩溃不传染。治理层挂了，Agent 仍可直连（降级模式）。
- **协议无关**：首个版本支持 HTTP/gRPC，后续可扩展 WebSocket/stdio。

### 2.3 逻辑架构（4 层）

```
┌──────────────────────────────────────────────────────────────────┐
│ L4  组织层    │ 审计报告 / 合规仪表盘 / 策略管理 UI               │
├──────────────────────────────────────────────────────────────────┤
│ L3  策略层    │ 策略引擎（YAML→可执行规则） / 冲突检测 / 优先级    │
├──────────────────────────────────────────────────────────────────┤
│ L2  决策层    │ 拦截 → 分析 → 裁决 → 转发 / 拒绝 / 升级            │
├──────────────────────────────────────────────────────────────────┤
│ L1  数据层    │ 请求/响应日志 / 决策记录 / 状态快照 / 密码学签名    │
└──────────────────────────────────────────────────────────────────┘
```

#### L1: 数据层

| 组件 | 说明 | 技术选型 |
|------|------|----------|
| RequestLog | 完整的 HTTP/gRPC 请求/响应记录 | JSON Lines 文件 + SQLite |
| DecisionRecord | 每次裁决的完整记录（输入、规则匹配、结果、时间戳） | SQLite（本地）/ PostgreSQL（集群） |
| StateSnapshot | Agent 状态快照（用于回滚和分析） | SQLite BLOB |
| CryptoSigner | 对决策记录进行签名（防篡改审计） | Ed25519 / HMAC-SHA256 |

**v1 教训**：v1 的数据层是内存字典（`DecisionLog = List[dict]`），进程重启全丢失。v2 必须持久化。

#### L2: 决策层

这是 v2 的核心——请求拦截与裁决引擎。

```
Request → [Parse] → [PolicyMatch] → [Verdict] → Forward / Deny / Escalate
                         │
                         ├─ 匹配策略规则
                         ├─ 计算风险分数
                         ├─ 检查速率限制
                         └─ 记录决策日志
```

| 裁决 | 动作 |
|------|------|
| `ALLOW` | 转发请求到 Agent，记录日志 |
| `DENY` | 返回 403，记录日志 + 原因 |
| `ESCALATE` | 挂起请求，推送审批通知（Webhook / Slack / 飞书） |

**v1 教训**：v1 的裁决是纯内存运算，无超时、无熔断、无人工审批通道。v2 必须实现：

- **超时**：单次裁决 > 500ms 自动降级为 DENY/ESCALATE（**fail-closed**，不因性能降级放行攻击面）
- **熔断**：连续 10 次 ESCALATE 未获审批 → 熔断 DENY（**fail-closed**，v0.2.x 起熔断状态持久化，重启不重置冷却）
- **人工审批**：Webhook 推送 → 外部系统确认 → 回调继续

#### L3: 策略层

策略用 YAML 定义，由策略引擎编译为可执行规则。

```yaml
# policy: block_delete.yaml
name: block-delete-operations
scope: ["production"]
rules:
  - action: DENY
    condition:
      method: POST
      path_pattern: "/api/delete/*"
    reason: "删除操作在生产环境被禁止"
  - action: ESCALATE
    condition:
      method: POST
      path_pattern: "/api/config/*"
    reason: "配置修改需要人工审批"
    escalation:
      channel: slack
      timeout: 300  # 5 分钟后自动降级为 DENY
```

**v1 教训**：v1 的"策略"是硬编码在 Python 字典里的字符串（`"halve_learning_rate"`），不是可配置的规则。v2 的策略必须是**数据（YAML/JSON），不是代码**。

**v0.3.0 新增（TASK-REAL-010，B 阶段 json_path 工具治理）**：规则可携带 `json_path`（零依赖 JSONPath 子集：`$` `.key` `..`（递归下降） `[N]` `[*]`）+ `json_pattern`（正则），命中路径/方法后再检查**请求体 JSON**：

**v0.4.0 新增（TASK-REAL-011，C 阶段 Trace 因果追踪 + TASK-REAL-011.1 批判修复）**：决策全链路可追踪——`trace_id`/`parent_span_id` 12 列持久化（`_migrate` 无损扩容）+ `GET /v1/trace/{trace_id}` 递归 CTE 调用树端点 + `X-Trace-ID`/`X-Parent-Span-ID`/`X-Span-ID` 头协议（intercept 与 chat/completions 两个入口全覆盖，含 DENY/流式/非流式全分支）+ 超长头值 fail-safe 降级（>128 视为缺失）+ 网关版本 0.4.0。

**v0.5.0 新增（TASK-REAL-012，Phase 4 治理大脑阶段 1——可解释引擎 + 五级判定）**：`DecisionRecord.rationale` 第 13 列（每个决策记录匹配规则与原因，`_migrate` 12→13 列无损扩容）+ **五级 Verdict**——`ALLOW`（200 透传）/ `ALLOW_WITH_WARNING`（200 + `X-Governance-Warning` 响应头，转发不中断）/ `ESCALATE`（202 升舱待审）/ `DENY`（403 硬拒）/ `SUSPEND`（403 挂起待人工复审，与 DENY 区分"临时冻结"）+ `create_app(config_path)` 策略注入（测试/多租户可加载独立策略文件）+ 网关版本 0.5.0。

**v0.6.0 新增（TASK-REAL-012，Phase 5 Context Hook HMAC——L3 治理大脑收尾）**：治理头防伪造——`X-Trace-ID`/`X-Parent-Span-ID`/`X-Span-ID` 以 HMAC-SHA256 签名（`X-Governance-Signature` + `X-Governance-Timestamp`，±300s 防重放窗），伪造头 fail-safe 降级为新链根（隔离孤立节点，永不进入审计链）；`CONTEXT_HMAC_KEY` 环境变量开关（未设置 = 兼容模式，行为与 v0.5.0 完全一致）+ 网关版本 0.6.0。五层架构 L1-L5 全部闭环。

**v1.25.0 新增（Tree-sitter AST 硬阻断引擎——L1 内核强化）**：Priority 0 前门先于一切 YAML 规则匹配——`src/ast_guard.py`（P1 Capture 校验 / P2 payload_extractor 提取 / P3 命令表仅存 .scm 零硬编码 / fail-closed 启动）+ `queries/{python,bash,sql}.scm`（S-expression 零正则）+ policy.py `_ast_gate` 集成 + main.py 注入（`AG_AST_DISABLE=1` 逃生舱）；审计 trace 携带精确行号 + S-expression 标签；依赖锁定 `tree-sitter==0.21.3` + `tree-sitter-languages==1.5.0`（0.25+ 移除 Query 匹配 API）；574 tests。

**v1.24.0 新增（社区标准合规补全——模范开源项目）**：CODE_OF_CONDUCT.md + SECURITY.md + Issue/PR 模板 + dependabot.yml + codeql.yml + README 3 社区徽章；13 项开源社区标准核查全闭合；542 tests。

**v1.13.0 基线（P6 认证层前置，main.py 兼容模式引用）**：五层架构闭环后、P13 认证授权层引入前的稳定基线——`auth: Optional[TenantAuth] = None` 即"兼容模式"（直接放行，391 回归保障）；本条目为 README 版本声明与 main.py 历史版本引用的一致性记录（Critic-Docs D2）。

```yaml
  # 任意内部路径 + body 声明 shell 工具 → DENY
  - name: block-shell-tool
    path_pattern: "*"
    method: POST
    action: DENY
    priority: 10
    json_path: "$..name"
    json_pattern: "^(execute_command|system_run|shell_exec|bash|python_exec)$"
    reason: "LLM 请求声明系统级工具 — 拒绝 (json_path 治理)"
```

安全语义：非 JSON 体/无法提取 → 条件不满足 → 规则不匹配（结构化体才承载工具调用；无法解析体的兜底由 fail-closed 层负责）。完整设计见 `docs/json_path_governance_report.md`。

#### L4: 组织层

| 组件 | 说明 |
|------|------|
| 审计报告 | 从 DecisionRecord 生成合规报告（谁在何时做了什么裁决） |
| 合规仪表盘 | Grafana 面板：请求量、拒绝率、升级率、延迟分布 |
| 策略管理 UI | 可视化的策略编辑器（YAML → 表单），非技术人员可操作 |

**v1 教训**：v1 的"可观测性"是 `get_state()` 返回一个字典。v2 的可观测性必须是**实时指标 + 持久化日志 + 可视化**。

---

## 第三章：v1 → v2 模块映射

### 3.1 可保留的概念（重新实现，不移植代码）

| v1 模块 | v1 实现 | v2 保留的概念 | v2 实现方式 |
|---------|---------|---------------|-------------|
| GodelianBoundary | 关键词正则匹配 | "自指命题可能导致不安全行为"这个想法本身 | 在策略层设置规则：检测 Agent 对自身代码/配置的修改请求 → 自动 ESCALATE |
| FixedPointDetector | `abs(x-y) < epsilon` | "行为收敛不等于找到最优解"这个想法 | 在决策层增加滑动窗口分析：连续 N 次相同 Action → 标记为 `PATTERN_STUCK` → 发告警 |
| MetaCognitiveLoop | 玩具算式 | "Agent 需要知道自己的局限"这个想法 | 在决策层增加 `CapabilityCheck`：跨过策略定义的能力边界时 → 注入 "你确定吗？" 元提示到响应头 |
| SelfCheck | `len(desc) < 3` | "系统需要自我验证"这个想法 | 在数据层增加 `HealthCheck`：定时验证日志完整性、签名有效性、策略一致性 |
| AgentInterface | ABC 继承 | "标准化的 Agent 行为描述" | 在 L3 策略层用 YAML schema 描述 Agent 能力，而非 Python 继承 |

### 3.2 直接抛弃（无保留价值）

| v1 模块 | 为什么抛弃 |
|---------|-----------|
| test_*.py (全部 530 个) | dataclass 赋值验证，等同于无测试 |
| adp_taxonomy.py | 学术分类法无工程价值 |
| applicability.py | "适用性门"的阈值判定无实际用途 |
| database_governance.py | 纯 dataclass 包装，无数据库交互 |

### 3.3 保留并改进（少量代码可移植）

| v1 模块 | 保留部分 | 改进方向 |
|---------|----------|----------|
| code_hole_detector.py | AST 扫描逻辑可用 | 从 lint 工具升级为 CI 门禁 |
| github_guardian.py | Issue/PR 健康扫描逻辑 | 从静态分析升级为事件驱动 |

---

## 第四章：第一个模块 — HTTP 拦截网关

### 4.1 模块规格

```
模块名: governance-gateway
语言: Python 3.10+
框架: aiohttp (异步 HTTP) / grpcio (gRPC)
端口: 9000 (默认，可配置)
协议: HTTP/1.1 + gRPC (首版支持 HTTP)
```

### 4.2 API 规范

```
POST /v1/intercept
  - 请求体: 原始 Agent 请求的完整副本（method, path, headers, body）
  - 响应: ALLOW(200, 转发) / DENY(403) / ESCALATE(202, 挂起)
  - 超时: 500ms（超时自动 DENY/ESCALATE，fail-closed）

GET /v1/health
  - 返回: {"status": "ok", "uptime": 3600, "decisions": 1423}

GET /v1/decisions?from=2026-08-01T00:00:00Z&to=2026-08-02T00:00:00Z
  - 返回: 决策记录列表（分页）

GET /v1/trace/{trace_id}   （v0.4.0，TASK-REAL-011 C 阶段）
  - 返回: 该 trace 的完整调用树（递归 CTE：parent_span_id IS NULL 为根，
    每节点含 tool_name/tool_lethality 边权重；depth ≤ 50，节点 ≤ 500）
  - 404: trace_id 未知或超长（>128 字符）
  - Trace 头协议: 请求带 X-Trace-ID（缺省生成 UUID 链根）/
    X-Parent-Span-ID（缺省 NULL=根锚点）; 响应回传 X-Span-ID（=decision.id）;
    超长头值（>128）fail-safe 降级为缺失语义
```

### 4.3 数据流

```
                Agent Client                    agent-governance-v2                  Actual Agent
                    │                                    │                                │
                    │  POST /api/chat                    │                                │
                    │  {"message": "delete user 42"}     │                                │
                    │ ─────────────────────────────────→ │                                │
                    │                                    │                                │
                    │                                    │  1. Parse request              │
                    │                                    │  2. Match policies             │
                    │                                    │     → block_delete matched     │
                    │                                    │  3. Verdict: DENY             │
                    │                                    │  4. Log decision               │
                    │                                    │                                │
                    │  403 Forbidden                     │                                │
                    │  {"reason": "block-delete-..."}    │                                │
                    │ ←───────────────────────────────── │                                │
```

### 4.4 第一个 PR 的验收标准

- [ ] `POST /v1/intercept` 返回 `ALLOW` 当无匹配策略时
- [ ] `POST /v1/intercept` 返回 `ALLOW_WITH_WARNING`（200 + `X-Governance-Warning` 头）当匹配警告策略时
- [ ] `POST /v1/intercept` 返回 `DENY` 当匹配禁止策略时
- [ ] `POST /v1/intercept` 返回 `ESCALATE` 当匹配升级策略时
- [ ] `POST /v1/intercept` 返回 `SUSPEND`（403）当匹配挂起策略时
- [ ] 超时 500ms 后自动 DENY/ESCALATE（fail-closed，不阻塞 Agent 但绝不放行攻击面）
- [ ] 所有决策写入 SQLite（可查询、不可篡改）
- [ ] `GET /v1/health` 返回运行状态
- [ ] 测试：包含真实的 HTTP 请求/响应（非 dataclass 赋值）
- [ ] 测试：包含超时场景
- [ ] 测试：包含并发场景（≥10 并发请求）

---

## 附录 A：架构决策记录 (ADR)

### ADR-001: 为什么选 Sidecar 而非 SDK

| 选项 | 优点 | 缺点 | 决定 |
|------|------|------|:--:|
| SDK (v1 方式) | 集成简单 | Agent 代码必须修改；框架升级需重新部署 Agent | ❌ |
| Sidecar (v2 方式) | Agent 零修改；独立升级；崩溃不传染 | 增加网络延迟 | ✅ |
| WASM 插件 | 性能最优 | 生态不成熟；调试困难 | 🔮 未来 |

### ADR-002: 为什么选 aiohttp 而非 FastAPI

| 选项 | 优点 | 缺点 | 决定 |
|------|------|------|:--:|
| FastAPI | 自动 OpenAPI、Type Hints | 依赖重（Starlette+Pydantic）；拦截代理不需要这些 | ❌ |
| aiohttp | 轻量（~2MB）；原生异步；适合代理场景 | 无自动文档 | ✅ |

### ADR-003: 为什么选 SQLite 而非 PostgreSQL（首版）

| 选项 | 优点 | 缺点 | 决定 |
|------|------|------|:--:|
| SQLite | 零配置；单文件；适合单机 Sidecar | 不适合多副本 | ✅ (v2.0) |
| PostgreSQL | 集群友好；强一致 | 需要独立部署 | 🔮 (v2.1+) |

---

## 附录 B：v2 与 v1 的关键差异总结

| 维度 | v1.7.0-PoC | v2.0 |
|------|------------|------|
| 侵入性 | ABC 继承 | Sidecar 代理（零修改） |
| 策略定义 | 硬编码 Python 字典 | YAML 配置文件 |
| 决策引擎 | if-else + regex | 策略匹配树 + 优先级 |
| 持久化 | 内存字典 | SQLite / PostgreSQL |
| 可观测性 | `get_state()` 字典 | Prometheus 指标 + Grafana |
| 人工审批 | 无 | Webhook 推送 + 回调 |
| 超时/熔断 | 无 | 500ms 超时 fail-closed + 连续失败熔断 fail-closed（状态持久化） |
| 测试 | dataclass 赋值验证 | 真实 HTTP/gRPC 请求 |
| 诚实度 | 学术名词堆砌 | 每个宣称有代码证据 |

---

## 📚 更多文档

| 文档 | 说明 |
|------|------|
| 📖 [Wiki 首页](https://github.com/Iamnobody78/agent-governance-v2/wiki) | 完整文档体系：入门/架构/API/部署/路线图/治理/FAQ |
| 🏛️ [架构设计](https://github.com/Iamnobody78/agent-governance-v2/wiki/Architecture) | 五层架构详解 + 数据流 |
| 📚 [API 参考](https://github.com/Iamnobody78/agent-governance-v2/wiki/API-Reference) | 所有端点 + 请求/响应格式 |
| 🛠️ [部署指南](https://github.com/Iamnobody78/agent-governance-v2/wiki/Deployment) | Docker / K8s / 生产部署 |
| 🧭 [路线图](https://github.com/Iamnobody78/agent-governance-v2/wiki/Roadmap) | 已完成 + 计划功能 |
| 🤝 [治理机制](https://github.com/Iamnobody78/agent-governance-v2/wiki/Governance) | 治理流程 + Critic 机制 + 元能力 |

---

*本文档随 agent-governance v2 的每次架构变更更新。最后更新：2026-08-03（TASK-REAL-008：铁律 2 措辞与 GATE 1 对齐；超时/熔断 fail-closed 表述修正）。*
