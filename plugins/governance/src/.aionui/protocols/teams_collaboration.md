# 🧬 Teams 代理团队协作协议 v2.0

> **定位**：让 2-5 个 AionUI 子代理组成自治团队，并行处理 agent-governance 项目的开发、测试、审查、归档任务。
>
> **核心约束（来自实验）**：
> - 单代理工作量 ≤2 文件、≤5 维度
> - 单次 Spawn ≤3 代理并行（4+ 会资源竞争超时）
> - **子代理之间无法互相通信** → 必须用两阶段 Spawn（见 §2.4）

---

## 一、角色定义

| 角色 | 职责 | 允许写入 | 典型任务 |
|------|------|:--:|------|
| **Builder** 🛠️ | 生成/修改源代码 | `src/`, `config/` | 实现新模块、修复 bug、重构 |
| **Tester** 🧪 | 编写测试、运行测试 | `tests/` | 补充测试用例、修复 flaky test |
| **Reviewer** 🔍 | 审查代码、审计安全 | 只读（输出报告） | 安全审计、架构合规检查 |
| **Archivist** 📁 | 更新文档、记录日志 | `*.md`, `.aionui/` | 更新 CHANGELOG、写审查报告 |

**规则**：
- Builder 和 Reviewer 不能是同一代理（不可自我审查）。
- 每次变更必须经过"Builder → Reviewer → Archivist"三阶段闭环。
- 如果团队只有 2 个代理：省略 Archivist 角色，Reviewer 兼任。
- **Spawn 子代理是"哑执行者"**：它们只执行明确指令并输出结果，不做跨代理协调——协调永远是 Coordinator（主代理）的职责。

---

## 二、任务分配协议

### 2.1 任务模板

Coordinator 使用以下模板分配任务：

```markdown
## 任务分配 — {{TASK_ID}}

### 背景
[一句话：为什么需要这个任务]

### 优先级
P0 / P1 / P2 / P3

### 文件分配表（防撞车）
| 文件 | 负责代理 | 角色 |
|------|----------|------|
| src/xxx.py | Builder-1 | 修改 |
| tests/test_xxx.py | Tester-1 | 新增 |

### 验收标准
- [ ] 测试通过 (pytest -q)
- [ ] GATE 1-4 全部通过
- [ ] Reviewer 输出 PASS
- [ ] Archivist 记录到 CHANGELOG

### 截止时间
[时间窗口]
```

### 2.2 粒度限制（强制）

| 约束 | 值 | 来源 |
|------|:--:|------|
| 单代理最大文件数 | 2 | 实验数据：3 文件 → 超时 |
| 单代理最大审查维度 | 5 | 实验数据：超过 5 维度 → 超时 |
| 单次 Spawn 最大并行代理数 | 3 | 实验数据：4+ 代理 → 资源竞争 |
| 单代理最大输出行数 | 100 | **Spawn 输出 4096 token 截断**，超长会被切掉 |

### 2.3 两阶段 Spawn 架构（关键）

**由于 Spawn 子代理之间无法互相通信，禁止在单次 Spawn 中构建跨代理依赖链。**

```
阶段 1 — Spawn #1（并行，无依赖）
┌─────────────┬─────────────┬─────────────┐
│  Builder-1  │  Builder-2  │  Tester-1   │
│  写 src/     │  写 config/ │  写 tests/  │
└──────┬──────┴──────┬──────┴──────┬──────┘
       └─────────────┼─────────────┘
                     ▼
       Coordinator 验证层（必须执行，不可跳过）
       ├── git diff 检查文件变更
       ├── python -m pytest tests/ -q
       └── python scripts/check_test_quality.py
                     ▼
阶段 2 — Spawn #2（串行，读最终文件）
       ┌─────────────┐
       │  Reviewer   │
       │  读最终文件  │ ← 独立读取，不依赖 Builder 的交接块
       └──────┬──────┘
              ▼
       Coordinator 汇总
       ├── 通过 → git add + commit + push
       ├── REJECT → 分配回 Builder 重做（新 Spawn）
       └── 记录 → Archivist 任务（或 Coordinator 兼任）
```

