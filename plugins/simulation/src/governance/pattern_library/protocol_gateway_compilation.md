# Pattern: protocol_gateway_compilation

## 一句话
将协议编译器（A1）产出的 11 列声明式协议 YAML 编译为规则引擎（PolicyEngine）可执行规则，实现"协议不再停留于声明层、可被网关自动执行"的闭环。

## 问题
治理协议（如费曼测试、熵值去噪、逻辑链检查）以声明式 YAML 存在（`schema_version: 11-col-v1`，12 必需字段），规则引擎无法直接执行自然语言 trigger/ethics_boundary/expected_output。协议与执行之间存在语义鸿沟。

## 解决方案（三步闭环）
1. **协议加载**：`Protocol.from_yaml()` 校验 schema_version + 12 必需字段 + level 合法性（fail-closed：任何缺失/非法 → 拒绝加载）。
2. **规则编译**：每个协议编译为 3 条规则：
   | 规则 | 条件 | 动作 | priority |
   |------|------|------|----------|
   | `protocol-{module}-ethics` | 请求体声明 `violation` 非空 | DENY | 5 |
   | `protocol-{module}-enforce` | 状态对象含 `triggered:true` 且无 `satisfied:true`（负向前瞻） | ESCALATE | 15/20 (L3/L2) |
   | `protocol-{module}-ok` | 状态对象含 `satisfied:true` | ALLOW_WITH_WARNING | 25/30 (L3/L2) |
3. **执行**：编译产物为 `config/protocol_policies.generated.yaml`，PolicyEngine 原生加载；请求体携带 `governance.protocols.{module}.{triggered/satisfied/violation}` 声明时自动裁决。

## 关键设计决策
- **priority 语义**：DENY(5) < enforce(15/20) < ok(25/30)，evaluate 按 priority 升序返回首个命中 → 伦理违规先于触发升级，触发先于放行。
- **正/负向前瞻**：enforce/ok 都匹配整个协议状态对象（紧凑 JSON），`(?=.*"triggered":true)(?!.*"satisfied":true)` 避免 triggered+satisfied 并存时误报 ESCALATE。
- **零影响**：规则 path_pattern="*"，但仅当 json_path 提取到 governance 声明才命中；无声明的既有流量零影响（实测 979 测试全过）。
- **fail-closed**：缺 schema_version / 缺字段 / 非法 level / 空目录 / 重复 module → 全部拒绝加载，不静默跳过。

## 验证
- 23 单测：编译契约、priority 排序、执行裁决（triggered/satisfied/violation 各态）、边界（并存、空 violation、未知 module）、零影响、fail-closed、端到端 roundtrip。
- 全量回归：74 测试文件 979 测试 PASS。

## 适用场景
- 声明式治理规范（协议/契约/边界）需接入事件裁决引擎时
- 需要"声明 → 可执行"自动编译管线时
- 需要伦理边界优先于业务规则时

## 关联
- Sprint 63 / feature/s63_protocol_gateway
- agent-governance-v2: src/protocol_gateway.py, config/protocols/, config/protocol_policies.generated.yaml, scripts/compile_protocol_policies.py
- 上游: bottlesumo_pi/governance/protocols/protocol_compiler.py（A1 编译器）
