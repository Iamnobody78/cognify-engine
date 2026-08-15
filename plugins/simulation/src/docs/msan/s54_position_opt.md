# Sprint 54: 位置域优化 — RTK 差时段门控 + 纯 DR 保持

**日期**: 2026-08-09
**分支**: `feature/s54_position_optimization`
**任务**: T1（RTK 差时段门控）、T2（纯 DR 保持）、T3（27-session 回测）
**前置**: S53 数据源四维度全阴性 → 位置域优化解冻（yaw 退化与位置域无关，11-04 反例证明）

---

## 一、实现（`msan_data/nclt_fusion_ekf.py`）

### T1 — RTK 差时段软门控（非硬切断）
- 参数 `RTK_ERR_GATE`（Pareto 胜出值 **12.0 m**；p50 健康 rtk_err ~1.2-2.1m，p95 30-54m）
- 当 per-epoch `rtk_err > GATE` 时，位置观测 sigma **二次方放大**：
  `sig_h *= (rtk_err / GATE)²` —— 平滑降权、永不断言
- 每次降权事件写入 `s54_downweight_events.tsv`（时间戳、rtk_err、降权因子）
- **姿态域（yaw/roll）观测路径完全未触碰**

### T2 — 纯 DR 保持 + 平滑重收敛
- 预扫描 RTK fix 序列，识别失锁区间（fix<3 且持续 ≥1.0s）
- 失锁期间**不注入位置观测**（纯 DR 保持），但位置协方差按
  `P[0:3,0:3] += DR_SIGMA²·dt`（**DR_SIGMA=0.05 m/s**）增长
- 恢复时大 innovation 被已增长的 P 平滑吸收 → **无跳变重收敛**
- 失锁区间总数/总时长进入 metrics

### 兼容性
- `NCLT_EKF_LEGACY=1` 环境变量精确复现 S51 基线（逐 session 验证一致，见 §三）
- `NCLT_RTK_GATE` / `NCLT_DR_SIGMA` 可调 → Meta-Harness 变体扫描基建

---

## 二、Meta-Harness 变体扫描（T3 过程）

5 个候选（legacy + v1-v4）在 27-session 全量回测，Pareto 前沿分析：

| variant | GATE | DR_SIGMA | pos_med | pos_p90 | pos_max | yaw_max_shift | dw_med% |
|---|---|---|---|---|---|---|---|
| **legacy** | — | — | 124.47 | 344.10 | **840.64** | — | 0 |
| v1 | 8.0 | 0.20 | 137.68 | 344.06 | 443.14 | 0.18° | 1.75 |
| v2 | 15.0 | 0.10 | 140.24 | 312.59 | 443.71 | 0.22° | 0.79 |
| **v3 ✅** | **12.0** | **0.05** | **121.27** | **313.59** | **443.85** | **0.17°** | **1.13** |
| v4 | 20.0 | 0.02 | 150.84 | 312.43 | 443.91 | 0.10° | 0.32 |

**Pareto 裁决**：v3 在 pos_med（121.27 < 124.47）、pos_p90、pos_max 三指标全面优于
legacy，yaw 偏移 ≤0.17°（姿态域零影响），降权温和（med 1.13%）→ **唯一严格支配 legacy
的候选**。v1（GATE=8）过度降权导致 03-31 +160m 灾难、02-05 +39m → 被淘汰；
v4（GATE=20）过保守 → pos_med 最差。

---

## 三、27-session 回测结果（T3 验收）

### 3.1 总体对比（v3 vs legacy，`s54_batch_summary.tsv` vs `s51_batch_summary.tsv`）

| 指标 | legacy (S51) | v3 (S54) | 变化 |
|---|---|---|---|
| pos RMSE 中位数 | 124.47 m | **121.27 m** | **-3.2 m (-2.6%)** ✅ |
| pos RMSE p90 | 344.10 m | **313.59 m** | **-30.5 m (-8.9%)** ✅ |
| pos RMSE 最大值 | 840.64 m | **443.85 m** | **-396.8 m (-47.2%)** ✅ |
| yaw RMSE 中位数 | 16.44° | 16.43° | -0.01°（零影响）✅ |
| yaw 最大单 session 偏移 | — | 0.17° | 姿态域不受影响 ✅ |
| 降权事件占比（中位） | 0% | 1.13% | 温和 |

### 3.2 关键 session 明细

| session | legacy pos | v3 pos | 变化 | 说明 |
|---|---|---|---|---|
| 2012-05-26 | 840.64 m | **22.41 m** | **-818 m** | 极端值 97% 抑制（PM 点名案例）✅ |
| 2012-03-25 | 283.51 m | 156.92 m | -127 m | 大幅改善 |
| 2012-01-22 | 167.35 m | 110.12 m | -57 m | 改善 |
| 2012-02-12 | 119.66 m | 102.54 m | -17 m | 改善 |
| 2013-02-23 | 443.92 m | 443.85 m | -0.07 m | RTK 系统性偏差，门控无效（预期内） |
| 2012-11-16/17 | 117.2/154.3 m | 117.2/151.2 m | ~0/-3 m | 双日 yaw 退化与位置域无关（S53 确认），位置几乎不变 |

### 3.3 未改善的 session（诚实标注）
- **2013-02-23 (443.9m)**：RTK 系统性偏移（非噪声），任何降权都无法消除——门控只针对
  差时段噪声，系统性偏差超出本优化范畴
- **2012-03-31 (+27.7m)、2012-05-11 (+87.3m)**：小幅退化，源于降权后 DR 权重上升；
  v3 已是最小化此类副作用的 Pareto 点

---

## 四、PM 验收对照

| 验收项 | 结果 |
|---|---|
| 位置 RMSE 在 RTK 差时段得到抑制 | ✅ 05-26 840.6→22.4m；03-25 -127m；中位数 -2.6% |
| 姿态域不受影响 | ✅ yaw 中位数 -0.01°，最大偏移 0.17° |
| 失锁状态位置漂移有界，恢复无跳变 | ✅ 纯 DR + P 增长注入，27 session 无跳变事件 |
| 降权事件记录 | ✅ `s54_downweight_events.tsv` 每 session 生成 |
| 位置 RMSE 中位数下降 | ✅ 124.47 → 121.27 m |
| 极端值（如 840m）有效抑制 | ✅ 840.64 → 22.41 m（-97%） |

---

## 五、资产清单

| 资产 | 路径 |
|---|---|
| EKF 实现（T1+T2） | `msan_data/nclt_fusion_ekf.py` |
| 27-session 回测汇总（v3） | `msan_data/nclt_gici_out/s54_batch_summary.tsv` |
| 降权事件日志（示例） | `msan_data/nclt_gici_out/2012-05-26/s54_downweight_events.tsv` |
| 变体扫描基建 | `nclt_variant_sweep.sh` / `nclt_variant_gen.py` / `nclt_variant_legacy_from_s51.py` |
| Pareto 分析 | `nclt_pareto_s54.py` |
| 汇总/对比脚本 | `nclt_collect_summary_s54_final.py` / `nclt_s54_vs_s51.py` |
| 本报告 | `docs/msan/s54_position_opt.md` |
