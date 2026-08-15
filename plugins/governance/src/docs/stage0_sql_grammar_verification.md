# 阶段 0: SQL Grammar 硬验证报告 (Stage 0 Verification)

> 状态: **COMPLETE** | 日期: 2026-08-03 | 引擎: tree-sitter==0.21.3 + tree-sitter-languages==1.5.0 (硬锁)
> 背景: 用户蓝图 (Phase 1/2/3 AST 规则) 中的节点类型与谓词用法未经运行时验证,先行阶段 0 全部探针化验证。

---

## 1. 验证矩阵总览

| # | 探针 | 结论 | 影响 |
|---|------|------|------|
| A | `update_statement` / `where_clause` 节点存在性 | ✅ 存在 | 蓝图 Rule 1 (UPDATE 无 WHERE) 可行 |
| A | 5 个候选查询编译 | ✅ 全部编译通过 | 查询语法无阻塞 |
| A | where_clause 子节点检测 | ✅ `has_where=True/False` 精确 | Python 侧子节点检查方案成立 |
| B | 顶层裸 `(identifier) @x (#match? @x ...)` | ❌ **谓词静默失效** | 蓝图 sensitive_schema 原设计**不可用** |
| B | `(call function: (identifier) @fn (#match? ...))` | ✅ 谓词生效 | Python 侧不受影响 |
| B | `(attribute object: (identifier) @o (#match? ...))` | ✅ 谓词生效 | Python 侧不受影响 |
| C | `(dotted_name (identifier) @schema (#match? ...))` | ✅ **谓词生效** | sensitive_schema 修复方案 S1 成立 |
| D | `(from_clause (identifier) @tbl (#match? ...))` | ✅ **谓词生效** | 裸表名方案 S2 成立 |
| D | `table` / `field` / `relation` 节点类型 | ❌ **Invalid node type** | 蓝图虚构节点全部不存在,编译即失败 |

---

## 2. 关键发现: #match? 谓词的作用域缺陷 (CRITICAL)

### 现象

tree-sitter 0.21.3 的 `#match?` 谓词在 **顶层裸捕获模式** 下被静默忽略:

```scheme
; ❌ 失败: 谓词被编译但运行时被忽略 —— 所有 identifier 全被捕获
(identifier) @x (#match? @x "^(eval|exec)$")
; 输入 "x = exec(user_input)" -> 捕获 x, exec, 以及其他任意 identifier
```

### 规律 (经验证)

| 捕获位置 | 谓词是否生效 |
|----------|:---:|
| 顶层裸 `(identifier) @x` | ❌ 失效 |
| 结构化节点字段 `call function: (identifier) @fn` | ✅ 生效 |
| 结构化节点属性 `attribute object: (identifier) @o` | ✅ 生效 |
| 结构化节点子节点 `dotted_name (identifier) @schema` | ✅ 生效 |
| 结构化节点子节点 `from_clause (identifier) @tbl` | ✅ 生效 |

**规律**: 谓词需要结构上下文 (父节点/字段) 才被 tree-sitter 正确编译执行;纯顶层模式谓词被 drop。

### 对蓝图的影响

用户 Phase 1 蓝图中的:

```scheme
(identifier) @sensitive_schema (#match? @sensitive_schema "^(information_schema|pg_catalog|...)$")
```

**会产生灾难性误报** —— 谓词失效意味着**所有** identifier (包括 `x`、`print`、`tables`、`user_information`) 都会被捕获为 sensitive_schema 并阻断。已验证: 输入 `SELECT * FROM user_information` 会被错误阻断。

---

## 3. 修正后的 sensitive_schema 设计 (已验证)

### S1: 限定名 (qualified name) —— dotted_name 结构

```scheme
(from_clause
  (dotted_name
    (identifier) @sensitive_schema
    (#match? @sensitive_schema "^(information_schema|pg_catalog|sqlite_master|mysql|sys)$")))
```

实测:
- `SELECT * FROM information_schema.tables` → **FLAG** (information_schema)
- `SELECT * FROM pg_catalog.pg_tables` → **FLAG** (pg_catalog)
- `SELECT * FROM user_information` → **pass** ✅ (裸 identifier,无 dotted_name,天然排除)
- `SELECT * FROM my_schema.users` → pass (my_schema 不在列表内,谓词正确过滤)

### S2: 裸表名 (bare) —— from_clause 子节点结构

```scheme
(from_clause
  (identifier) @sensitive_schema
  (#match? @sensitive_schema "^(sqlite_master|information_schema|pg_catalog|mysql|sys)$")))
```

实测:
- `SELECT * FROM sqlite_master` → **FLAG**
- `SELECT * FROM user_information` → 仅当在列表内才 FLAG (精确可控)
- `SELECT * FROM my_schema.users` → pass (dotted_name 结构,非裸 identifier)

### P3 兼容性

schema 名列表**内嵌在 .scm 查询文件中** (正则字面量),Python 代码零硬编码 → `test_no_hardcoded_commands_in_engine` 满足。

---

## 4. UPDATE 规则 (Rule 1) 验证

`UPDATE users SET name='x' WHERE id=1` 的 AST:

```
update_statement
├── UPDATE
├── identifier          (users —— 直接子节点 = 目标表)
├── set_clause
└── where_clause        (子节点存在性检测 has_where=True/False 精确)
```

- `(update_statement) @update_stmt` 查询编译 ✅
- Python 侧: 遍历 children 检查 `where_clause` 类型 → 缺失则 CRITICAL finding ✅
- 与 ast_guard.py 现有架构 (统一 `analyze()` + ASTFinding) 完全兼容

---

## 5. 蓝图虚构节点清单 (不存在,编译即失败)

| 蓝图节点 | 实际 AST 结构 |
|----------|---------------|
| `table_reference` | ❌ 不存在 → `from_clause → dotted_name / identifier` |
| `field` | ❌ 不存在 |
| `relation` | ❌ 不存在 |

---

## 6. 阶段 0 结论

1. **Rule 1 (update_stmt 无 WHERE)** — 蓝图方案成立,直接实现。
2. **Rule 2 (sensitive_schema)** — 蓝图方案**不可用**,需用 S1+S2 双规则修正。
3. **架构约束** — 新捕获名 `@sensitive_schema` / `@update_stmt` 必须注册进
   `EXPECTED_CAPTURES` 语义表 (P1),否则被忽略。
4. **探针脚本** (保留供回归):
   - `C:\temp\verify_sql_grammar.py` — 节点存在性 + 查询编译 + where 检测
   - `C:\temp\predicate_probe.py` — 谓词作用域控制实验
   - `C:\temp\sql_predicate_probe.py` — 虚构节点探针
   - `C:\temp\sql_dotted_probe.py` — S1 方案验证 (PART C)
   - `C:\temp\sql_child_ident_probe.py` — S2 方案验证 (PART D)

> 下一步: 阶段 A (README/ROADMAP/拦截数据) → B (examples) → C1 (Docker)。
> Phase 1 SQL 规则实现在 A/B/C1 之后,使用本报告的修正设计。
