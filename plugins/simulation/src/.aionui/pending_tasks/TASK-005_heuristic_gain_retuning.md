# TASK-005: Heuristic aggressive/counter gain retuning

- **状态**: OPEN (已裁决, 排入 Queue #5 首项 / Sprint 5)
- **裁决人**: 用户 (coordinator), 2026-08-05, docs/audits/audit_queue4_closeout.md
- **关联**: DEBT-016 (Gazebo 不硬执行 velocity limit), heuristic_config.yaml (TASK-005 前置配置化已完成)
- **触发条件**: 接近距离 < 0.3m 时, 将转向增益从当前 Kp 提升 1.5 倍, 并启用开环前馈补偿
- **背景**: 模型物理化 (0.7→0.53 m/s) 后 MuJoCo heuristic aggressive/counter = 0%
  (旧策略依赖虚假高速冲锋)。这是物理诚实后的真实性能回落 = 有价值的负面基线。

## 待调参数 (heuristic_config.yaml → task005_retuning)

| 参数 | 当前值 (基线, 不可改) | 目标 (TASK-005 调参期) |
|------|----------------------|------------------------|
| engage_dist | 0.3 m | 按 step_response 实测标定 |
| gain_multiplier | 1.5 | 按实测转向增益标定 |
| feedforward_enabled | false | true (开环前馈) |

## 前置依赖

1. 在真实 Gazebo 跑一组 step_response (阶跃响应), 实测最大角速度 → 重算转向前馈项
   (禁止拍脑袋写死数值)。
2. 调参基于新实测最大角速度, 非旧 0.7 m/s 时代参数。

## 验收标准

- MuJoCo heuristic aggressive/counter 0% → ≥ 50% (阶段性) → 目标 90%
- 回归: lightweight/abdl/v11 baseline 不退化
- 行为回归由 tests/test_heuristic_rules.py 守护 (配置化契约)

## 配置化 (已完成, 随 audit_queue4_closed 合入)

- simulation/heuristic_config.yaml: 魔数抽出 (L0 0.15/0.1, L1 0.5/0.3, TR-002 0.8)
- v9_gate_evaluator.py: _load_heuristic_rules() 加载 + 回退默认值
- 数值与 6d1e5d9 时代完全一致, 行为零变化 (tests 12/12)
