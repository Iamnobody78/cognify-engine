# BottleSumo Domain Spec (Meta-Harness)

> Stanford IRIS Lab Meta-Harness (arXiv:2603.28052) 域规范 — BottleSumo 定制
> 版本: v1.1 | 日期: 2026-08-07 | 状态: 生效
> **ONBOARDING 对齐 (v1.1, 2026-08-07)**: 对照官方 ONBOARDING.md 强制字段补全
> （Problem framing / Harness definition / Evaluation / Baselines / Offline / Online / Budget），
> 明确 search-set 与 held-out test 隔离声明。

---

## 0. Problem Framing（问题框架，ONBOARDING 强制字段）

- **用户想改进什么**: BottleSumo 机器人相扑的**胜率与效率**（门回归 winrate + 步数）。
  改进单位是 **Harness 代码层**（感知→动作的转换逻辑），非策略模型权重。
- **评估单位**: 单次门评估 = 5 对手 × 2 局 = 10 局（确定性种子）；验收 = 20 局门回归
  （V9_WINRATE_THRESHOLD = 0.6）。
- **固定项（不可变）**: 策略模型（ABDL 引擎）、动作枚举（21 离散）、评估器裁判逻辑、
  基座模型 qwen2.5:7b（Harness 优化围绕固定基座进行，不修改模型权重）。
- **可变项（搜索空间）**: 5 个 Harness 文件（见 §1）的参数与逻辑。
- **基座模型**: qwen2.5:7b（本地 Ollama，CPU 推理，~1.7 token/s）。
- **总预算**: 见 §7 Budget。

## 1. Harness Definition（Harness 接口，ONBOARDING 强制字段）

Harness = 包围固定策略模型外部的**代码层**, 决定行为如何从感知转化为动作。
BottleSumo lightweight_env 门的 Harness 由 5 个文件构成 (全部真实磁盘路径):

| 文件 | 角色 | 可调参数示例 |
|------|------|-------------|
| `governance/meta_language/simulation_rules.abdl` | 声明式规则引擎 (13 条: L0 安全/L1 战术/L2 高级/L3 心理) | 优先级、角度窗口、距离门、edge 门 |
| `core/meta_language/abdl_action_bridge.py` | 策略→离散动作映射 (PolicyID→Action) | 侧翼分档阈值 (45°/0.20m)、推力动作选择 |
| `simulation/lightweight_env.py` | 物理/观测 (推力碰撞、抓地衰减、出生朝向) | `_resolve_collision` 动量系数、DOHYO 常量 |
| `simulation/reward_functions.py` | V10Reward 权重 | 边缘惩罚、推进奖励、terminal 阈值 |
| `simulation/v9_gate_evaluator.py` | 对手档案 (5 策略) 与门聚合 | OpponentStrategies 常量、阈值 |

- **输入/输出契约**: Harness 文件被策略模型在运行时 import/读取；候选 = 文件内容 diff。
- **状态维护**: 候选评估前 git 快照（`variants/_snapshots/<ts>/` 5 文件），评估后恢复。
- **写作用域 (allowed_write_paths)**: 仅上述 5 文件可被候选修改；禁止修改
  `governance/meta_language/*.abdl` 规则语法之外的文件、评估器裁判逻辑、测试套件。

**非 Harness** (固定): 策略模型 (ABDL 引擎本身)、动作枚举 (21 离散)。

## 2. Evaluation（评估协议，ONBOARDING 强制字段）

```
evaluate(working_tree) -> {
  "score":      winrate ∈ [0,1], 阈值 0.6 (V9_WINRATE_THRESHOLD),
  "passed":     bool,
  "cost":       {"wall_s": float, "total_steps": int, "episodes": int},
  "trajectory": {per_strategy winrate/avg_steps, episode_results[steps,reward,win,mode]}
}
```

- **基准**: 5 对手 × 2 局 = 10 局, 种子确定 (`_stable_seed(episode_idx, opponent)`),
  确定性可复现。
- **胜利判定**: `terminated AND reward > 5` (真实出界, 非奖励通胀)。
- **效率轴**: wall-clock 秒 + 总步数 (僵局=240 步超时 为失败信号)。
- **执行**: `python3 governance/meta_harness/evaluator_v9.py [--episodes 10]`

### 2.1 search-set 与 held-out test 隔离声明（ONBOARDING 强制）

- **search-set**（进化暴露集）: 门回归 10-20 局，使用确定性种子
  `_stable_seed(episode_idx, opponent)`——**候选生成与选择完全基于此集**。
- **held-out test**（隔离验证集）: 未参与进化的种子区间与场景组合（如
  `seed_offset >= 1000` 的对手/局组合、未在 search-set 使用的 edge 场景变体）。
  **进化过程中绝不暴露**；仅在 Sprint 收官时用于最终验收（防过拟合 search-set）。
- **隔离机制**: 评估器通过 `--heldout` 标志启用 held-out 种子；候选进化路径
  （outer_loop 评估）恒用 search-set 种子，held-out 种子仅手动/收官触发。

## 3. 候选 Harness 格式 (变体)

