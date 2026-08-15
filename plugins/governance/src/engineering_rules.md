# Engineering Rules (GOV-EVOLVE 维护)

## GOV-001: 拦截路径双轨验证

**规则**: 验证策略拦截时必须同时走两条生产路径：
1. 引擎直测（`PolicyEngine.evaluate(path, method, body)` — benchmark 路径）
2. HTTP 全链路（`/v1/chat/completions` — 网关路径）

**理由**: GOV Round 1 发现 `mkfs.ext4` 在两条路径上路由不同规则
（script 字段 → AST 门；tools 声明 → block-shell-tool json_pattern），
只看一条路径会误判为"缺口"。两条路径都是有效拦截链。

**触发条件**: 任何"发现拦截缺口"的假设在落盘前必须双轨验证。

## GOV-002: 候选描述基于实测证据

**规则**: 策略候选的 gap 描述必须附 AST 证据（sexp）+ 裁决结果，
假设验证失败须创建"诚实修正"候选而非删除记录。

**理由**: Round 1 的 mkfs 缺口假设被实测推翻，修正候选
`4a46928dec_gov-r1-verify-mkfs-path` 保留了完整证据链。

## GOV-003: tool_lethality 语义评分

**规则**: 工具声明用 lethality 分档（bash=0.95 高威胁 → 拦截；
math_calculator=0.6 中 → 放行），AST 语义门零字符串匹配。

**理由**: Round 1 实弹验证 block-shell-tool 对 bash 工具声明 0.95 拦截，
对非 shell 工具放行，无字符串误报。
