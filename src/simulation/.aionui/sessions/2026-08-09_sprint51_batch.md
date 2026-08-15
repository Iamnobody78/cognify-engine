# Session 记录 — SPRINT 51 批处理统计验证 (2026-08-09)

## 裁决与触发
- **PM 裁决 A (P0)**: NCLT 27 session 批处理——从"单点验证"走向"系统验证"（不同天气/季节/路径下的漂移抑制一致性）
- **T1**: 27 session 数据下载 + session 清单
- **T2**: 批量融合评估（yaw RMSE / pos RMSE / 抑制比 → 27 行指标表 + 统计）
- **T3**: 统计显著性报告（退化模式分类 + 改进建议）

## 交付物
| 项 | 状态 |
|---|---|
| `msan_data/nclt_batch_download.py` — 27-session 下载器 | ✅ |
| `msan_data/nclt_sessions_manifest.tsv` — 27 行可追溯清单 | ✅ |
| `msan_data/nclt_gici_out/s51_batch_summary.tsv` — 27 行指标表 | ✅ |
| `docs/msan/s51_batch_summary.png` — 4 面板汇总图 | ✅ |
| `docs/msan/s51_batch_stats_report.md` — T3 统计报告 | ✅ |
| git: `5d94c78` on feature/s51_nclt_batch | ✅ |

## 最终 KPI
- **27/27 session 成功运行（100%）**
- **PASS 率 24/27 = 88.9%**（抑制比 < 0.20）
- 融合 yaw: mean 16.0° / med 16.4° / std 2.9°（跨 session 高度一致，CV=18%）
- 抑制比: mean 0.170 / med 0.156
- 位置 RMSE: med 124.5 m / max 840.6 m（修复后）

## 关键发现（T3 统计规律）
1. **噪声底定律**: corr(fused_yaw, openloop)=+0.31, corr(suppress, openloop)=-0.69。
   融合残差由航向伪观测噪声底主导（~15-17°），与开环漂移无关。开环>100° 时抑制比稳定 0.15-0.18；
   开环<55° 时 20% 判据低于噪声底 → 3 个 FAIL（0.295-0.368）全部是低开环 session（判据问题，非估计器缺陷）。
2. **退化模式 A（RTK 质量差）**: 2012-11-04/2013-02-23/2012-05-26 — rtk_err 尖峰（198-229m）→ sig_h 膨胀 → 位置漂移（pos 420-840m），但 **yaw/roll 不受影响**（姿态鲁棒）。
3. **退化模式 B（数据坏行）**: 2012-09-28 — fix≥3 但 lat/lon=0 行 + 首行 alt=nan → alt0=0 基准 → pos 109,795m → **修复后 77.7m**。

## 工程修复（批处理驱动）
1. 零坐标坏行过滤 `lat==0 or lon==0`（NCLT 2012-09-28+ 存在）
2. 基准行 `i0 = first(fix>=3)`（alt0 不被 fix<3/nan 行污染）
3. rtk_err 过滤 nan/≤0/>1000m（防 6.3e6 m 极端值污染 sig_h）

## 建议（供 PM）
1. 判据演进：低开环 session 增加"绝对残差 ≤21.6°"补充判据（3 个 FAIL 在绝对判据下全 PASS）
2. 位置域优化：RTK 差时段可"rtk_err 门控 + 纯 DR 保持"
3. **GICI 原生路径不建议启动**（27-session 一致性验证实证支撑 PM 裁决 B）
