---
name: RTK-fix2-degradation
type: sensor_degradation
symptom_keywords: ["fix=2", "fix=0", "坐标冻结", "frozen coords", "速度发散", "velocity divergence", "DR保持", "pure-DR", "位置漂移", "position drift", "gravity leak", "chi2恒过", "P_pos爆炸", "roll/pitch误差"]
sensor: RTK-GPS
fix_state: "2"
parameters:
  F2_USE: "on"
  F2_SIGMA: "15m (备选 25m)"
  F2_STALE_RATE: "0.5 m/s/sqrt(s)"
  F2_MIN_GAP: "2.0s"
  F2_VCLAMP: "20 m/s"
  update_kind: 4
validation:
  session_count: 27
  pos_median_delta: "-74.4% (121.3 -> 31.0m)"
  improved_sessions: "26/27"
  target_session: "02-23: 443.8 -> 31.60m (-92.9%)"
  regression: "01-10 +2.3m (15.4 -> 17.7m), 已披露"
  yaw_max_shift: "+0.66 deg"
discovered: "Sprint 56 (2026-08-10)"
rule: "RULE-MC-011: 传感器退化段不是失锁"
---

# 模式：RTK fix=2 退化段 (Sensor Degradation)

> 从 Sprint 56 系统性偏差处理经验固化 · 元学习首个实证闭环

## 1. 症状特征（检测输入）

| 特征 | 典型值 | 数据来源 |
| :--- | :--- | :--- |
| fix 状态 | 3→2 降级（或 3→0 完全失锁的同类变体） | RTK 输出 |
| 坐标冻结 | 连续 >2s 坐标几乎不变（<0.01m 抖动） | 相邻 RTK 观测量 |
| 退化段占比 | 6.5-17.9% 行（27 会话均值 ~13%） | fix2_audit |
| 最长连续段 | 55-348s | run-merging 15s gap |
| 速度发散 | 148-155 m/s（纯 DR 保持 + 重力泄漏） | fused_check |
| P_pos | σ→1100m，chi2 恒过，状态永不恢复 | 方差分析 |

## 2. 根因机制（三源验证法）

1. **触发**：RTK fix 3→2 退化段被 fix>=3-only 门当作完全失锁
2. **放大**：纯 DR 保持 → 陀螺 ±29°/s 机动 → roll/pitch 误差 ~5.7° → 重力泄漏 9.81·dθ
3. **失控**：速度 148-155 m/s → 位置 +10km → P_pos σ→1100m → chi2 恒过 → 无法恢复

## 3. 修复参数（可直接复用）

| 参数 | 值 | 设计意图 |
| :--- | :--- | :--- |
| F2_USE | on | 启用 fix=2 软定位 |
| F2_SIGMA | 15m | 软定位 sigma（优于退化段前真实精度）；01-10 退化补偿备选 25m |
| F2_STALE_RATE | 0.5 m/s/√s | 退化段 P_pos 增长 |
| F2_MIN_GAP | 2.0s | 外科手术式：仅 ±2s 内无 fix>=3 才调度 |
| F2_VCLAMP | 20 m/s | 速度防爆走安全网 |
| update_kind | 4 | 2-dof 水平 Huber + 1-dof 垂直 Huber，镜像 kind=0 |

**机理**：P_pos 爆炸 → K≈0.84 高增益 → fix=2 更新把状态钉到冻结坐标 → 交叉协方差抑制 yaw/roll 漂移 → 重力泄漏降至 0.1 m/s² → 速度 ≤0.41 m/s。

## 4. 适用条件与边界

- ✅ 适用：RTK/GNSS fix 降级段、坐标冻结 >2s、退化段内有机动
- ⚠️ 注意：t_rtk 已是秒（加载时 /1e6），检测时**不要再除一次**
- ⚠️ 注意：内部 rtk 数组为 7 列（n_sats 已丢弃），[6]=spd、[5]=trk——**勿按原始 CSV 列号索引**
- ❌ 不适用：fix>=3 正常段（走 kind=0 全量更新）
- 回滚方案：`F2_USE=off` 一键回退（S54 基线行为）

## 5. 验证结果（27-session 回测）

| 指标 | S54 基线 | S56 修复 | 变化 |
| :--- | :--- | :--- | :--- |
| pos median | 121.3m | 31.0m | **-74.4%** |
| pos max | 443.8m | 62.6m | -85.9% |
| p90 | 344.1m | 50.1m | -85.4% |
| 改善会话 | - | 26/27 | 1 退化 (01-10, +2.3m, 已披露) |

## 6. 复用入口（诊断新退化时）

```
python governance/meta_harness/pattern_retrieval.py --query "RTK fix=2 frozen coords velocity divergence"
# 期望命中本模式, 输出 F2 参数 + 验证统计 + 回滚方案
```

## 7. 历史诊断成本（对照基准）

S56 初期无模式库：4 个假设全部证伪（跳变率/时间戳伪速度/RTK 平台期/列索引）+ 三源交叉验证 = **7 轮诊断**。
模式库建立后：特征检索 1 轮命中 → 直接进入参数适配。**预期减少重复诊断 ≥85%**。
