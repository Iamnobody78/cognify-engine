# AC3 — 审计链（parent_hash + verify_audit_chain）

- **状态**: ✅ DOCUMENTED（设计已论证，待条件触发实现）
- **来源**: 外部治理资源整合任务 3/AC3（v1.37.0 元提示）；概念映射自 CAVA（arXiv:2607.13716 "Canonical Action Verification and Attestation for Runtime Governance"）
- **保留决定**: 2026-08-04 修正版判定 — "不建议当前推进" ≠ 废弃；作为 v2.0 合规增强保留

## 设计论证（已就绪）

### 数据模型
- `decisions` 表新增第 14 列 `parent_hash TEXT`（`_migrate()` 幂等 `ALTER TABLE ADD COLUMN`；新库 CREATE TABLE 同步带列 → 新老库列位一致，`_row_to_dict` 按 `len(row)>13` 兼容）
- `_INSERT_SQL` 由 13 占位符 → 14；`_entry_tuple` 追加 `decision.get("parent_hash")`

### 哈希语义（Git 式链绑定）
- `_canonical_json(decision)`: 13 个内容字段（id/verdict/reason/matched_rule/timestamp/path/method/agent_id/tool_name/tool_lethality/trace_id/parent_span_id/rationale）排序键 + 紧凑分隔符 + ensure_ascii=False → 跨平台可复现
- `_compute_hash(decision)` = SHA256(`parent_hash || '\n' || canonical_json`) — 记录自身哈希**提交**父链接 + 内容
- 写入时（`_flush_write_buffer` 与 `flush_pending` 两处）按插入序计算：`entry.parent_hash = 链尾哈希; 链尾 = _compute_hash(entry)`；链尾从 DB `SELECT * ... ORDER BY rowid DESC LIMIT 1` 取（锁内）
- `verify_audit_chain()`: `SELECT rowid,* ORDER BY rowid ASC` 遍历 → 每条 parent_hash 必须等于前条自身哈希（首条必须 NULL=创世）→ 返回 `(valid, issues[])`；任何非尾行篡改（改内容/改链接/删行/换序）→ 下一行失配被检测

### 诚实边界（必须写入文档）
- **仅删除链尾最后一行无法链内检测**（尾部截断需外部锚点 — 如快照持久化链头水位线；本设计提供 `chain_head_hash()` 原语供外部锚定，锚定机制超出 AC3 范围）
- 链是全局审计日志序（rowid），非 trace 因果树序；二者并存（parent_span_id 管因果，parent_hash 管完整性）

## 触发条件
1. 合规/审计需求确认（v2.0 阶段）：外部审计方要求"审计日志可证明未篡改"
2. 或：`verify_audit_chain` 作为 GATE 新检查项被要求

## 不实现的原因（当前）
- 无外部合规压力；storage 已 100% 测试覆盖，加链需迁移+回归（估算 ~1-2h），当前迭代资源分配给更高价值项

## 相关
- CAVA 论文映射见 docs/external_research_integration.md §优先级表
- 核查: docs/meta_harness_verification.md 未涉及（属 storage 层, 非 meta-harness）
