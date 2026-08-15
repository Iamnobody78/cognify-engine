# B 阶段：json_path 工具治理 + 可解释主控 Step 1 审计 Schema 扩充

> 任务: **TASK-REAL-010**（DEBT-0016 后首个新能力批次；用户裁决 B 优先，执行顺序 B → C → D，A 生产化待硬件到位）
> 版本: v0.3.0（网关） / policies.yaml v0.2.0 / 治理快照 v1.8.0
> 日期: 2026-08-03
> 关联债务: DEBT-0021（新登记，见 §5）

---

## 1. 任务范围（用户裁决合并项）

| 输入 | 内容 |
|------|------|
| **B 阶段** | json_path 工具治理——YAML 规则可选 `json_path` 字段，在策略预处理层解析请求体 |
| **可解释主控 Step 1** | 审计日志 Schema 扩充：工具杀伤半径权重表（Ls）+ DecisionRecord 扩展（tool_name/tool_lethality）+ storage 迁移 |
| 执行顺序 | B → C（Trace，DEBT-0019）→ D（反馈调节器）；A 生产化标记"待硬件到位" |

## 2. 交付物清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/norm.py` | 新增 (~35 行) | 工具名归一化管线（NFKC→confusables→casefold）单一事实源，自 main.py 抽取 |
| `src/lethality.py` | 新增 (~75 行) | 工具杀伤半径权重表（Ls 0.1-0.95）+ `lethality_for_tool()`（未知工具 0.6 记账） |
| `src/policy.py` | 修改 | `Rule` 新增 `json_path`/`json_pattern` 字段 + 加载期 fail-closed 校验；`matches()`/`evaluate()` 扩展 body 参数；`_parse_json_path`/`_json_extract`/`_extract_at`（零依赖 JSONPath 子集） |
| `src/models.py` | 修改 | `DecisionRecord` 新增 `tool_name`/`tool_lethality`（Optional，默认 None） |
| `src/storage.py` | 修改 | decisions 表 10 列（+2）；`_migrate()` 对旧 8 列库 ALTER ADD COLUMN（无损）；save/flush_pending/_row_to_dict 支持新列 |
| `src/main.py` | 修改 | evaluate 传 body；`_audit_tool_fields()`（取最高杀伤工具）；_deny_decision 工具字段；版本 v0.3.0 |
| `config/policies.yaml` | 修改 | v0.2.0；新增 `block-shell-tool`(DENY) + `escalate-file-write-tool`(ESCALATE) 两条 json_path 规则 |
| `examples/policy_probe.py` | 修改 (GATE 5) | json_path 规则豁免路径覆盖检查 + 新增 4 项条件规则约束校验 |
| `scripts/policy_sync.py` | 修改 (GATE 7) | json_path 规则豁免 path 覆盖列表（action 白名单仍生效） |
| `tests/test_json_path_policy.py` | 新增 (35 测试) | 解析器/提取/规则语义/fail-closed/lethality/审计 schema 迁移/e2e 全覆盖 |
| `docs/json_path_governance_report.md` | 新增 | 本报告 |

## 3. 核心设计

### 3.1 json_path 条件规则（B 阶段）

规则命中由**三重条件**决定：路径（`path_pattern`）∧ 方法（`method`）∧ **请求体**（`json_path` + `json_pattern`）。

支持的零依赖 JSONPath 子集（`src/policy.py` 内实现，约 120 行，不引入 jsonpath-ng）：

| 语法 | 语义 | 示例 |
|------|------|------|
| `$` | 根（可选前缀） | `$.a.b` ≡ `a.b` |
| `.key` | 字典成员 | `$.tool_calls[0].name` |
| `..name` | 递归下降（任意深度） | `$..name` 匹配所有 `name` 成员 |
| `[N]` | 列表索引 | `$.messages[0]` |
| `[*]` | 任意列表元素 / 任意字典值 | `$.tool_calls[*].name` |

**安全回退语义**（测试锚点）：非 JSON 体（None/不可解析字符串/标量）→ 提取结果为空 → 规则**不匹配**。依据：结构化体才承载工具调用；无法解析体的兜底由 fail-closed 层负责（危险前缀仅在超时分支执行）。这与"DENY 前无法验证就必须拒绝"的教义不冲突——json_path 规则的触发条件本就要求"能读到结构化体"，空体 ≠ 无法验证的工具调用，而是不存在工具调用。

**加载期 fail-closed 校验**（`Rule.__post_init__`）：
- `json_path` 语法错误 → `ValueError` → 策略加载失败（拒绝带病规则进入热加载）
- `json_pattern` 缺 `json_path` → `ValueError`（body 模式规则必须有提取路径）
- `json_pattern` 非法正则 → `ValueError`

