# Pattern: Declaration Verification Channel（声明验证通道）

## 一句话
给协议网关加一个**可插拔的外部验证层**：放行声明（`satisfied=true`）必须经过验证器独立核验，验证失败就把 ALLOW 降级为 ESCALATE——让"谎报声明"从零成本变成高风险操作。

## 问题
S65 VCE 扫描发现 `declaration_only` 盲点：协议网关全部 9 条规则裁决依赖 agent 请求体自我声明（triggered/satisfied/violation），恶意 agent 谎报 `satisfied=true` 即可绕过 enforce 升级路径。规则引擎"自审"发现缺陷，但规则引擎本身无法"自证"声明可信。

## 解决方案（可插拔验证器接口）
1. **统一协议**：`DeclarationValidator.validate(rule, path, method, body) -> VerificationResult{claim, verified, confidence, reason, validator}`——单一接口，容纳多策略实现：
   - `NoopValidator`（默认，诚实边界）：不验证，verified=False/c=0，网关行为与 S65 一致
   - `BaselineDeclarationValidator`（基线，确定性）：一致性检查
   - 未来插槽：LLM 语义验证器（策略 A）、签名验证器（策略 B）
2. **注入方式**：构造器 `ProtocolGateway(validator=...)` + `set_validator()` 热切换
3. **谎报缓解主路径**：`evaluate_verified()` 命中 ok 规则（ALLOW_WITH_WARNING）且验证失败 → action 降级 `ESCALATE`；NoopValidator 不降级（向后兼容）
4. **基线五项确定性检查**：
   - violation+satisfied 矛盾 → False (c=0.95)
   - satisfied+证据锚点（evidence/output/result/proof 非空）→ True (c=0.8)
   - satisfied 无锚点 → False (c=0.6) ← 盲点缓解主路径
   - 协议状态缺失/非 dict → False (c=0.9)
   - 非声明依赖规则（ethics）→ 平凡通过 (c=1.0)
5. **VCE 联动**：`vce_scan_rules(..., verification_channel="baseline")` → declaration_only 盲点消除（盲点 3→0 实证），报告记录 `Verification_Channel` 字段；无通道调用保持 S65 行为

## 关键设计决策
- **可插拔不排斥**：接口层统一，LLM/签名策略未来直接实现同一协议——不用改网关代码
- **确定性优先**：基线全部逻辑确定性（可复现/可测试/可审计），治理裁决必须可复现
- **诚实边界不伪称**：基线只做一致性检查，不声称能证明 agent 真的执行了协议；honest_boundary 明确"深层语义谎报需 LLM 层"（S65 版本同步修订）
- **降级而非拒绝**：验证失败 → ESCALATE（升级复核），不是一刀切 DENY——给合法但锚点缺失的声明留复核通道

## 验证
- 18 单测：注入/热切换/NoopValidator 默认、verify_declaration、evaluate_verified 降级语义、基线五项检查、VCE 联动（带通道盲点消失/无通道保留）
- 回归 65/65（S63 23 + S64 20 + S65 22）+ 18 = 83/83 全过
- 实证产物：config/verification_channel.generated.json（3 类样本裁决）+ vce_scan_report.json 重扫（盲点 0）

## 适用场景
- 治理网关接真实 agent 流量前的声明核验（防止 agent 自报成绩）
- 审计链：每条放行裁决附带 verification 结果（claim/confidence/reason/validator）
- 多 Agent 治理（外环）：agent 上报"我完成了 X"时，网关可独立核验

## 关联
- Sprint 66 (CVE-S Phase 3: Governance verifiable) / feature/s66_declaration_fix
- agent-governance-v2: src/verification.py, src/protocol_gateway.py (evaluate_verified), src/vce_scanner.py (verification_channel)
- 上游: S65 VCE 扫描器（declaration_only 盲点）、S64 MCE AST、S63 协议编译
- 下游: S67 CEE 推演器（消费 Verification_Channel 状态）、LLM 语义验证器插槽（策略 A）
- 协议: HONEST-BOUNDARY（能力边界声明）、TRACE-AGENT（verification 可审计）
