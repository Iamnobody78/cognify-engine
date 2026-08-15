# 🤝 会话交接文档（Handover）— agent-governance-v2

> 用途：新会话/新 Agent 快速恢复上下文。**30 秒读完本文件即可开工**。
> 生成：2026-08-05 · 版本：v1.42.4-step2b · 配套快照：`TRIPLE_LOOP_SNAPSHOT.md`
> 完整审计历史：`audit_log.md`（最新 AUDIT-0068）；外部记忆：aionrs memory 目录

## 1. 项目是什么

Agent 规则治理网关（agent-rule governance gateway）——拦截 Agent 的
`/v1/intercept` 与 `/v1/chat/completions` 请求，按 YAML 策略规则 + LLM-Judge
语义审计裁决（DENY/SUSPEND/ESCALATE/ALLOW），并把每条决策写入可解释轨迹
（rationale → CoT → semantic_judge → context_drift），审计数据落
SQLite（decisions / decision_meta / traces 表）。

- **仓库**：本目录（`agent-governance-v2/`），git 已推送
- **测试 venv**：`.venv-b1\Scripts\python.exe`（唯一含 tree_sitter 的环境）
- **测试命令**：`.\.venv-b1\Scripts\python.exe -m pytest tests/ -q`

## 2. 当前状态（2026-08-05 闭合点）

| 项 | 状态 |
|---|---|
| 测试 | **948 passed + 1 skipped**（全绿，收集 949） |
| 工作树 | 干净（0 未提交） |
| 提交链 | 8 连绿：`2649ffa`(外部审查修复) → `e1523ee`(元认知层) → `04655a5`(bodylimit DEBT-0018) → `8b7af5e`(输出侧语义补判 DEBT-0020) → `da7545b`(Stage A 生产化) → `044b61b`(Step 2 CoT) → `43726e1`(Step 3 上下文漂移) → `f465fdb`(Step 4 Judge 入 CoT) → `2ee95c2`(Step 2b Ls YAML) |
| 可解释主控 | **Step 1-4 + Step 2b 全部闭环**（AUDIT-0061~0068） |
| 活跃债务 | 仅 DEBT-0021（已接受） |

## 3. 架构速览（六层治理）

```
请求 ──► 1.路径/方法黑名单 → 2.PolicyEngine(YAML 规则, mtime 热重载 DEBT-0005)
      → 3.Ls 杀伤权重(config/lethality.yaml, maybe_reload_lethality 热重载)
      → 4.LLM-Judge(qwen2.5:7b, 8765; AST 代码片段 + 输出侧补判)
      → 5.MetacognitionObserver(决策元数据 + CoT 轨迹回放)
      → 6.后台任务(post-save): semantic_audit / semantic_code_audit /
          semantic_context_drift / semantic_output_audit
      └─► 决策落库 → 语义事件(on_semantic/on_drift 回调)追加 CoT
```

- **CoT 链（诚实回放）**：`request → policy → reason/trace → verdict`（同步）
  + `semantic_judge / context_drift`（异步追加在 verdict 后，幂等）
- **弱信号不覆盖强信号**：漂移不覆盖已 revoke 轨迹的原因为红线的输入侧原因

## 4. 启动与验证

```powershell
# Judge 服务（Stage A 常驻）：
#   127.0.0.1:8765, 模型 qwen2.5:7b, OLLAMA_TIMEOUT=120
#   健康检查: GET http://127.0.0.1:8765/v1/health  → 200 {"status":"ok",...}
#     (注意: 是 /v1/health 不是 /health — 已核实路由)
#   启动（从仓库根目录, 入口为脚本 judge/llm_judge.py — 已核实 CLI）：
#     ollama serve
#     python judge/llm_judge.py --model qwen2.5:7b --port 8765
#   可用参数: --host(默认127.0.0.1) --timeout(默认120)
# 关键环境变量：
#   GOV_LETHALITY_CONFIG   Ls 权重表路径（默认 config/lethality.yaml，缺失拒绝启动）
#   GOV_META_DB / meta_observer_override   观察层激活（未设 = 不接线，向后兼容）
#   SEMANTIC_HOOK_ENABLED=1 语义审计激活（默认关闭）
# 全量回归：约 4 分钟；新增文件快测：
#   pytest tests/test_semantic_judge_cot.py tests/test_lethality_yaml.py -q
```

## 5. 本会话最近交付（重点回顾）

| 交付 | 提交 | 要点 |
|---|---|---|
| Step 2b Ls YAML | `2ee95c2` | 权重表数据化；fail-closed 校验；mtime 热重载；`GOV_LETHALITY_CONFIG` 覆盖 |
| Step 4 Judge 入 CoT | `f465fdb` | `append_semantic` + `_append_event_locked`（append_drift 重构为薄包装）；审计任务移 post-save；低分诚实记录 |
| Step 3 上下文漂移 | `43726e1` | per-agent 滑动窗口 + judge 一致性；漂移≥0.75 → revoke + CoT 事件 |
| Step 2 CoT 回放 | `044b61b` | 观察层 island 修复；`_build_cot` 三保存点接线 |
| Stage A 生产化 | `da7545b` | judge 服务 + --model/--timeout 修复 |

## 6. Backlog（下一轮候选）

0. **rate_limiter.py 孤岛接入**（2026-08-05 自查发现, LOW）：`src/rate_limiter.py`
   41 行 + 13 测试但生产零引用（与 Step 2 修复的 observer 孤岛同型）——窗口
   计数限流可作网关层 DoS 防线（DEBT-0018 姊妹能力）；触发：网关层 DoS 加固。
   另：CRITIQUE_V2.md 的 2026-08-31 缺陷复核 deadline 需按期兑现。
1. **OpenCV MCP**（visionpower 替代）— **评估已完成**（`OPENCV_MCP_EVALUATION.md`，2026-08-05）：
   结论 = **暂缓（方案 C）+ 自建 audit-only MCP 预案入册（方案 B）**。社区包
   `opencv-mcp-server` 真实存在（PyPI 0.1.2）但 11 个月未推送、依赖 contrib
   全家桶（~90MB）、通用工具面大（含相机控制）——不入治理栈。治理侧当前
   **无图像入口**（intercept 只处理文本 JSON）→ 视觉 MCP 无调用方。
   **触发条件**：①治理流量出现多模态输入 → 自建 load_image/analyze MCP 接
   入语义审计链；②BottleSumo 视觉立项 → 机器人侧另用社区包。自建先例：
   本工作区已有 5 个自建 Python MCP 服务器（`.aionui/mcp/`）。
2. DEBT-0021（已接受，无需处理）

## 7. 工程惯例（新会话必读）

- **事实核查先行**：用户方案先对照代码，计划与实现矛盾时记录"架构事实核查修正"
  （AUDIT-0067/0068 已 4 次），再动手
- **测试隔离**：conftest 两个 autouse fixture（drift 窗口清理 + lethality 状态恢复）；
  patch 注意值绑定（`main_module.semantic_hook_enabled`）vs 模块属性（`sh.is_enabled`）双 patch
- **审计纪律**：每次变更 → 全量回归 → audit_log.md（AUDIT-XXXX）→
  TRIPLE_LOOP_SNAPSHOT.md 版本快照 → README 计数 → 提交推送 → 记忆同步
- **完成确认**：任务收尾生成 6 章节完成确认报告（三重证据：代码 + 测试 + 提交/审计）
