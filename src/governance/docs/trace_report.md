# C 阶段：Trace 因果追踪（DEBT-0019）

> 任务: **TASK-REAL-011**（用户批准 C 阶段，B→C→D 顺次）
> 版本: 网关 v0.4.0 / 治理快照 v1.9.0
> 日期: 2026-08-03
> 关联债务: DEBT-0022（新登记，见 §6）

---

## 1. 任务范围（用户执行确认表）

| 项目 | 交付 |
|------|------|
| 新增列 | `trace_id`（UUID）、`parent_span_id`（UUID）✓ |
| 迁移方式 | 复用 `_migrate()` 无损模式（ALTER TABLE ADD COLUMN）✓ |
| 查询接口 | `GET /v1/trace/{trace_id}` 递归 CTE（SQLite WITH RECURSIVE）✓ |
| 集成点 | `intercept_handler` 入口：无 `X-Trace-ID` 则生成，无 `X-Parent-Span-ID` 则生成 ✓ |
| 增量 | ~130 行核心代码 + 20 测试（超出确认表 10 测试——含迁移/环防护/e2e 链式验证，均为必要覆盖） |

**与 B 阶段衔接**：`tool_lethality` 作为 Trace 边权重——每个节点展示杀伤半径，审计人员快速定位"哪一步引入最大风险"（`test_lethality_as_edge_weight` 锚定）。

## 2. 交付物清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/models.py` | 修改 | `DecisionRecord` + `trace_id`/`parent_span_id`；`InterceptResponse` + `trace_id` |
| `src/storage.py` | 修改 | decisions 表 12 列 + `_migrate()` 加 2 列（无损）+ `idx_trace` 索引 + `get_trace()` 递归 CTE |
| `src/main.py` | 修改 | `_trace_context()` 头提取/生成；intercept 入口集成；响应头 `X-Trace-ID`/`X-Span-ID` 回传；`trace_handler` + 路由；v0.4.0 |
| `tests/test_trace.py` | 新建 (20 测试) | 上下文语义 / 模型字段 / schema 迁移 / CTE 树/链/防护 / e2e 五连 |
| `docs/trace_report.md` | 新建 | 本报告 |

## 3. 核心设计

### 3.1 span 模型：`span_id == decision.id`

调用树由**单亲链**构成（每行一个 `parent_span_id`）：

```
Agent A ──POST /v1/intercept──▶ {trace_id: T(生成), parent: NULL}   ← 链根
  │ 响应头 X-Trace-ID: T, X-Span-ID: d1 (decision.id)
  ▼
Agent B ──POST /v1/intercept──▶ {trace_id: T(继承), parent: d1}      ← 子节点
  │ 响应头 X-Trace-ID: T, X-Span-ID: d2
  ▼
Agent C ──POST /v1/intercept──▶ {trace_id: T(继承), parent: d2}      ← 孙节点
```

**设计裁决（对确认表的唯一自洽落地）**：确认表写"若无 X-Parent-Span-ID 则生成"。随机占位 UUID 无法被 CTE 锚定（`parent_span_id` 必须指向真实父决策 id），因此"生成"落地为**新链根语义**：父缺失 → `NULL`（根锚点），链根身份由响应头 `X-Span-ID`（= decision.id）传递，下游请求携带 `X-Parent-Span-ID` 指向它即形成链。这是唯一自洽实现，已在 `_trace_context()` docstring 与 §3.3 记录。

### 3.2 递归 CTE（storage.get_trace）

```sql
WITH RECURSIVE tree(...) AS (
    SELECT ..., 0 FROM decisions
    WHERE trace_id = ? AND parent_span_id IS NULL          -- 根锚点
    UNION
    SELECT d..., t.depth + 1 FROM decisions d
    JOIN tree t ON d.parent_span_id = t.id
    WHERE d.trace_id = ? AND t.depth < ?
)
SELECT ... FROM tree ORDER BY depth, timestamp LIMIT ?;
```

