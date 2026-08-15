---
name: vision-feature-degradation
type: sensor_degradation
symptom_keywords: ["视觉", "vision", "特征点不足", "insufficient features", "光照变化", "illumination change", "纹理缺失", "textureless", "动态遮挡", "dynamic occlusion", "特征跟踪丢失", "feature tracking loss", "ORB特征", "ORB features", "匹配失败", "matching failure", "低纹理", "low texture", "帧间跳变", "frame jump", "重定位失败", "relocalization failure"]
sensor: Camera
modality: "mono / stereo / RGB-D"
parameters:
  min_features_per_frame: "100 (ORB, 640x480)"
  min_track_ratio: "0.5 (成功跟踪/检测)"
  parallax_threshold: "0.5 px (弱视差检测)"
  illumination_gain: "automatic (直方图均衡)"
  outlier_reject: "RANSAC + 对极几何"
  fallback_mode: "IMU 传播保持 2s"
validation:
  scenario: "视觉里程计特征退化 (文献基准)"
  feature_drop_rate: "> 70% 触发退化告警"
  track_loss_threshold: "< 30% 成功跟踪"
  typical_recovery: "重新初始化 2-5 帧"
  note: "视觉退化是结构性退化 (光照/遮挡), 与 RTK fix 降级同构"
discovered: "Sprint 57 (模式库跨域扩展)"
rule: "RULE-MC-013: 特征质量是视觉观测的信息熵, 退化时须降低观测信任而非丢弃"
---

# 模式：视觉特征退化 (Sensor Degradation)

> Sprint 57 模式库跨域扩展 · 将 sensor_degradation 模板复用到视觉域

## 1. 症状特征（检测输入）

| 特征 | 典型值 | 数据来源 |
| :--- | :--- | :--- |
| 特征点数量 | < 100 帧（ORB） | 特征检测器 |
| 跟踪成功率 | < 30% 连续 5 帧 | 光流/描述子匹配 |
| 视差 | < 0.5 px（纯旋转/退化） | 三角化 |
| 匹配内点率 | < 40% RANSAC | 对极几何 |
| 场景类型 | 白墙/走廊/夜间 | 图像统计 |

## 2. 根因机制（与 RTK fix 降级同构）

1. **触发**：纹理缺失/光照突变/动态遮挡 → 特征检测与跟踪失败
2. **放大**：VO 定位退化 → 位姿估计漂移 → 地图错误注入 → 后续帧级联失败
3. **失控**：重定位失败 → 里程计完全失效 → 位置发散

**结构同构**：视觉特征退化 ≈ RTK fix=2 降级（观测质量下降, 不是完全失效）
→ F2_SIGMA 自适应思路可复用：**按特征质量动态调整观测噪声 sigma**

## 3. 修复参数（可直接复用）

| 参数 | 值 | 设计意图 |
| :--- | :--- | :--- |
| min_features_per_frame | 100 | 低于此值触发退化监测 |
| min_track_ratio | 0.5 | 跟踪质量门 |
| parallax_threshold | 0.5 px | 弱视差 = 退化段 |
| illumination_gain | 自动 | 光照自适应预处理 |
| outlier_reject | RANSAC | 动态遮挡剔除 |
| fallback_mode | IMU 传播 2s | 短时保持, 不引入漂移 |

**机理**：特征质量评分 → 视觉观测 sigma 动态调整（质量高=sigma 小, 退化=sigma 大）
→ 与 S57-P1 会话自适应 F2_SIGMA 完全同构。

## 4. 适用条件与边界

- ✅ 适用：单目/双目/RGB-D VO、光照剧变、低纹理环境、动态场景
- ⚠️ 注意：特征数量 ≠ 特征质量（大量重复纹理也是退化）
- ⚠️ 注意：纯旋转场景视差不足, 即使特征充足也是退化
- ❌ 不适用：有外部绝对定位（RTK/GNSS）时的短时 VO 退化（直接切换信源）
- 回滚方案：视觉观测 sigma → 固定默认值, 或降级为 IMU-only

## 5. 验证状态

| 维度 | 状态 |
| :--- | :--- |
| 模板复用 | ✅ frontmatter 结构与 sensor_degradation 一致 |
| 检索命中 | 待 pattern_retrieval.py 跨域查询验证 |
| 实证数据 | 文献基准 + 与 RTK 模式结构同构推演 |
| 后续验证 | 需要视觉数据集回测 (待 S58+) |

## 6. 复用入口（诊断新退化时）

```
python governance/meta_harness/pattern_retrieval.py --query "visual feature tracking loss low texture dynamic occlusion"
# 期望命中本模式, 输出特征质量参数 + 自适应 sigma 思路 + 回滚方案
```