**为什么必须两阶段**：
- 阶段 1 的 Builder 们互不依赖 → 可安全并行
- 阶段 2 的 Reviewer 需要看 Builder 的**最终落盘文件** → 必须等阶段 1 完成后单独启动
- 单次 Spawn 内传"交接块"给另一个子代理是**不可能的**（独立上下文）

### 2.4 结果汇总格式

子代理输出必须精简（≤100 行），格式固定：

```markdown
## {{ROLE}} 输出 — {{TASK_ID}}

### 结果
PASS / FAIL / REJECT

### 变更摘要
- 文件: `src/xxx.py` (+12, -5)
- 关键变更: [1-2 句话]

### 待 Coordinator 验证
1. [请跑 pytest 确认 xxx]
2. [请检查 GATE 1 是否通过]

### 已知限制
- [未覆盖的边界情况，如有]
```

---

### 2.6 调度层第二阶段：并行接力 + 合并审查（v0.2.3+，AUDIT-0011）

> **目标**：Builder + Tester 并行执行（互不阻塞）→ Reviewer 合并审查双方产物。
> 验证实验：TASK-SCHED-002（Builder 写 src/task_scheduler.py + Tester 并行写 tests → Reviewer 合并审查 → PASS，1 轮完成）。

**并行语义（实测确认）**：
1. **同一 Spawn 调用内发多个任务 = 真并行**（各自独立上下文，互不等待）
2. **接口契约必须双方预共享**：Builder 和 Tester 并行时无实现可见性 → 两个 prompt 必须携带**完全相同的接口契约**（类名/方法签名/语义/边界行为），否则并行产物必然不匹配
3. **独立产物落盘**：Builder 写 uilder_output.md，Tester 写 	ester_output.md（各自工作区路径），Reviewer 读取两者

**截断容错（TASK-SCHED-002 实测教训）**：
- Tester v1 被截断（5 turns）→ **测试文件未落盘** → 接力无法继续
- 修复：TEST(2) 轮重新 Spawn，强制 "STEP 1 = 先写文件，再运行"，成功
- **规则**：并行任务的每个角色，产物必须"先落盘"；Coordinator 在每轮结束后**验证产物文件存在 + 内容完整**（行数/字节数），缺失即自动进入修复轮，不依赖子代理自述

**合并审查（Reviewer）**：
- Reviewer 读取 Builder + Tester 两份报告 + 两份产物，独立重跑全部验证
- 交叉核对：Builder 声称 vs Tester 声称 vs 实测（行数/测试数/通过数），不一致即 REJECT
- verdict 先落盘（provisional）→ 深查后更新（final）——先落盘原则延续

**本轮实测数据**：Builder 90 行自检 OK；Tester 177 行 21 用例全过；Reviewer 独立重跑 21 passed + AST 精确 + 契约探测全过；双报告交叉一致（0 偏差）；全量回归 **130 passed**。
### 2.7 调度层第三阶段：MCP 工具共享 + 真实场景边界约束（v0.2.4+，AUDIT-0012/0013）

> **目标**：子代理经 MCP 统一工具总线交换产物（Builder/Tester 写、Reviewer 只读）。
> 验证实验：TASK-SCHED-003（MCP 通道，142 passed）+ TASK-REAL-001（真实债务清偿，152 passed）。

**MCP 通道**（§8 详述）：`scripts/mcp_client.py` → `filesystem_mcp_server.py`（stdio JSON-RPC）；
工具 read_file / write_file / list_directory / create_directory / file_info；沙箱 = repo root，路径逃逸拒绝。

**真实场景边界约束（TASK-REAL-001 实测暴露，最高优先级）**：

