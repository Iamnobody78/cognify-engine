# examples/ — 治理引擎示例

> 目的：证明 `agent-governance` 可迁移治理**任意外部 Agent**——不是声称，
> 而是可运行的代码 + 真实治理证据（DENY/ESCALATE 裁决 + trace_id 追踪链）。

## v2.0 治理闭环示例（S63-S69，推荐优先看）

| 文件 | 演示能力 | 运行命令 | 预期判定 |
|------|---------|---------|---------|
| `feynman_test_false_claim.py` | **S66 谎报缓解**——裸 `satisfied` 声明 → 验证通道降级 `ESCALATE` (c=0.6)；带证据锚点 → 放行；矛盾声明 → 伦理 `DENY` | `python examples/feynman_test_false_claim.py` | PASS — 谎报被拦截 |
| `ethics_deny_demo.py` | 伦理边界 `DENY` 硬阻断——不依赖 satisfied 声明，验证通道平凡通过 | `python examples/ethics_deny_demo.py` | PASS — DENY 不受谎报通道影响 |
| `vce_scan_demo.py` | **S65 治理自审**——VCE 2.0 扫描（极化指数 / 冲突 / 盲点）+ MCE 自省 | `python examples/vce_scan_demo.py` | PASS — 扫描报告可生成 |

三个示例直接调用 `ProtocolGateway`（`src/protocol_gateway.py`），验证通道为
`BaselineDeclarationValidator`（baseline）。示例以 exit code 断言判定，可接入 CI。

## 外部代理接入示例（v1 时代，P9）

> 目的：证明 `agent-governance` 可迁移治理**任意外部 Agent**——不是声称，
> 而是可运行的代码 + 真实治理证据（DENY/ESCALATE 裁决 + trace_id 追踪链）。

## 三个示例 + 测试双翼

| 文件 | Agent 类型 | 接入方式 | 治理证据 |
|------|-----------|----------|----------|
| `external_agent_demo.py` | 通用 Python Agent | 进程内 `from src.agent_tools import ...` | `run_self_critic()` 结构化报告 + `get_self_trace()` 因果链 + `heal_candidate()` 修正建议 |
| `langchain_agent.py` | LangChain 生态 | **零侵入**——唯一网关引用 `ChatOpenAI(base_url=网关/v1)`，无内部模块 import | 真实 SDK 调用被网关 403 拦截（`PermissionDeniedError: governance_denied`）+ ALLOW/ESCALATE/DENY 裁决行 |
| `autogen_agent.py` | AutoGen 生态 | **零侵入**——`base_url=网关/v1`（模型客户端配置唯一网关引用） | ALLOW/ESCALATE/DENY 裁决行 + `trace_id` 追踪链 |
| `autogen_groupchat.py` | AutoGen 群聊库模块 | 零侵入 `base_url`（B2 契约文件，被 `tests/test_integration_autogen.py` 消费） | `build_groupchat(gateway_url, dangerous)` 构造经网关治理的群聊 |
| `_stub_llm.py` | 测试双（**非产品**） | 模拟上游 LLM（:8000） | 让 ALLOW 路径可端到端演示（网关转发目标） |

**零侵入定义（AC2/AC3）**：示例代码中**无** `import src.critic` / `src.storage`
等内部模块——Agent 只见网关 HTTP 契约（`POST /v1/chat/completions` 被动拦截），
治理完全由网关侧完成。既有契约测试 `tests/test_integration_langchain.py` /
`tests/test_integration_autogen.py` 用 AST 证明这一点（禁止 "src"/"gateway"/"main"
import；`base_url=` 是唯一网关引用；禁止主动 `/v1/intercept` 调用）。

外部依赖（langchain/autogen）为可选：已安装时走**真实 SDK 路径**（langchain
1.3.x / autogen-agentchat 0.7.x 实测）；未安装时自动降级为标准库 HTTP 客户端，
**协议一致、可运行、证据不缺失**（AST 契约测试只解析源码，从不导入模块）。

## 快速开始

```powershell
# Windows（原生 PowerShell runner：stub LLM :8000 + 网关 :9000 + 3 示例 + 证据校验）
powershell -ExecutionPolicy Bypass -File examples/run_examples.ps1

# Git Bash（等价 POSIX runner）
bash examples/run_examples.sh
```

手动方式（分步）：

```bash
# 1. 启动 stub LLM（ALLOW 路径的上游，:8000）与治理网关（:9000）
.venv-b2/Scripts/python.exe examples/_stub_llm.py &   # 需 aiohttp
.venv-b2/Scripts/python.exe -m src.main &             # 监听 :9000

# 2. 跑示例（真实 SDK 需要对应 venv：langchain → .venv-b1；其余 → .venv-b2）
.venv-b2/Scripts/python.exe examples/external_agent_demo.py
.venv-b1/Scripts/python.exe examples/langchain_agent.py   # .venv-b1 含 langchain
.venv-b2/Scripts/python.exe examples/autogen_agent.py     # .venv-b2 含 autogen
```

## 验证治理效果

每个示例输出含可验证裁决行，例如（真实输出节选）：

```
[SDK] create_agent(ChatOpenAI(base_url=http://127.0.0.1:9000/v1)) built: CompiledStateGraph
[SDK] real SDK call governed by gateway -> PermissionDeniedError: 403 governance_denied ['delete_file']
[ALLOW]    safe chat, no tools                  status=200 trace_id=3f2c… decision_id=…
[ESCALATE] tool: write_file (sensitive)         status=202 reason=匹配规则 'escalate-file-write-tool' → 升级 … trace_id=…
[DENY]     tool: delete_file (dangerous)        status=403 reason=LLM 请求声明危险工具调用 ['delete_file'] — 拒绝转发 trace_id=…
```

判定：`DENY` 出现 = 危险工具被阻断；`ESCALATE` 出现 = 敏感操作升级人工 =
治理生效。审计链可在网关 SQLite 中复核（`decisions` 表每条都有 decision_id
与 trace_id；`GET /v1/trace/{trace_id}` 返回因果链）。

## 接入成本（可迁移性证据）

| 场景 | 接入代码量 | 说明 |
|------|-----------|------|
| 通用 Python Agent | ≈0 行改动 | 同仓库直接 `from src.agent_tools import ...`；跨仓库用网关 HTTP |
| LangChain | 1 处配置 | `ChatOpenAI(base_url=...)` 指向网关 /v1，SDK 调用即被治理 |
| AutoGen | 1 处配置 | 模型客户端 `base_url` 指向网关 /v1，OpenAI 兼容流量即被治理 |

## 验收（AC1-AC6）

- AC1 `external_agent_demo.py` 调用 `self_critic()` ✅
- AC2/AC3 LangChain/AutoGen 零侵入（AST 契约证明 + 真实运行）✅
- AC4 每个示例触发 DENY/ESCALATE（runner 证据校验 PASS）✅
- AC5 全量测试 450 passed ✅
- AC6 快照 v1.18.0 ✅
