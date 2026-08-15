# Releases

版本历史 + 变更日志（与 README 版本历史段同源，详细版）。

## v1.25.0（2026-08-03）— Tree-sitter AST 硬阻断引擎

**AUDIT-0046**。Priority 0 前门：AST block 先于一切 YAML 规则匹配。

- `src/ast_guard.py`：P1 Capture 校验（未知捕获忽略并记录）/ P2 payload_extractor 提取 / P3 命令表仅存 .scm 零硬编码；fail-closed 启动（查询缺失/损坏拒绝启动）
- `src/payload_extractor.py`：代码片段提取（语言提示字段 + 父键名映射 + 防 DoS 上限）
- `queries/{python,bash,sql}.scm`：S-expression 危险模式（零正则）
- `src/policy.py`：`_ast_gate` 集成（evaluate 首行）；`src/main.py` 注入 + `AG_AST_DISABLE=1` 逃生舱
- 依赖锁定：`tree-sitter==0.21.3` + `tree-sitter-languages==1.5.0`
- 测试：**574 passed**（+32）；GATE 8 5/5 PASS
- 修复 Critic：T1（测试裸 assert）、D2（main.py v1.13.0 注释版本 → README 条目）

## v1.24.0（2026-08-03）— 社区标准合规补全

**AUDIT-0045**。13 项开源社区标准核查全闭合，成为"模范开源项目"。

- CODE_OF_CONDUCT.md（Contributor Covenant 2.1）
- SECURITY.md（24h 响应 / 7d 初评 / 30d 补丁 + 私钥事件披露）
- .github/ISSUE_TEMPLATE/（bug_report + feature_request，needs-triage）
- .github/PULL_REQUEST_TEMPLATE.md（检查清单 + ED25519 签名项）
- .github/dependabot.yml（pip + github-actions weekly）
- .github/workflows/codeql.yml（代码扫描）
- README 3 社区徽章 + v1.13.0 基线条目
- 测试：542 passed

## v1.23.0（2026-08-03）— P13 认证授权层

**AUDIT-0043**。`src/auth.py` + `config/tenants.yaml` + main.py 中间件。

- Bearer + X-API-Key 双头认证，常量时间比较，fail-closed
- 租户隔离（tenant_id 贯穿决策链）
- 测试：531 passed

## v1.22.0（2026-08-03）— 安全 + P3 Meta 层

**AUDIT-0042**。8 层安全框架 + 6 P3 元认知模块；14 层审计 67.4/100；28 调度器执行器；20/42 meta-layer（47.6%）；P0-P3 全完成。

## v1.21.0（2026-08-03）— P12 Bootstrap 运行时

**AUDIT-0041**。确定性调度器（传感器→诊断器→部署器→调度器）+ bootstrap_state.db + codegen 漂移检测 + 白名单提交。

## v1.20.0（2026-08-03）— Meta-Harness + 元编程声明

> **⚠️ 更正（AUDIT-0059, 2026-08-04）**：本行"Meta-Scheduler（6 层总线 + 优先级队列 + 无锁 + 心跳）"为 **BottleSumo v11.20 内容污染**——本仓库 src/ 无 `meta_scheduler.py`（仅有 src/task_scheduler.py 与 src/bootstrap/scheduler.py, 后者为 P12 确定性调度器）。"因果 + 晋升"亦非本仓库 adapter 能力（src/meta_harness/adapter.py 为确定性 DENY 扫描 + 3 层门控）。原文保留作审计轨迹。核查见 docs/meta_harness_verification.md §文档-源码漂移。

**AUDIT-0040**。Meta-Harness 适配器（3 层门控 + 帕累托 + 因果 + 晋升）+ Meta-Scheduler（6 层总线 + 优先级队列 + 无锁 + 心跳）；docs/META_CAPABILITIES.md 7 项诚实声明（✅×5 ⚠️×2）；488 tests。

## v1.13.0 基线（P6 认证层前置）

**历史基线**。五层架构闭环后、P13 认证授权层引入前的稳定基线——`auth=None` 兼容模式（直接放行）。此条目为 main.py 历史版本引用的一致性记录。

## v0.6.0（TASK-REAL-012）— Context Hook HMAC

治理头防伪造：X-Trace-ID/X-Parent-Span-ID/X-Span-ID 以 HMAC-SHA256 签名（±300s 防重放窗）；伪造头 fail-safe 降级为孤立链根。五层架构 L1-L5 闭环。

## v0.5.0 — Trace 因果链

决策追踪 + Trace CTE 递归查询。

## v0.4.0 — 核心网关

Sidecar 代理 + YAML 策略引擎 + json_path 条件 + SQLite 审计。

---

**版本链规则**：每个版本必须 README ↔ TRIPLE_LOOP_SNAPSHOT.md ↔ main.py ↔ ci.yml GATE 7 四端一致，且审计日志有 AUDIT-00XX 记录。