| # | 约束 | 规则（必须遵守） | 实测教训 |
|:-:|------|------------------|----------|
| R1 | **真实任务 prompt 过大 → Builder READ 阶段截断** | **补丁语义而非探索语义**：子代理任务指令必须携带完整 diff / 精确锚点（锚点唯一性断言 count==1），禁止"读全部代码再设计"；需要探索时由 Coordinator 完成并注入 | v1 12 turns 0 writes（只读不写）→ v2 补丁语义恢复 |
| R2 | **mcp_client `\n` 转义损坏真实代码**（f-string 含字面 `\n`） | **JSON-RPC 直写而非 CLI 转义**：内容含 `\n` 字面量/复杂转义时，绕过 CLI 的 `\n`→换行替换，直接 JSON-RPC 发送原始 payload；或先 `file_info` 自证 + 立即重跑受影响测试 | check_policy.py f-string 被 `\n` 转义损坏 → 直接 JSON-RPC 重提交修复 |
| R3 | **Reviewer 在 verdict 写盘前截断** | **协调者兜底落盘**：Reviewer 截断时，Coordinator 按子代理 stdout 输出补全 verdict 落盘（标注"Coordinator 补全"），写后审协议优先于渠道纯净 | Reviewer 输出 OVERALL 但 verdict 仍是 PROVISIONAL skeleton（592B）→ Coordinator 补全（2080B） |
| R4 | **任务规模超单子代理单轮预算**（Builder/Tester 双双 token 截断 0 writes） | **规模拆分**：>6 锚点或 >1 大文件重写 → 拆分为多次 Spawn（每次 ≤6 锚点）或 Coordinator 直接兜底执行 + 标注"R4 兜底"；禁止让单子代理硬扛大任务 | REAL-002: Builder+Tester 双截断 → R3 兜底恢复；REAL-001: 单 Builder 截断 |
| R5 | **子代理将"不要调用工具"指令系统性误解为全局工具禁令**（S1 REAL-003 返回 BLOCKED 0 edits，但锚点验证完整） | **显式工具启用声明**：每个子代理 prompt 首行必须声明"TOOL CALLS ARE ENABLED AND REQUIRED. You MUST call Write/Edit. Do not return 'BLOCKED'."；"不要调用工具"类指令仅针对特定动作（如 Reviewer 禁止写源文件），必须限定范围 | REAL-003 S1: 12 turns BLOCKED 0 writes → Coordinator R3 兜底；S3 加声明后 14 turns 完成 3 文件全部编辑 |
| R6 | **迁移私有符号时遗漏非测试消费者**（policy_sync.py 经 AST 读 `DANGEROUS_PREFIXES`，常量迁走 → GATE 7 假漂移） | **迁移前枚举全部消费者**：Coordinator 在拆解任务时 Grep 目标符号全仓引用（含 scripts/、非测试代码），全部纳入迁移范围；迁移后跑消费者自身的验证命令（如 policy_sync 门） | REAL-003: DEBT-0002 迁移 `_is_dangerous` → 仅 grep 到 tests+examples，漏 AST 消费者 policy_sync → verify 阶段 GATE 7 险误报 → 补 R6 扫描迁移 |

**恢复流程（真实任务专用）**：
- 子代理截断 → Coordinator 检查落盘产物（file_info）：
  - 产物缺失 + 任务规模 >6 锚点/1 大文件 → **R4 拆分**：拆成多次 Spawn（每次 ≤6 锚点）
  或 Coordinator 兜底执行（应用子代理已确认的锚点设计 + 标注"R4 兜底"）
- 产物缺失 + 任务规模小 → 用**补丁语义**重建（注入完整 diff + 锚点，禁止重新探索）
  - 产物存在但 incomplete → 接受现状 + 标注，或按 stdout 补全（仅 Reviewer verdict）
- 每轮 MCP 写入后必须 `file_info` 自证大小（防截断丢失）

### 2.5 调度层第一阶段：自动接力循环（v0.2.2+，AUDIT-0010）

> **目标**：Builder → Reviewer 接力由 Coordinator **自动驱动**，用户零介入。
> 验证实验：TASK-SCHED-001（Builder 写 src/time_utils.py + tests → Reviewer 独立审查 → PASS，1 轮完成）。

**架构约束（实测确认，勿违反）**：
1. Spawn schema 明确禁止 "shared state or sequential coordination" → **子代理之间无法互相对话/嵌套 Spawn**
2. 协调永远是 Coordinator（主代理）职责 → "自动接力" = Coordinator 在单次会话内连续执行 Builder→Reviewer→(修复→复审) 循环，直到 PASS 或达 MAX_ROUNDS
3. 共享上下文 = **工作区文件系统**（work/<TASK_ID>/ 是接力总线）

