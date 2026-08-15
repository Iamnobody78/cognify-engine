# agent-governance v2 — 架构设计（权威参考）

> **版本对应**: 快照 v1.25.0 · 提交 Tree-sitter AST 硬阻断引擎（Priority 0 前门，五层架构 L1 内核强化） · 2026-08-03
> **维护铁律**: 本文档与代码同仓库、同提交链。任何架构级变更（新增模块/层、修改请求生命周期、加固点增减）必须在同一提交中同步更新本文档——「文档与代码同提交」。
> **关联**: README.md（v1→v2 演进叙事 + ADR 附录，历史叙述）；`.aionui/context/TRIPLE_LOOP_SNAPSHOT.md`（治理快照，状态维度）。

---

## 0. 总体视图

五层架构 L1-L5 全部闭环，外加 Meta-Harness 双环治理（内环=GATE 8 批判者驱动自我修复；外环=Agent 注册表/协议/任务档案驱动的多 Agent 协作）。

```
                         ┌─────────────────────────────────────────────┐
                         │       治理闭环 (Meta-Harness 双环融合)         │
                         │                                             │
   ┌─────────┐           │  外环: protocols/ + agent_registry.yaml    │
   │ 外部流量 │──────────▶│       + scheduler/work/ 任务档案           │
   └─────────┘           │             ▲                │             │
                         │             │ 修复指令         │ 批判报告     │
                         │  内环: GATE 8 五批判者 ───────┘             │
                         │       (runner → critic_report)              │
                         └─────────────────────────────────────────────┘
                                     │ 规则/反馈
┌─────────────────────────────────────────────────────────────────────────┐
│ L5 Meta-Harness   meta_harness/adapter.py (264L) + sandbox.py (286L)    │
│                   策略建议生成/候选验证/沙箱隔离 (pending_rules)          │
├─────────────────────────────────────────────────────────────────────────┤
│ L4 Critic Agent   critic/ (7 文件, 905L)                                │
│                   runner 五批判者: audit/security/arch/test/docs        │
│                   GATE 8: exit 0=PASS, 1=REJECT/REVISION → Builder 修正  │
├─────────────────────────────────────────────────────────────────────────┤
│ L3 治理大脑       五级判定 (ALLOW/ALLOW_WITH_WARNING/ESCALATE/DENY/      │
│                   SUSPEND) + DecisionRecord.rationale + context_hmac.py │
│                   (113L, HMAC 信任门: canonical 字段序 + ±300s 防重放)   │
├─────────────────────────────────────────────────────────────────────────┤
│ L2 核心网关       main.py (aiohttp + intercept 中间件)                   │
│                   auth.py (P6: TenantAuth 身份门 — 401/403 第一道门)     │
│                   policy.py (规则引擎 + JsonPathIndex + tenant 作用域)   │
│                   danger/lethality/norm 启发式 + semantic_hook 异步监督  │
│                   revoke.py (RevokeRegistry 撤销注册表)                  │
├─────────────────────────────────────────────────────────────────────────┤
│ L1 基础设施        storage.py (373L, SQLite WAL+批量+降级缓冲+Trace CTE) │
│                    ha/ (Phase HA: FileLock + Lease + FailoverCoordinator)│
│                    models.py (88L, DecisionRecord 13 列)                │
│                    rate_limiter / time_utils / task_scheduler           │
└─────────────────────────────────────────────────────────────────────────┘
```

## 1. 分层职责

### L1 基础设施 — 可观测、可降级的存储
| 文件 | 职责 | 关键机制 |
|---|---|---|
| `storage.py` 373L | 决策记录持久化 | **P2 加固**：`journal_mode=WAL` + `synchronous=NORMAL`；`save()` 写缓冲满批 `executemany` 提交；读路径前置 flush（读-己-写一致）；写失败降级 `_buffer_or_fallback`（`PENDING_MAX` 有界 + 最旧落盘）；`get_trace` 递归 CTE（`max_depth=50`）重建因果链 |
| `models.py` 88L | `DecisionRecord` | 13 列：含 `trace_id/parent_span_id/rationale/verdict` 全链路字段 |
| `rate_limiter.py` 41L | 限流 | 窗口计数 |
| `task_scheduler.py` 90L | 治理任务 | 调度执行 |
| `ha/`（**Phase HA 新增**） | 高可用多实例协调 | `FileLock`（跨平台 OS 级短临界区互斥）；`Lease`（租约心跳 + 过期检测，TTL 5s/续约 2s + 时钟容差 1s）；`FailoverCoordinator`（单写者模型：`guard_write` 非主写抛 `NotPrimaryError` + `recover` 过期接管）。零新基础设施（不引入 Redis/PostgreSQL——storage.py 深度耦合 SQLite 特有语法）；设计详见 `docs/ha_design.md` |
| `certification/`（**P8 新增**） | 认证层（证明协议地基） | `sign.py`（ED25519 私钥→base64 签名 + 密钥自动生成 PKCS8 PEM chmod 600）；`verify.py`（公钥+文件+签名→True/False，fail-closed）；CLI：`python -m src.certification.sign/verify`。新增依赖 `cryptography==50.0.0` |

