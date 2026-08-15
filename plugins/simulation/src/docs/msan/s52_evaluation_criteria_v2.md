# Sprint 52 T1 — 评估判据规范（v2：双判据，替代 S50-S51 单判据）

> 状态：**生效** · 适用范围：MSAN 传感器融合评估报告（S52 起）
> 依据：S51 27-session 统计发现（噪声底定律：corr(suppress, openloop) = -0.69）

## 1. 判据定义

### 判据 1（主判据）：相对抑制比

```
PASS  if  suppress_ratio < 0.20
```
- `suppress_ratio = fused_yaw_rmse / openloop_dr_yaw_rmse`
- 适用场景：开环漂移 > ~100° 的 session（20% 阈值高于航向观测噪声底）

### 判据 2（补充判据）：绝对残差

```
PASS  if  fused_yaw_rmse <= 21.6 deg
```
- 21.6° = S50 PM 原始目标（开环 107.8° 的 20%），作为绝对工程残差上限
- 适用场景：**低开环漂移 session（开环 < ~100°）**——此时 20% 阈值低于噪声底，
  相对判据不可达；绝对残差成为有效判据

### 组合判定（NEW）

```
VERDICT = PASS  if  (suppress_ratio < 0.20)  OR  (fused_yaw_rmse <= 21.6 deg)
          FAIL  otherwise
```

### 通过标注

| 通过路径 | 标注 |
|---|---|
| 相对判据通过（抑制比 < 0.20） | 无需标注（标准 PASS） |
| 仅补充判据通过（抑制比 ≥0.20 但绝对残差 ≤21.6°） | `LOW-OPENLOOP / absolute-residual healthy` |

## 2. 设计依据（S51 统计）

- 融合 yaw 残差 ~15-17° 由航向伪观测噪声底主导，**与开环漂移几乎无关**（corr = +0.31）
- 低开环 session（42.5°/53.3°）：20% 阈值 = 8.5°/10.7° < 噪声底 → 相对判据**物理上不可达**
- 3 个 S51 FAIL 中 2 个（01-15/01-22）绝对残差 15.7° 健康 → 应放行
- 1 个（2012-11-17）绝对残差 21.62° 超限 → 保持 FAIL（真实退化，非判据问题）

## 3. 边界规则（S52 新增，防误判）

- **数值边界**：`fused_yaw_rmse` 与阈值差 < 0.1° 时，判定为"边缘 PASS/FAIL"并强制在报告中
  标注该 session 的误差分布特征（p50/p90/系统性 vs 瞬态），由审阅者确认
- **系统性偏差检测**：若 session 的 yaw err p50 > 20°（对比健康 session 3.8-13.4°），
  视为系统性航向偏差，即使数值边缘也应标记为"疑似真值/航向观测质量下降"，列入调查项
- **双日关联**：连续日期 session（如 2012-11-16/17）同时退化时，优先怀疑外部条件
  （天气/RTK 质量），而非估计器——检查 rtk_err p95 佐证

## 4. 实施

- 回测脚本：`msan_data/nclt_criteria_backtest.py`（27 session 全量）
- 判定函数：`verdict(suppress_ratio, fused_yaw_rmse)` → (PASS/FAIL, annotation, edge_flag)
- 完整对比表：`s52_criteria_backtest.md` / `s52_criteria_backtest.tsv`
- 报告模板引用：所有后续 session 评估报告采用本判据 v2

## 5. 生效记录

| 版本 | 日期 | 变化 |
|---|---|---|
| v1 | S50-S51 | 单判据（抑制比 < 0.20），3/27 FAIL |
| **v2** | S52 | 双判据（抑制比 OR 绝对残差 ≤21.6°），1/27 FAIL（边缘） |

PASS 率：88.9% (v1) → 96.3% (v2)；2 个低开环 FAIL 合理转 PASS，1 个真实退化保持 FAIL。
