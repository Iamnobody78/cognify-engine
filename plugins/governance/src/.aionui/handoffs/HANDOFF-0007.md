# 会话交接记录 — agent-governance-v2

> 规则：每个会话结束前必须写交接；新交接追加在顶部；下一个会话从最新交接继续。
> 交接必须包含：做了什么（有测试证据）、到哪了、下一步、遗留债务。

---

## HANDOFF-0009 — 2026-08-03T09:30:00Z

**会话主题**: B2 AutoGen 零侵入集成完成 + 外部批判 15 项证据核验 + v0.2.2 工程修复

**做了什么**（全部有测试/门控证据）:
- **B2 完成（AUDIT-0009）**: AutoGen 0.7.5 GroupChat 多 Agent 经网关零侵入验证:
  - examples/autogen_groupchat.py（AST 0 gateway import，唯一引用 base_url）; 	ests/test_integration_autogen.py（G1 零侵入 ×3 / G2 解析器 vs AutoGen schema ×5 / G3 真实端点 ×4）; scripts/b2_e2e.py 真实 SDK E2E
  - **E2E 证据**: SAFE GroupChat 4 轮全 ALLOW 转发（upstream 4 requests）; DANGEROUS GroupChat executor 声明 delete_file → 403 PermissionDeniedError, 携带 delete_file 请求 **0 次**到达 upstream; 6 决策入库（5 ALLOW + 1 DENY）
  - **关键调试教训**: 初版 e2e 断言 upstream_after == before 是错误预期（proposer 首轮无工具合法 ALLOW 转发 +1）; 正确断言 = 危险声明 0 上游 + 403 抛出 + DENY 入库; AutoGen 被拒消息打印巨型 traceback → 压制 autogen_core logger
- **外部批判（网页版 DeepSeek）15 项声明证据核验**: 12 STALE（v0.1.0 快照, 已修复）+ 2 夸大 + 2 VALID + 1 部分有效。核验表见会话记录/AUDIT-0009
- **v0.2.2 修复 VALID 2 项**:
  - src/policy.py: Rule.action → `Literal` + `__post_init__` 校验 fail-closed（typo 配置拒绝启动）; 顺带修复大小写 bug（YAML `deny` 原静默变 ALLOW）
  - src/storage.py: `threading.Lock` 序列化共享 sqlite3 连接; `src/main.py`: 3 处 `storage.save` → `await asyncio.to_thread`, `_deny_decision` 改 `async def`
- **新增 7 个异常路径测试**: `tests/test_policy_config_validation.py`（typo/空 action 拒绝加载、小写归一、32 线程并发 save、roundtrip）
- 全量回归 **94/94**（87 + 7）; b2_e2e.py 重跑 PASS（async 化后链路完好）
- 债务登记 DEBT-0005..0008（热更新/AST 误报/shutdown_timeout 显式化/DB 失败降级测试）

**进行中/未完成**:
- B2/B1 全部代码**待提交**（src/main.py, src/policy.py, src/storage.py, tests/test_policy_config_validation.py, scripts/b2_e2e.py, EXPERIMENT_B_REPORT.md, debt_registry.md, audit_log.md, decisions/DECISION-0002, handoff）
- B3 混合模式（LangChain + AutoGen 同网关统一治理）— 下一步
- b1/b2_e2e.py 依赖各自 venv 未接 CI
- 团队制 agents 调度/执行/MCP 适配（用户核心需求）

**遗留债务**: 见 debt_registry.md DEBT-0001..0008（全部 LOW）; 无未修 HIGH/MEDIUM

---
## HANDOFF-0008 — 2026-08-03T08:00:00Z

**会话主题**: B1 LangChain 集成 + 团队化两阶段 Spawn 验证（REJECT→PASS 完整闭环）

