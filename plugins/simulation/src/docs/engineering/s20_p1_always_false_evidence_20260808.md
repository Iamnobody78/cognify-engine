# Sprint 20 P1 恒 False 模式检测 — 证据文档（2026-08-08）

> 范围：`feature/sprint20_heuristic_distill` 分支（基线 main@f2ca93e + tag sprint19-closed）
> 依据：PM Sprint 20 裁决 — "P1 恒 False 启发式 ✅ 批准，作为 S18/S19 的第三层防御（在 diff 应用前用轻量级静态分析拦截明显损坏候选，减少评估开销）"
> 学术映射：RefDiff Diff Token Filter（λ∈(0.5,1.0] 假阳性预过滤范式）、Shadow Replay pre-merge sanity check（预演而非实演范式）

## 1. 问题定义（FP-MC-018）

恒 False 候选（自引用比较 `dist < dist`、空条件 `if:`、恒 False 字面量 `if 0:`）此前：
- 能通过 resolve_diff 字符串匹配（合法语法）
- 能通过 apply_precheck 锚点计数（old 锚点真实存在）
- **进入评估后才被差分门禁拦截**（SUSPICIOUS/INCONCLUSIVE）→ 评估预算浪费

## 2. 三层防御设计

```
┌─ 第一层（生成层）────────────────────────────────────────────┐
│ code_agent_proposer.resolve_diff: 三形态(A/B/C) append 前     │
│   detect_always_false(line, new) → 命中返回 (False, reason)   │
│   → 带病候选绝不进入 apply                                    │
└──────────────────────────────────────────────────────────────┘
┌─ 第二层（运行时）────────────────────────────────────────────┐
│ outer_loop.apply_precheck: pair 循环 先于锚点计数检测          │
│   detect_always_false(old, new) → 命中返回 (False, reason)     │
│   → 记录 apply_precheck_failed（零评估预算）                   │
└──────────────────────────────────────────────────────────────┘
┌─ 第三层（共享检测器，variants.detect_always_false）───────────┐
│ 1. 自引用比较:  \b(\w+)\s*(<=|>=|<|>)\s*\1\b                  │
│    dist < dist (恒 False) / d <= d (恒 True) → 无信息量       │
│ 2. 空条件:      \b(if|elif|while)\s*[:(]?\s*[)]?\s*:          │
│    if: / if (): / while : → 语法级恒错                        │
│ 3. 恒 False 字面量: \b(if|elif|while)\s+(0(?:\.0+)?(?![\d.])  │
│    |False|None)\b  → if 0: / while False: / if 0.0: / elif    │
│    None: → 分支不可达                                         │
│ 负向前瞻 (?![\d.]) 防误报: if 0.5: (非零真值) 不拦截           │
└──────────────────────────────────────────────────────────────┘
```

## 3. 验收证据

### 3.1 三端回归全绿（验收②）
| 套件 | 基线 | P1 后 | 结果 |
|------|------|-------|------|
| Windows（顶层 tests 除 mujoco） | 57/57 | 57/57 | ✅ |
| WSL（顶层 tests 含 mujoco） | 73/73 | 73/73 | ✅ |
| meta_harness | 48/48 | **65/65**（+17） | ✅ |

### 3.2 恒 False 候选被拦截（验收③，≥1）
| 用例 | 模式 | 拦截层 | 结果 |
|------|------|--------|------|
| test_af_self_cmp_lt_blocks | `if dist < dist:` | detect_always_false | ✅ 恒 False |
| test_af_self_cmp_le_verdict_true | `if d <= d:` | detect_always_false | ✅ 恒 True |
| test_af_empty_cond_blocks | `if:` / `if ():` / `while :` | detect_always_false | ✅ |
| test_af_false_literal_blocks | `if 0:` / `while False:` / `if 0.0:` / `elif None:` | detect_always_false | ✅ |
| test_af_checks_old_line_too | old 行含恒 False | detect_always_false | ✅ |
| test_resolve_diff_blocks_self_cmp | 形态 B 候选 new 自引用 | **生成层 resolve_diff** | ✅ |
| test_resolve_diff_blocks_false_literal | 形态 A 候选 new `if 0:` | **生成层 resolve_diff** | ✅ |
| test_precheck_blocks_self_cmp | expected 正确仍拦截 | **运行时 apply_precheck** | ✅ |
| test_precheck_blocks_false_literal | `if 0:` | **运行时 apply_precheck** | ✅ |
| test_precheck_blocks_old_line_always_false | old 坏行 | **运行时 apply_precheck** | ✅ |
| test_run_round_records_apply_precheck_failed_for_self_cmp | 集成：s20_bad 记录 + 零评估 | **run_round** | ✅ |

### 3.3 防误报负例（7 个）
`dist < 0.20`、`opponent_angle > 15`、`momentum = net * TIMESTEP`、`if (dist < 0.20):`、`while d > 0.1:`、`if 0.5:`、`if 1:` → 全部不拦截 ✅

### 3.4 真实运行零误报（S20_P2DATA）
5 轮请求：3 轮后探索饱和停止；种子候选 9 次评估全部干净 apply（**无 apply_precheck_failed 记录**）
→ P1 检测器对真实工作树锚点零误报（含 `BETWEEN(...)`、`dist < 0.20`、`TIMESTEP*1.0` 等既有模式）

## 4. 运行数据（未提交，RL-4 保留）
- `_tmp/s20_p2data_run.log`：S20_P2DATA 运行日志
- `governance/meta_harness/meta_decisions.jsonl`：9 条 diff_gate（6 SUSPICIOUS + 3 INCONCLUSIVE）+ 1 条 stagnation
- 快照：`variants/_snapshots/20260808_*`

## 5. 关联
- ROADMAP_v2 §11.16；failure_analysis FP-MC-018；pareto_frontier Sprint 20 运行记录
- P2 设计：docs/engineering/s20_p2_distill_design_20260808.md（触发条件已满足）