**GATE 5/7 联动**：json_path 规则是"体内治理"，触发条件由 body 决定而非路径——timeout 分支的 path 启发式（danger.py）看不到 body，故路径覆盖不变量对其豁免（缺口登记 DEBT-0021，见 §5）。GATE 5 新增 4 项条件规则约束：ALLOW+json_path 拒绝（白名单走火器）、DENY/ESCALATE 必须携带 json_pattern（仅凭路径存在即拦截过于宽泛）、json_path 语法校验、json_pattern 正则校验。

### 3.2 工具杀伤半径权重表 Ls（Step 1）

```python
# src/lethality.py
TOOL_LETHALITY = {
    "search": 0.2, "read": 0.2, ...            # 只读 0.1-0.3
    "write_file": 0.7, "edit": 0.7, ...        # 写入 0.5-0.7
    "execute_command": 0.95, "system_run": 0.95, ...  # 系统执行 0.85-0.95
    "delete_file": 0.95, "rm": 0.95, ...       # 删除 0.9-0.95
    "sudo_exec": 0.95, ...                     # 提权 0.85-0.95
}
_DEFAULT = 0.6   # 未知工具中等记账（不放大不隐匿）
```

- 名称匹配复用 `src/norm.py` 单一归一化管线：`Execute_Command`→0.95、`delete_fιle`（U+03B9）→0.95、全角 NFKC 折叠→0.95（测试锚点）。
- 设计原则：Ls 只做**审计记账**，不参与决策路径（避免第二个策略事实源）；Step 2+ 计划将权重表迁移 YAML（"策略是数据"铁律）。

### 3.3 审计 Schema 扩充（Step 1）

`DecisionRecord` 新增 2 字段；`decisions` 表 8 列 → 10 列：

```sql
-- 新库直建
CREATE TABLE decisions (
    ... agent_id TEXT,
    tool_name TEXT,          -- 请求中杀伤半径最高的工具名（归一化前原样）
    tool_lethality REAL      -- 对应 Ls；NULL = 无工具声明
);
-- 旧库无损迁移（_migrate()）
ALTER TABLE decisions ADD COLUMN tool_name TEXT;
ALTER TABLE decisions ADD COLUMN tool_lethality REAL;
```

- `_audit_tool_fields()`：先精确 OpenAI 格式提取；无结果退化为 `$..name` 通配（覆盖非 OpenAI 结构化体）；取**最高杀伤**工具（max Ls）而非第一个名字——审计字段反映最大风险。
- 每次决策（含 DENY/ESCALATE/ALLOW）都记录工具字段，供事后归因与仪表盘聚合。

## 4. 验证证据

| 项 | 结果 |
|----|------|
| 新增测试 | `tests/test_json_path_policy.py` 35 个（解析器 4 + 提取 5 + 规则语义 6 + 引擎集成 5 + lethality 4 + 审计 schema 6 + e2e 4） |
| 全量回归 | **250 passed**（215 基线 + 35 新增） |
| 覆盖率 | **90.07%**（门槛 ≥60%，上轮 88.71%） |
| GATE 1+2 | PASS（511 asserts 0 违规；测试数含新增文件） |
| GATE 3 | PASS（12 个 src 文件无硬编码策略；lethality 表键不含 allow/deny/block/escalate/rule） |
| GATE 5 | PASS（json_path 规则豁免 + 4 项新校验全过） |
| GATE 6 | PASS（新代码零安全反模式：无 startswith、无裸 except、无 re.compile） |
| GATE 7 | PASS（4 条非 json_path 阻断规则覆盖检查；json_path 规则豁免且 action 白名单生效） |
| e2e 契约 | /v1/intercept + body 声明 `execute_command` → **403 DENY**（block-shell-tool）；`write_file` → **202 ESCALATE**（escalate-file-write-tool）；`get_weather` → 200 ALLOW；无 name 键旧格式体 → 不受影响 |

## 5. 新登记债务

| ID | 描述 | 严重度 | 阻塞? |
|----|------|:---:|:---:|
| DEBT-0021 | timeout fail-closed 分支的 path 启发式（danger.py）看不到请求体——json_path 规则在超时降级路径不生效（接受为已文档化缺口：timeout 3s+熔断兜底；json_path 规则是纵深防御的附加层） | LOW | 否 |

## 6. 后续（待用户裁决）

1. **C 阶段**（DEBT-0019 Trace 因果追踪）——json_path 工具审计字段天然成为 Trace 的边权重输入
2. **D 阶段**（统计反馈调节器）
3. **可解释主控 Step 2+**（CoT 推理链 / 上下文漂移）——标记"待 A 就绪"，Ls 权重表届时迁移 YAML
4. **A 生产化**（拉取 qwen2.5:7b，`JUDGE_MODEL` 热切换）——待硬件到位
