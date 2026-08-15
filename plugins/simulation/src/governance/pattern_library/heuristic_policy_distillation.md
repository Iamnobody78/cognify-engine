---
name: heuristic_policy_distillation
type: optimization-pattern
symptom_keywords:
  - rule-chain latency
  - heuristic decision chain
  - inference latency
  - embedded deployment
  - behavior cloning
  - distillation
  - MLP policy
  - lightweight policy
  - 规则链延迟
  - 蒸馏
  - 轻量策略
parameters:
  trigger: "heuristic 规则链 (多层 if-elif + 模拟量比较) 每次决策遍历全部分支; 需实时/嵌入式部署"
  symptom: "教师启发式门分数 100% 但决策延迟 28.4ms/步; 实时性受限"
  diagnostic: "教师 select_action 平均 28.4ms (1000 次实测); 分支遍历无固定计算图"
  fix:
    - "以当前最优 heuristic Harness 为教师 (force_heuristic=True), 9 维 obs → 采集演示 (200 eps, 99% 教师胜率)"
    - "学生 = 3 层 MLP (NanoQNet9: 9→hidden→21, hidden=24, 1,365 params, 8.5KB)"
    - "BC 交叉熵训练 60 epochs, val_acc 91.1% → 门级等效 (10/10 PASS)"
    - "env 按对手组复用 (避免防御性对手 speed_scale=0.40 的逐 ep 重建开销)"
  counters: "教师代码零改动; sentinel 修复 (`_heuristic_notified`) 保证日志不重复打印"
validation:
  metrics: "学生门分数 100% (≥90% 目标); 延迟 318.1x speedup (89.3μs vs 28.4ms, ≥10x 目标); 防御性 avg_steps 180 < 教师 216"
  sessions: "eval_s60_nano.py + v9_gate_evaluator --agent rl --model 双接入点 × 10-episode"
  date: "2026-08-10 (Sprint 60)"
  status: "validated"
notes: "核心洞见: (1) 延迟收益主要来自'无分支固定计算图'而非模型小本身; (2) val_acc 91% 即达门级等效 — 门测试决策边界宽于 val 分布, 无需 100% 模仿; (3) 蒸馏学生隐式压缩了教师早期探测行为 (defensive 216→180 步)"
