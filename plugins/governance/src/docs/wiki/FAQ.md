# FAQ

常见问题解答。

## Q1: agent-governance 是什么？

一个 **Sidecar 治理网关**：为任何 AI Agent 提供"元认知、自演进、安全边界"三大能力，Agent 代码零修改。用 Agent 治理 Agent，让治理框架治理自身。

## Q2: 需要修改我的 Agent 代码吗？

**不需要。** Sidecar 模式：Agent 的请求经网关拦截/判定/转发。唯一要求是请求通过网关（改 base_url 或代理地址）。

## Q3: "零正则" AST 硬阻断是什么意思？

v1.25.0 起，请求体中的代码片段（Python/Bash/SQL）由 **Tree-sitter AST**（真正的语法树）分析危险模式，查询文件是 S-expression（`queries/*.scm`），不用手写正则解析代码。正则仅作为查询谓词做模式筛选（tree-sitter 0.21.3 的 `#match?`），AST 解析始终由 tree-sitter 完成。

## Q4: 为什么依赖锁定 tree-sitter==0.21.3？

依赖考古结论：tree-sitter 0.25+ **移除**了 Query 匹配 API（`captures`/`matches`）；0.22-0.24 与 tree-sitter-languages 聚合包的双参 `Language` 不兼容；SQL grammar 的 ABI 15 版本需要 0.25+ 核心。0.21.3 + tree-sitter-languages 1.5.0 是唯一全语言（python/bash/sql）可用的组合。

## Q5: 测试数量怎么从 488 涨到 574？

574 = 基线 + 历次新增（P12/P13/Meta-Harness/安全层/AST 引擎 32 个等）。每次新增功能都附带测试，Critic-Test T1 守护断言质量。

## Q6: 有 2 个测试偶尔失败？

`test_revoke` / `test_semantic_hook` 在本地偶发 mock 连接超时（`127.0.0.1` mock 端口被本地代理干扰），CI 环境通常自愈。已记录在审计日志，不属于逻辑回归。

## Q7: 如何确保 AST 前门不误伤正常请求？

- 提取器（`payload_extractor.py`）只提取有语言提示的字段（如 `{"language": "python", "code": ...}`），纯文本 prompt 不受影响
- 无代码请求 100% 走原 YAML 路径（Authorization passthrough，隔离测试覆盖）
- 逃生舱 `AG_AST_DISABLE=1`（生产不推荐）

## Q8: 决策记录能审计吗？

能。所有判定写入 SQLite `DecisionRecord`（含 verdict/reason/rationale/trace_id），`/v1/decisions` 查询，`/v1/trace/{id}` 看因果链，治理头带 HMAC 签名防伪造。

## Q9: 支持哪些语言协议？

HTTP + JSON。Agent 可通过 OpenAI 兼容接口（`/v1/chat/completions`）接入。

## Q10: 项目自举是什么意思？

本项目由 agent-governance 框架**治理自身**：代码评审（Critic）、测试、审计日志、快照、Meta-Binding（ED25519 签名绑定，AUDIT-0044）全部用框架自身能力完成。见 `docs/META_BINDING.md`。

## Q11: 如何贡献？

看 [Contributing](Contributing) + 认领 Good First Issues（Docker 支持 / 性能基准 / OpenAPI 文档）。

## Q12: 遇到问题去哪报告？

- Bug → Issues（用模板）
- 安全漏洞 → SECURITY.md 流程（私有报告，不要公开）
- 讨论 → Discussions
