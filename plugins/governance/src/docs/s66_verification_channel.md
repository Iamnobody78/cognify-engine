# S66 — declaration_only 盲点验证通道 (Verification Channel) 设计

- 版本: v1.0 (T1 交付)
- 日期: 2026-08-10
- 关联: S65 VCE 2.0 扫描器发现的 `declaration_only` 盲点
- 治理层: agent-governance-v2 / CVE-S Phase 3 (Governance verifiable)

## 1. 问题定义

S65 扫描报告确认: 协议网关全部 9 条规则的裁决完全依赖 agent 请求体中的
**自我声明** (`triggered` / `satisfied` / `violation`), 无独立验证通道。

攻击面 (S65 honest_boundary 已声明):

```
恶意 agent: {"governance": {"protocols": {"feynman_test": {"satisfied": true}}}}
             ↓
匹配 protocol-feynman_test-ok (ALLOW_WITH_WARNING, p=30)
             ↓
ESCALATE 永不触发 → 绕过治理
```

本 Sprint 目标: 为协议网关增加**外部验证层** (Verification Channel),
使谎报 `satisfied=true` 不再是零成本操作。

## 2. 三种候选策略对比

### 策略 A: LLM 语义验证 (LLM Semantic Validation)

| 维度 | 评估 |
|------|------|
| 机制 | 调用 LLM 对请求体 + 协议上下文做语义一致性判定 ("该声明是否可信?") |
| 优点 | 语义覆盖最深; 可理解自然语言产出 (如"去噪后的要点列表") |
| 缺点 | 成本/延迟高 (每次裁决一次 LLM 调用); 非确定性 (同输入可能不同判定); 需要 LLM 基础设施; 判定不可审计复现 |
| 适用 | 作为**可选增强验证器**, 不宜作为默认基线 |

### 策略 B: 轻量签名 (Lightweight Signature)

| 维度 | 评估 |
|------|------|
| 机制 | agent 侧用密钥对声明签名, 网关验签 (HMAC/Ed25519) |
| 优点 | 密码学强度高; 确定性; 可审计 |
| 缺点 | 只验证**真实性** (声明确实来自该 agent), 不验证**语义正确性** (agent 仍可诚实地谎报); 需要 agent 侧密钥分发与轮换基础设施 |
| 适用 | 解决的是"谁在声明", 不是"声明是否可信" — 与 declaration_only 盲点**正交**, 可作为未来另一验证器 |

### 策略 C: 可插拔验证器接口 (Pluggable Validator Interface) ★ 推荐

| 维度 | 评估 |
|------|------|
| 机制 | 协议网关注入 `DeclarationValidator` 接口 (构造器注入 + set_validator); 默认 `NoopValidator` (诚实边界); 基线 `BaselineDeclarationValidator` 做确定性一致性检查 |
| 优点 | 确定性/零成本/可测试; 单一接口可容纳未来 LLM 验证器 (策略 A) 与签名验证器 (策略 B) 作为不同实现; 向后兼容 (无验证器时行为不变) |
| 缺点 | 基线只能做**一致性检查** (矛盾检测/证据锚点), 无法证明语义真实性 (honest_boundary 保留此声明) |
| 适用 | 作为验证通道的**主架构**, 满足 T2/T3 全部要求 |

### 裁决结论

**采用策略 C 作为主架构, 策略 A/B 作为其未来的具体实现插槽。**
理由:
1. T2 要求 "pluggable validator interface" — 策略 C 即 PM 指定方向;
2. 策略 C 的单一接口可统一承载 A (LLM 语义) 与 B (签名) — 不排斥;
3. 确定性基线保证可审计性与测试稳定性, 符合治理场景 (治理裁决必须可复现);
4. HONEST-BOUNDARY 协议: 基线明确声明能力边界 ("一致性检查 ≠ 语义证明"),
   不做超范围承诺。

## 3. 接口契约 (T2 交付)

### VerificationResult

```python
@dataclass
class VerificationResult:
    claim: str          # 被验证的声明 (如 "satisfied=true")
    verified: bool      # 是否通过验证
    confidence: float   # 置信度 [0,1]
    reason: str         # 人类可读原因 (审计用)
    validator: str      # 验证器名称 (NoopValidator / baseline)
```

### DeclarationValidator Protocol

```python
class DeclarationValidator(Protocol):
    name: str
    def validate(self, rule: Rule, path: str, method: str,
                 body: dict) -> VerificationResult: ...
```

### ProtocolGateway 注入

```python
gw = ProtocolGateway(protocols_dir=..., validator=BaselineDeclarationValidator())
gw.set_validator(NoopValidator())          # 可热切换
res = gw.verify_declaration(rule, path, method, body)   # 单条验证
out = gw.evaluate_verified(path, method, body)          # 裁决+验证合一
```

`evaluate_verified` 语义 (谎报缓解):
- 命中 ok 规则 (ALLOW_WITH_WARNING) 且验证失败 → action 降级为 `ESCALATE`
  (声明不可信 → 转人工/升级通道复核);
- 命中 enforce 规则 → 已升级, 验证结果附加为信息;
- 命中 ethics (DENY) → DENY 不变;
- 无验证器 (NoopValidator) → `verification.verified=False, confidence=0`,
  但 action 不做降级 (保持原行为, 向后兼容), 报告标记 `channel="none"`。

## 4. 基线验证器语义 (T3 交付)

`BaselineDeclarationValidator` 对声明做**确定性一致性检查**:

| # | 检查 | 判定 |
|---|------|------|
| 1 | `violation` 非空 且 `satisfied=true` 并存 | 矛盾声明 → verified=False, confidence=0.95 |
| 2 | `satisfied=true` 且协议状态含非空 `evidence`/`output` 锚点 | verified=True, confidence=0.8 (有上下文锚定) |
| 3 | `satisfied=true` 但无任何证据锚点 | verified=False, confidence=0.6 (声明无上下文支撑 — 盲点缓解主路径) |
| 4 | 协议状态非 dict / 声明字段缺失 | verified=False, confidence=0.9 (结构异常) |
| 5 | 规则不依赖 satisfied 声明 (如 ethics DENY) | verified=True, confidence=1.0 (无可验证声明, 平凡通过) |

诚实边界: 基线**不声称**能证明 agent 真的执行了协议 — 它阻断的是
"零成本谎报" (无锚点即不可信), 深层语义留给 LLM 验证器插槽 (策略 A)。

## 5. VCE 联动 (PM 验收项)

- `vce_scan_rules(..., verification_channel="baseline")`:
  - `declaration_only` 盲点**不再报告** (验证通道存在 → 盲点消除);
  - 报告中新增 `Verification_Channel` 字段记录通道类型与验证器名称;
  - `honest_boundary.does_not_detect` 更新: "恶意 agent 谎报声明" 降级为
    "深层语义谎报 (基线一致性已覆盖, 语义层需 LLM)"。
- 不传 `verification_channel` (旧调用) → 行为不变 (向后兼容, S65 测试全保留)。

## 6. 验收标准

1. T2: `validator` 构造器注入 + `set_validator` 热切换 + 单元测试全过;
2. T3: 基线验证器 5 项检查单测全过, 对合法声明 (含锚点) 不误伤;
3. VCE linkage: 带通道重扫 → `declaration_only` 从 BlindSpots 消失,
   `Verification_Channel` 字段出现; 无通道重扫 → 行为与 S65 一致;
4. 全量测试 (23+20+22+新测试) 全过, GATE 检查表全 PASS。
