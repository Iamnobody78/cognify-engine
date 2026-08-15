# AC5 — meta_harness 候选自动 pytest 验证

- **状态**: ✅ DOCUMENTED（设计完成，待触发；**部分能力已存在**）
- **来源**: 外部治理资源整合任务 3/AC5（"meta_harness 自进化增强"——候选策略自动 pytest 测试后合并）
- **保留决定**: 2026-08-04 修正版判定 — "自进化"能力的自然扩展，待当前只读建议器稳定后再评估

## 现状（2026-08-04 源码核查）

**✅ 沙箱已实现**（`src/meta_harness/sandbox.py`）:
- `evaluate_candidate_in_sandbox(rules, run_tests=True)`: 候选规则 → pending_rules/ 临时 YAML → 策略引擎加载校验（fail-closed）→ 子进程真实 pytest（`run_pytest_regression`, subprocess + TimeoutExpired 防护, 返回真实输出摘要"防伪造原则"）→ 命中率回放
- 测试覆盖: `tests/test_meta_harness.py`（沙箱 + 回归验证路径）

**❌ 缺口（接线层）**:
- `src/pareto/loop.py` EvolutionLoop 的 score_fn 由外部注入 — 沙箱验证**未接为循环默认评分器**；候选合并无强制"测试通过"门槛
- 无 CI/调度器持续驱动循环（融合演示为一次性 3 轮）

## 设计（待触发时实现）

```
触发（策略建议器建议 3 次以上被采纳后）:
  EvolutionLoop(propose_fn=策略建议器,
                score_fn=evaluate_candidate_in_sandbox,  # 接线点
                rounds=3) → 非支配集 → 合并前门槛:
                [0] run_pytest_regression 通过（tests_passed>0 且 0 fail）
                [1] 命中率 ≥ 当前基线
                [2] 人工/仲裁确认（人类在环, 与 P12 一致）
```

## 触发条件
1. 只读策略建议器（adapter）稳定运行 ≥3 轮且建议被采纳（证明候选质量值得自动化）
2. 或：GATE 新增"候选自动验证"检查项要求

## 不实现的原因（当前）
- adapter 为确定性规则扫描，建议质量有限且需人工裁决；自动化验证的价值在建议器"变聪明"后才显著
- 与斯坦福原版对齐时（docs/meta_harness_verification.md §建议 P1）此为第一步接线

## 相关
- docs/meta_harness_verification.md §建议 P1
- src/meta_harness/sandbox.py（能力已存在, 缺口在 loop.py 接线）
