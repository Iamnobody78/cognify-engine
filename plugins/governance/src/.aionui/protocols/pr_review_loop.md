# 🔄 PR Review Loop — 协议 v1.0

> **定位**：定义 PR 从创建到合并的完整治理循环——CI 自动检查 + Reviewer 语义审查 + audit_log 永久记录。
>
> **上游依赖**：Teams 协作协议 v2.0（两阶段 Spawn）、CI 五门控
> **下游输出**：PR 评论、`.aionui/audit_log.md`、合并决策

---

## 1. 触发条件

| 触发 | 条件 | 动作 |
|------|------|------|
| **自动** | PR 创建且 CI Gates 1-5 全部通过 | Coordinator 标记 `@team-review-needed` → 进入审查 |
| **手动** | PR 评论区输入 `@team review` | 立即触发审查 |
| **手动** | PR 评论区输入 `@team review --force` | 跳过 CI 状态强制审查（仅人工场景） |

## 2. 角色

| 角色 | 职责 |
|------|------|
| **Coordinator**（主代理） | 读取 PR diff → 生成审查任务 → Spawn Reviewer → 处理结果 → 回贴 PR |
| **Reviewer**（子代理） | 独立审查代码 → 输出 PASS/REJECT + 问题列表 + 评级（只读，不写代码） |

## 3. 审查任务格式（Coordinator 生成）

```markdown
## 审查任务 — PR #{N}

### 变更概览
- PR 标题: {title}
- 变更文件: {≤3 个文件列表}
- 变更行数: {+N/-M}

### 审查维度（5 维度，逐项检查）
1. **安全**: SQL 注入 / 命令注入 / 硬编码密钥 / 输入验证
2. **超时**: 所有 I/O 有超时控制？超时后 fail-closed？
3. **熔断**: 连续失败有熔断？熔断后行为明确？
4. **持久化**: 数据持久化？重启状态不丢失？
5. **测试**: 测试真实？覆盖本次变更的边界？

### 输出要求
- 评级: A/B/C/D/F
- 结论: PASS / REJECT
- 问题列表: 表格 (严重度 | 问题 | 位置)
- 总输出 ≤100 行
```

## 4. Reviewer 输出格式（强制）

```markdown
**总体评级**: {A/B/C/D/F}
**结论**: PASS / REJECT
**问题列表**:
| 严重度 | 问题 | 位置 |
|:--:|------|------|
| HIGH | {描述} | `{file}:{line}` |
| MEDIUM | {描述} | `{file}:{line}` |
| LOW | {描述} | `{file}:{line}` |
**改进建议**:
1. {建议}
**变更是否引入新风险**: {是/否 + 说明}
```

## 5. 回贴 PR 流程

```
Reviewer 输出
    ↓
Coordinator 解析
    ├── PASS → 回贴 "✅ PASS ({评级})" + 可选建议
    │         → 移除 @team-review-needed 标签
    │         → 允许合并（用户确认或自动，按项目配置）
    │
    ├── REJECT (HIGH > 0) → 回贴 "❌ REJECT" + 问题表格
    │         → 保持 @team-review-needed 标签
    │         → 通知用户，等待修复后重新审查
    │         → ⚠️ 需要人类确认后才能继续（协议 §7）
    │
    └── REJECT (仅 MEDIUM/LOW) → 回贴 "⚠️ CONDITIONAL" + 问题列表
              → 移除标签，允许合并（MEDIUM/LOW 记录到 audit_log）
```

## 6. audit_log 记录（每次审查必写）

写入 `.aionui/audit_log.md`：

```markdown
## AUDIT-{SEQ} — {ISO8601 时间}

- PR: #{N}
- 标题: {title}
- 变更文件: {文件列表}
- 变更行数: +{N}/-{M}
- 评级: {A/B/C/D/F}
- 结论: {PASS/REJECT/CONDITIONAL}
- 问题数: HIGH:{X} MEDIUM:{Y} LOW:{Z}
- Reviewer: {spawn 代理名}
- Commit: {hash}
- 备注: {一句话}
```

## 7. 人工介入规则

| 条件 | 动作 |
|------|------|
| REJECT 且 HIGH 问题 > 0 | **必须**获得人类在 PR 评论区的确认才能继续（不得自动重试） |
| PR 修改 > 3 个文件 或 > 500 行 | 分段审查（多次 Spawn，每次 ≤3 文件） |
| Reviewer 输出 > 100 行 | 打回重跑，要求精简 |
| CI Gates 1-5 未全过 | 不进入 Reviewer 阶段，先修 CI |

## 8. 审查质量铁律

| # | 铁律 | 违反后果 |
|:--:|------|----------|
| 1 | **Reviewer 禁止写代码** — 只审查，不修复 | 输出作废，换代理重审 |
| 2 | **Reviewer 禁止只检查格式** — 必须做语义审查（数据流/状态迁移/安全） | 输出作废，换代理重审 |
| 3 | **Coordinator 禁止跳过审查** — PASS 未得，不合并 | 治理违规，记录到 audit_log |
| 4 | **Reviewer 输出 ≤100 行** — 简洁为王（4096 token 截断） | 打回重跑 |
| 5 | **Coordinator 必须自己验证测试** — 不信任子代理"测试通过"声明 | 治理违规 |

## 9. 与 CI 的衔接

```
push/PR
  ↓
CI 自动跑 Gates 1-5
  ├── 失败 → PR 标红，Reviewer 不启动
  └── 通过 → 标记 @team-review-needed
                ↓
          Coordinator 启动 (Spawn #2 独立审查)
                ↓
          回贴 PR + audit_log 记录
```

---

*本协议 v1.0 由 agent-governance v2 实验生成，2026-08-03。*
*更新日志：v1.0 初版（CI 5 门控 + PR 审查闭环）。*
