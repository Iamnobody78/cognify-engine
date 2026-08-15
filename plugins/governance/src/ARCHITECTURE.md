# agent-governance v2 — 架构设计（顶层视图）

> **快照**: v2.0.0 · 治理闭环 S63→S69 · 2026-08-10
> **维护铁律**: 本文档与代码同仓库、同提交链。任何架构级变更（新增模块/层、修改请求生命周期、加固点增减）必须在同一提交中同步更新本文档——「文档与代码同提交」。
> **详细历史**: 五层架构 L1-L5 的逐层机制见 [docs/architecture.md](docs/architecture.md)（v1.25.0 权威快照）；演进叙事见 [CHANGELOG.md](CHANGELOG.md)。

---

## 0. 架构演进：从"规则引擎"到"可验证治理闭环"

agent-governance-v2 的架构目标是**让代理行为的"声明"必须通过外部独立验证**，而非信任自报。

```
v1.x 时代 ─────────────────────────────► v2.0 时代（当前）
  五层架构 L1-L5 (aiohttp 网关)            四阶段能力闭环 (CVE-S)
  ├─ L1 基础设施 (SQLite WAL/HA/签名)      ├─ S63 可编译  协议 YAML (11-col-v1) → 可执行规则
  ├─ L2 核心网关 (auth/policy/revoke)      ├─ S64 可自省  每条规则回答"我为什么存在" (MCE AST)
  ├─ L3 治理大脑 (五级判定 + HMAC)         ├─ S65 可自审  VCE 扫描器发现规则冲突/盲点
  ├─ L4 Critic Agent (GATE 8 五批判者)     └─ S66 可验证  声明验证通道：谎报 → ESCALATE
  └─ L5 Meta-Harness (自我进化/沙箱)           │
                                             └─ S67-S69 产品化: Governance Dashboard + 策略编辑器
```

**关键转折（S66）**：此前"完成即放行"（`satisfied=true` 直通）。S66 引入 `DeclarationValidator` 验证通道——裸声明（无证据锚点）→ `verified=False` → 判定**降级**为 `ESCALATE`（c=0.6）。谎报从"零成本"变为"必然升级复核"。

---

## 1. 当前架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                    Governance Dashboard (S68/S69)                  │
│  FastAPI :8010 ── GovernanceEngine 门面 ── audit_sink 回调          │
│  (同进程 import 引擎; GOV_AGENTS_V2_PATH 可覆盖路径)                 │
└───────────────┬───────────────────────────────────────────────────┘
                │ 请求体 {"governance": {...}}
