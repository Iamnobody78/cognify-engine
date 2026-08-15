# 债务登记表 — debt_registry.md

> 规则（团队制铁律）:
> 1. 每个债务有 ID、描述、严重度、创建日期、是否阻塞
> 2. 新功能禁止引入未登记的债务
> 3. 会话结束时清点：0 阻塞债务是目标
> 4. 债务被修复 → 移入"已清偿"区并标注清偿 commit

## 活跃债务

| ID | 描述 | 严重度 | 创建日期 | 阻塞? | 来源 |
|----|------|:---:|------|:---:|------|
| DEBT-0021 | timeout fail-closed 分支的 path 启发式（danger.py）看不到请求体——json_path 规则在超时降级路径不生效（已文档化接受：timeout 3s+熔断兜底；json_path 规则是纵深防御附加层） | LOW | 2026-08-03 | 否 | TASK-REAL-010 已知边界 |
| DEBT-0026 | json_path 规则线性匹配（规则多时逐条解析 jsonpath 遍历，命中率低；→ 前缀索引树 ~60 行） | LOW | 2026-08-03 | 否 | 暗雷区 P3（已清偿 `ebe9002`，见清偿表） |

| DEBT-0027 | 身份认证缺失：L2-L5 治理能力暴露于未认证访问（外部评审结构性缺口 #1 → P6 已修复，见清偿表） | MEDIUM | 2026-08-03 | 否 | P6（已清偿 `9e91c03`，见清偿表） |

> **当前活跃债务：1 项（LOW×1，已文档化接受，无阻塞）** —— DEBT-0020（输出侧语义评估）已清偿于 v1.41.0（semantic_output_audit_async: fire-and-forget/fail-soft/只升不降, 与输入侧同构; extract_agent_response 有界截断 AGENT_RESPONSE_MAX_CHARS=3000; 三路触发: chat 非流式/流式有界累积/_proxy_forward; +12 测试, 900 全绿）。DEBT-0018（body 上限）已清偿于 v1.40.0。DEBT-0027（身份认证缺失）已清偿于 `9e91c03`（外部评审缺口 #1 闭合）；暗雷区 DEBT-0023/0024/0025/0026 此前已清偿。DEBT-0022 已清偿（`6c25bd9`，REAL-011.1）；DEBT-0019 已清偿（`d95f83c`）。上一批 16/16 已清偿于 TASK-REAL-001..008。

## 已清偿

