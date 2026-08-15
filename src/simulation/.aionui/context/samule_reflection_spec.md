# Failure Analysis — SAMULE 三层反思结构 (Queue #5 备选实验)

> 升级: 2026-08-05 — QA 质检建议 3 落地 (本能接收闭环)
> 依据: SAMULE (EMNLP 2025, 三层反思合成: 微观/中观/宏观)
> 状态: 规格已定, 挂载 Queue #5 观察清单 — TASK-005 调参完成后用此层反思审计失败片段
> 注意: 本文件为**活动格式规范**; 历史 INT8 量化分析保留在 `reports/failure_analysis.md`

## 三层结构

### 微观层（即时动作）— Single-Trajectory

单步指令的扭转/移动失败日志。每条记录:

```yaml
micro:
  ts: "ISO8601"
  context: "episode/step/obs摘要"
  action_taken: "action_id"
  action_intended: "branch"
  failure: "描述 (撞缘/转向不足/冲撞)"
  correction: "下一步修复动作"
```

### 中观层（片段策略）— Intra-Task

连续 5 步内的决策链崩塌检测。用于识别"策略模式错误"
（如 aggressive 接近时持续转向不足 → 蛇形/绕圈）。每条记录:

```yaml
meso:
  window: "episode 5-step 序列"
  pattern: "检测到的模式 (蛇形/停滞/绕圈/直冲)"
  divergence_point: "第N步与成功变体分歧"
  hypothesis: "根因假设 (增益不足/阈值错位/分支优先级)"
  validate: "如何在 Gazebo 验证"
```

### 宏观层（系统能力）— Inter-Task

门回归整体漂移 / 物理引擎根因。跨任务可迁移洞察:

```yaml
macro:
  scope: "gate/motor/physics/scheduler"
  metric: "门回归 baseline 对比"
  drift: "delta 与归因"
  root_cause: "引擎级根因 (如 DEBT-016 摩擦语义)"
  systemic_fix: "系统级修复 (如 21-action 表/FW_MAX)"
```

## 与 Meta-Harness 双环对接

- 微观 → 内环单次迭代失败轨迹 (lineage 追加)
- 中观 → 内环候选变体分歧点分析 (3 变体因果推理)
- 宏观 → 外环能力基线更新 (agent_registry.yaml)

## 触发时机

- TASK-005d 调参每轮失败后: 记录微观+中观
- 门回归每周/每次物理引擎改动后: 记录宏观