候选 = git 工作树快照 + 元数据 JSON:
```json
{
  "id": "t005d_hybrid_flank",
  "parent": "970c209",
  "changed": ["abdl_action_bridge.py", "simulation_rules.abdl"],
  "hypothesis": "dist<0.20 压进→弧线保推力; 退缩→纯转收敛",
  "evidence": ["F-106 侧接触锁定 -37°"],
  "score": {"winrate": 1.0, "passed": true}
}
```
- 变体保存于 `governance/meta_harness/variants/<id>/` (规则快照 + meta.json)
- 血缘: git 提交历史 + `failure_analysis.md` (F-100..F-106) + `pareto_frontier.md`

## 4. 提议器职责 (Agent 即 Proposer)

1. 读取血缘: `failure_analysis.md`, `pareto_frontier.md`, 上一变体 meta.json
2. 对每个候选回答三个因果问题:
   - 上一轮为什么失败? (失败模式编号 F-xxx)
   - 与成功变体在哪个决策节点分歧?
   - 如何精准修复而不破坏其他模块?
3. 单次迭代只改 1 个假说, 评估, 更新 Pareto, 记录。
4. **（v1.1 编码代理升级）**: Proposer 以编码代理模式运行（`--proposer code_agent --agent`），
   支持受限文件读取（只读 5 文件 + 血缘）与工具调用循环；候选生成仍经三形态 diff 契约
   确定性落地（anchor 唯一性校验），LLM 不做自由源码编辑。

## 5. 进化循环触发

| 触发 | 动作 |
|------|------|
| V9 门 < 0.6 或连续 3 轮胜率降 >10% | 启动外环: 提议→评估→分析→再提议 |
| Harness 文件被修改 | 自动触发候选生成 (3 变体) + 快速评估 (10 局) |
| 用户说"调度器不工作/优化决策逻辑" | 同上 |
| 前沿无进展 (Pareto 2 轮不变) | 停止迭代, 报告 |

## 6. Baselines（基线，ONBOARDING 强制字段）

- **基线 Harness**（970c209, 2026-08-05）: winrate 1.0 (10/10), 阈值 0.6 → PASS；
  aggressive 2/2 (16-24 步), defensive 2/2 (75-80 步), 零超时；~10 局 ≈ 60-90s wall。
- **里程碑基线（418 视觉闭环, TASK-006b）**: 门分数 1.0, 步数 418（视觉轨独立计数）。
- **规则轨基线（214 步, abdl 模式）**: GRIP_DECAY=0.08（P0 多轮迭代收敛值，PM 定稿）。
- **预期改进空间**: 胜率已达 1.0 上限——主要改进方向为**步数效率**（214 → 更少）
  与**鲁棒性**（held-out 场景不劣化）。

## 7. Budget（预算，ONBOARDING 强制字段）

| 维度 | 预算 | 备注 |
|------|------|------|
| 候选数/迭代 | 每任务 ≤ 5 轮（outer_loop `--iterations` 上限）；单轮 ≤ 3 候选 | 超限停止（探索饱和 3 轮无有效 → 停） |
| wall-clock | 单轮 ≤ 500s（LLM 生成 ≤ 480s timeout + 评估 ~90s） | P2-V4 触发阈值：>500s 执行压缩方案 |
| token 预算 | 单轮 prompt ≤ 3200 tokens + completion ≤ 250（num_ctx 4096） | 超出自动截断/重试 |
| 检索预算 | bge-m3 索引一次性 ~124s + 每轮检索 ≤ 15s | `_cache/semantic_index.json` 缓存 |
| 迭代总时长 | 5 轮验收 ~35-45 min | CPU 推理场景实测 |

## 8. Offline Experience（离线经验，ONBOARDING 强制字段）

- **先前运行轨迹**: `experience/sessions.jsonl`（每轮 prompt/completion/duration/有效候选）。
- **假设-结果配对**: `experience/hypotheses.jsonl`（confirmed/rejected + 置信度）。
- **失败模式库**: `failure_analysis.md`（F-100..F-106 缺陷描述 + 轮次记录）。
- **Pareto 演化**: `pareto_frontier.md`（ROUND 1-11 + P0/P1/P2 迭代全记录）。
- **候选快照**: `variants/_snapshots/<ts>/`（5 文件快照 + 保留变体报告）。
- **领域文档**: 本 domain_spec.md、`meta_harness_academic_alignment.md`（MHA-ARCH v1.0）。

## 9. Online Experience（在线经验，ONBOARDING 强制字段）

- **运行时学习**: 假设检验闭环（record_hypothesis → 命中率注入下次提议）—
  P0-V2 已实现；命中率 confirmed/rejected 计数注入系统提示。
- **自指改进**: meta_config 门裁决（P2-V4）— 连续 2 轮无效自动调整提议器参数，
  裁决历史 `meta_decisions.jsonl` 供后续迭代参考。
- **语义检索**: P1-V3 bge-m3 检索三源血缘（failure/pareto/hypotheses），
  检索结果注入系统提示（来源标注）——历史经验在运行时被主动利用。

## 10. ONBOARDING 元信息

- **onboarded 声明**: 本领域于 2026-08-05 首次 onboard（v1.0），
  2026-08-07 对照官方 ONBOARDING.md 强制字段补全（v1.1）。
- **聚焦问题迭代**: BottleSumo 领域通过 2 轮聚焦问题确认——
  (1) 评估单位与阈值（10 局 winrate 0.6）; (2) 搜索空间边界（5 文件，禁改裁判逻辑）。
- **held-out test 声明**: 见 §2.1（search-set = 确定性门回归；held-out = 未使用种子保留）。
