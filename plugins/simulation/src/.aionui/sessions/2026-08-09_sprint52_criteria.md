# Session 记录 — SPRINT 52 判据演进 + GICI 否决归档 (2026-08-09)

## 裁决与触发
- **PM 裁决 1 (P0)**: 判据演进——绝对残差 ≤21.6° 作为补充判据（低开环场景 20% 抑制比判据失效）
- **PM 裁决 2**: GICI 原生路径"实证否决"记录归档
- **PM 裁决 3**: 位置域优化延后至判据演进完成后

## 交付物
| 项 | 状态 |
|---|---|
| `docs/msan/s52_evaluation_criteria_v2.md` — 双判据规范（T1） | ✅ |
| `msan_data/nclt_criteria_backtest.py` + `s52_criteria_backtest.tsv` — 27-session 回测（T2） | ✅ |
| `docs/msan/s52_criteria_backtest.md` — 回测对比表报告（T2） | ✅ |
| `docs/engineering/s51_gici_native_path_veto.md` — 否决归档（T3） | ✅ |
| git: `8c6a4eb` on feature/s52_criteria_evolution | ✅ |

## 最终 KPI
- **v2 双判据 PASS 率：26/27 = 96.3%**（v1 为 88.9%）
- 2 个低开环 FAIL（01-15: 抑制比 0.295、01-22: 0.368）→ PASS（绝对残差 15.7° 健康）
- **2012-11-17 保持 FAIL（诚实修正 PM 预期：3 → 2）**

## ⚠️ 关键诚实修正
PM 预期"3 个 FAIL 全部 PASS"，实际仅 **2 个**。2012-11-17：
- 融合 yaw 21.622°（超阈值 0.02°）、抑制比 0.208（超 0.008）——边缘但真实 FAIL
- 非低开环（开环 103.7°）；yaw err **p50=22.1°**（系统性偏差，非瞬态）；
  rtk_err p95=30.65m（质量偏差）；与 11-16（20.4°，第二差）连续两天系统性退化
- 双判据设计价值恰在区分：01-15/01-22 是"判据不可达"（放行），11-17 是"真实退化"（FAIL）
- 已按边界规则标记 11-16/11-17 双日关联为 S52 遗留调查项

## 双判据定义（S52 生效）
```
VERDICT = PASS if (suppress_ratio < 0.20) OR (fused_yaw_rmse <= 21.6 deg)
```
- 低开环（<~100°）session 标注 "LOW-OPENLOOP / absolute-residual healthy"
- 边界规则：|Δ|<0.1° 强制报告误差分布特征；yaw err p50>20° 标记系统性偏差嫌疑

## GICI 否决归档要点（T3）
- 类型：实证否决（数据供给缺口 + 27-session 充分性 + 判据完备，非能力否决）
- 重启条件：① 新数据供给（原始 RINEX+tersus）② 位置精度升至厘米级目标 ③ GICI 上游新增 NMEA 输入