**做了什么**（全部有测试/门控证据）:
- **B1 完成**: OpenAI 兼容端点 `POST /v1/chat/completions` + `examples/langchain_agent.py`（零侵入，AST 证明 0 gateway import）+ 真实 SDK E2E（langchain 1.3.14，安全 ALLOW / 危险 DENY 双向入库）
- **团队化验证闭环**: Builder(3 文件) → Coordinator(验证) → **Spawn Reviewer 独立审查 REJECT**（4 洞）→ 修复 → **PASS**。证据: 75/75 测试 + GATE 1-7 全绿 + health_score 100/100
- **Reviewer R1 (HIGH) 类型混淆**: tools 传 dict 迭代 keys → 0 名字 → ALLOW 透传。修复: `_extract_tool_names` `isinstance(x, list)` fail-closed + 新增 `_malformed_tool_declaration` 结构校验（畸形声明整体 400 拒绝，不静默忽略）
- **Reviewer R2 (HIGH) Unicode/大小写变体**: `Delete_File`、`delete_fιle`(U+03B9) 绕过精确匹配。修复: `_norm_tool_name` NFKC → **confusable 同形映射**（希腊 iota/西里尔/罗马数字）→ casefold 三阶段。**关键教训: NFKC+casefold 不折叠同形字符，必须显式 confusable 表**
- **Reviewer R3 (MEDIUM) 字符串 function**: `"function": "delete_file"` str 非 dict → AttributeError 500。修复: `isinstance(fn, dict)` 防护 + 畸形声明 400
- **Reviewer R4 (LOW) 非字符串 name**: list/dict/数字 name 静默追加。修复: `isinstance(name, str) and name`
- **新增 11 个 Reviewer 回归测试**: R1 dict fail-closed ×3、R2 unicode/case/fullwidth 全栈 DENY ×3 + 持久化 ×1、R3 字符串 function ×1、R4 非字符串 name ×1
- AUDIT-0008 已更新为 PASS→REJECT→PASS 完整记录

**进行中/未完成**:
- B1 代码全部**待提交**（src/main.py、examples/langchain_agent.py、tests/test_integration_langchain.py、scripts/b1_e2e.py、EXPERIMENT_B_REPORT.md、audit_log.md、handoff）
- B2 AutoGen 集成（同 B1 零侵入验证路径）
- B3 混合模式（LangChain + AutoGen 同网关）
- b1_e2e.py 依赖 venv 未接 CI
- 团队制 agents 调度/执行/MCP 适配（用户核心需求，B1 只是验证载体）

**遗留债务**:
- 熔断器 LOW: reset-on-trip 无时间衰减（攻击者可分散触发，需 9 次 ESCALATE）
- 私有 API `_is_dangerous` 耦合（policy_probe 依赖私有符号）
- CI job 间无 `needs:` 声明（依赖分支保护）
- stub LLM（非真实 GPT）— 上游真实性待验证
- `_malformed_tool_declaration` 只校验 tools/messages 形状，`body` 顶层 JSON 解析错误路径需 e2e 覆盖（目前由 aiohttp 处理）

---

---

## HANDOFF-0007 — 2026-08-03T05:30:00Z

**会话主题**: v2 治理闭环 + 团队制落地

**做了什么**（全部有测试/门控证据）:
- AUDIT-0005 安全加固（v0.2.0）: 熔断 fail-closed + normpath 路径防御 + asyncio.Lock + Header 白名单。53/53 测试，GATE 1-5 绿
- AUDIT-0006 类型连续性（v0.2.1）: DecisionRecord 强类型化 + body Union + Docstring 去应激。53/53 测试
- GATE 6 已实现: `scripts/meta_security_scanner.py`（AST 反模式扫描）。对抗验证: fixture 恶意代码 exit 1，真实 src/ exit 0
- GATE 7 已实现: `scripts/policy_sync.py`（策略-代码漂移检测）。对抗验证: 小写 action/孤儿前缀 REJECT，恢复 PASS
- GATE 6/7 已接入 CI（7 门控全绿）
- `scripts/health_score.py` 已写（4 门控实测评分），**最后验证被取消，未跑完**
- pyproject.toml 加 [tool.pytest.ini_options] 锁 rootdir（修复 python -m pytest 漂移到父目录问题）

**进行中/未完成**:
- health_score.py 最终验证（pytest -m 方式已修复 53 passed，需重跑 score）
- 团队制 5 机制落地: index.md 已建，handoffs/decisions/failures/debt_registry 待建
- 团队制 agents 对话/调度/执行协议 + MCP/工具适配（用户核心需求）

**遗留债务**:
- 熔断器 LOW: reset-on-trip 无时间衰减（攻击者可分散触发，需 9 次 ESCALATE）
- 私有 API `_is_dangerous` 耦合（policy_probe 依赖私有符号）
- CI job 间无 `needs:` 声明（依赖分支保护）
- health_score.py 未验证

**下一步**:
1. 建 handoffs/decisions/failures/debt_registry 骨架
2. 重跑 health_score.py 验证
3. 升级 teams_collaboration.md 为 v3（对话/调度/执行 + MCP 适配）
4. 概念核查器 `concept_gap_audit.py`（用户元批判的落地工具）

---

