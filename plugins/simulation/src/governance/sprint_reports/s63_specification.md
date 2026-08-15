# Sprint 63 Specification — 协议网关（Protocol Gateway）

## 1. 目标

**将 `governance/protocols/` 下的 YAML 治理规范接入 `agent-governance-v2` 的规则引擎（核心目标：让协议编译器产出的治理规则可被自动执行）**

S62 A1 协议编译器把 11 列协议表编译为声明式 YAML（`bottlesumo_pi/governance/protocols/schema/*.yaml`），但声明式 YAML 无法被规则引擎自动执行。S63 在 agent-governance-v2 中构建**协议网关**：将协议 YAML 编译为 PolicyEngine 可加载执行的规则，使治理协议从"文档"变为"运行时裁决"。

## 2. 范围

### 2.1 协议源（3 个协议，来自 S62 A1 编译器）

| 协议 | category | level | trigger | ethics_boundary | expected_output |
|------|----------|-------|---------|-----------------|-----------------|
| feynman_test | 自我檢核 | L2 | 每次新协议入库时 | 不用于误导性简化 | 理解深度评分 ≥ 80% |
| entropy_denoise | 信息处理 | L3 | 输入信息熵 > 阈值时 | 不曲解原始意图 | 去噪后的要点列表 |
| logic_chain_check | 逻辑验证 | L3 | 关键决策前 | 不攻击人格 | 逻辑链完整报告 |

### 2.2 交付物

**agent-governance-v2**（治理执行层）：
- `src/protocol_gateway.py` — 协议网关核心（加载/编译/执行）
- `scripts/compile_protocol_policies.py` — 编译管线
- `config/protocols/` — 3 协议 YAML（自编译器产物同步）
- `config/protocol_policies.generated.yaml` — 编译产物（PolicyEngine 直接加载）
- `tests/test_protocol_gateway.py` — 23 单测

**bottlesumo_pi**（实验层）：
- `pattern_library/protocol_gateway_compilation.md` — 新模式
- `dashboard/engineering_rules.md` — RULE-GW-001..004

## 3. 验收判据

| # | 判据 | 度量 |
|---|------|------|
| G1 | 协议网关单测全过 | 23/23 |
| G2 | 全量回归零失败 | 979 PASS / 0 FAIL |
| G3 | 既有流量零影响 | 无 governance 声明 → 无规则命中 |
| G4 | fail-closed | 坏输入全部拒绝加载 |
| G5 | 端到端可执行 | 编译产物被 PolicyEngine 加载并正确裁决 |

## 4. 设计

### 4.1 协议 → 规则映射（每协议 3 规则）

| 规则 | json_path | json_pattern | action | priority |
|------|-----------|--------------|--------|----------|
| `protocol-{m}-ethics` | `$.governance.protocols.{m}.violation` | `.+`（非空） | DENY | 5 |
| `protocol-{m}-enforce` | `$.governance.protocols.{m}` | `(?=.*"triggered":true)(?!.*"satisfied":true)` | ESCALATE | 15 (L3) / 20 (L2) |
| `protocol-{m}-ok` | `$.governance.protocols.{m}` | `(?=.*"satisfied":true)` | ALLOW_WITH_WARNING | 25 (L3) / 30 (L2) |

### 4.2 请求体治理声明 schema

```json
{
  "governance": {
    "protocols": {
      "feynman_test": {"triggered": true, "satisfied": false},
      "logic_chain_check": {"violation": "attack person"}
    }
  }
}
```

### 4.3 关键机制

- **fail-closed 加载**：schema_version 必须为 `11-col-v1`；12 必需字段齐全；level ∈ {L2, L3}；目录非空；module 唯一。
- **priority 语义**：伦理(5) > 触发(15/20) > 放行(25/30)——伦理违规压过一切，L3 高风险先拦截。
- **零影响**：path_pattern="*" + json_path 提取条件，无声明不命中。

## 5. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 协议规则干扰既有流量 | json_path 门控：仅 governance 声明命中；979 回归验证 |
| triggered+satisfied 并存误报 | 负向前瞻正则（RULE-GW-003） |
| 协议 YAML 漂移（源/副本） | config/protocols 同步自编译器产物，git 可 diff |
| Notion token 无效 | 诚实披露；请求 PM 确认 token |

## 6. 关联

- 上游：S62 A1 协议编译器（protocol_compiler.py）
- 下游：DUAL-GOV-ITERATE 内环 G.1 治理健康检查（协议规则纳入探针矩阵）
- 模式：protocol_gateway_compilation