### L2 核心网关 — 身份、拦截、判定、监督
| 文件 | 职责 | 关键机制 |
|---|---|---|
| `auth.py` ~180L（**P6 新增**） | 服务身份认证 + 多租户隔离 | `TenantAuth`：API key → tenant_id（sha256 摘要 + 常量时间比较 + fail-closed 校验）；`Authorization: Bearer`/`X-API-Key` 认证，缺失/无效 → 401；`X-Tenant-ID` 与认证身份不符 → 403（防跨租户冒称）；`verify_service_signature` 复用 Phase 5 context_hmac（显式携带但伪造签名 → 401，服务身份边界）；启用 = `create_app(auth_override=...)` 或 `AUTH_ENABLED=1`，未启用 = 兼容模式（v1.13.0 行为完全一致） |
| `main.py` ~860L | aiohttp 应用 + `intercept` 中间件 | **认证门最先执行**（intercept/chat/decisions/trace 四端点受保护，`/v1/health` 探针放行）；提取 trace 上下文 → 规则评估 → 写决策记录 → 响应头回传（`X-Trace-ID/X-Span-ID/X-Governance-Warning`）；`create_app(config_path)` 策略注入；P0 分级异常日志 |
| `policy.py` ~390L | 规则引擎 | `PolicyEngine.evaluate` 优先级首中即停；**P3 加固**：`JsonPathIndex` 前缀索引树（首段键桶化 + 顶层键单次收集剪枝，与线性扫描逐位等价）+ segments 预解析缓存；**P6**：`PolicyRule.tenant_id` 作用域（None=全局），跨租户私有规则跳过（隔离语义） |
| `danger.py`/`lethality.py`/`norm.py` | 路径/方法启发式 | 危险模式、杀伤力评估、规范性检查 |
| `semantic_hook.py` 152L | 语义钩子 | **P1 加固**：`semantic_audit_async` 后台 fire-and-forget（原同步链路延迟消除） |
| `revoke.py` 62L | 撤销注册表 | 进程级单例、有界；judge 服务异常时**撤销保持而不是绕过**（DENY 优先只升不降） |

### L3 治理大脑 — 可解释的裁决
- **五级判定**：`ALLOW(200)` / `ALLOW_WITH_WARNING(200+警告头)` / `ESCALATE(202)` / `DENY(403)` / `SUSPEND(403)`
- **rationale 字段**：每条决策带可解释理由（审计可追溯）
- **`context_hmac.py` 113L（Phase 5）**：HMAC-SHA256 签名治理上下文头——canonical 固定字段序 + 防重放窗 ±300s + `compare_digest`；`CONTEXT_HMAC_KEY` 开关（未设=兼容模式）；**伪造头 → 新链根隔离**（方案 A：降级隔离，不 403）

### L4 Critic Agent — GATE 8 动态语义门控
`src/critic/` 7 文件 905L：`runner.py` 并行跑 **5 批判者**：
- `audit_critic`（含 A3 多阶段 relay_state 语义——修正"全完成仍 IN_PROGRESS"误报）
- `security_critic` / `arch_critic` / `test_critic` / `docs_critic`
- `verdict.py` 聚合成 `PASS/REVISION/REJECT` → `.aionui/critic_report.md`；**exit 0=PASS，1=REJECT/REVISION → Builder 修正**

### L5 Meta-Harness — 自我进化
`meta_harness/adapter.py`（264L）：`generate_policy_suggestions`（从决策流扫描生成候选策略）+ `validate_candidate`（3 层门控）；`sandbox.py`（286L）：候选规则沙箱隔离（`pending_rules/` 目录），验证通过才提升主策略。

## 2. 请求生命周期

```
请求 ──▶ 认证门 (P6: API key → tenant_id; 缺失/无效 → 401, X-Tenant-ID
   │      与身份不符 → 403; /v1/health 探针豁免)
   ──▶ HMAC 信任门 (L3: 签名验证, 伪造→新链根隔离)
   ──▶ intercept 中间件 (L2: 提取 X-Trace-ID, 组装 DecisionRecord 骨架)
   ──▶ PolicyEngine.evaluate (L2+L3: tenant 作用域过滤 + 路径/方法规则
   │      + json_path 条件规则[前缀索引剪枝])
   ──▶ 五级判定 (L3: action→verdict + rationale)
   ──▶ storage.save (L1: 写缓冲 → WAL 批量提交)
   ──▶ 响应头回传 (X-Span-ID / X-Governance-Warning; DENY/SUSPEND=403)
   ──▶ 异步语义监督 (P1: semantic_audit_async 后台)
         └─ 工具名命中 → judge 服务置信度 < 阈值 → RevokeRegistry 登记
            → 后续请求撤销短路 (DENY 优先只升不降)
```

