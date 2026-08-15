# Architecture

五层架构详解（与 `docs/architecture.md` 同源，Wiki 镜像）。

## 五层架构总览

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ L5: 自进化引擎 (Meta-Harness)                                              │
│     策略建议生成、沙箱验证、帕累托前沿搜索、因果推理                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ L4: 批判与审计层 (Critic Agent)                                            │
│     5 批判者 (Audit/Security/Arch/Test/Docs) + GATE 8 动态语义门控          │
├─────────────────────────────────────────────────────────────────────────────┤
│ L3: 治理大脑 (Governance Brain)                                            │
│     五级判定 + rationale 可解释 + HMAC Context Hook 防头伪造                │
├─────────────────────────────────────────────────────────────────────────────┤
│ L2: 核心网关 (Sidecar Proxy)                                               │
│     aiohttp + YAML 策略引擎 + json_path 条件 + Tree-sitter AST + SQLite 审计│
├─────────────────────────────────────────────────────────────────────────────┤
│ L1: 基础设施 (Infrastructure)                                              │
│     Teams 调度 + CI GATE 1-8 + 高可用文件锁 + ED25519 认证层                │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 请求处理流水线（L1 → L3）

1. **认证门（L1）**：Bearer / X-API-Key → tenant_id（fail-closed，常量时间比较）
2. **AST 前门（L2，Priority 0）**：请求体代码片段（python/bash/sql）过 Tree-sitter 查询，危险模式 → 直接 DENY（先于一切 YAML 规则）
3. **策略引擎（L2）**：YAML 规则 + json_path 条件匹配 → 五级判定
4. **治理大脑（L3）**：生成 verdict + rationale + DecisionRecord（SQLite 落库）
5. **Context Hook（L3）**：治理头 HMAC 签名（X-Governance-Signature ±300s 防重放）

## 五级判定

| Verdict | HTTP | 语义 |
|---------|------|------|
| ALLOW | 200 | 放行 |
| ALLOW_WITH_WARNING | 200 + header | 放行 + 警告头 |
| ESCALATE | 202 | 升级人工 |
| DENY | 403 | 拒绝（含 AST 硬阻断） |
| SUSPEND | 403 | 挂起 |

## AST 硬阻断引擎（v1.25.0，L2 内核强化）

- `src/ast_guard.py`：P1 Capture 校验（未知捕获忽略并记录）/ P2 payload_extractor 提取 / P3 命令表仅存 .scm 零硬编码；fail-closed 启动
- `queries/{python,bash,sql}.scm`：S-expression 查询（零正则）
  - python：eval/exec/compile + os/subprocess/pickle 等 20+ 模块方法 + importlib 动态导入
  - bash：70+ 危险命令表 + 危险标志组合（rm -rf /）
  - sql：DROP/DELETE/TRUNCATE
- 审计 trace：精确行号 + S-expression 标签 → `DecisionRecord.reason`

## 数据流（拦截请求）

```
Agent ──> [认证门] ──> [AST 前门] ──> [策略引擎] ──> [治理大脑] ──> 响应
                │            │              │              │
                └── tenant ──┴── DENY? ─────┴── SQLite ─────┘
                               (直接返回)     DecisionRecord
                                              + Trace 因果链
```

## 批判与审计（L4）

5 批判者（`src/critic/`）：Audit（版本/审计链）、Security（私钥泄漏/权限）、Arch（架构一致性）、Test（断言质量）、Docs（版本声明一致性）。GATE 8 聚合：PASS / REVISION / REJECT。

## 自进化（L5）

> **⚠️ 更正（AUDIT-0059, 2026-08-04）**："调度器执行器 28+，meta-layer 审计 14 层"为 **BottleSumo v11.23 内容污染**——本仓库无此规模（src 共 ~45 模块, 无 28+ 执行器/14 层审计实体）。Meta-Harness 部分仅实现确定性基础设施（见 docs/meta_harness_verification.md）：trace/proposer/pareto/sandbox 存在且测试覆盖, 无编码 Agent 提议器。原文保留作审计轨迹。

Meta-Harness 三循环：Trace（filesystem 决策轨迹）→ Proposer（候选策略生成）→ Pareto（帕累托前沿 + ≥3 轮演化）。调度器执行器 28+，meta-layer 审计 14 层。

## 持久化

| 存储 | 内容 |
|------|------|
| SQLite (`data/gateway.db`) | DecisionRecord + Trace |
| SQLite (`bootstrap_state.db`) | P12 确定性调度器状态 |
| filesystem (`src/trace/`) | Meta-Harness 决策轨迹 |
