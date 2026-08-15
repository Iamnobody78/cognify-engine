# Sprint 63 Gate Report — 协议网关（Protocol Gateway）

- **日期**: 2026-08-10
- **分支**: `feature/s63_protocol_gateway`（基自 `sprint62-closed` = `625a5e7`）
- **PM 指令**: 将 `governance/protocols/` 下的 YAML 治理规范接入 `agent-governance-v2` 的规则引擎（核心目标：让协议编译器产出的治理规则可被自动执行）

---

## 1. 交付摘要

| 资产 | 位置 | 说明 |
|------|------|------|
| 协议网关核心 | `agent-governance-v2/src/protocol_gateway.py` | Protocol/load_protocols/compile_protocol_rules/generate_policy_yaml/ProtocolGateway（fail-closed） |
| 编译管线 | `agent-governance-v2/scripts/compile_protocol_policies.py` | 协议 YAML → 可执行规则 YAML |
| 协议 YAML（同步） | `agent-governance-v2/config/protocols/` | 3 协议（feynman_test/entropy_denoise/logic_chain_check）自 S62 A1 编译器产物 |
| 编译产物 | `agent-governance-v2/config/protocol_policies.generated.yaml` | **PolicyEngine 可直接加载执行**（9 规则） |
| 测试 | `agent-governance-v2/tests/test_protocol_gateway.py` | **23/23 PASS** |
| 模式库 | `bottlesumo_pi/governance/pattern_library/protocol_gateway_compilation.md` | 新模式入库 |
| 工程规则 | `bottlesumo_pi/governance/dashboard/engineering_rules.md` | RULE-GW-001..004 |

## 2. 门禁判定

| 门 | 判据 | 结果 |
|----|------|------|
| 单测 | 23/23 协议网关测试通过 | ✅ |
| 回归 | 74 测试文件全量 PASS（979 测试，0 失败） | ✅ |
| 零影响 | 无 governance 声明的既有流量 → 协议规则不命中 | ✅ |
| fail-closed | 坏 schema/缺字段/非法 level/空目录/重复 module 全部拒绝 | ✅ |
| 端到端 | 编译 → 生成 YAML → PolicyEngine 加载 → 执行裁决 | ✅ |

**GATE 判定：✅ PASS（5/5）**

## 3. 架构：协议 → 可执行规则

```
协议 YAML (11 列声明式)                     请求体 governance 声明
┌──────────────────────────┐              ┌──────────────────────────┐
│ schema_version: 11-col-v1 │              │ "governance": {           │
│ protocol:                 │  compile     │   "protocols": {          │
│  module: feynman_test     │──────────────▶│     "feynman_test": {    │
│  trigger: 每次新协议入库时  │  编译管线      │       "triggered": true  │
│  ethics_boundary: ...     │              │     }                     │
│  expected_output: ≥80%    │              │   }                       │
└──────────────────────────┘              └──────────────────────────┘
          │                                        │
          ▼                                        ▼
┌───────────────────────────────────────────────────────────┐
│ PolicyEngine (规则引擎, 零改动)                              │
│  protocol-{m}-ethics  (violation 非空 → DENY)    priority 5  │
│  protocol-{m}-enforce (triggered∧¬satisfied → ESCALATE) 15/20│
│  protocol-{m}-ok      (satisfied → ALLOW_WITH_WARNING) 25/30 │
└───────────────────────────────────────────────────────────┘
```

**每个协议编译为 3 条规则**（9 总规则），priority 语义：伦理 > 触发 > 放行。

## 4. 关键设计决策

1. **编译产物而非运行时解释**（RULE-GW-001）：协议 YAML → `protocol_policies.generated.yaml`，PolicyEngine 零改动原生加载执行。产物可审计、可版本化。
2. **priority 语义**（RULE-GW-002）：DENY(5) < enforce(15/20) < ok(25/30)，伦理违规压过一切；L3 高风险协议 enforce 更早拦截。
3. **正/负向前瞻防误报**（RULE-GW-003）：enforce 匹配整个状态对象 `(?=.*"triggered":true)(?!.*"satisfied":true)`，修复 triggered+satisfied 并存的边界 bug。
4. **fail-closed**（RULE-GW-004）：缺 schema_version / 缺字段 / 非法 level / 空目录 / 重复 module 全部拒绝加载。
5. **零影响**：规则 path_pattern="*" 但仅当 json_path 提取到 governance 声明才命中。

## 5. 诚实披露

1. **Notion API token 无效**：用户提供 `ntn_b93...` token 实测两个端点均失败——官方 v1 API 返回 `401 API token is invalid`，v3 loadPageChunk 返回 `400`。token 未写入任何代码/配置/git。S62 RULE-NOTION-001（CSR 墙）维持：官方 API 认证也无法在无有效 token 时读取。已向 PM 请求确认 token 有效性（或提供 workspace 内 integration 的 secret_ 前缀 token）。
2. **协议语义映射的边界**：协议 YAML 的 trigger/ethics_boundary/expected_output 为自然语言；本网关通过**请求体 governance 声明**（triggered/satisfied/violation 三态）作为机器可检查条件。若未来协议要求引擎自行解析自然语言触发，需要 LLM 语义层（不在本 Sprint 范围）。

## 6. 与双项目元提示词（DUAL-GOV-ITERATE / JIT-PARALLEL）的衔接

- **DUAL-GOV-ITERATE**: 本 Sprint 实践"治理→实验"联动——协议网关是治理执行层的可执行化；G.1 治理健康检查（8 GATE + 探针）在此 Sprint 以"23 单测 + 979 回归 + 零影响验证"落地产物。
- **JIT-PARALLEL**: 全量回归采用并行分组（GA/GB/GC/B1/B2/FINAL8）替代串行 74 文件，定位慢文件（test_concurrent.py 22s）并隔离；后续纳入 Phase P 标准流程。

## 7. 遗留（P1/P2）

| 优先级 | 项 |
|--------|----|
| P1 | A3 MMCE 工具箱 |
| P1 | A2 记忆脚手架采用到真实 .aionui/ |
| P2 | 研究引擎扩展至 rosbag/mcap 仿真数据源 |
| P2 | 协议自然语言触发 → LLM 语义层（突破 triggered/satisfied/violation 三态声明） |