┌───────────────▼───────────────────────────────────────────────────┐
│ L3 治理大脑 — ProtocolGateway.evaluate_verified                    │
│   1. 编译协议规则 (compile_protocol_rules)                          │
│   2. 规则裁决 → action (ALLOW / ALLOW_WITH_WARNING /               │
│                     ESCALATE / DENY / SUSPEND)                     │
│   3. 声明验证 (DeclarationValidator) → verified + confidence       │
│   4. 降级裁定: 裸 satisfied → ESCALATE (c=0.6)                     │
│   5. audit_sink(record) — fail-open，审计失败不阻塞裁决             │
├───────────────────────────────────────────────────────────────────┤
│ 治理自省/自审层                                                    │
│   MCE 2.0 (mce_introspection.py) — 规则 why-exists/governs/origin   │
│   VCE 2.0 (vce_scanner.py) — 极化指数/冲突/盲点/验证通道状态        │
│   Verification (verification.py) — Noop 基线 / LLM 语义 (插槽)     │
├───────────────────────────────────────────────────────────────────┤
│ 配置层                                                             │
│   config/protocols/*.yaml (11-col-v1 声明式协议)                    │
│   └─ schema 校验 fail-closed: 缺字段 → load 失败                    │
│   └─ 部署: Dashboard POST /policies/deploy → YAML + 重建网关        │
│        + .bak 回滚 + 路径遍历防护 (_safe_protocol_name)            │
├───────────────────────────────────────────────────────────────────┤
│ L1/L4/L5 历史层（v1.25.0 继承，详见 docs/architecture.md）           │
│   storage.py (SQLite WAL) · critic/ (GATE 8) · meta_harness/       │
└───────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心模块（src/）

| 模块 | 职责 | 关键机制 |
|---|---|---|
| `protocol_gateway.py` | 协议网关（当前主入口） | `load_protocols` → `compile_protocol_rules`（每协议 3 规则: enforce/ESCALATE + ethics/DENY + ok/ALLOW_WITH_WARNING）；`evaluate_verified`（裁决+验证）；`scan`（VCE 通道）；`audit_sink` 注入；validator 可插拔 |
| `verification.py` | 声明验证通道 | `DeclarationValidator` 协议；`BaselineDeclarationValidator` 基线（无证据锚点 → verified=False, c=0.6）；NoopValidator 兼容模式 |
| `mce_introspection.py` | 治理自省（S64） | 规则 why-exists / governs / origin 溯源；MCE 2.0 AST |
| `vce_scanner.py` | 治理自审（S65） | 极化指数、RuleConflicts、BlindSpots、Verification_Channel 状态 |
| `ast_guard.py` | AST 语义门 | tree-sitter 解析（0.21.3 固定版本）；Priority 0 硬阻断 |
| `critic/` | GATE 8 批判者 | 五批判者（audit/security/arch/test/docs）并行 → PASS/REVISION/REJECT |
| `certification/` | 认证层 | ED25519 签名/验证（v1 继承） |
| `meta_harness/` | 自我进化 | 策略建议生成 + 沙箱隔离（v1 继承） |

---

## 3. 协议模型（11-col-v1）

协议是**声明式 YAML**，不是手写规则数组。编译器从 `protocol:` 块生成规则：

```yaml
schema_version: 11-col-v1
protocol:
  module: feynman_test
  category: epistemology
  level: 1
  core_purpose: 以费曼测试反制"用复杂名词掩盖无知"
  metacognitive_q: 我能否用大白话向非专家解释？
  collab_directive: 发现解释缺口时，告知用户而非含糊跳过
  trigger: 请求涉及专业概念解释
  ethics_boundary: 不得用术语掩盖不确定性
  source: docs/architecture.md#L1
  frequency: always
  strategy: plain_language
  expected_output: 提供通俗解释或明确承认缺口
```

**12 个必填字段**（module/category/level/core_purpose/metacognitive_q/collab_directive/trigger/ethics_boundary/source/frequency/strategy/expected_output）。缺任一字段 → schema 校验 fail-closed → load 失败（可发现错误优于静默放行）。

**规则生成**（每协议 3 条）：
| 规则 | action | 触发 |
|---|---|---|
| `enforce` | `ESCALATE` | 协议应满足而未满足 |
| `ethics` | `DENY` | 触发伦理边界 |
| `ok` | `ALLOW_WITH_WARNING` | 正常满足 |

---

## 4. 请求生命周期（v2.0 主链路）

```
外部 Agent ──▶ {governance: {protocols: {X: {satisfied: true}}}}
      │
      ▼
ProtocolGateway.evaluate_verified
      │ ① 规则裁决（协议编译结果首中即停）
      │ ② DeclarationValidator 验证声明（证据锚点检查）
      ├─ 有证据锚点 → verified=True  → 按规则 action
      ├─ 无证据锚点（裸声明）→ verified=False → 判定降级 ESCALATE (c=0.6)
      └─ ③ audit_sink(DecisionRecord) — fail-open
      │
      ▼
返回 {action, rationale, trace_id, verification:{verified, confidence}}
```

---

## 5. 部署与集成模式

| 模式 | 说明 |
|---|---|
| **库嵌入（Dashboard）** | 同进程 `import`（sys.path 相对路径，`GOV_AGENTS_V2_PATH` 覆盖）；`ProtocolGateway(audit_sink=...)` 回调 |
| **策略热部署** | `POST /api/policies/deploy` → 校验（YAML 语法 + 11-col-v1 schema + 临时目录预编译）→ 写入 `config/protocols/` → 重建网关（保留 validator + audit_sink）→ 快照；失败自动 `.bak` 回滚 |
| **独立运行** | 协议 YAML + `ProtocolGateway` 直接嵌入业务代码（examples/ 演示） |

**安全边界**：
- `_safe_protocol_name` 正则 `[a-z_][a-z0-9_]*` 防路径遍历
- 测试隔离：deploy 测试使用临时协议目录（复制真实 YAML），绝不写入真实 config

---

## 6. 设计决策记录（ADR 摘要）

| 决策 | 理由 | 位置 |
|---|---|---|
| 协议 YAML 声明式而非手写规则 | 规则由编译器统一生成，避免 3 处重复维护 | §3 |
| 验证通道 fail-open 审计 | 审计失败不阻塞裁决（可用性优先），但裁决本身 fail-closed | §4 |
| 裸声明降级 ESCALATE 而非 DENY | 保留人类复核机会；谎报成本从 0 升到必查 | §4 |
| tree-sitter 固定 0.21.3 | 与 tree-sitter-languages 1.5.0 兼容；AST 门禁稳定 | §2 |
| 测试必须仓库根目录运行 | config 相对路径解析；避免 CWD 导致的假失败/假通过 | CONTRIBUTING §2 |
| 部署带 .bak 回滚 | 热更新失败不损坏运行中网关 | §5 |
