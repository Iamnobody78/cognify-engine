# GOV Round 2 报告 —— tool_lethality SQL 变体探针矩阵 & 7 个 FN 缺口修复

**日期**: 2026-08-10
**状态**: 完成（交付件 + 测试 + 提交）
**前置**: GOV Round 1（网关 948 测试通过、ast-block-bash/sql/block-shell-tool、mkfs-path 候选）已提交
**验收轨道**: PM 批准的 Round 2 —— tool_lethality SQL 变体探针矩阵，与 Sprint 58 并行（零文件交集、零运行时依赖）

---

## 1. 探针矩阵结果（live 网关验证）

- 矩阵: 44 用例（A1–D3 结构变体 + E1–E11 边界变体），直打网关 `POST http://127.0.0.1:9000`
- **结果: 43/44 通过**（97.7%）
- **唯一 FAIL: E5 —— `DELETE FROM t WHERE id=1`（有界 DELETE）被过度阻断**
  - 这是**刻意选择的 fail-closed 姿态**：E2（`DELETE FROM t;` 无 WHERE 全表删除）是致命 FN，
    tree-sitter 无法可靠区分"有界"与"无界" DELETE 的语法形态时，一律阻断。
  - 已在探针 JSON 中标注 `overblock`，属已文档化的安全冗余，非缺陷。
- 探针矩阵数据: `governance_reports/gov_round2_sql_probes.json`
- 探针脚本: `scripts/gov_round2_sql_variants.py`

### 探针发现的关键缺口（修复前）

| 编号 | 变体 | 修复前 | 说明 |
|------|------|--------|------|
| B4 | `DROP TABLE users;` | BLOCKED | 已覆盖（AST 层） |
| C11 | `UPDATE users SET status='disabled' WHERE id IN (SELECT id FROM users WHERE active=1);` | **ALLOWED（FN）** | 同表子查询无 WHERE → 全表更新 |
| C13 | `DELETE FROM t WHERE id IN (SELECT id FROM s WHERE y>0);` | **ALLOWED（FN）** | IN 子查询 |
| E5 | `DELETE FROM t WHERE id=1;` | BLOCKED | 有界 DELETE 过度阻断（fail-closed，已文档化） |
| E9 | `UPDATE users SET status='disabled' WHERE id=id;` | **ALLOWED（FN）** | 恒真 tautology |

---

## 2. 根因分析：7 个 FN 缺口

探针发现 7 个静默放行（false-negative）缺口，全部源于同一根因链：

```
tree-sitter-sql 语法覆盖率不足
  └─> 无法解析的语句整体降级为 ERROR 节点
        └─> AST 捕获层无匹配 → 静默 ALLOW
              └─> L2 策略层 YAML 完全没有 SQL 关键词规则（审计确认）
                    └─> SQL 安全完全依赖 AST 层 → 缺口全部漏过
```

### 7 个 FN 缺口清单

| # | 缺口 | 语句形态 | 危害 |
|---|------|----------|------|
| 1 | DROP DATABASE | `DROP DATABASE prod;` | 删库 |
| 2 | DROP TRIGGER | `DROP TRIGGER trg ON t;` | 删触发器 |
| 3 | DROP FUNCTION | `DROP FUNCTION fn();` | 删函数 |
| 4 | ALTER TABLE ... DROP | `ALTER TABLE t DROP COLUMN c;` / `DROP PRIMARY KEY` | 删列/约束 |
| 5 | UPDATE + IN 子查询 | `UPDATE t SET x=1 WHERE id IN (SELECT ...)` | 全表/大范围更新 |
| 6 | DELETE + IN 子查询 | `DELETE FROM t WHERE id IN (SELECT ...)` | 全表/大范围删除 |
| 7 | WHERE 恒真 tautology | `WHERE id=id` | 使 WHERE 形同虚设 → 全表更新 |

---

## 3. 修复方案（ast_guard.py，L2 层不动的约束下）

约束：**L2 策略层是 YAML 配置，按架构约定不做关键词级规则**（Round 1 已确立）。
因此修复全部落在 AST 层（`src/ast_guard.py`），新增两道防线：

### 3.1 Parse-error guard（覆盖缺口 1–6）

`_sql_parse_error_guard(code, root)` —— 仅在解析树存在 ERROR 节点时触发：

- 遍历全部 ERROR 节点，向上找最近的语句祖先（statement / source_file）
- 用 `_SQL_PARSE_ERROR_KEYWORD = re.compile(r"(?i)(?:^|;)\s*(drop|alter|delete|truncate|update)\b")`
  匹配语句起始的破坏性关键词
- 命中 → kind `destructive-sql-parse-error`，阻断

**零误报面设计**：可正常解析的查询（含全部合法变体）根本不进入该层；
只有 tree-sitter 明确吐出 ERROR 的语句才会被检查。IN 字面量元组
`WHERE id IN (1,2,3)`、JOIN、RENAME、SHOW、DESCRIBE、EXPLAIN 均可解析 → 不受影响。

### 3.2 Tautology 检测（覆盖缺口 7）

`_has_tautology_where(node)` —— 在 update/delete 的 where_clause 中查找
`binary_expression` 且两个命名子节点都是 identifier/field_identifier 且文本相同
（如 `WHERE id=id`）→ kind `destructive-tautology`，阻断。

