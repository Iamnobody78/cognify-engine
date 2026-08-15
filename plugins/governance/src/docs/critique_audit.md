# 批判审计回应 — 实证、修复与诚实边界

- 日期: 2026-08-04
- 触发: 外部 7 点尖锐批判 + 确认审计(3 HIGH / 2 MEDIUM / 2 LOW)
- 状态: 3 HIGH 全部修复并回归验证; MEDIUM/LOW 部分处理,边界诚实声明
- 关联提交: (见 git log)

---

## 1. 实证: 批判方挑战的 Base64+eval 绕过

批判方原话: *"如果你不服,请用我上面给的 Base64 编码 + eval 跑一下你的网关,看看是不是轻松绕过。能过,那我的批判就全中。"*

探针脚本 `scripts/probe_base64_bypass.py` 保留为审计证据,直接运行可复现:

| # | 形态 | 修复前 | 修复后 |
|---|------|--------|--------|
| 1 | 批判方原始 payload: `base64.b64decode(...)` + `eval(user_input)` | **BLOCK** | BLOCK |
| 2 | 对照组: `eval('__import__("os").system("id")')` | BLOCK | BLOCK |
| 3 | `getattr(__builtins__, 'ev'+'al')` 别名 + 调用 | **PASS(绕过)** | PASS(见 §4 边界) |
| 4 | `__builtins__['e'+'val'](...)` 下标拼接 | **PASS(绕过)** | PASS(见 §4 边界) |
| 5 | `function_call.arguments` JSON 串内藏 `eval` | **PASS(绕过)** | **BLOCK** ✅ |
| 6 | `tool_calls[].function.arguments = {"command": "rm -rf /"}` | **PASS(绕过)** | **BLOCK** ✅ |

**诚实结论:**
- 批判方给出的**具体例子**(Base64 + 裸 `eval` 调用)恰好被旧规则阻断 —— `eval` 以裸 identifier 出现,命中模式 1。这一点批判方说错了。
- 但批判的**实质完全成立**:等价的别名/下标/工具参数形态轻松绕过。修复前 6 例中 4 例放行(含 2 个"工具参数盲区"高危)。
- 修复后:直接形态(3/4 的直接字符串版、5/6)全部阻断;拼接形态为静态不可判定边界(§4)。

## 2. 三项 HIGH 修复

### HIGH-2: AST 只看函数名 → 别名/下标形态补漏
- `queries/python.scm` 新增:
  - **模式 4** `@alias_exec`: `getattr(__builtins__|__builtin__|builtins, 'eval'|'exec'|'compile'|'__import__'|'input')` → `code-execution-alias`
  - **模式 5** `@sub_exec`: `__builtins__['eval'](...)` 下标调用 → `code-execution-subscript`
- `src/ast_guard.py` `EXPECTED_CAPTURES` 同步登记(表驱动,P1 校验自动覆盖)。
- 回归: `tests/test_ast_guard_bypass.py` 4 例别名/下标恶意 + 3 例良性对照(含 `getattr(obj,'eval_method')` 对象属性名含 eval 的合法形态,零误报)。

### HIGH-3: 工具参数治理盲区(最危险盲区)
- `src/payload_extractor.py`:
  - 新增 `_JSON_CONTAINER_KEYS = (arguments, tool_calls, function_call, parameters, tool_input, args)`
  - 新增 `_try_json_container()`: 容器键下 JSON 字符串先解析再递归,解析失败保持原"无提示跳过"语义(零误判)。
- 效果: `function_call.arguments` / `tool_calls[].function.arguments`(JSON 串或 dict 形态)内的 `code`/`command` 等键重新进入语言提示提取链。
- 回归: 3 例工具参数恶意 + 1 例良性。

### SQL WHERE 恒真(审计附带的语义漏洞)
- `queries/sql.scm` 新增 `@trivial_where`:
  - `WHERE 1=1` / `WHERE 1 = 1`(`binary_expression` + 双 `number` 恒等)
  - `WHERE TRUE`(关键字节点)
- 旧测试 `test_update_where_constant_true_allowed_by_grammar`(断言"恒真放行")**按修复目标重写**为 `..._blocked` —— 该测试正是旧漏洞行为的断言。
- 回归: 4 例恒真恶意 + 3 例有界良性。

## 3. HIGH-1: 统计把戏 → benchmark 样本扩充

| | 修复前 | 修复后 |
|---|--------|--------|
| 恶意样本 | 15 | **29**(+14: 别名/下标/工具参数/恒真 WHERE 绕过变体) |
| 良性样本 | 13 | **19**(+6: 别名/下标合法用法、有界 WHERE、良性工具参数) |
| 检测率 | 86.7% → 100% | **100%**(29/29) |
| 误报率 | 0% | **0%**(0/19) |
| 样本相关性 | 训练/测试同源相关 | 绕过变体独立注入,不再是同源变换 |