**状态机**（.aionui/scheduler/relay_state.json）：
- Coordinator 创建任务时初始化；每轮 Builder/Reviewer 完成后追加 history；终态 DONE_PASS / DONE_REJECT
- 字段: task_id / status / round / max_rounds / builder_output / reviewer_verdict / history[]

**接力循环**：
`
BUILD(n) → 验证产物落盘 → REVIEW(n) → 读 verdict
  ├─ PASS  → 终态 DONE_PASS（可提交）
  ├─ REJECT → BUILD(n+1)（把 verdict 的 Required fixes 原样传入 Builder）→ REVIEW(n+1)
  └─ n >= MAX_ROUNDS → DONE_REJECT（升级人工）
`

**关键教训（TASK-SCHED-001 实测）**：
1. **先落盘原则**：Reviewer v1 被 Spawn 截断（2 turns）导致 verdict 未写入 → 接力中断。
   修正：Reviewer prompt 强制 "STEP 3 = 立即写 verdict 文件，即使有未决疑点"，深查在落盘之后。
   所有**关键产物**（verdict、报告）必须"先落盘、后完善"，不得依赖子代理完整跑完。
2. **Builder 必须自证**：测试命令 + 真实输出写在 builder_output.md，Reviewer 独立重跑验证（防口头通过）。
3. **断言 vs 产物**：接力判断只认落盘文件（verdict 存在且首行含 PASS/REJECT），不认子代理的 stdout 摘要。
4. **协调者兜底落盘（TASK-REAL-001 新增）**：Reviewer（或任何子代理）在 verdict 写盘前被截断时，
   Coordinator 必须按其 stdout 输出**补全 verdict 落盘**，并标注「Coordinator 补全（子代理截断）」。
   写后审协议优先于渠道纯净——接力判断只认落盘文件，不认 stdout，但落盘内容可以来自 stdout（带标注）。

**文件分配**（防撞车，沿用 §2.2）：
- Builder 写 src/、	ests/（≤2 文件）+ work/<TASK>/builder_output.md
- Reviewer 只写 work/<TASK>/reviewer_verdict.md（其余全只读）
## 三、协作协议

### 3.1 Coordinator 验证铁律

| 铁律 | 说明 |
|------|------|
| **不可信任子代理的自报结果** | 子代理说"测试通过"不等于测试通过。Coordinator 必须自己跑 `pytest -q` |
| **不可跳过 Reviewer** | 任何代码变更必须经过独立 Reviewer 审查 |
| **不可并行分配冲突文件** | 同一文件只允许一个 Builder 写（见文件分配表） |
| **GATE 未过不提交** | 4 门控任何一个失败 → 打回重做 |

### 3.2 冲突解决

如果两个 Builder 修改同一文件（分配表被违反）：
1. Coordinator 标记冲突。
2. 保留较早提交的变更，通知后提交的 Builder 基于最新版本重做。
3. 如果无法合并，放弃该文件的最新变更，仅保留经 Reviewer 通过的部分。

### 3.3 失败处理

| 失败类型 | 处理方式 |
|----------|----------|
| 单代理超时 (>5min) | Coordinator 重新分配同任务给新代理 |
| 子代理输出被截断 | 要求重跑，输出 ≤100 行 |
| 子代理假报"测试通过" | Coordinator 自己跑测试发现 → 标记该代理不可信，下次换新代理 |
| Reviewer REJECT | 分配回原 Builder 重做（新 Spawn 阶段 1） |
| GATE 失败 | Coordinator 直接修复（小问题）或分配 Builder（大问题） |

---

## 四、与现有协议的集成

```
Teams 协作协议 ← 本协议
    │
    ├── 触发条件:
    │   - 用户说 "用团队模式" / "@team start"
    │   - 任务涉及 3+ 文件修改
    │   - 需要并行审查
    │
    ├── 上游依赖:
    │   - 主治医师健康诊断 (每次会话启动)
    │   - CI 四门控 (每次提交前)
    │
    └── 下游输出:
        - Archivist → CHANGELOG.md
        - Archivist → .aionui/audit_log.md
        - Reviewer → CRITIQUE_V*.md (如有发现)
```

---

## 五、Coordinator 启动序列

