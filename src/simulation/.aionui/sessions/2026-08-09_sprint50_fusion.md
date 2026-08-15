# Session 记录 — SPRINT 50 融合估计器交付 (2026-08-09)

## 裁决与触发
- **PM 裁决 A**: GICI spp_imu integrator = P0。"真实 IMU 零偏下的纯积分漂移曲线（107.8°/94min）已绘出，下一步必须用融合估计器在闭环中抑制该漂移，将残差从'开环物理事实'收敛到'融合后工程残差'。"
- **T1**: GICI spp_imu 配置适配 → **阻断确认**（NmeaFormator 输出唯一，NCLT 无原始观测）→ 位置域 EKF 等价替代。
- **T2**: 融合姿态残差 ≤ 21.6°（开环漂移 20%）。
- **T3**: 合成→真实→融合三段式对比图/报告。

## 交付物
| 项 | 状态 |
|---|---|
| `msan_data/nclt_fusion_ekf.py` — 18 态误差状态 EKF（右扰动 Solà）+ 鲁棒更新 | ✅ |
| `docs/msan/s50_research_methods.md` — 三段式报告 + 前置可行性探测方法论 | ✅ |
| `docs/msan/s50_fusion_three_stage.png` — 2×2 对比图 | ✅ |
| `msan_data/nclt_gici_out/s50_fusion_metrics.json` + `fused_pose.csv` | ✅ |
| 诊断族（nclt_pos_diag / ekf_diag2,3 / enu_check / yawcheck2 / traj3 ...） | ✅ |
| git: `338535a` on feature/s50_spp_imu | ✅ |

## 最终 KPI（全部达标）
- **融合 yaw RMSE = 17.52° ≤ 21.6°**（抑制比 0.163）✅
- roll RMSE 1.39°；位置 RMSE **78.2 m**（8772m → 78.2m，决定性修复）✅
- 开环基线（S49 交叉复核）：107.815° 锁定

## 关键决策: 垂直硬门限 → Huber 3σ 膨胀（S50 决定性修复）
- 失败模式：急弯航向滞后 → yaw ±50° → 姿态污染 → 重力泄漏 → v_z +19 m/s；50m 硬门限超限后永久关闭垂直校正 → p_z 单调发散 +25.5km。
- 修复：垂直更新无硬门限，Huber 3σ 膨胀（与水平同设计）→ p_d 80s 自愈，位置 RMSE 8772→78m。
- 机动自适应 yaw σ（V1）单独使用反而更差（10660m）——σ 时序依据（瞬时 ω_z）与偏差来源（30s 累积窗）错位；需叠加创新 Huber 兜底。

## 纪律
- GICI 原生路径全程如实标注 "position-domain EKF equivalent"，不冒充原生结果。
- 内环 3 变体验证（V0 基线 / V1 机动σ / V2 Huber）→ 因果推理 → 裁决 V2 → 写入主交付（metacognition trace 归档）。
