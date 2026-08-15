---
name: imu-bias-drift
type: sensor_degradation
symptom_keywords: ["IMU", "零偏", "bias drift", "温度漂移", "temperature drift", "零速漂移", "zero-velocity drift", "加速度计偏置", "accelerometer bias", "陀螺偏置", "gyro bias", "积分漂移", "integral drift", "yaw漂移", "yaw drift", "纯DR", "pure-DR", "角度漂移", "angle drift"]
sensor: IMU
axis: "3D (gyro + accel)"
parameters:
  bias_warmup_sec: "300s (温漂稳定时间)"
  bias_calib_method: "静止初始化 (stationary init)"
  gyro_bias_bound: "0.01 deg/s"
  accel_bias_bound: "0.05 m/s^2"
  drift_rate_alert: "yaw > 0.5 deg/min"
  temp_coeff: "0.001 deg/s/C (典型 MEMS)"
validation:
  scenario: "NCLT 真实 IMU 融合"
  zero_bias_openloop_yaw: "107.8 deg/30min (未补偿)"
  synthetic_zero_bias: "0.000 deg (理想)"
  fusion_benefit: "yaw 17.52deg -> 1.08deg (S50 实证)"
  note: "零偏是累积型错误, 融合必要性量化证据"
discovered: "Sprint 49-50 (NCLT 真实 IMU 集成)"
rule: "RULE-MC-012: 真实传感器必须有零偏补偿, 合成数据掩盖退化"
---

# 模式：IMU 零偏漂移 (Sensor Degradation)

> 从 Sprint 49/50 NCLT 真实 IMU 集成经验固化 · 融合必要性量化证据

## 1. 症状特征（检测输入）

| 特征 | 典型值 | 数据来源 |
| :--- | :--- | :--- |
| 零偏积分漂移 | 107.8° yaw / 30min（未补偿） | 静止零偏积分 |
| 合成数据表现 | 0.000°（掩盖问题！） | 合成 IMU |
| 温度漂移 | 0.001-0.01 deg/s/°C | MEMS 数据手册 |
| 温漂稳定时间 | 300s 左右（上电后） | 实测 |
| 融合后 yaw | 17.52° → 1.08°（S50） | EKF 融合 |

## 2. 根因机制

1. **触发**：真实 MEMS IMU 存在常值零偏（bias ≠ 0），上电初始未被标定
2. **放大**：零偏积分 → 角度持续漂移（θ = ∫bias dt）→ 位置二次积分误差爆炸
3. **掩盖**：合成 IMU 零偏 = 0 → 一切仿真指标虚高 → 真实部署暴露差距

## 3. 修复参数（可直接复用）

| 参数 | 值 | 设计意图 |
| :--- | :--- | :--- |
| 静止初始化 | 上电后静止 ≥5s 采集 | 估计初始零偏 |
| gyro_bias_bound | 0.01 deg/s | 零偏估计上限检查 |
| accel_bias_bound | 0.05 m/s² | 重力对齐检查 |
| 温度补偿 | 线性/多项式拟合 | 温漂抑制 |
| 融合 | EKF 状态含 bias 估计 | 在线补偿残余零偏 |

**机理**：bias 进入 EKF 状态向量 → 观测校正持续估计 → 等效零偏被在线吸收 → 漂移率降至噪声水平。

## 4. 适用条件与边界

- ✅ 适用：任何真实 MEMS IMU 集成、长时纯 DR、温度变化环境
- ⚠️ 注意：合成数据验证**不能**证明零偏处理正确——必须用真实数据
- ⚠️ 注意：NCLT 数据集有真实 IMU，KITTI 是合成（零偏=0）
- ❌ 不适用：零偏已被硬件级补偿的光纤陀螺（FOG）
- 回滚方案：关闭 bias 状态估计 → 回到固定零偏假设

## 5. 验证结果（Sprint 49/50 实证）

| 指标 | 未补偿 | 融合后 | 变化 |
| :--- | :--- | :--- | :--- |
| yaw RMSE | 107.8° (open-loop) | 1.08° (S50) | **-99.0%** |
| 融合必要性 | 107.8° vs 0.000° | 量化证据 | 合成数据误导 |

## 6. 复用入口（诊断新退化时）

```
python governance/meta_harness/pattern_retrieval.py --query "IMU temperature bias drift yaw drift pure-DR"
# 期望命中本模式, 输出 bias 补偿参数 + 验证统计 + 回滚方案
```
