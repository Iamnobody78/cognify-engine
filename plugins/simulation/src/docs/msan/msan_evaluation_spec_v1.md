# MSAN 评估规范 v1.0 — 统一双域判据（姿态域 + 位置域）

**日期**: 2026-08-09
**状态**: 生效 · 适用范围：MSAN 传感器融合评估报告（S55 起）
**分支**: `feature/s55_position_criteria`
**组成**: 姿态域判据 v2（S52，继承）+ 位置域判据 v1.0（S55，新增）
**替代**: S52 评估判据规范 v2（姿态域单域版）

---

## 1. 总体判定结构

MSAN 评估 = **双域并联判定**：姿态域（航向/横滚）+ 位置域（水平位置）。

```
总判定 = ATTITUDE_VERDICT  ×  POSITION_VERDICT

ATTITUDE_VERDICT ∈ {PASS, FAIL}    （S52 v2 双判据，§2）
POSITION_VERDICT ∈ {PASS, WARN, FAIL}  （S55 多级判据，§3）

总判定规则:
  OVERALL = PASS   if  ATTITUDE_VERDICT == PASS  AND  POSITION_VERDICT != FAIL
  OVERALL = WARN   if  ATTITUDE_VERDICT == PASS  AND  POSITION_VERDICT == WARN
  OVERALL = FAIL   otherwise
```

> 设计说明：姿态域为布尔（PASS/FAIL），位置域为三级（PASS/WARN/FAIL）。
> 位置 WARN 降级总判定为 WARN（而非 FAIL）——位置 200-400m 区间对应 RTK 差时段
> 噪声，属"可接受但需报告"；姿态 FAIL 无降级，直接 FAIL（航向偏差不可接受）。

---

## 2. 姿态域判据（继承 S52 v2，未修改）

### 判据 1（主判据）：相对抑制比
```
PASS  if  suppress_ratio < 0.20
```
- `suppress_ratio = fused_yaw_rmse / openloop_dr_yaw_rmse`
- 适用：开环漂移 > ~100° 的 session

### 判据 2（补充判据）：绝对残差
```
PASS  if  fused_yaw_rmse <= 21.6 deg
```
- 适用：低开环漂移 session（开环 < ~100°），20% 阈值低于噪声底不可达时

### 组合判定
```
ATTITUDE_VERDICT = PASS  if  (suppress_ratio < 0.20)  OR  (fused_yaw_rmse <= 21.6 deg)
                   FAIL  otherwise
```

### 边界规则（S52 §3 保留）
- 数值边界 <0.1° → 边缘 PASS/FAIL + 强制误差分布报告
- yaw err p50 > 20° → 系统性偏差嫌疑标注
- 连续日期双日退化 → 先查外部条件（天气/RTK）

---

## 3. 位置域判据（S55 新增）

### 多级边界
```
PASS  if  pos_rmse < 200 m
WARN  if  200 m <= pos_rmse < 400 m
FAIL  if  pos_rmse >= 400 m
```

### 分布依据（v3 优化后 27-session）
p25=77m, p50=121m, p75=180m, p90=344m, p95=419m, max=444m
→ PASS<200 覆盖 p75 以下健康主体；FAIL≥400 仅捕 2 个系统性异常 session

### 报告要求
- WARN：报告 RTK 差时段 vs 系统性偏移贡献，引用降权/DR 统计佐证
- FAIL：触发系统性偏差检查流程（区分随机噪声 vs 系统性偏差），列入调查项
- 边缘（边界差 <5m）：强制报告 fix3% / rtk_err p95

---

## 4. 判据版本与回测结果（27-session 全量）

| 版本 | 姿态域 | 位置域 | 总判定 |
|---|---|---|---|
| S51 v1 | 抑制比<0.20 单判据 | 无 | PASS 24/27 (88.9%) |
| S52 v2 | 双判据（抑制比 OR ≤21.6°） | 无 | PASS 26/27 (96.3%) |
| **S55 v1.0** | 双判据（不变） | 三级（200/400） | **PASS 24/27 (88.9%)** + WARN 0 + FAIL 3/27 |

### v1.0 回测明细（v3 配置）

| 总判定 | session | 原因 |
|---|---|---|
| **FAIL (3)** | 2012-11-04 | 位置 FAIL (419m)；姿态 PASS |
| | 2013-02-23 | 位置 FAIL (444m) 系统性偏差；姿态 PASS |
| | 2012-11-17 | 姿态 FAIL（21.63° > 21.6° 边缘）；位置 PASS |
| **PASS (24)** | 其余 24 个 | 姿态 PASS 且位置非 FAIL |

> v1.0 PASS 率 88.9% 低于 v2 的 96.3%——**这不是退化，而是判据变严**：
> 新增位置维度捕捉到 2 个姿态域漏掉的 session（11-04/02-23 位置 FAIL）。
> 姿态域判定本身未变（26/27 姿态 PASS）。v2 的 96.3% 是"姿态域 PASS 率"，
> v1.0 的 88.9% 是"双域综合 PASS 率"，两者口径不同，不可直接比较。

---

## 5. 生效记录

| 版本 | 日期 | 变化 |
|---|---|---|
| v1 | S50-S51 | 姿态单判据（抑制比），3/27 FAIL |
| v2 | S52 | 姿态双判据（抑制比 OR ≤21.6°），1/27 边缘 FAIL |
| **v1.0** | **S55** | **+位置域三级判据（200/400），双域并联；3/27 FAIL（含 2 位置 FAIL）** |

---

## 6. 实施与引用

- 回测脚本：`msan_data/nclt_s55_criteria.py`
- 数据源：`msan_data/nclt_gici_out/s54_batch_summary.tsv`（v3）/ `s51_batch_summary.tsv`（legacy）
- 详细判据依据：`docs/msan/s55_position_criteria.md`（T1/T2）
- 引用规范：所有 S55 起 session 评估报告采用本规范 v1.0
- 已纳入 MSAN 证据链：`docs/msan/`（S50→S55 完整链）
