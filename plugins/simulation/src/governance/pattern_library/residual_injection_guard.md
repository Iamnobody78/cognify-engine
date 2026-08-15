---
name: residual_injection_guard
type: research-derived-pattern
symptom_keywords:
  - lightweight policy robustness
  - safety guard
  - residual injection
  - rule + learned hybrid
  - 轻量策略鲁棒性
  - 安全守卫
  - 残差注入
  - 规则+学习混合
parameters:
  trigger: "学生 MLP 已过门但无显式安全边界; 需在不损害预训练知识下增强危险态鲁棒性"
  symptom: "纯 MLP 在训练分布边缘 (临界边缘状态) 无安全保证"
  diagnostic: "nominal play 守卫激活占比 < 0.5 则注入合理 (BottleSumo: circler 轨迹验证)"
  fix:
    - "学生 MLP 为主干 (预训练知识精确保持)"
    - "规则守卫残差: 仅当任一 edge < edge_critical 时接管 (与守卫自身触发线一致!)"
    - "CLI: --agent residual --model <student.pt>"
  counters: "激活线必须用 CRITICAL 而非 danger 告警带 (RULE-DI-008); 误用导致过度干预"
validation:
  metrics: "residual 学生门分数 ≥ 90%; safe 态延迟 = 纯学生 (近零开销); danger 态守卫接管"
  sessions: "v9_gate_evaluator --agent residual --model + test_s61_research_r0.py"
  date: "2026-08-10 (Sprint 61)"
  status: "validated"
notes: "源自 MoDE-VLA (arXiv:2603.08122) residual injection + ReTouch (arXiv:2608.01824) 闭环精化; 帕累托改进: 安全态 0 干扰, 危险态守卫接管, 两者不冲突"