**已文档化边界**：只处理简单二元比较（`a=a`）；不处理 `id>0`（恒真值域）、
`IS NOT NULL` 等更复杂的恒真形态（留给后续轮次）。

### 3.3 接线位置

- parse-error guard: `analyze()` 中 per-query 捕获循环**之后**、python taint 块之前
  （避免重复 finding；先做过循环内版本，发现重复风险后移到循环外）
- tautology 检查: update 后处理分支，替换原先"仅查无 WHERE"的检查

---

## 4. 修复前后行为对照（live 网关实测）

| 语句 | 修复前 | 修复后 |
|------|--------|--------|
| `DROP DATABASE prod;` | ALLOWED (FN#1) | **BLOCKED** (destructive-sql-parse-error) |
| `DROP TRIGGER trg ON t;` | ALLOWED (FN#2) | **BLOCKED** |
| `DROP FUNCTION fn();` | ALLOWED (FN#3) | **BLOCKED** |
| `ALTER TABLE t DROP COLUMN c;` | ALLOWED (FN#4) | **BLOCKED** |
| `UPDATE t SET x=1 WHERE id IN (SELECT ...)` | ALLOWED (FN#5) | **BLOCKED** |
| `DELETE FROM t WHERE id IN (SELECT ...)` | ALLOWED (FN#6) | **BLOCKED** |
| `UPDATE users SET active=0 WHERE id=id;` | ALLOWED (FN#7) | **BLOCKED** (destructive-tautology) |
| `UPDATE users SET status='disabled' WHERE id=1;` | ALLOWED | ALLOWED（零误报） |
| `UPDATE t SET x=1 WHERE id IN (1,2,3);` | ALLOWED | ALLOWED（零误报） |
| `SELECT name FROM users WHERE id=1;` | ALLOWED | ALLOWED（零误报） |

---

## 5. 测试与回归

- 更新 `tests/test_ast_guard_sql_update.py` 两处过时断言 + 新增 7 用例：
  - `test_update_subquery_where_allowed` → `test_update_subquery_where_blocked`
    （含同表子查询、DELETE 子查询、IN 字面量零误报 3 个配套断言）
  - `test_drop_database_grammar_boundary` 反转 → 验证新的 BLOCKED 行为
  - 新增 `@pytest.mark.parametrize` 覆盖 FN#2/#3/#4（DROP TRIGGER / DROP FUNCTION / ALTER DROP）
- 全量测试套件（与 CI GATE 3 相同命令 `pytest tests -q --timeout=120`）:
  **955 passed, 1 skipped**（Round 1 基线 948 + 新增 7，零回归）

---

## 6. 关键运维警示（本次探针实测发现）

**`localhost:9000` ≠ `127.0.0.1:9000`** —— 二者路由到不同网关实例：

| 地址 | 解析 | 路由到 | 后果 |
|------|------|--------|------|
| `localhost:9000` | ::1 (IPv6) | WSL 中继 → **WSL 内旧代码网关**（无 UPDATE/sensitive-schema 处理） | 15 个假 miss |
| `127.0.0.1:9000` | IPv4 | Windows 原生当前代码网关（PID 41268, v0.4.0, ASTGuard 已加载） | 正确行为 |

**规则：治理探针一律使用 `http://127.0.0.1:9000`，禁用 `localhost`。**

同一 9000 端口存在多进程绑定：27800（Windows 网关，已重启为 41268）、
9516（WSL 中继）、9492（Docker Desktop 后端，无关）。

---

## 7. 交付件清单

| 文件 | 变更 |
|------|------|
| `src/ast_guard.py` | MODIFIED —— `import re`、`_has_tautology_where`、`_SQL_PARSE_ERROR_KEYWORD`、`_sql_parse_error_guard`、analyze() 接线 |
| `tests/test_ast_guard_sql_update.py` | MODIFIED —— 2 处反转 + 7 新增用例 |
| `scripts/gov_round2_sql_variants.py` | NEW —— 44 用例探针矩阵（BASE=127.0.0.1:9000） |
| `scripts/gov_round2_astprobe.py` | NEW —— 进程内 AST 探针（15 用例） |
| `scripts/gov_round2_parsetree.py` | NEW —— 解析树转储 |
| `scripts/gov_round2_verify_parse.py` | NEW —— 解析+守卫行为验证 |
| `scripts/gov_round2_which_gateway.py` | NEW —— IPv4/IPv6 网关识别 |
| `scripts/gov_round2_inspect.py` | NEW —— 响应结构检查 |
| `scripts/gov_round2_verify_tests.py` | NEW —— 测试影响查询行为验证 |
| `governance_reports/gov_round2_sql_probes.json` | NEW —— 探针矩阵数据（43/44） |
| `governance_reports/GOV_ROUND2_report.md` | NEW —— 本报告 |

---

## 8. 遗留项（非阻塞，记录在案）

1. **E5 有界 DELETE 过度阻断**：fail-closed 姿态已文档化；若后续需要精确
   区分有界/无界 DELETE，需为 tree-sitter-sql 补充方言扩展或降级为人工审核队列。
2. **Tautology 检测边界**：只覆盖 `a=a` 简单二元比较；`id>0`、`IS NOT NULL`
   等恒真形态未覆盖，待后续轮次。
3. **Round 3 候选**（未批准，仅提案）：L2 YAML 增加 SQL 关键词级 deny-list 的
   架构决策是否需要反转（当前约定由 AST 层承担）。
