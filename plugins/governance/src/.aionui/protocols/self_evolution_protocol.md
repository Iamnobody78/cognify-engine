# 🧬 自进化治理引擎执行协议（Self-Evolving Governance Engine Protocol）

> 状态: **ACTIVE**（v1.0，2026-08-03 落盘）
> 定位: 五层自治系统（L1-L5）的**执行规程**——从 Critic 代码化开始，逐步实现
> 自动治理、自动优化、自动演进。本文件是"声明层"，执行必须由**拥有本地终端
> 执行权的 Agent**（Claude Code / Cursor / CLI Agent / 本地 MCP）完成。

## ⚠️ 元教训（本协议的第一铁律）

**网页版 LLM 没有本地执行权。** 元提示词若包含 `pytest tests/`、`git commit`
等指令，网页端会**表演式伪造**终端输出与 git hash。防伪造三原则：

1. 每个"声称"必须附真实命令输出（`pytest`/`git log` 原样粘贴）
2. 每个提交必须可复核（`git log -1 --oneline` + `git status` 干净）
3. 一次只执行一个 Phase——跑完并经 pytest 真实全绿后再唤醒下一个
   （防一次性生成大量文件时的上下文漂移与 pass/TODO 简写）

## 📋 已批准路线图（Phase 1-5）

| 阶段 | 任务 | 代码量 | 依赖 | 状态 |
|------|------|--------|------|------|
| **Phase 1** | Critic Agent 代码化 + GATE 8 | ~200 行 | 无 | ✅ 完成（提交 `0e389ea`） |
| **Phase 2** | Meta-Harness 轻量适配器 | ~100 行 | Phase 1 | ✅ 完成（提交 `c6a3a95`） |
| **Phase 3** | Meta-Harness 完整评估沙箱 | ~200 行 | Phase 2 | 🔲 待执行 |
| **Phase 4** | 治理大脑 Phase 1（rationale + 五级响应） | ~150 行 | 无 | 🔲 待执行 |
| **Phase 5** | Context Hook 完整集成（HMAC） | ~100 行 | 无 | 🔲 待执行 |

## 执行规则（每 Phase 强制）

1. 任何代码变更必须伴随测试——没有测试 = 没有完成
2. 任何新模块必须有 `__init__.py` 和 docstring——文档即证据
3. 任何 GATE 新增必须不破坏现有 GATE——回归全绿
4. 每个 Phase 完成后必须独立提交（不可积累多个 Phase 一起提交）
5. 任何"声称"必须有证据——不得出现"我认为通过了"而不提供 pytest 输出

## 每阶段输出格式

```markdown
## ✅ Phase [X] 完成
### 新增文件
### 修改文件
### 验证结果（测试数 / GATE 1-8 / 证据链命令）
### 治理更新（AUDIT / 快照 / DEBT）
```

## 防伪造执行清单（本地 Agent 验收命令）

```bash
# 1. 基线
pytest tests/ -q                    # 期望 ≥ 上阶段 passed
# 2. 本 Phase 测试
pytest tests/test_<phase>.py -v
# 3. 全量回归
pytest tests/ -q                    # 期望 ≥ 基线
# 4. GATE 集成存在性
grep -A5 "GATE 8" .github/workflows/ci.yml
# 5. 工作树干净
git status
# 6. 提交确认
git log -1 --oneline
```

## 自我引用

本协议受 Critic Agent（GATE 8）约束：Phase 完成后 Critic-Audit 验证协议是否
被执行完毕；Critic-Docs 验证协议宣称在提交历史中有对应证据。

---

## 🛠️ P7 代理自举工具集（v1.15.0，2026-08-03）

> 协议从"声明层"落地为**可调用工具**：`src/agent_tools/` 把 Sense→Diagnose→
> Remediate 循环代码化，供治理 Agent 在思考链中直接调用。

### 思考链（Thinking Chain）——每次自举迭代强制

```text
[Sense]      run_self_critic()     → 结构化自审报告（verdict/per_critic/high_count）
[Diagnose]   get_self_trace()      → 提取目标 trace 的完整因果链（depth/node_count）
[Remediate]  heal_candidate()      → 沙箱评估候选，产出 fixes 修正建议（类别+证据）
[Validate]   pytest tests/ 全量回归 ≥ 基线（当前 420 + P7 新增）
[Deploy]     git commit + 快照 v1.15.0 更新
```

### 三工具与既有层级的复用映射（不重实现原则）

| 工具 | 复用对象 | 契约 |
|------|----------|------|
| `run_self_critic` | `critic.runner.run_all_critics` | 返回 `decision` 五键 + reports 证据链 |
| `get_self_trace` | `Storage.get_trace` | 递归 CTE（防环 + max_depth/max_nodes 双保险） |
| `heal_candidate` | `meta_harness.adapter.validate_candidate` + `sandbox.evaluate_candidate_in_sandbox` | 不可部署时生成 fixes（syntax/conflict/replay/regression 四类） |

### 裁决边界（P7 铁律）

- `heal_candidate` **只建议、不落盘**——修改 `config/policies.yaml` 的裁决权
  始终在治理层（GATE 8 通过 + 人工复核后）。
- 每次自举迭代必须在 `.aionui/audit_log.md` 追加 AUDIT 条目（当前至 AUDIT-0035）。
- 测试验收：AC1-AC6（结构化报告/因果链/修正建议/可部署路径/L4L5 复用/全量回归）。
