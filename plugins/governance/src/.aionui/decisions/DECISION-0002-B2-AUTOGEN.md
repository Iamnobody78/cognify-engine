# DECISION-0002: B2 AutoGen 多 Agent 集成 —— 执行计划

- 日期: 2026-08-03
- 决策者: Meta Harness Proposer (lead) + 用户确认
- 状态: **已批准执行**

## 背景

B1 (LangChain) 已验证**单 Agent 场景**的零侵入宣称（commit 1828c68, AUDIT-0008）。
B2 验证 **AutoGen 多 Agent 场景** —— 这是"零侵入"宣称的最后一站：
单 Agent (LangChain) + 多 Agent (AutoGen) 覆盖后，主流框架证据链完整。

团队制基础设施已就绪：Hermes Leader 对话 ✅ + 治理规则注入 ✅（flash 模型修复后）。
`team members` CLI 回传失败 / aionrs teammate 启动失败 是 AionUi 限制，**不阻塞 B2**
（用文件交接 + Spawn 补足审查环节）。

## 核心目标

1. **零侵入验证（多 Agent）**：AutoGen GroupChat 只设 `base_url=网关/v1`，
   AST 证明 0 个 gateway import —— 网关对 AutoGen 完全透明
2. **声明级拦截（多 Agent 场景）**：任一 Agent 声明危险工具 → 网关 403 DENY，
   upstream 0 次调用（验证 B1 发现 2 在多 Agent 对话流中依然成立）
3. **多 Agent 对话转发**：安全 GroupChat（多 Agent 互相对话）经网关 ALLOW 转发
4. **决策入库**：多 Agent 会话的 ALLOW/DENY 全部落库，可审计

## 技术选型

| 项 | 选择 | 理由 |
|----|------|------|
| SDK | `autogen-agentchat 0.7.5`（新 API） | 官方推荐新一代；OpenAI 兼容 client 直接支持 `base_url`；与 B1 的 langchain 1.3 同代 |
| 版本 | 0.7.5 | pip 可用，Python 3.13 兼容（dry-run 通过），依赖与现有环境无冲突 |
| venv | 新建 `.venv-b2` | 与 `.venv-b1` 隔离，避免 langchain/pydantic 依赖纠缠 |
| 对话拓扑 | GroupChat + RoundRobinGroupChat | 多 Agent 互相对话的典型形态 |
| 危险工具 | `delete_file`（复用 B1 黑名单） | 与 B1 对照，验证同一治理策略跨框架生效 |

## 交付物（6 个文件）

| # | 文件 | 内容 |
|---|------|------|
| 1 | `examples/autogen_groupchat.py` | AutoGen 多 Agent 示例（零侵入，0 个 gateway import） |
| 2 | `tests/test_integration_autogen.py` | ~12 个测试（AST 零侵入 / 工具解析 / GroupChat 端点 / 持久化） |
| 3 | `scripts/b2_e2e.py` | 真实 AutoGen SDK 端到端（venv-b2 运行） |
| 4 | `EXPERIMENT_B_REPORT.md` | 追加 B2 章节 |
| 5 | `.aionui/audit_log.md` | AUDIT-0009（含 Spawn Reviewer 循环） |
| 6 | `.aionui/handoffs/HANDOFF-0009.md` | 会话交接 |

## 验收标准（Gate）

1. **零侵入 AST**：`examples/autogen_groupchat.py` 0 个 gateway import（测试断言）
2. **唯一集成点**：仅 `base_url` 引用网关，不调用 `/v1/intercept`
3. **多 Agent ALLOW**：安全 GroupChat（≥2 Agent 对话）→ 200 + stub 回复返回
4. **多 Agent DENY**：任一 Agent 声明 `delete_file` → 403，upstream 0 调用
5. **决策入库**：ALLOW + DENY 各 ≥1 条可查
6. **回归**：B1 75 测试 + B2 新测试全绿；GATE 1-7 全过；health_score ≥ 90
7. **团队化审查**：Builder → Coordinator → Spawn Reviewer 两阶段验证（复用 B1 协议），
   Reviewer REJECT 的漏洞必须修复后再 PASS

## 时间线（预计 60-90 分钟）

| 阶段 | 动作 | 预计 |
|:---:|------|:---:|
| 1 | 创建 `.venv-b2` + 安装 autogen-agentchat 0.7.5 | 10 min |
| 2 | 写 `examples/autogen_groupchat.py`（零侵入）+ 冒烟验证 | 15 min |
| 3 | 写 `tests/test_integration_autogen.py`（~12 测试） | 20 min |
| 4 | 真实 SDK E2E `scripts/b2_e2e.py`（venv-b2） | 15 min |
| 5 | **Spawn Reviewer 独立审查**（REJECT→修复→PASS） | 15 min |
| 6 | 全量回归 + GATE 1-7 + 文档/审计/交接 + commit | 15 min |

## 执行日志

