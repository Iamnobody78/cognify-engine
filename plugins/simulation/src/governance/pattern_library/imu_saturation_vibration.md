---
name: imu-saturation-vibration
type: sensor_degradation
symptom_keywords: ["IMU", "饱和", "saturation", "振动噪声", "vibration noise", "量程超限", "range exceed", "随机游走", "random walk", "噪声放大", "noise amplification", "机械振动", "mechanical vibration", "角速率饱和", "gyro saturation", "加速度饱和", "accel saturation", "非线性失真", "nonlinear distortion"]
sensor: IMU
axis: "3D (gyro + accel)"
parameters:
  gyro_saturation: "±450 deg/s (典型 MEMS 量程)"
  accel_saturation: "±16 g (典型 MEMS 量程)"
  vibration_freq_band: "100 Hz - 1 kHz (机械振动)"
  noise_density: "0.005 deg/s/√Hz (白噪声)"
  saturation_detect: "连续 3 样本触顶"
  mitigation: "量程裕量 > 2x 或降采样"
validation:
  scenario: "高动态运动 + 车载振动"
  saturation_rate: "> 5% 样本 触顶 → 退化告警"
  vibration_effect: "角速率噪声放大 2-5x"
  note: "饱和是非线性错误, 卡尔曼白噪声假设失效"
discovered: "Sprint 57 (模式库跨域扩展)"
rule: "RULE-MC-014: 传感器饱和/振动破坏白噪声假设, 需先检测再融合"
---

# 模式：IMU 饱和与振动噪声 (Sensor Degradation)

> Sprint 57 模式库跨域扩展 · 与零偏漂移互补的第二类 IMU 退化

## 1. 症状特征（检测输入）

| 特征 | 典型值 | 数据来源 |
| :--- | :--- | :--- |
| 角速率触顶 | 连续 ≥3 样本 = 满量程 | 原始样本 |
| 加速度触顶 | 连续 ≥3 样本 = 满量程 | 原始样本 |
| 高频振动 | 100Hz-1kHz 功率谱异常 | FFT |
| 噪声方差突变 | 基线 5-10 倍 | 滑动窗口统计 |
| 随机游走 | σ(t) ∝ √t 超线性 | Allan 方差 |

## 2. 根因机制

1. **饱和**：高动态机动/撞击 → 角速率或加速度超量程 → 触顶截断 → 非线性失真
2. **振动**：机械共振/路面激励 → 噪声谱污染 → 卡尔曼白噪声假设失效
3. **放大**：白噪声假设失效 → 滤波器对噪声敏感 → 状态估计抖动 → 融合权重错误

## 3. 修复参数

| 参数 | 值 | 设计意图 |
| :--- | :--- | :--- |
| saturation_detect | 连续 3 样本触顶 | 可靠检测, 防单点误报 |
| mitigation | 量程裕量 > 2x | 硬件选型预防 |
| noise_adapt | 滑动窗口 σ² 估计 | 噪声自适应 |
| 抗混叠滤波 | 低通 < 0.5×采样率 | 振动抑制 |
| 降权策略 | 饱和段 IMU 权重 ↓ | 防错误注入 |

**机理**：噪声自适应（N = 滑动窗口 σ²）+ 饱和段降权 → 滤波器对退化段"半盲"而非"全盲"。

## 4. 适用条件与边界

- ✅ 适用：车载/机载高动态、电机振动环境、撞击场景
- ⚠️ 注意：饱和段的积分错误不可逆（非线性截断）
- ⚠️ 注意：FFT 需要足够窗长（>1s）避免频谱泄漏
- ❌ 不适用：静止环境（无振动激励）
- 回滚方案：关闭噪声自适应 → 固定 N 矩阵

## 5. 验证状态

| 维度 | 状态 |
| :--- | :--- |
| 模板复用 | ✅ frontmatter 结构与 sensor_degradation 一致 |
| 检索命中 | 待 pattern_retrieval.py 跨域查询验证 |
| 实证数据 | 文献基准 + 机理推演 |
| 后续验证 | NCLT 高动态段回测 (待 S58+) |

## 6. 复用入口

```
python governance/meta_harness/pattern_retrieval.py --query "IMU gyro saturation vibration noise random walk high dynamic"
# 期望命中本模式, 输出饱和检测 + 噪声自适应参数 + 回滚方案
```