诚实声明: 29+19 仍是小样本,且恶意集与规则集同仓库演化(有监督同源风险未消除);统计上这是"规则对已知形态的回归测试",不能外推为"攻击者未知形态下的拦截率"。下一步方向见 §6。

## 4. 诚实边界(不修复的理由)

1. **字符串拼接形态**(实证 3/4): `getattr(__builtins__, 'ev'+'al')` / `__builtins__['e'+'val']` — 静态值不可判定(binary_operator),超出 tree-sitter 模式能力。已写入 scm 注释为 `documented bypass`。**任何基于语法匹配的守卫都无法根治**,需要数据流/常量折叠分析(§6)。
2. **Meta-Harness 只读顾问**: 批判正确 — `adapter.py` 是只读检索 + 建议,不自动修改主分支。这是**设计决策**(人类在环,裁决门),非缺陷;已在此文档声明,不改。
3. **orchestrator 加权平均投票**: 批判正确 — 当前是简单加权融合。深度集成(如不确定性加权、模型置信度门控)列入 backlog。
4. **性能**: ASTGuard 每次请求重新 parse。基准测试中 29 例 ~秒级,可接受;高吞吐场景需 LRU 缓存(backlog)。
5. **tree-sitter-sql 方言限制**: 仅覆盖标准 SQL 结构,MySQL/PostgreSQL 专有语法(如 `LIMIT` 变体、`ON CONFLICT`)不可解析 —— 未解析内容静默跳过,属 fail-open 风险,已在 L2 YAML 层兜底声明。
6. **Wiki 404 / Docker 镜像缺失**: 质量缺陷成立,已列入 backlog(与 P2 gpt-researcher 部署一起处理)。

## 5. MEDIUM/LOW 处置

| 项 | 处置 |
|----|------|
| Meta-Harness 只读(花瓶) | 已声明为设计决策(裁决门),文档化 |
| 性能(无缓存、同步 SQLite) | backlog: analyze LRU 缓存 + WAL 已部分落地 |
| 5 层架构 over-engineering | 部分成立: L1-L5 分层文档化,合并层会破坏现有契约测试,暂缓 |
| Wiki 404 / Docker | backlog 质量债(与 P2 部署脚本一并处理) |
| benchmark 硬编码路径 | 已确认脚本内相对路径,CI 环境一致,低风险 |

## 6. 下一步(按优先级)

1. **~~数据流分析(L2.5)~~ ✅ 已完成 (2026-08-04)**: `src/taint.py` — 字符串常量折叠
   (`'ev'+'al'`→`'eval'`) + 变量别名表 (`fn = getattr(__builtins__,'ev'+'al')` → fn↦builtins.eval)
   + 汇点检测 (`fn(payload)` 解析调用目标)。探针实证 3/4(拼接形态)**已由 PASS 翻转为 BLOCK**,
   探针 6/6 全 BLOCK。集成于 ASTGuard.analyze Python 分支(补强层, 失败静默不影响主判定)。
   测试: `tests/test_taint.py` 11 例(含良性零误报: 普通 getattr / 非 builtins 拼接 / mapping 下标)。
   诚实边界: 函数参数跨界流动/条件分支/属性链等复杂传播仍未覆盖(需完整数据流框架)。
2. **benchmark 独立语料**: 从真实攻击样本库(PoC-in-GitHub 数据集)提取跨仓库变体,切断"规则与样本同源"的相关性。
3. **L2 YAML 工具参数规则**: 工具名 + 参数结构(如 `run_shell.command`)的声明式策略,与 AST 层互为兜底。
4. **性能**: ASTGuard LRU 缓存(仅缓存 parse 树,findings 每次生成)。
5. **GitHub 手工设置 3 项** + Wiki 404 修复 + Docker compose 落地。
6. **路径 B MCP 封装 ✅ (2026-08-04)**: `run_research` 工具(gpt-researcher 子进程,
   scripts/p2_research_runner.py + research_mcp_server.py 扩展), 协议级 smoke 通过;
   待 DEEPSEEK_API_KEY 激活后真实验证。

## 7. 测试基线

- 新增回归: `tests/test_ast_guard_bypass.py` **18 例**(恶意 10 + 良性 8)
- 重写: `test_ast_guard_sql_update.py` 1 例(恒真 WHERE: 放行 → 阻断)
- 全量: 分批全绿(环境级慢,非回归; 见会话记录 ~760+ passed)
- benchmark: 29/29 检测, 0/19 误报, exit 0
