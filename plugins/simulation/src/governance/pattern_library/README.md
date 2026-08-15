---
name: pattern-library
type: index
---

# 模式库 (Pattern Library)

> 元学习能力的第一实证闭环：将已验证的失败/修复经验固化为可检索、可复用的模式。

## 检索服务

```
python governance/meta_harness/pattern_retrieval.py --query "<症状特征>" [--top N]
```

元系统在诊断新退化时调用本服务自动召回类似模式（预期减少重复诊断轮次 ≥85%）。

## 现有模式

| 模式 | 类型 | 来源 | 状态 |
| :--- | :--- | :--- | :--- |
| sensor_degradation (RTK fix=2) | 传感器退化 | Sprint 56 | ✅ 已固化 + 27-session 验证 |
| imu_bias_drift | 传感器退化 (IMU) | Sprint 57 | ✅ 跨域扩展 + 检索验证 |
| imu_saturation_vibration | 传感器退化 (IMU) | Sprint 57 | ✅ 跨域扩展 + 检索验证 |
| vision_feature_degradation | 传感器退化 (视觉) | Sprint 57 | ✅ 跨域扩展 + 检索验证 |
| vision_illumination_occlusion | 传感器退化 (视觉) | Sprint 57 | ✅ 跨域扩展 + 检索验证 |
| defensive_shove_stalemate | 对抗模式 (反冲拉锯) | Sprint 59 | ✅ 已固化 + 门回归验证 |

## 跨域检索验证 (Sprint 57 P3)

| 查询 | 命中第一 | score | 关键词命中 |
| :--- | :--- | :--- | :--- |
| "IMU temperature bias drift yaw drift pure-DR" | imu_bias_drift | 0.465 | IMU/bias drift/yaw drift/pure-DR |
| "visual feature tracking loss low texture dynamic occlusion" | vision_feature_degradation | 0.467 | dynamic occlusion/feature tracking loss/low texture |

✅ 模板抽象层跨域通用：frontmatter 检索元数据（name/type/symptom_keywords/parameters/validation）在 RTK/IMU/视觉三域均有效

## 维护规范

- 每个模式一个 .md，frontmatter 必须含: `name / type / symptom_keywords / parameters / validation`
- 新模式须经 Anti-Drift 看门狗闸门评估（L3 层：仅 TRACE 记录）后入库
- 索引重建: `python pattern_retrieval.py --rebuild-index`
- 复用验证: `python pattern_retrieval.py --stats`