防护三重（fail-closed 精神）：
1. **UNION 去重**：SQLite 递归 CTE 语义下已访问行不再扩展——病态数据（自引用）天然终止（`test_self_loop_detaches_terminates`）
2. **max_depth=50 上限**：深链截断不挂起（`test_deep_chain_depth_bound`：60 层链 → 精确返回 51 节点）
3. **max_nodes=500 上限**：防滥用

诚实边界记录：单亲列结构下"可达环"在数学上不可能（改父必脱链）；防护针对真实的病态数据（自引用/跨 trace 指针——`WHERE d.trace_id = ?` 过滤掉跨链 JOIN）。

### 3.3 头协议（Agent 生态零修改）

| 头 | 方向 | 语义 |
|----|------|------|
| `X-Trace-ID` | 请求/响应 | 调用链根标识；请求缺失 → 网关生成新 UUID |
| `X-Parent-Span-ID` | 请求 | 父决策 id；缺失 → NULL（链根） |
| `X-Span-ID` | 响应 | 本决策 id（= decision.id）；下游用其作 X-Parent-Span-ID |

响应体 `InterceptResponse.trace_id` 同步回传（非头依赖）。

## 4. 验证证据

| 项 | 结果 |
|----|------|
| 新增测试 | `tests/test_trace.py` 20 个（上下文 4 + 模型 2 + schema/迁移 3 + CTE 5 + e2e 5 + lethality 边权重 1） |
| 全量回归 | **270 passed**（250 基线 + 20 新增） |
| 覆盖率 | **90.12%**（门槛 ≥60%） |
| GATE 1+2 | PASS（565 asserts 0 dataclass；257 测试 marker 批准） |
| GATE 3/5/6/7 | 全 PASS（exit 0） |
| e2e 契约 | 无头 POST → 响应头 X-Trace-ID/X-Span-ID 生成 ✓；带头 → 复用 ✓；roundtrip GET /v1/trace → 200 单节点 ✓；两跳链 → 2 节点 parent 正确 ✓；未知 trace → 404 ✓ |
| 迁移契约 | 10 列旧库（REAL-010 schema）→ Storage 初始化后 12 列，旧行 trace 字段 NULL 无损 ✓ |

## 5. 执行期自发现与修复

| 问题 | 上下文 | 修复 |
|------|--------|------|
| `idx_trace` 建在 `_migrate()` 之前 | 旧库（10 列）初始化时 CREATE INDEX 触发 "no such column: trace_id" | 索引移至 `_migrate()` 之后（+ 注释说明顺序依赖），并清理重复 `_migrate()` 调用 |
| 环测试断言错误 | 单亲链"可达环"数学上不可能（改父必脱链）→ 原测试构造的环使根脱链，断言 `{R,A,B}` 失败 | 重构为两个诚实测试：自引用脱链终止（`{R,A}`）+ 60 层深链 depth 截断（精确 51 节点）；报告中记录该结构事实 |
| GATE 1 违规 ×2 | `{n["id"] for n in nodes} == {...}`（推导式左值）、`tree.status == 200`（非豁免根） | 改 `sorted(...) == [...]`（调用根）+ 变量名 `resp`（豁免根） |

## 6. 新登记债务

| ID | 描述 | 严重度 | 阻塞? |
|----|------|:---:|:---:|
| DEBT-0022 | `/v1/chat/completions` 路径未注入 trace 上下文——链只在 intercept 层串联，chat 请求本身不入链（确认表集成点仅限 intercept；chat 侧补链待后续裁决） | LOW | 否 |

活跃债务合计 5（0018/0019→已清偿/0020/0021/0022）——**DEBT-0019 已清偿**。

## 7. 后续（待用户裁决）

1. **D 阶段**（统计反馈调节器）——5min 扫描高频 DENY 模式 → pending_rules 建议；trace 树可提供"调用链级"模式（同链多 DENY = 结构化攻击信号）
2. **外部评审"治理大脑"Phase 1-4**（可解释引擎 rationale 字段 / 五级响应 ALLOW_WITH_WARNING+SUSPEND / 学习引擎 ≈ D 阶段 / 协商引擎）——与可解释主控 Step 2+（CoT/上下文漂移，待 A 就绪）重叠，建议合并评审后裁决
3. **A 生产化**（7B）——待硬件到位
