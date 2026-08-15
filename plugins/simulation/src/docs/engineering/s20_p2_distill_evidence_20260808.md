# Sprint 20/21 P2 自蒸馏 M1+M3 — 证据文档（2026-08-08）

> 依据：PM Sprint 20 裁决（M1+M3 优先、M2 延后、不触发 V9 门、独立证据文档简化格式）
> 分支：`feature/sprint21_p2_distill`（基线 main@b60fa22 + tag sprint20-closed）
> 学术对齐：EvolveR 闭环（离线蒸馏→在线检索）、arXiv 2607.17558（防 decoding collapse：蒸馏结构化判定语义而非 LLM 自由文本）、EDV（Execute→Distill→Verify）

## 1. 蒸馏数据来源与字段映射

| 数据源 | 消费字段 | 蒸馏资产 |
|--------|----------|----------|
| `meta_decisions.jsonl`（type=diff_gate） | `diff_verdict`（确定性标签）、`layer`、`score`（winrate 饱和判定）、`ts`、`reason`（指纹差异类别） | D1 失敏检测 / D2 扰动先验 / D3 多样性 |
| `mcp_usage_report.jsonl` | `tool`、`duration_ms`、`status` | D3 上下文（元认知工具分布） |
| `experience/distill_rules_<ts>.json`（输出） | 版本化规则（meta + d1/d2/d3 + stats） | 供 M3 提示与后续种子参数化消费 |

**结构化蒸馏定义**（防 decoding collapse）：每条蒸馏规则 = `{id, source, layer, signal(结构化), verdict(确定性), action(模板), evidence(reason)}`——不引入 LLM 自由文本生成，教师 = 门禁判定（无教师漂移）。

## 2. M1 实现（distill_loop.py，226 行）

```
distill_loop.py
├─ load_jsonl: 容错空行/坏行
├─ filter_diff_gate: type 过滤 + verdict 白名单
├─ distill_d1: SUSPICIOUS -> 失敏规则 (winrate 饱和 -> 次级信号降级)
├─ distill_d2: INCONCLUSIVE -> 扰动先验 (层 -> D2_PRIOR 表: 角度>=10°/阈值>=20%/系数>=0.2)
├─ distill_d3: layer x verdict 矩阵 + MCP 工具分布
├─ write_rules: 版本化 JSON (experience/distill_rules_<ts>.json)
└─ run/main: --since 时间过滤, --decisions/--mcp/--out 参数化
```

## 3. M3 实现（code_agent_proposer.py）

`PERTURBATION_PRIOR` 常量（三类行为感知阈值，从 S19/S20 INCONCLUSIVE 案例归纳）→ `build_system_prompt` 硬约束第 4 条注入：
- 角度锚点（BETWEEN/abs 比较）：变化 ≥ 10 度
- 数值阈值（dist/score 常量）：变化 ≥ 20%
- 物理系数（momentum/decay/TIMESTEP 乘数）：变化 ≥ 0.2

## 4. M1+M3 验收

| 项 | 结果 |
|----|------|
| 新增测试 | `test_distill_loop.py` 18 用例（load/filter/D1/D2/D3/write/run/since + M3 提示注入/常量/不破坏既有 prompt） |
| meta_harness 全量 | **83/83**（65+18） |
| 三端回归 | Windows 57/57 + WSL 73/73（P1 未回归，本 Sprint 改动仅 meta_harness 内，基线保持） |

## 5. M1 真实数据蒸馏结果

### 5.1 基线蒸馏（--since 20260808，S19_VERIFY+S20_P2DATA 合并 19 条）
```
diff_gate_total=19 | SUSPICIOUS=12 (全饱和) | INCONCLUSIVE=7
layer x verdict:  rules→INCONCLUSIVE 7/7 | mapping→SUSPICIOUS 6/6 | physics→SUSPICIOUS 6/6
```

### 5.2 S21 运行（S21_M1M3，5 轮请求 → 3 轮后探索饱和）
```
diff_gate_total=9 | SUSPICIOUS=6 (全饱和) | INCONCLUSIVE=3
layer x verdict:  rules→INCONCLUSIVE 3/3 | mapping→SUSPICIOUS 3/3 | physics→SUSPICIOUS 3/3
```
判定分布与 S19/S20 **完全同构**（rules 层扰动系统性不足 → INCONCLUSIVE；mapping/physics 扰动产生行为变化但 winrate 饱和失敏 → SUSPICIOUS）。

### 5.3 跨轮判定分布（P2 闭环数据基线）
| 运行 | 请求轮 | 实际轮 | 评估 | INCONCLUSIVE | SUSPICIOUS | PASSED | apply_precheck_failed |
|------|--------|--------|------|--------------|------------|--------|----------------------|
| S19_VERIFY | 5 | 3 | 9 | 3 | 6 | 0 | 0 |
| S20_P2DATA | 5 | 3 | 9 | 3 | 6 | 0 | 0 |
| S21_M1M3 | 5 | 3 | 9 | 3 | 6 | 0 | 0 |
| **合计** | | | **27** | **9** | **18** | **0** | **0** |

## 6. 关键发现（待 PM 裁决）

**F1：M3 落点缺口——种子路径未受益**。真实运行候选源是 `_seed_variants` 种子（mh_*_seed_002，模板参数小幅扰动），不走 LLM prompt；M3 注入的 `build_system_prompt` 只影响 LLM 提议路径。种子扰动幅度由 `_seed_variants` 参数模板决定（如 BETWEEN(-10,10)→(-8,8)，仅 2° 变化，远低于 M3 先验 10°）——**D2 蒸馏规则（角度≥10°）未被种子路径消费**，闭环断点。

**F2：D2 闭环缺口**。distill_loop 的 D2 输出已确认 rules 层扰动不足（7+3 条 INCONCLUSIVE），但 `_seed_variants` 无扰动幅度校验/参数化入口。

**F3：D1 失敏信号 27/27 全饱和**。mapping/physics 层 SUSPICIOUS 全部 winrate=1.0 饱和——D1 规则已归纳（评估层降级到次级信号），M2（评估层重构）的决策依据充分但按裁决延后。

**建议（Sprint 21 后续候选）**：
1. **M3 扩展**：`_seed_variants` 消费 D2_PRIOR（扰动幅度参数化：种子生成时校验 |new-old| 变化 ≥ 层阈值，不足则加大扰动或跳过）——补齐闭环断点，预期 rules 层 INCONCLUSIVE 下降
2. M2 仍按裁决延后，待 M3 扩展后重跑 5 轮再评估

## 7. 运行数据（未提交，RL-4 保留）
- `_tmp/s21_m1m3_run.log`；`governance/meta_harness/meta_decisions.jsonl`（+9 条 diff_gate）
- `experience/distill_rules_20260808_131140.json`（基线）、`distill_rules_20260808_131249.json`（S21）
- 快照 `variants/_snapshots/20260808_1311*`
