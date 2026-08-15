---
name: intervention_censored_distillation
type: research-derived-pattern
symptom_keywords:
  - distillation noise
  - guard branches
  - teacher intervention
  - behavior cloning
  - mimicry
  - 蒸馏噪声
  - 守卫干预
  - 行为克隆
parameters:
  trigger: "教师策略含安全/规避守卫分支; 蒸馏时守卫触发样本与策略样本混训"
  symptom: "学生模仿守卫反射 (edge escape/curve dodge) 而非策略决策; 蒸馏保真度被噪声稀释"
  diagnostic: "trace branch 字段显示守卫分支占比高 (BottleSumo 实测 32.8%)"
  fix:
    - "采集时用 select_action_traced() 逐帧记录 branch → guard_mask"
    - "BC 损失按样本加权: 守卫样本 weight=0.25, 策略样本 weight=1.0 (intervention-censored)"
    - "权重可调 (--intervention-weight); 1.0 = 纯 BC 对照"
  counters: "源自 TORL-VLA (arXiv:2606.09337) intervention-censored critic 的蒸馏版移植"
validation:
  metrics: "学生门分数 ≥ 90%; val_acc 不低于纯 BC; guard 占比报告"
  sessions: "distill_s60_heuristic.py --intervention-weight 0.25 + test_s61_research_r0.py"
  date: "2026-08-10 (Sprint 61)"
  status: "validated"
notes: "核心洞见: 守卫动作是教师对危险状态的'干预'而非自主决策 — 干预后的成功不应归因于干预前动作 (TORL-VLA 核心命题); 蒸馏版 = 损失降权而非状态过滤, 保留教师行为分布"
