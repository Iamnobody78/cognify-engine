# Sprint 64 Specification — MCE 2.0 AST 自省（CVE-S on governance-v2 Phase 1）

## 1. 目标

**在 protocol_gateway 中增加 MCE 2.0 AST 自省（规则可反问"我为什么存在" + 校验逻辑）**

S63 证明"治理可编译"（协议 YAML → 可执行规则）；S64 证明"治理可自省"——让每条规则能回答"我为什么存在、我在治理什么"，这是 CVE-S on governance-v2 的第一阶段。

## 2. 范围

### 2.1 MCE 2.0 契约（复用既有实现）

| AST 字段 | 语义 | 规则来源 |
|----------|------|----------|
| Core_Directive | 核心指令（规则存在的根本原因） | 规则类型语义 + 协议名 + 规则名 |
| Entities | 治理对象实体 | trigger/ethics/output/module 文本提取 |
| Structural_Constraints | 结构约束 | trigger + ethics + output |
| Tension_Vectors | 张力向量（潜在冲突） | 规则类型预置 |
| Entropy_Score | 熵值（复杂度） | 实体多样性 + 约束数 → [0.1, 0.9] |

### 2.2 交付物

**agent-governance-v2**：
- `src/mce_introspection.py` — RuleMCE/ProtocolMCE/build_mce_introspection
- `src/protocol_gateway.py` — 增加 `introspect()` 集成点
- `scripts/compile_mce_introspection.py` — 产物管线
- `config/mce_introspection.generated.json` — 可审计自省产物
- `tests/test_mce_introspection.py` — 20 单测

**bottlesumo_pi**：
- `pattern_library/mce_introspection_governance.md` — 新模式
- `dashboard/engineering_rules.md` — RULE-MCE-001..003 + RULE-NOTION-001 修订
- `sprint_reports/s64_*.md` — 报告

## 3. 验收判据

| # | 判据 | 度量 |
|---|------|------|
| G1 | MCE 单测全过 | 20/20 |
| G2 | S63 协议网关回归 | 23/23（合计 43/43） |
| G3 | AST 契约对齐 meta_edu MCE 2.0 | 5 字段 |
| G4 | 每条规则可自省 | why_exists/what_it_governs/constraints |
| G5 | 溯源完备 | origin 4 字段 + JSON 可序列化 |

## 4. 设计

### 4.1 自省集成

```
ProtocolGateway.rules (9 条, S63)  ──introspect()──▶  MCE 2.0 AST (9 个)
                                                       ├─ 自省接口
                                                       ├─ 溯源 origin
                                                       └─ 张力 Tension_Vectors
```

### 4.2 关键机制

- **契约复用**（RULE-MCE-001）：字段对齐 meta_edu，自包含实现，零跨仓库运行时依赖
- **自省即一等公民**（RULE-MCE-002）：`introspect()` 原生方法 + 产物管线
- **张力显式预置**（RULE-MCE-003）：为 S65 VCE 扫描做输入准备

## 5. Notion 突破（附）

- 新 token 有效（认证通过 200/404），child_page.title 可读完整内容
- S62 旧 URL 页面未共享（404），但 workspace 有 50+ 可访问页面
- RULE-NOTION-001 修订为认证态两分支

## 6. 关联

- 上游：S63 协议网关（规则产物）
- 契约：bottlesumo_pi/governance/meta_harness/meta_edu.py（MCE 2.0）
- 下游：S65 VCE 2.0 扫描器（消费 Tension_Vectors）、S66 CEE、S67 双向往复
