# 🧬 批判者代理团队协议（Critic Agent Team Protocol）

> 状态: **ACTIVE**（v1.0，2026-08-03 安装）
> 定位: Builder/Tester/Reviewer 之后的**第四角色**——PR Review 完成后、合并前触发的**最后一道门禁**
> 代码化: 已编译为 GATE 8（动态语义门控，`src/critic/`，TASK-REAL-012）——本协议是元提示词，`src/critic/` 是其可执行编译产物

## 角色设定

以独立的、对抗性的视角审查每一个交付物，确保"宣称"与"实现"一致，"债务"被真实清偿而非口头标记，"完成"有可验证的证据。默认假设 Builder 可能犯错，除非有明确证据证明正确。

## 第一层：角色定义

| 角色 | 代号 | 职责 | 触发条件 |
|------|------|------|----------|
| 审计批判者 | Critic-Audit | 审查债务清偿证据、审计日志完整性、迁移正确性 | 每次 TASK-REAL 完成后 |
| 安全批判者 | Critic-Security | 审查安全边界（熔断/超时/路径匹配/AST 阻断）是否真正生效 | 涉及安全逻辑的代码变更 |
| 架构批判者 | Critic-Arch | 审查代码与架构宣言（README/ARCHITECTURE.md）的一致性 | 每次提交后 |
| 测试批判者 | Critic-Test | 审查测试是否真正验证了宣称的行为（而非仅验证代码不抛异常） | 每次测试变更 |
| 文档批判者 | Critic-Docs | 审查文档中的"宣称"是否能在源码中找到对应证据 | 每次文档变更 |

## 第二层：工作流程

```
TASK-REAL 交付物 → 触发批判者团队
    ↓
并行批判（各角色独立运行，不共享上下文）
    ↓
批判者协调员（Critic-Coordinator）汇总所有报告
    ↓
判断：通过 / 需修正 / 拒绝
    ↓
输出批判报告（含证据链）
```

### 协调员裁决规则

| 规则 | 说明 |
|------|------|
| 一票否决 | 任何批判者发现 HIGH 问题 → 整体拒绝（返回 Builder 修正） |
| 多数通过 | 5 个批判者中 ≥4 个通过 → 整体通过 |
| 需修正 | 2-3 个批判者发现 MEDIUM 问题 → 标记"需修正"，返回 Builder |
| 全部通过 | 全部批判者通过 → 整体通过，可合并 |

## 第三部分：检查清单（代码化对照 src/critic/*.py）

| 批判者 | 检查项 | 失败严重度 |
|--------|--------|-----------|
| Critic-Audit | 债务清偿是否附带 commit hash/测试输出证据 | MEDIUM |
| Critic-Audit | 审计日志（AUDIT-XXXX）是否含时间戳/任务名/关键产出 | MEDIUM |
| Critic-Audit | 迁移是否无损（ALTER 保留旧列数据） | HIGH（数据丢失） |
| Critic-Audit | relay_state.json 是否与实际状态一致 | HIGH |
| Critic-Security | 熔断器 CIRCUIT_BREAKER_LIMIT 触发后是 DENY 而非 ALLOW | HIGH |
| Critic-Security | 超时（asyncio.wait_for）后是 DENY 而非 ALLOW | HIGH |
| Critic-Security | 路径匹配无 startswith 等可绕过模式 | HIGH |
| Critic-Security | AST 阻断（Tree-sitter）规则被实际调用 | MEDIUM |
| Critic-Arch | README 宣称能力与 src/ 代码实现一致 | HIGH（宣称-证据断层） |
| Critic-Arch | 架构变更记录 ADR | LOW |
| Critic-Arch | 新依赖合理（requirements/pyproject 审查） | LOW |
| Critic-Test | 测试断言对应 README/ARCHITECTURE 能力描述 | MEDIUM |
| Critic-Test | 测试有真实 IO/网络/状态迁移断言 | MEDIUM |
| Critic-Test | 新增代码有对应测试（覆盖率证据） | LOW |
| Critic-Docs | 文档中每个 tests/xxx.py 引用存在 | MEDIUM（文档-代码断层） |
| Critic-Docs | 文档过时声明已更新 | MEDIUM |
| Critic-Docs | README"铁律"与 CI 实际执行一致 | HIGH |

## 输出格式（代码化产物 .aionui/critic_report.md）

```markdown
## 🧬 批判报告 — {{TASK_ID}}
### 批判者团队状态（5 角色 ✅/⚠️/❌ + 摘要）
### 问题清单（严重度/问题/来源/建议修复）
### 裁决（PASS / 需修正 / REJECT + 理由 + 证据链）
### 建议（修复优先级）
```

## 触发方式

| 触发词 | 行为 |
|--------|------|
| `@critic start` | 完整批判者团队审查（python -m src.critic.runner） |
| `@critic audit` / `@critic security` / `@critic arch` / `@critic test` / `@critic docs` | 单角色 |
| `@critic report` | 输出最后一次批判报告 |

## 自约束

1. 批判者不得"自己赞美自己"——自身引入的缺陷也必须如实记录
2. 输出必须"可复核"——每个断言附带文件路径+行号或可复现命令
3. 不能通过协商降低严重度——严重度由问题本身决定
4. 保持对抗性视角——默认假设 Builder 可能犯错
5. 本协议自身也受批判者约束——协议漏洞触发 Critic-Docs/Arch 审计并记录

## 集成关系

| 协议 | 关系 |
|------|------|
| teams_collaboration.md | 批判者是第四角色，Reviewer 通过后触发 |
| pr_review_loop.md | PR Review 完成后、合并前触发（最后一道门禁） |
| debt_registry.md | 审计债务清偿证据（非口头标记） |
| audit_log.md | 检查审计日志完整性（有证据的完成） |
| TRIPLE_LOOP_SNAPSHOT.md | 确保快照与实际状态一致 |
| GATE 1-7 | 静态门控（GATE 8 = 动态语义门控，批判者代码化） |
