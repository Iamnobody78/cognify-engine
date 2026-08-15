# Governance

治理流程 + Critic 机制 + 元能力状态。

## 治理流程

```
1. 提交    → 代码变更通过 PR 提交
2. GATE 1-7 → 静态门控（Lint/测试/策略一致性/AST 版本耦合/CI）
3. GATE 8   → 5 批判者动态语义审计（Critic Agent）
4. 裁决    → PASS / REVISION / REJECT
5. 审计    → 通过后写入 SQLite + audit_log.md（AUDIT-00XX 编号）
6. 快照    → TRIPLE_LOOP_SNAPSHOT.md 更新版本链
```

## Critic 机制（L4，GATE 8）

5 批判者（`src/critic/`）：

| 批判者 | 检查内容 |
|--------|----------|
| Critic-Audit | 版本一致性、审计链完整性、快照-提交对应 |
| Critic-Security | 私钥泄漏、权限沙箱、fail-closed 语义 |
| Critic-Arch | 架构声明 vs 实现一致性 |
| Critic-Test | 测试断言质量（裸 assert 存在性）、覆盖率 |
| Critic-Docs | README 版本声明一致性（D2）、文档完整性 |

GATE 8 聚合输出：`PASS`（0 CRITICAL）/ `REVISION` / `REJECT`。

## 元能力状态

| 元能力 | 状态 | 证据 |
|--------|------|------|
| 自审计 | ✅ | Critic Agent（5 批判者 + GATE 8） |
| 自修复 | ✅ | self_heal 工具 + codegen 漂移自愈 |
| 自追踪 | ✅ | Trace CTE 因果链 |
| 自认证 | ✅ | ED25519 签名（Meta-Binding，AUDIT-0044） |
| 自生成 | ✅ | codegen YAML→Python + 运行时等价性测试 |
| 自修改 | ⚠️ | 人类在环（补丁经裁决） |
| 自部署 | ⚠️ | 人类在环（CI/CD 半自动） |

## AST 治理前门（v1.25.0）

- **位置**：policy.py `evaluate()` 首行（Priority 0，先于一切 YAML 规则）
- **语义**：请求体代码片段（python/bash/sql）危险模式 → 合成 `ast-block-*` DENY Rule
- **审计**：`Rule.reason` → `DecisionRecord.reason`（精确行号 + S-expression 标签）
- **fail-closed**：查询文件缺失/损坏 → 拒绝启动；逃生舱 `AG_AST_DISABLE=1`
- **约束**：P1 Capture 校验 / P2 payload_extractor 提取 / P3 命令表仅存 .scm 零硬编码

## 治理铁律

1. **验证优先于扩展**：先跑通测试，再叠加功能
2. **诚实优先于想象**：文件不存在就不假装修复（Meta-Harness 记忆-现实漂移检查）
3. **fail-closed**：缺失即拒绝，绝不静默放行
4. **版本链四端一致**：README ↔ 快照 ↔ main.py ↔ ci.yml GATE 7
