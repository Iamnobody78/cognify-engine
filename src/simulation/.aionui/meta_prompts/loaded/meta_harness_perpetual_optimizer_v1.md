# Meta-Harness 永续优化器 v1.0 (Perpetual Optimizer)

> 装载: 2026-08-05 | 来源: PM 授权 P1 (会话 48324704)
> ⚠️ 出处说明 (provenance): PM 原文在上下文压缩中丢失 (磁盘/会话状态/记忆均无逐字副本)。
> 本文件依据会话压缩记录中保留的协议要素 **忠实重建** (5 步循环、物理约束、
> HALT/STOP 终止词、输出格式、禁忌项), 未新增任何未授权内容。若 PM 持有原文,
> 请以原文覆盖本文件。

---

## 0. 定位

**永续优化器** = 双环协议内环 (学术层) 的常驻执行体, 由 `variants.py` (变体生成)
+ `outer_loop.py` (外环编排) + `evaluator_v9.py` (评估器) 共同实现。
不是一次性的调参脚本, 而是一个 **永不主动停机** 的演化循环 —
除非出现终止词、达到 MAX_ITERATIONS、或探索饱和。

## 1. 硬约束 (物理 + 法规)

### 物理约束 (违反即废案)
| 量 | 上限 | 依据 |
|----|------|------|
| 直线速度 | ≤ 0.534 m/s | 实测标定 steady_v 0.5279 (步进响应 20260805_140916) |
| 角速度 | ≤ 4.0 rad/s | 电机/陀螺仪规格 |

任何变体不得要求机器人超过上述物理极限。

### 法规约束 (可视化)
- 所有训练/调试/评估必须 GUI 可见 (Rerun Web Viewer localhost:9090)。
- 无头 (headless) 运行仅限 PM 批准的执行器 (V9 门批次 = 已批准 harness)。
- Web Viewer :9090 是未来一切变更的强制回归基线。

## 2. 五步永续循环 (每轮必须完整执行)

```
┌─────────────────────────────────────────────────────────────┐
│  ROUND n                                                      │
│                                                               │
│  ① 快照 (Snapshot)                                            │
│     复制 5 个 Harness 文件 → variants/_snapshots/<ts>/        │
│     记录当前胜率/效率 (Pareto 前沿最新点)                      │
│                                                               │
│  ② 生成 3 个变体 (Generate)                                   │
│     读取 failure_analysis.md (F-100..F-106)                   │
│     读取 pareto_frontier.md (TASK-005d 表)                    │
│     输出 3 候选: 规则层 / 映射层 / 物理层 各 1                 │
│     每个变体必须携带: id, target_file, diff,                  │
│                        hypothesis(F-xxx), bloodline           │
│                                                               │
│  ③ 评估 (Evaluate) — 本地 + GUI 验证                          │
│     evaluator_v9.py --episodes 10 (确定性种子)                │
│     必须 ≥ 1 次 GUI 目视验证 (localhost:9090)                 │
│     记录 score / passed / cost / trajectory                   │
│                                                               │
│  ④ Pareto 更新 (Update)                                       │
│     score ≥ 当前最优 → 保留, 写入 pareto_frontier.md          │
│     score < 当前最优 → 回滚 (rollback)                        │
│     禁止 "已达到最优所以跳过" — 每轮必须产出 1 个新变体        │
│                                                               │
│  ⑤ 自反思 (Self-reflection)                                   │
│     追加至 failure_analysis.md (新失败模式或证伪记录)          │
│     判断: 本轮发现了什么? 下一轮该试什么?                     │
└─────────────────────────────────────────────────────────────┘
```

## 3. 终止条件 (满足任一即停)

| 条件 | 说明 |
|------|------|
| 终止词 | `HALT` / `STOP` / `暂停优化` / `结束本次循环` |
| MAX_ITERATIONS | CLI `--iterations N`, 达 N 轮后停止 |
| 探索饱和 | 连续 3 轮全部低于 Pareto 最优 **且** 无新缺陷类别 |

> 注意: 探索饱和 ≠ "已达最优"。禁止用"已达最优"作为提前终止理由;
> 饱和必须是 **3 轮实证失败 + 无新类别** 双重条件。

## 4. 每轮输出格式 (必须遵守)

```
## ROUND n — <日期>
- 快照: <路径> (胜率 <x> / 效率 <y> 步)
- 候选:
  - <id> [规则层] 假说=<hypothesis> 依据=<F-xxx> → score=<s> <PASS/FAIL>
  - <id> [映射层] 假说=<hypothesis> 依据=<F-xxx> → score=<s> <PASS/FAIL>
  - <id> [物理层] 假说=<hypothesis> 依据=<F-xxx> → score=<s> <PASS/FAIL>
- Pareto 更新: <保持/更新> (新前沿: <list>)
- 自反思: <发现> → 下一轮建议 <action>
```

## 5. 禁忌 (Forbidden)

1. ❌ 不产出变体就直接宣称最优 ("每轮必须产出 1 个新变体")
2. ❌ 超过物理约束 (0.534 m/s / 4.0 rad/s) 的变体
3. ❌ 无 GUI 目视验证就写 PASS
4. ❌ 篡改评估结果或捏造胜率
5. ❌ 不读血缘文件 (failure_analysis.md / pareto_frontier.md) 就生成变体
6. ❌ 修改非 Harness 文件 (ABDL 引擎本体、21 离散动作枚举)
7. ❌ 单轮改多个假说 (每轮 1 个假说, 精准归因)

## 6. 变体格式 (与 domain_spec.md §3 一致)

```json
{
  "id": "mh_rules_001",
  "parent": "970c209",
  "layer": "rules",
  "target_file": "governance/meta_language/simulation_rules.abdl",
  "diff": [{"old": "...", "new": "..."}],
  "hypothesis": "一句话因果假说",
  "evidence": ["F-100"],
  "bloodline": "970c209 -> mh_rules_001",
  "score": {"winrate": null, "passed": null}
}
```

## 7. 与 V9 裁决门 / plateau_explorer 的关系

- V9 门阈值 0.6: 低于 0.6 的变体一律回滚, 并触发失败分析。
- 当前基线 1.0 (10/10, 提交 970c209 + 4fcb55c): 永续优化器在其之上
  探索效率轴 (更少步数) 与鲁棒性 (更多对手变体), 不回归质量。
- plateau_explorer 自蒸馏: 连续 3 轮胜率降 >10% 时触发 — 永续优化器
  每轮产出即是对"平原"的主动探索, 与自蒸馏互补。
