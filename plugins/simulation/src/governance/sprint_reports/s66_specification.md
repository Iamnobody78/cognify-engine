# Sprint 66 Specification — declaration_only 盲点验证通道（CVE-S on governance-v2 Phase 3）

## 1. 目标

**为协议网关增加外部验证层（Verification Channel），使 agent 无法通过谎报 `satisfied=true` 绕过治理规则**

S63 证明"治理可编译"→ S64 证明"治理可自省"（规则回答"我为什么存在"）→ S65 证明"治理可自审"（扫描器发现自身冲突/盲点）→ **S66 证明"治理可验证"**（声明经外部独立核验）。

S65 扫描发现的 `declaration_only` 盲点是本 Sprint 的直接动机：全部 9 条规则裁决依赖 agent 请求体自我声明，恶意 agent 谎报 `satisfied=true` 即可让 ESCALATE 永不触发。

## 2. 范围（PM 指令 T1/T2/T3 + VCE 联动）

| 任务 | 内容 | 交付物 |
|------|------|--------|
| T1 | 验证通道设计：3 策略对比（LLM 语义验证 / 轻量签名 / 可插拔验证器接口） | `docs/s66_verification_channel.md`（裁决：策略 C 主架构，A/B 为插槽） |
| T2 | 验证器接口实现：`ProtocolGateway` validator 注入（构造器 + set_validator 热切换）+ `verify_declaration` + `evaluate_verified` | `src/verification.py` 接口 + `src/protocol_gateway.py` 集成 + 单测 |
| T3 | 基线验证器：检查 satisfied 声明与请求上下文一致性（确定性五项检查） | `src/verification.py` BaselineDeclarationValidator + 单测 |
| VCE 联动 | 带验证通道重扫 → declaration_only 不再出现 | `vce_scan_report.json` 重扫（盲点 3→0）|

## 3. 验收判据（GATE 门禁）

| # | 判据 | 度量 |
|---|------|------|
| G1 | T2 验证器接口单测全过（注入/热切换/调用） | test_verification.py |
| G2 | T3 基线验证器五项检查单测全过 | test_verification.py |
| G3 | 全量回归（S63 23 + S64 20 + S65 22 + S66 新） | 83/83 |
| G4 | VCE 联动：带通道扫描 declaration_only 消失 + Verification_Channel 字段出现 | 盲点 0 |
| G5 | 向后兼容：无通道扫描行为与 S65 一致（declaration_only 保留） | 回归测试 |
| G6 | 谎报缓解实证：`evaluate_verified` 放行声明验证失败 → action 降级 ESCALATE | 样本裁决 JSON |

## 4. 设计

### 4.1 架构：治理可验证

```
S65 scan() 发现 declaration_only 盲点
        │
        ▼
S66 Verification Channel（外部验证层）
        ├─ DeclarationValidator 协议（单一接口）
        │    ├─ NoopValidator（默认, 诚实边界, 向后兼容）
        │    ├─ BaselineDeclarationValidator（基线, 确定性一致性检查）★ T3
        │    └─ [插槽] LLM 语义验证器 / 签名验证器（策略 A/B, 未来实现）
        │
        ├─ ProtocolGateway 注入：构造器 validator= + set_validator() 热切换
        ├─ evaluate_verified()：裁决+验证合一
        │    └─ ok 规则验证失败 → action 降级 ESCALATE（谎报缓解主路径）
        └─ scan(verification_channel)：VCE 联动, declaration_only 消除
```

### 4.2 基线验证器五项确定性检查（T3）

| # | 检查 | 判定 |
|---|------|------|
| 1 | violation 非空 + satisfied=true 并存 | verified=False, confidence=0.95（矛盾声明） |
| 2 | satisfied=true + 非空证据锚点（evidence/output/result/proof） | verified=True, confidence=0.8 |
| 3 | satisfied=true 无任何锚点 | verified=False, confidence=0.6（盲点缓解主路径） |
| 4 | 协议状态缺失/非 dict | verified=False, confidence=0.9（结构异常） |
| 5 | 非声明依赖规则（ethics） | 平凡通过 verified=True, confidence=1.0 |

### 4.3 诚实边界

基线验证器只做**一致性检查**，不声称能证明 agent 真的执行了协议（如"feynman 检查真跑过"）。深层语义验证属于 LLM 层插槽。VCE honest_boundary 随通道存在而更新：`does_not_detect` 从"恶意 agent 谎报声明（需外部验证通道）"修订为"深层语义谎报（基线一致性已覆盖，语义层需 LLM）"。

## 5. 交付物清单

**agent-governance-v2**（commit + push GitHub）：
- `src/verification.py`（新）— VerificationResult/DeclarationValidator/NoopValidator/BaselineDeclarationValidator
- `src/protocol_gateway.py`（改）— validator 注入 + verify_declaration + evaluate_verified + scan 联动
- `src/vce_scanner.py`（改）— verification_channel 参数 + Verification_Channel 字段
- `tests/test_verification.py`（新）— 18 单测
- `scripts/compile_verification_channel.py`（新）— 产物管线
- `config/verification_channel.generated.json`（新）— 通道状态 + 3 类样本裁决
- `config/vce_scan_report.json`（重扫）— 盲点 0 + Verification_Channel
- `docs/s66_verification_channel.md`（新）— T1 设计文档

**bottlesumo_pi**（主仓库，feature/s66_declaration_fix）：
- `governance/dashboard/engineering_rules.md` — RULE-VER-001..003
- `governance/pattern_library/governance/VerificationChannel.md`（新）
- `governance/sprint_reports/s66_*.md` — 本规格 + 门报告
- `governance/research/outputs/s66_samuel.md` — S.A.M.U.E.L. 报告

## 6. 遗留（P1/P2，下轮）

| 优先级 | 项 |
|--------|----|
| P1 | LLM 语义验证器插槽（策略 A 落地，验证自然语言产出可信度） |
| P1 | A3 MMCE 工具箱、A2 记忆脚手架采用 |
| P2 | S67: CEE 推演器（消费 RuleConflicts/BlindSpots + Verification_Channel 状态） |
| P2 | 产品化路线图执行（PRODUCT_STRATEGY.md 等，分支 feature/productization_plan 未建） |
| P2 | Web UI MVP (S68-S69) |