| ID | 描述 | 清偿 commit | 清偿日期 |
|----|------|------|------|
| DEBT-0001 | 熔断器无时间衰减（trip 后立即恢复计数，分散触发可绕过） | `0e18760` (TASK-REAL-002) | 2026-08-03 |
| DEBT-0018 | 请求/响应无大小上限（10MB body 拖慢反序列化与 hook 截断前的内存占用；hook 输入已截断 2000 字符，但网关层无显式 body 上限） | `(v1.40.0)` | 2026-08-05 |
| DEBT-0020 | 语义输出侧评估缺失（A 阶段仅评估 user_prompt 输入侧；agent_response 在代理转发后产生，可异步补判） | `(v1.41.0)` | 2026-08-05 |
| DEBT-0008 | SQLite 写入失败无降级路径（直接抛异常，无内存缓存重试） | `0e18760` (TASK-REAL-002) | 2026-08-03 |
| DEBT-0005 | YAML 策略无热更新（修改 policies.yaml 需重启网关生效） | `661b77f` (TASK-REAL-001) | 2026-08-03 |
| DEBT-0006 | check_policy.py AST 规则误报含 allow/deny 子串的 dict key（如 `allow_retry`） | `661b77f` (TASK-REAL-001) | 2026-08-03 |
| DEBT-0002 | 私有 API `_is_dangerous` 耦合（policy_probe 依赖 src.main 私有符号） | `368907c` (TASK-REAL-003) | 2026-08-03 |
| DEBT-0007 | `web.run_app` 未显式 shutdown_timeout（依赖 aiohttp 默认 60s） | `368907c` (TASK-REAL-003) | 2026-08-03 |
| DEBT-0009 | `_pending` 内存缓存无上限（长时降级时内存占用风险） | `368907c` (TASK-REAL-003) | 2026-08-03 |
| DEBT-0010 | `flush_pending()` 重试时机未明确（建议 main.py 启动/关闭时触发） | `368907c` (TASK-REAL-003) | 2026-08-03 |
| DEBT-0004 | chat 端点无流式（stream:true 客户端 TTFT 退化 + SSE 语义丢失） | `3aea7d2` (TASK-REAL-004) | 2026-08-03 |
| DEBT-0003 | CI job 间无 `needs:` 声明（依赖分支保护） | `bd3f8f1` (TASK-REAL-005) | 2026-08-03 |
| DEBT-0011 | 熔断状态不持久化（内存变量，重启清零 → 重启绕过冷却窗口） | `dfaef6b` (TASK-REAL-006) | 2026-08-03 |
| DEBT-0012 | 空 policies.yaml 静默启动（rules 空 → 全 ALLOW，违反 fail-closed） | `dfaef6b` (TASK-REAL-006) | 2026-08-03 |
| DEBT-0013 | `_pending` 超限丢弃最旧记录无持久化备份（长期 DB 不可用 → 审计记录永久丢失） | `f61e5fa` (TASK-REAL-007) | 2026-08-03 |
| DEBT-0014 | `flush_pending()` 无重试上限与退避（DB 持续不可用 → 无限重试循环） | `f61e5fa` (TASK-REAL-007) | 2026-08-03 |
| DEBT-0015 | `_flush_pending_on_shutdown` 与 shutdown_timeout=10 未联动（flush 超时 → aiohttp 强制终止，待决记录丢失） | `f61e5fa` (TASK-REAL-007) | 2026-08-03 |
| DEBT-0017 | GATE 1 扫描器误判状态验证断言（21 违规中 16 个为历史测试的真实 IO/状态断言；门控豁免逻辑已修复） | `dfaef6b` (TASK-REAL-006) | 2026-08-03 |
| DEBT-0016 | 文档诚实性：CRITIQUE_V2.md 过时（标注"500ms 超时 ALLOW"但已修复 fail-closed）；EXPERIMENT_REPORT.md 未反映 v2 当前已知缺陷 | `e3f575d` (TASK-REAL-008) | 2026-08-03 |
| DEBT-0019 | 无 Trace-ID 因果关联（多智能体协作时无法串联"Agent A 诱导 Agent B 违规"的调用链） | `d95f83c` (TASK-REAL-011) | 2026-08-03 |
| DEBT-0022 | chat/completions 路径未注入 trace 上下文（chat 端点决策无 trace_id/parent_span_id，跨端点断链） | `6c25bd9` (TASK-REAL-011.1) | 2026-08-03 |
| DEBT-0023 | 异常处理"过于优雅"：主路径日志无堆栈/异常细节，故障时仅 1 行无上下文（→ logger.exception + traceback.debug 分级） | `1ef39a0` (暗雷区 P0) | 2026-08-03 |
| DEBT-0024 | 语义钩子同步链路延迟 + judge 服务异常时绕过监督无撤销路径（→ semantic_audit_async 异步弱监督 + RevokeRegistry 进程级单例，DENY 优先只升不降） | `be0b5ee` (暗雷区 P1) | 2026-08-03 |
| DEBT-0025 | SQLite 逐条 INSERT + 每事务 fsync 提交的写锁瓶颈（→ WAL + synchronous=NORMAL + batch_size 批量 executemany 提交 + 读路径前置 flush 保读-己-写一致 + 降级 _buffer_or_fallback） | `c40dc41` (暗雷区 P2) | 2026-08-03 |
| DEBT-0026 | json_path 规则线性匹配（→ JsonPathIndex 前缀索引树：首段键桶化 + 顶层键集合单次收集剪枝 + segments 预解析缓存；首段 wild/descend/idx 不可剪枝；候选保持优先级序，与线性扫描逐位等价） | `ebe9002` (暗雷区 P3) | 2026-08-03 |
| DEBT-0027 | 身份认证缺失：L2-L5 治理能力暴露于未认证访问（→ P6：TenantAuth API key 认证 401 + X-Tenant-ID 一致性 403 + PolicyRule.tenant_id 作用域隔离 + HMAC 服务签名复用；AUTH_ENABLED 开关兼容模式零回归） | `9e91c03` (P6) | 2026-08-03 |