当主代理以 Coordinator 角色启动 Teams 协作时，执行以下序列：

```
1. 主治医师健康诊断
   └── 输出当前项目健康度 → 决定优先处理的风险

2. 任务拆解
   └── 按粒度限制 (<2 files/<5 dims) 拆解待办任务
   └── 生成文件分配表（防撞车）

3. 阶段 1: 并行执行（Spawn #1）
   └── Builder/Tester 并行，最多 3 个，超时 5min

4. Coordinator 验证层（不可跳过）
   ├── git diff 检查
   ├── python -m pytest tests/ -q
   └── python scripts/check_test_quality.py

5. 阶段 2: 独立审查（Spawn #2）
   └── Reviewer 读最终文件，输出 PASS/REJECT

6. 汇总与提交
   ├── 通过 → git add + commit + push
   ├── REJECT → 回步骤 3（新 Spawn 重做）
   └── 记录 → Archivist 写入 CHANGELOG + audit_log
```

---

## 六、快速启动命令

| 命令 | 效果 |
|------|------|
| `@team start` | 启动 Teams 协作模式（执行启动序列） |
| `@team review <文件>` | 派 Reviewer 审查指定文件（阶段 2） |
| `@team build <任务描述>` | 派 Builder 实现功能（阶段 1） |
| `@team test <模块名>` | 派 Tester 补测试（阶段 1） |
| `@team status` | Coordinator 输出团队当前状态 |
| `@team handoff` | 输出交接块到 `.aionui/teams/handoff_YYYYMMDD.md`，供下一个会话续接 |

---

## 七、工作空间约定

| 位置 | 用途 |
|------|------|
| `.aionui/teams/` | 团队运行状态、handoff 文件 |
| `.aionui/teams/handoff_YYYYMMDD.md` | 每日交接块（`@team handoff` 写入） |
| `.aionui/audit_log.md` | 审查记录（永久保留） |
| `CHANGELOG.md` | 版本记录（Archivist 维护） |

---

*本协议由 agent-governance v2 实验生成。v1.0 于 2026-08-03 首版，v2.0 修正"子代理无法互相通信"架构缺陷后升级。*
*每次 Spawn 实验后更新粒度限制参数。*




## 八、MCP 工具共享（阶段 3，TASK-SCHED-003）

**目标**: 子代理经统一 MCP 共享通道交换 artifact（Builder/Tester 写，Reviewer 读），
不再依赖"各自写文件 + Coordinator 代读"的间接模式。

### 8.1 通道
- 服务器: `filesystem_mcp_server.py`（BottleSumo 平台 stdio MCP 服务器，JSON-RPC 2.0，JSON-lines framing）
- 客户端 CLI: `scripts/mcp_client.py`（`tools` / `call <tool> k=v...`；`\n` → 换行；exit 0/1/2）
- 沙箱: `BOTTLESUMO_ROOT` env var 设根；路径逃逸拒绝（"Access denied: path escapes project root"）
- 工具集: `read_file` / `write_file` / `list_directory` / `create_directory` / `file_info`

### 8.2 纪律（写后审 + 自证）
1. **写后审优先**: 子代理先经 MCP 写入 artifact（verdict/report/源码），再深入审查；中继只判断已落盘文件
2. **每轮自证**: 每次 MCP 写后立即 `file_info` 核对大小（防截断丢失；本轮 1425/1500/2872/3185 全匹配）
3. **Reviewer 只读 MCP**: Reviewer 禁止原生 Read，只能 read_file/file_info；本轮 8/8 读取 OK
4. **单 argv 传递**: PowerShell 下内容含双引号会拆分命令 → 用 Python subprocess 传单 argv（helper 脚本）

### 8.3 并行分歧裁决先例
Tester 对契约严格解释（remaining() 也校验空键）vs Builder 宽松实现 → **测试优先**（契约原文 + 纵深防御）。
裁决记录在 relay_state.json history。

### 8.4 已知限制
- mcp_client cp950 codec 读取带 BOM 的 UTF-8 文件失败（仅客户端显示问题；服务器正常）—— 客户端应强制 UTF-8
- 子代理可能"声称写入但未落盘"（截断）→ 必须 file_info 自证，缺失即重建
