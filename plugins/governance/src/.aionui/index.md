# Agent Governance v2 — 全仓文件索引

> 会话启动时 Glob 扫描并更新此文件（防跨对话文件丢失）。
> 规则：新文件必须登记；找不到文件先查此索引，再查 git log。

## 核心代码

| 路径 | 职责 | 测试 |
|------|------|------|
| `src/main.py` | Sidecar 网关：/v1/intercept + OpenAI 兼容端点 + 熔断器 + /v1/trace 递归 CTE | tests/test_intercept.py、tests/test_trace.py |
| `src/policy.py` | YAML 策略引擎（normpath + json_path 条件规则） | tests/test_json_path_policy.py |
| `src/storage.py` | SQLite 持久化（decisions 表 13 列 + _migrate 无损迁移 + get_trace） | tests/test_trace.py、tests/test_governance_brain.py |
| `src/models.py` | Pydantic 模型（强类型，Verdict 五级 ALLOW/ALLOW_WITH_WARNING/ESCALATE/DENY/SUSPEND + DecisionRecord.rationale） | tests/test_models_types.py、tests/test_governance_brain.py |
| `src/norm.py` | 规范化单一来源（NFKC→confusable→casefold） | tests/test_json_path_policy.py |
| `src/lethality.py` | Ls 工具致死性表（审计用） | tests/test_json_path_policy.py |
| `src/critic/` | 批判者代理团队（GATE 8：audit/security/arch/test/docs + verdict + runner） | tests/test_critic.py |
| `src/context_hmac.py` | Context Hook HMAC（治理头签名防伪造，CONTEXT_HMAC_KEY 开关，Phase 5） | tests/test_hmac.py |
| `src/meta_harness/adapter.py` | Meta-Harness 轻量适配器（DENY 扫描→pending_rules 候选 YAML） | tests/test_meta_harness.py |
| `src/meta_harness/sandbox.py` | Meta-Harness 沙箱（conflict 检查 + pytest 回归 + 可逆部署） | tests/test_sandbox.py |

## CI 门控（8 个）

| GATE | 脚本 | 职责 |
|:---:|------|------|
| 1 | `scripts/check_test_quality.py` | 无 dataclass 断言（AST） |
| 2 | `scripts/check_test_quality.py` | 测试数 ≤50（GATE2-APPROVED 豁免） |
| 3 | `scripts/check_policy.py` | 无硬编码策略（AST） |
| 4 | pytest + coverage | 测试全绿 + 覆盖率 ≥60% |
| 5 | `examples/policy_probe.py` | 策略一致性（action 白名单 + 孤儿前缀） |
| 6 | `scripts/meta_security_scanner.py` | 安全反模式（熔断放行/超时放行/静默吞异常/startswith） |
| 7 | `scripts/policy_sync.py` | 代码-策略漂移（DENY+ESCALATE 覆盖 + action 原始值校验） |
| 8 | `src/critic/runner.py` | 动态语义门控（5 批判者 + 一票否决/多数通过裁决） |

## 工具脚本

| 路径 | 职责 |
|------|------|
| `scripts/health_score.py` | 每日健康评分（4 门控实测 → 0-100） |
| `examples/echo_agent.py` | 零侵入验证 Agent |
| `examples/policy_probe.py` | 策略一致性工具（供 GATE 5） |

## 文档

| 路径 | 职责 |
|------|------|
| `README.md` | v2 蓝图（= ARCHITECTURE.md） |
| `CRITIQUE.md` | v1 批判（6 模块逐行验证） |
| `CRITIQUE_V2.md` | v2 自我审查 + AUDIT-0005 外部审查 |
| `EXPERIMENT_REPORT.md` | v1→v2 对照实验 |
| `docs/json_path_governance_report.md` | B 阶段 json_path 工具治理报告 |
| `docs/trace_report.md` | C 阶段 Trace 因果追踪报告 |
| `.aionui/audit_log.md` | 审计日志（AUDIT-0001~0029） |
| `.aionui/critic_report.md` | GATE 8 批判报告（每次运行覆盖） |
| `.aionui/protocols/teams_collaboration.md` | 两阶段 Spawn 协议 |
| `.aionui/protocols/pr_review_loop.md` | PR 审查闭环 |
| `.aionui/protocols/critic_team.md` | 批判者代理团队协议（GATE 8 元提示词） |
| `.aionui/protocols/self_evolution_protocol.md` | 自进化治理引擎执行协议（Phase 1-5 路线图 + 防伪造铁律） |
| `.aionui/protocols/reviewer_prompt_template.md` | 审查提示词模板 |

## 协议文件（团队协作契约）

| 路径 | 职责 |
|------|------|
| `.aionui/handoffs/` | 会话交接记录（最新在前） |
| `.aionui/decisions/` | 重大决策归档 |
| `.aionui/failures/` | 失败归档（bug/CI 失败） |
| `debt_registry.md` | 债务登记（0 阻塞目标） |
| `.aionui/memory/` | 项目记忆（跨会话持久） |