## 3. 治理闭环：Meta-Harness 双环

| 环 | 触发 | 机制 |
|---|---|---|
| **内环**（调度器自动发现） | GATE 8 批判者发现 FAIL/REVISION | runner → critic_report → 因果修复（例：A3 多阶段语义修复使基线 328→331，GATE 8 自我修复 `ae311aa`） |
| **外环**（Agent 治理） | 多 Agent 协作任务 | `tools/agent_registry.yaml` 注册表 + `protocols/`（pr_review_loop/teams_collaboration/self_evolution_protocol 等 5 协议）+ `scheduler/work/` 任务档案 + `handoffs/` 移交 |

治理工作文件：`audit_log.md`（AUDIT-0001~0045 永久审计链）、`TRIPLE_LOOP_SNAPSHOT.md`（v1.24.0）、`debt_registry.md`（22 清偿/3 活跃）、`critic_report.md`、`audit/health_score.md`。

## 4. 暗雷区加固（P0-P3，架构韧性）

| 加固 | 风险 | 方案 | 提交 | 测试证明 |
|---|---|---|---|---|
| P0 | 异常"过于优雅"无堆栈 | `logger.exception` + `traceback.debug` 分级，响应体不泄内情 | `1ef39a0` | +10 测试 |
| P1 | 语义钩子延迟+绕过 | 异步弱监督 + 撤销注册表（DENY 只升不降） | `be0b5ee` | +10 测试 |
| P2 | SQLite 写锁瓶颈 | WAL + 批量提交 + 降级缓冲（读-己-写一致） | `c40dc41` | +10 测试 |
| P3 | json_path 线性匹配 | 前缀索引树（剪枝等价性证明：首段键∉顶层→提取必空；descend/wild 不可剪） | `ebe9002` | +21 测试 |

## 4b. P7 代理自举工具集（agent_tools 层）

**定位**: 治理 Agent 自举的"可调用化"——把 self_evolution_protocol 的
Sense→Diagnose→Remediate 循环从声明层落地为工具，复用 L4/L5 既有能力（不重实现）。

| 工具 | 复用对象 | 返回 | 契约边界 |
|------|----------|------|----------|
| `run_self_critic` | `critic.runner.run_all_critics` | verdict/reason/per_critic/high_count/reports | 5 批判者全量或子集 |
| `get_self_trace` | `Storage.get_trace` | 因果链 nodes/depth/node_count | 递归 CTE 防环 + 双上限 |
| `heal_candidate` | `validate_candidate` + 沙箱 | deployable/reasons/conflicts/hit_rate/fixes | **只建议不落盘**（裁决权在治理层） |

**fixes 四类别**: syntax（YAML 结构）/ conflict（action 冲突）/ replay（命中率不足）/
regression（pytest 失败）——每项含 category + hint + evidence。

## 5. 当前状态

- **测试**: 450 passed 零失败；**GATE 8**: 5/5 PASS；**覆盖率**: 87%（`--source=src` 含 meta_harness 68-70%；90.12% 为 REAL-008 期旧口径，非回归）
- **架构**: L1-L5 全闭环 + **P6 身份认证/多租户**（外部评审缺口 #1 闭合）+ **P7 代理自举工具集**（agent_tools 三工具）+ **Phase HA 高可用**（src/ha/ 多实例协调）+ **P8 认证层**（src/certification/ ED25519 签名，证明协议地基）+ **P9 外部代理示例**（examples/ 三生态零侵入接入：通用 Python 进程内 agent_tools / LangChain / AutoGen 被动 sidecar base_url）；暗雷区 4/4 收官；活跃债务 3（DEBT-0018/0020/0021，无阻塞）
- **兼容模式**: auth 未启用 = v1.13.0 行为完全一致（零回归保障，`AUTH_ENABLED=1` 或 `auth_override` 注入时启用）
- **HA 部署拓扑**: 单写者模型——主实例唯一写 storage，副本只读 + 租约轮询；主崩溃 → 租约过期（TTL 5s）→ 副本接管（脑裂防护 = FileLock + 租约双重判定）
- **认证层**: ED25519 签名所有证明文件（`python -m src.certification.sign --file <f>`）；防伪造证明链 = 签名 → 审计 → 公开
- **已知上游怪癖**: Python 3.13 + aiohttp `AioHTTPTestCase` 的 tearDown "never awaited" RuntimeWarning（P1 前即存在，非本仓库引入，状态隔离实测有效）
- **下一候选**: P14 性能基准（P13 完成后用户指定下一候选）