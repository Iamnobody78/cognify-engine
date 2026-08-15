---
name: defensive_shove_stalemate
type: adversarial-pattern
symptom_keywords:
  - defensive opponent
  - shove counter-push
  - edge stalemate
  - straight-line charge
  - REV_SLOW loop
  - sawtooth streak
  - timeout draw
  - 反冲拉锯
  - 边缘死循环
parameters:
  trigger: "opp_dist < 0.4 → opponent HARD_FORWARD (直线反冲)"
  symptom: "攻击方直线逼近 → 被反冲推至边缘 → 直线后退 → 再直线逼近 (500步超时)"
  diagnostic: "branch_hist 中 SR-001/edge_f 占比 >50% (实测 58%), avg_steps 接近 MAX_STEPS"
  fix:
    - "反冲区边缘正对 → 侧向曲线绕行 (shove_dist=0.45, vectored), 不直线冲锋"
    - "直线冲锋收紧至反冲区以内 (charge_dist=0.35)"
    - "连续前缘规避后强制横向转向 (edge_f_turn_streak=3, 选更开阔侧)"
  counters: "无环境改动; 仅策略层; 确定性方向选择 (edge_l/edge_r 比较)"
validation:
  metrics: "defensive 胜率 50%→100%; avg_steps 334→216; heuristic 全门 90%→100%"
  sessions: "v9_gate_evaluator lightweight 10-episode × 3 轮复现"
  date: "2026-08-10 (Sprint 59)"
  status: "validated"
notes: "跨域启示: '单步安全立即重置计数器' 是通用陷阱 (锯齿饥饿); 需脱离守卫 (2+ 步安全才重置)"
