# Pattern: RuleConflict Detection（VCE 2.0）

## 一句话
用 VCE 2.0 扫描器对治理规则集做结构化自审，检测规则间的极化、冲突与盲点，产出可审计的 `vce_scan_report.json`——让规则引擎能"自审"自身的治理质量。

## 问题
规则引擎（PolicyEngine）只执行规则，不知道自己规则的冲突与盲区。S64 MCE AST 让规则能"自省"（解释自己），但无法发现：priority 撞车导致裁决不确定、条件重叠依赖脆弱正则、全部裁决依赖 agent 声明可被谎报绕过。

## 解决方案（VCE 2.0 结构化扫描）
1. **契约复用**：输出字段对齐 meta_edu VCE 2.0（Polarization_Index / Value_Tensions / Asymmetric_Perspectives），扩展 RuleConflicts + BlindSpots——面向规则结构而非自然语言。
2. **冲突检测**（结构化，可审计）：
   - `priority_collision`（high）：同 priority 不同 action → evaluate 顺序依赖 dict 排序，裁决不确定
   - `condition_overlap`（low）：同模块 enforce/ok json_path 同域 → 依赖负向前瞻区分，schema 变化即误判
   - `action_ambiguity`（low）：ethics(DENY) vs ok(ALLOW) 同域并存 → violation+satisfied 同时声明时语义需明确
3. **盲点检测**：
   - `missing_rule_type`（high）：模块缺规则类型 → 治理维度空洞
   - `declaration_only`（medium）：全部裁决依赖 agent 声明 → 恶意谎报绕过风险（VCE 最有价值的发现）
4. **极化系数**：`0.4*action多样性 + 0.35*priority差距 + 0.25*张力密度` → [0,1]
5. **集成**：`ProtocolGateway.scan()` 与 `introspect()` 并列；产物 `config/vce_scan_report.json`。

## 关键设计决策
- **诚实边界**：honest_boundary 字段声明 detects（能检测什么）/does_not_detect（检测不了什么：恶意谎报需外部验证、自然语言语义偏差需 LLM 层）——HONEST-BOUNDARY 协议落地。
- **基线即发现**：扫描 9 规则立即发现 3 declaration_only 盲点（S63/S64 未显式记录）——证明自审不是形式主义。
- **冲突分危级**：high（priority 撞车）> low（重叠/歧义）——供 CEE 推演（S66）按危级排序演化路径。

## 验证
- 22 单测：契约 5 字段、极化范围、3 类冲突（含合成 priority_collision）、2 类盲点、集成、honest_boundary、空输入安全。
- 回归 43/43（S63+S64），合计 65/65。

## 适用场景
- 规则集成长后的健康检查（GUARDIAN 周检 Phase A 代码健康子维度）
- 治理策略变更前的冲突预检
- 安全审计：发现"依赖声明"类可绕过盲区

## 关联
- Sprint 65 (CVE-S Phase 2) / feature/s65_vce_scanner
- agent-governance-v2: src/vce_scanner.py, config/vce_scan_report.json
- 上游: S64 MCE AST（消费 Tension_Vectors/Entities/Constraints）
- 下游: S66 CEE 推演器（消费 RuleConflicts/BlindSpots）
- 协议: HONEST-BOUNDARY（边界声明）、TRACE-AGENT（审计）、GUARDIAN（周检接入）
