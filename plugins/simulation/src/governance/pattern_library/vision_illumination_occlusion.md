---
name: vision-illumination-occlusion
type: sensor_degradation
symptom_keywords: ["视觉", "vision", "光照变化", "illumination change", "动态遮挡", "dynamic occlusion", "过曝", "overexposure", "欠曝", "underexposure", "阴影", "shadow", "逆光", "backlight", "遮挡", "occlusion", "曝光突变", "exposure jump", "HDR", "直方图偏移", "histogram shift", "gamma", "对比度", "contrast"]
sensor: Camera
modality: "mono / stereo"
parameters:
  exposure_jump_threshold: "> 2 EV 帧间"
  histogram_shift: "> 30% 像素亮度偏移"
  occlusion_ratio: "> 40% 画面被挡"
  hdr_enable: "auto (高动态场景)"
  auto_exposure: "AEC 开启 + 增益上限 8x"
  fallback: "特征退级 + sigma 自适应"
validation:
  scenario: "隧道进出/树影/逆光走廊"
  feature_drop_illumination: "特征量下降 50-80%"
  recovery_time: "曝光稳定后 2-5 帧"
  note: "光照/遮挡是视觉退化最频繁诱因"
discovered: "Sprint 57 (模式库跨域扩展)"
rule: "RULE-MC-015: 曝光与遮挡先于特征失效发生, 是视觉退化的前哨信号"
---

# 模式：视觉光照变化与动态遮挡 (Sensor Degradation)

> Sprint 57 模式库跨域扩展 · 视觉退化最频繁诱因

## 1. 症状特征（检测输入）

| 特征 | 典型值 | 数据来源 |
| :--- | :--- | :--- |
| 曝光跳变 | > 2 EV 帧间 | 相机 AEC |
| 直方图偏移 | > 30% 像素亮度偏移 | 图像统计 |
| 遮挡比例 | > 40% 画面 | 语义分割/光流 |
| 特征量下降 | 50-80% | 特征检测器 |
| 对比度骤降 | < 20 (0-255) | 灰度方差 |

## 2. 根因机制

1. **光照**：隧道进出/逆光/阴影 → 曝光突变 → 特征描述子失配（光照不变性假设失效）
2. **遮挡**：行人/车辆/枝叶 → 视场部分失效 → 特征点不足 → 位姿退化
3. **前哨性**：曝光跳变和遮挡**先于**特征失效发生 → 是预测性退化检测信号

## 3. 修复参数

| 参数 | 值 | 设计意图 |
| :--- | :--- | :--- |
| exposure_jump_threshold | 2 EV | 曝光突变检测 |
| hdr_enable | auto | 高动态范围预处理 |
| auto_exposure | AEC + 增益上限 8x | 防过曝/欠曝 |
| occlusion_ratio | 40% | 遮挡触发降级 |
| sigma_adapt | 特征量映射 | 观测噪声自适应 |

**机理**：曝光/遮挡检测 → 触发特征退级 → 视觉观测 sigma 增大 → 与 RTK/F2_SIGMA 自适应同构。

## 4. 适用条件与边界

- ✅ 适用：室外光照剧变、室内外转换、人车混行、隧道
- ⚠️ 注意：HDR 增加延迟（~1帧），实时性敏感场景权衡
- ⚠️ 注意：遮挡检测本身依赖模型（算力成本）
- ❌ 不适用：恒定光照实验室环境
- 回滚方案：sigma_adapt 关闭 → 固定视觉噪声

## 5. 验证状态

| 维度 | 状态 |
| :--- | :--- |
| 模板复用 | ✅ 与 sensor_degradation 一致 |
| 检索命中 | 待 pattern_retrieval.py 跨域查询验证 |
| 实证数据 | 文献基准 + 机理推演 |
| 后续验证 | 视觉数据集回测 (待 S58+) |

## 6. 复用入口

```
python governance/meta_harness/pattern_retrieval.py --query "vision illumination change exposure jump dynamic occlusion tunnel"
# 期望命中本模式, 输出曝光检测 + sigma 自适应 + 回滚方案
```
