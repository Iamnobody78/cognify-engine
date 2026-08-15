# Pattern: mce_introspection_governance

## 一句话
在治理规则引擎之上叠加 MCE 2.0 元认知编译层，让每条可执行规则能回答"我为什么存在、我在治理什么"——治理从静态规则执行升级为可自省的活系统。

## 问题
S63 协议网关解决了"声明式协议 → 可执行规则"，但规则是"哑"的：它执行但无法解释自己。治理审计、规则修正、冲突检测都需要规则能自省其存在理由与治理对象。

## 解决方案（MCE 2.0 AST 自省）
1. **契约复用**：AST 字段对齐既有 MCE 2.0（`meta_harness/meta_edu.py` 的 mce_compile 输出）：`Core_Directive / Entities / Structural_Constraints / Tension_Vectors / Entropy_Score`——跨仓库契约兼容，但实现为面向规则的结构化编译（输入 Rule + 协议语义字段）。
2. **规则 → AST**：每条规则编译为可自省 AST：
   - `Core_Directive` = 规则类型语义（ethics=伦理守卫 / enforce=触发执行 / ok=放行记录）+ 协议名 + 规则名
   - `Entities` = 从 trigger/ethics/output/module 提取治理对象
   - `Structural_Constraints` = trigger/ethics/output 三约束
   - `Tension_Vectors` = 规则类型预置潜在冲突（供 VCE 2.0 扫描）
   - `Entropy_Score` = 实体多样性 + 约束数 → [0.1, 0.9]
3. **集成**：`ProtocolGateway.introspect()` 原生方法 + 产物管线 → 可审计 JSON。

## 关键设计决策
- **面向规则而非自然语言**：meta_edu 的 mce_compile 面向自由文本；本模式输入是结构化 Rule + 协议字段，输出确定、可测。
- **跨仓库解耦**：agent-governance-v2 自包含实现，仅契约对齐（不 import bottlesumo_pi），运行时零依赖。
- **自省接口**：`why_exists()` / `what_it_governs()` / `constraints()`——规则的"自我解释"能力。
- **张力显式化**：Tension_Vectors 预置三类风险（enforce vs ok 并存误报 / ethics 优先级 / ok 声明即满足），为 S65 VCE 扫描做输入准备。

## 验证
- 20 单测：AST 契约 5 字段、自省接口、溯源、张力、完整性（3 协议 × 3 规则）、集成。
- S63 回归 23/23（合计 43/43）。

## 适用场景
- 需要规则可审计/可解释的治理系统
- 为规则冲突/极化检测（VCE）做准备
- 需要"规则为什么存在"的认知溯源

## 关联
- Sprint 64 (CVE-S Phase 1) / feature/s64_cve_on_governance
- agent-governance-v2: src/mce_introspection.py, config/mce_introspection.generated.json
- 上游契约: bottlesumo_pi/governance/meta_harness/meta_edu.py (MCE 2.0)
- 下游: S65 VCE 2.0 扫描器（消费 Tension_Vectors）
