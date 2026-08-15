# ROADMAP — governance-gateway

> 状态基准:2026-08-03 · 维护者:meta-harness 双环治理
> 约定:✅ 已交付并验证 · 🔄 进行中 · 🎯 规划中(未承诺日期)

---

## 阶段 0 — 事实核查与硬验证 ✅

| 项目 | 状态 | 说明 |
|------|:----:|------|
| tree-sitter 依赖硬锁 | ✅ | `0.21.3` + `1.5.0`,dependabot ignore 已配 |
| SQL 语法四探针验证 | ✅ | `update_statement`/`where_clause` 节点确认;`#match?` 谓词作用域缺陷实证;S1/S2 修正设计验证 |
| 虚构节点清剿 | ✅ | `table_reference`/`field`/`relation` 不存在,已排除出设计 |
| 真实拦截率基准 | ✅ | 100% 检测 / 0% 误报(15+13 载荷矩阵) |
| 基线缺口修复 | ✅ | `mkfs.*` 变体 + 重定向敏感目标 2 缺口闭环 |

## 阶段 A — 项目定位与可读性 ✅

| 项目 | 状态 | 说明 |
|------|:----:|------|
| 真实 README.md | ✅ | 从架构叙事中剥离,成为项目首页 |
| 架构文档迁移 | ✅ | `docs/architecture_narrative.md`(git mv 保历史) |
| ROADMAP.md | ✅ | 本文档 |
| 拦截率数据落盘 | ✅ | `docs/interception_benchmark.json` + 复现脚本 |

## 阶段 B — 可视化与示例 ✅

| 项目 | 状态 | 说明 |
|------|:----:|------|
| `examples/demo_self_heal.py` | ✅ | 自愈链路演示:真实 Sense→Diagnose→Remediate 闭环(5 批判者 verdict / trace 链 / 沙箱冲突检测 / fail-closed 熔断) |
| `examples/browser_guard_demo.py` | ✅ | 浏览器防护演示:真实 ASTGuard+PolicyEngine,6 拦截 3 放行 |
| 徽章系统 | 🎯 | CI 状态 / 拦截率 / 版本徽章 |

## 阶段 C — 交付形态

### C1:容器化一键启动 ✅

| 项目 | 状态 | 说明 |
|------|:----:|------|
| `/metrics` 端点 | ✅ | 7 Prometheus gauge(uptime/decisions/escalations/breaker×2/ast_languages/pending_flush),`tests/test_metrics.py` |
| `Dockerfile` | ✅ | 多阶段构建,python:3.11-slim,tree-sitter 锁版,非 root,healthcheck |
| `docker-compose.yml` | ✅ | 网关 + Prometheus + Grafana 11.1.0,实机验证(health 200 / prom 200 / 容器内拦截生效) |

### C2:MCP 协议支持 🎯(MCP 平台化后置,独立里程碑)

| 项目 | 状态 | 说明 |
|------|:----:|------|
| MCP 服务注册 | 🎯 | 作为 MCP server 注册到 .aionui/mcp |
| 工具级治理 | 🎯 | MCP 工具调用纳入五层裁决 |

## 阶段 D — 工程完备性

| 项目 | 状态 | 说明 |
|------|:----:|------|
| Phase 1 SQL 规则 | ✅ | 已交付(AUDIT-0050,v1.27.0-sql):`update_stmt` 无 WHERE→DENY / 有 WHERE→ALLOW;`sensitive_schema` S1/S2/S3 三规则(信息_schema/pg_catalog/sqlite_master 等 8 库名);DROP DATABASE 语法边界诚实记录(YAML L2 兜底);AC1-AC5 全过,606 tests |
| Phase 2 Bash 深度规则 | 🎯 | 管道/命令替换/变量间接寻址等语义层 |
| Phase 3 Python 深度规则 | 🎯 | 类重绑定/装饰器逃逸/二进制协议等 |
| 许可证 | 🎯 | 选定 MIT/APACHE 并落实 LICENSE 文件 |
| CHANGELOG + 语义化版本 | 🎯 | Keep a Changelog 规范 |

## 元批判采纳项(2026-08-03 核查后)

### 已采纳-立即(本次已执行)
| 项目 | 说明 |
|------|------|
| 文档诚实化:L5 宣称修正 | ✅ architecture_narrative "完整 Harness 工程自动化" → "策略建议器 + 能力边界明确"(adapter 源码自证只读/仅 YAML) |
| 认证边界说明 | ✅ CERTIFICATION.md 补 ED25519 与 Git GPG 不兼容声明(项目内闭环,无 GitHub 徽章) |
| GATE 合并评估 → 执行 | ✅ 8 GATE → 3 核心 job(quality/policy/critic)+ all-gates;GATE 7 版本无关化;Semgrep 列为 backlog 候选 |
| bootstrap 因果链 → 执行 | ✅ Cycles 表新增 `repair_chain` JSON 列(problem→diagnosis→fix→verification);`auto_push=True` + 双环境变量门禁 |

### 已采纳-backlog(评估中)
| 项目 | 说明 |
|------|------|
| tree-sitter 迁移路径 | 文档化 0.22+/1.6+ 升级路径评估(批判: 锁死属实但为主动决策) |
| OTel 可观测性 | 从 /metrics 演进为 span 级决策链绑定(v2 候选) |

### 已裁决-暂不执行(方向性建议,避免重装备债务)
| 项目 | 理由 |
|------|------|
| OPA/Rego 替换自研 YAML | 哲学性重构;自研 YAML 零依赖+已验证 100%/0% 拦截;Rego 重装备(单机 PoC 过度) |
| DID/AIP 去中心化身份 | 多 Agent 生态场景才有价值;当前租户+API Key 够用 |
| 事务性沙箱 | 纵深防御合理但单机 PoC 价值有限;列为 v3 研究 |
| "砍掉 bootstrap 演示模式" | 反驳: auto_push=False 是**人类在环设计**非演示;文档已诚实声明能力边界 |

## 持续运行(每轮迭代)

| 项目 | 说明 |
|------|------|
| 拦截率回归 | 每次引擎改动跑 `scripts/benchmark_interception.py` |
| Meta-Harness 内环 | 胜率连续 3 轮下降 >10% → 自动生成 3 变体验证 |
| 审计日志 | 每次交付写 `.aionui/audit_log.md` |
| 依赖升级 | dependabot 已 ignore 破坏性 tree-sitter 升级 |

---

## 变更历史

| 日期 | 变更 |
|------|------|
| 2026-08-04 | v1.27.0-sql:Phase 1 SQL 规则交付(S1/S2/S3,AC1-AC5 ✅,606 tests)+ 嵌套容器绕过修复 + C1 容器化完成 + P0-1/P0-2/P1-1 诚实硬化 |
| 2026-08-03 | 基线:阶段 0 完成;阶段 A 完成(README/ROADMAP/数据/迁移);阶段 B 完成(自愈 + 浏览器防护双 demo);阶段 C1/C2/D 规划中 |
