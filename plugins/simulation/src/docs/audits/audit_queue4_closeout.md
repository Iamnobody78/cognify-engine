# Queue #4 收口: 电机物理审计 + 门回归 (audit_queue4_closed)

**日期**: 2026-08-05
**状态**: ✅ CLOSED (用户 PM 签署, Tag `audit_queue4_closed`)
**范围**: Rev2 仿真物理可信度里程碑 — ME/EE/SIM 联调

---

## 1. 交付摘要

| 维度 | 结果 |
|------|------|
| V9 门 MuJoCo abdl | **80%** (模型物理化后诚实回落, 门限 60% 仍达标) |
| MuJoCo v11 | 100% (不变量) |
| MuJoCo heuristic | 60% (压线; aggressive/counter 0% = 负面基线) |
| lightweight abdl | 60% (压线) |
| 回归测试 | 61/61 + 新增 heuristic 12/12 = **73/73 全绿** |
| 双后端+对照 | 全部零破坏 |

## 2. 电机审计 (Queue #4 step 1-4, commit 2ec63f9 + 71ff4f9)

1. **型号确认**: N20 6V 300rpm 输出 (design_spec.json + controller.yaml 双源)
2. **Datasheet 参数**: 31.4 rad/s / 堵转 0.3 N·m / 0.025 kg / 2× / TB6612FNG
3. **模型统一**: urdf.xacro + rev2.sdf + mujoco_env.py + motor_spec.json (4 处矛盾修正)
4. **Gazebo 负载测试 PASS**: 轮速 31.18 rad/s = 300rpm (99.3%), odom 0.523 m/s (98%)

## 3. 关键根因链 (三层)

| 层 | 症状 | 真根因 | 修复 |
|----|------|--------|------|
| 传感器 | odom 超速 2.2e15 | probe 读取混乱 / 插件配置 | 双源探针 (odom+joint_states) |
| 引擎解析 | 机器人不动 | `<dynamics friction>` 被当粘性摩擦 → 0.2 在 31.4 rad/s 时 6.3 N·m = 堵转 21 倍 | damping=0.001 friction=0.02 (实测 300rpm ✓) |
| 阈值对齐 | 数值爆炸 1.7e47 | wheel 惯量过小 | N20 反射惯量 1.28e-4 加入 izz |

**G2 时代 Gazebo "motion proof" 是 mock 的物理根因**: 摩擦 0.2 死锁 → 本次审计真正让机器人在物理中动起来。

## 4. 裁决记录 (用户 PM 签署, 2026-08-05)

### 裁决 1: 轮径 48mm vs 34mm → 维持 34mm, DEBT-017
- **决策逻辑**: V9 门契约稳定优先; 几何校准不混入物理修复收益; HAL `wheel_radius_multiplier` 可映射。
- **行动**: motor_spec.json 追加 `sim_radius_mm=34 / physical_reference_mm=48 / status=calibration_pending`。

### 裁决 2: heuristic aggressive/counter 0% → 不热修, TASK-005 排 Queue #5 首项
- **决策逻辑**: 审计边界洁净 (物理修复 vs 策略补偿不混淆); 调参依赖 Gazebo step_response 实测角速度。
- **行动**: 魔数抽为 heuristic_config.yaml (数值零变化, 行为不变) — 本收口合入。

## 5. 代码合并 (PM 批准)

- `71ff4f9` + `6d1e5d9` + 本次收口 commit → Tag **`audit_queue4_closed`**

## 6. 遗留 (Queue #5)

- TASK-005: heuristic aggressive/counter gain retuning (触发: 接近 <0.3m, 增益 ×1.5 + 前馈)
- DEBT-017: HIL 轮径校准 (物理样机实测后反推)
- 选项 C 待裁决: counter 微调 → 高质量数据 → MuJoCo 蒸馏训练