### 阶段 1（完成）：venv-b2 + AutoGen 安装 ✅
- `.venv-b2` 创建，Python 3.13 兼容
- `autogen-agentchat==0.7.5` + `autogen-ext[openai]==0.7.5`（扩展需单独装）
- 冒烟通过：`OpenAIChatCompletionClient` 支持 `base_url`，底层 client 指向网关 `/v1/`
- 前置知识：`model_info` 需含 `structured_output` 字段（0.7.5 要求）；client 惰性初始化

### 阶段 2（完成）：零侵入示例 + 冒烟测试 ✅
- `examples/autogen_groupchat.py`（125 行）：RoundRobinGroupChat（proposer + executor 双 Agent）
- AST 验证：0 个 gateway import，仅 `base_url` 引用网关，无 `/v1/intercept`
- 冒烟通过：`build_groupchat` safe/dangerous 两形态都构造成功
- 关键确认：executor 的 `tools=[delete_file]` 由 AutoGen 自动生成 OpenAI function schema
  → B1 的 `_extract_tool_names` 应可直接解析（阶段 3 验证）

### 阶段 3（完成）：集成测试 ✅
- `tests/test_integration_autogen.py`（3 组 12 测试）：
  - G1 AST 零侵入 ×3（0 gateway import / 仅 base_url / 无 /v1/intercept）
  - G2 网关解析器 vs AutoGen schema ×5（get_time / async / delete_file / 空 tools / FunctionTool 无干扰）
  - G3 真实网关端点 ×4（safe ALLOW / dangerous DENY 403 + upstream 0 调用 / 决策入库 / **真实 AutoGen GroupChat e2e 往返**）
- 验证：系统 Python 86 passed + 1 skipped（e2e 无 AutoGen 自动跳过）；venv-b2 87 passed（e2e 真实执行）
- **团队化纠错**：用户提交的初版测试从 examples 导入 `_extract_tool_names`（函数不存在 + 会破坏零侵入）
  → 改为从 `src.main` 导入解析器（与 B1 测试模式一致）——示例文件保持纯 AutoGen SDK
- 关键确认：AutoGen 的 tools JSON 与 OpenAI 兼容端点**格式一致**，B1 的解析器零修改直接拦截

### 阶段 4（完成）：真实 SDK E2E `scripts/b2_e2e.py` ✅
- **真实 AutoGen GroupChat 全链路**（venv-b2 + autogen-agentchat 0.7.5 + 真实网关 + stub upstream）：
  - SAFE GroupChat（executor tools=[get_time]）：4 轮多 agent 全 ALLOW 转发 → `SAFE GROUPCHAT FINAL: stub: ...`
  - DANGEROUS GroupChat（executor tools=[get_time, delete_file]）：executor 声明 `delete_file` → 网关 403 `PermissionDeniedError`，GroupChat 正常抛出
  - 持久化：`PERSISTED: 6 decisions (5 ALLOW, 1 DENY; 1 delete_file DENY)`
  - 结论：`B2 E2E PASS: multi-agent safe→ALLOW, dangerous→DENY, both persisted`（exit 0）
- **调试教训（重要）**：初版断言 `upstream_after_danger == upstream_before_danger` 是**错误预期**——
  RoundRobinGroupChat 中 proposer 首轮无工具 → 合法 ALLOW 转发（+1 请求），executor 轮才被 DENY。
  网关实际一直正确拦截；误报来自测试断言而非治理缺陷。
  修复：断言改为 (i) 危险聊天确实抛 403，(ii) 携带 `delete_file` 的声明 0 次到达 upstream，
  (iii) DENY 决策入库。另压制 AutoGen 对每个被拒消息打印的巨型 traceback（`autogen_core` logger CRITICAL）。
- 附：`_dbg_gateway_codes.py` 用 AutoGen 真实 body 形状（含 `strict:false` 附加字段）直连网关 → 403 + upstream 0 调用，
  证明解析器对 AutoGen schema 的附加字段零修改正确处理。

## 风险与绕过

| 风险 | 应对 |
|------|------|
| AutoGen 0.7.5 的 tool 声明格式与 OpenAI 兼容端点有差异 | 先冒烟验证 `_extract_tool_names` 能否解析 AutoGen 的 tools JSON；不行则扩展解析 |
| GroupChat 轮次多导致测试慢 | 测试设 `max_turns` 小值；e2e 用 `asyncio.to_thread`（B1 已学） |
| AutoGen 需要真实 LLM 才产生 tool_calls | 用 stub LLM 返回带 tool_calls 的固定响应（B1 已有 stub 基础设施） |
| `team members` 工具问题再次干扰 | 团队制仅用 Hermes 对话 + 文件交接，不依赖 CLI 工具 |

## 完成后决策点

B2 交付后：
- **B3 混合模式**（LangChain + AutoGen 同网关）—— 若 B2 顺利
- **团队制剩余问题修复**（team members CLI / aionrs teammate）—— 仅当 B2 过程中必须用时
