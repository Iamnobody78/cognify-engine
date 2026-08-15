# TASK-REAL-001 新约束固化提案（待批准）

> 来源：TASK-REAL-001 真实项目治理验证暴露的 3 条真实场景边界
> 日期：2026-08-03 · 状态：**PROPOSED**（经批准后合并）

---

## 增量 1：teams_collaboration.md §2.6 后新增小节「§2.7 真实场景边界约束」

```markdown
### 2.7 调度层第三阶段：MCP 工具共享 + 真实场景边界约束（v0.2.4+，AUDIT-0012/0013）

> **目标**：子代理经 MCP 统一工具总线交换产物（Builder/Tester 写、Reviewer 只读）。
> 验证实验：TASK-SCHED-003（MCP 通道，142 passed）+ TASK-REAL-001（真实债务清偿，152 passed）。

**MCP 通道**（§8 详述）：`scripts/mcp_client.py` → `filesystem_mcp_server.py`（stdio JSON-RPC）；
工具 read_file / write_file / list_directory / create_directory / file_info；沙箱 = repo root，路径逃逸拒绝。

**真实场景边界约束（TASK-REAL-001 实测暴露，最高优先级）**：

| # | 约束 | 规则（必须遵守） | 实测教训 |
|:-:|------|------------------|----------|
| R1 | **真实任务 prompt 过大 → Builder READ 阶段截断** | **补丁语义而非探索语义**：子代理任务指令必须携带完整 diff / 精确锚点（锚点唯一性断言 count==1），禁止"读全部代码再设计"；需要探索时由 Coordinator 完成并注入 | v1 12 turns 0 writes（只读不写）→ v2 补丁语义恢复 |
| R2 | **mcp_client `\n` 转义损坏真实代码**（f-string 含字面 `\n`） | **JSON-RPC 直写而非 CLI 转义**：内容含 `\n` 字面量/复杂转义时，绕过 CLI 的 `\\n`→换行替换，直接 JSON-RPC 发送原始 payload；或先 `file_info` 自证 + 立即重跑受影响测试 | check_policy.py f-string 被 `\n` 转义损坏 → 直接 JSON-RPC 重提交修复 |
| R3 | **Reviewer 在 verdict 写盘前截断** | **协调者兜底落盘**：Reviewer 截断时，Coordinator 按子代理 stdout 输出补全 verdict 落盘（标注"Coordinator 补全"），写后审协议优先于渠道纯净 | Reviewer 输出 OVERALL 但 verdict 仍是 PROVISIONAL skeleton（592B）→ Coordinator 补全（2080B） |

**恢复流程（真实任务专用）**：
- 子代理截断 → Coordinator 检查落盘产物（file_info）：
  - 产物缺失 → 用**补丁语义**重建（注入完整 diff + 锚点，禁止重新探索）
  - 产物存在但 incomplete → 接受现状 + 标注，或按 stdout 补全（仅 Reviewer verdict）
- 每轮 MCP 写入后必须 `file_info` 自证大小（防截断丢失）
```

---

## 增量 2：teams_collaboration.md §2.5「关键教训」追加第 4 条

```markdown
4. **协调者兜底落盘（TASK-REAL-001 新增）**：Reviewer（或任何子代理）在 verdict 写盘前被截断时，
   Coordinator 必须按其 stdout 输出**补全 verdict 落盘**，并标注"Coordinator 补全（子代理截断）"。
   写后审协议优先于渠道纯净——接力判断只认落盘文件，不认 stdout，但落盘内容可以来自 stdout（带标注）。
```

---

## 增量 3：agent_registry.yaml Builder 行 + 路由仲裁规则追加

```yaml
# Builder 能力边界追加（第 5 列「补丁语义」）
| **Builder** 🛠️ | 生成/修改源代码 ≤2 文件/任务；**任务指令必须携带完整 diff/精确锚点（补丁语义），禁止探索式读取** | `src/`, `config/`, `tests/` | — | 可用（SCHED-001/002/003 + REAL-001 验证） |
```

```markdown
### 路由仲裁规则（追加第 9-11 条）
9. 真实任务（>自造任务复杂度）→ Builder 指令必须**补丁语义**：携带完整 diff / 精确锚点（count==1 断言），
   禁止"读全部代码再设计"（TASK-REAL-001: Builder v1 READ 截断 0 writes 教训）
10. 内容含 `\n` 字面量/复杂转义 → 禁用 mcp_client CLI 转义，**JSON-RPC 直写**原始 payload（TASK-REAL-001: f-string 损坏教训）
11. Reviewer verdict 未落盘即截断 → Coordinator **兜底补全落盘**并标注（写后审优先于渠道纯净）
```

---

## 待批准项

| 增量 | 文件 | 位置 | 类型 |
|:---:|------|------|------|
| 1 | teams_collaboration.md | §2.6 后新增 §2.7 | 新增小节（含 R1/R2/R3 表格） |
| 2 | teams_collaboration.md | §2.5 关键教训追加第 4 条 | 补充 |
| 3a | agent_registry.yaml | Builder 行第 5 列 | 字段扩展 |
| 3b | agent_registry.yaml | 路由仲裁规则追加 9-11 | 新增规则 |

**批准后执行**：合并三处 → 追加 AUDIT-0014 → 提交 → 再评估 DEBT-0001/0008 优先级。
