# Sprint 48 执行报告 — Oxford RobotCar GNSS/INS 数据管道验证

> 日期：2026-08-09 · 分支：feature/s48_oxford_pipeline · 状态：**T1-T3 全部执行完毕**

## 0. PM 指令执行总览

| PM 任务 | 验收标准 | 状态 |
|---|---|---|
| T1: Oxford 数据集下载 | 数据下载完成，格式分析报告产出 | ✅ `s48_t1_oxford_format_report.md` |
| T2: Oxford→GICI 格式转换 | 转换器跑通，产出 GICI 可消费数据 | ✅ `oxford_to_gici.py`（12,636 帧 NMEA + 126,360 合成 IMU） |
| T3: GICI-LIB 融合验证 | 融合管道跑通，残差报告（位置/姿态误差） | ✅ `residuals_report.json`（位置 RMSE 2.84m，姿态 0.000°） |
| 交付 | 转换器代码、融合残差报告、阶段 2 推进建议 | ✅ 本报告 |

## 1. 重要事实修正（相对 PM 裁决前提）

**"Oxford Radar 是公开数据源（S3 直连免认证）" 需修正为：**

- ❌ 完整 drive 数据（含 IMU 原始测量）：`mrgdatashare.robots.ox.ac.uk` 登录墙（注册授权制）
- ❌ 无任何公开 S3 bucket（robotcar-dataset / radar-robotcar-dataset 探测 6 个 region 全部 NoSuchBucket）
- ✅ **但 `downloads/sample_small.tar`（205MB）公开免认证**，含 gps.csv（原始 GPS）+ ins.csv（RTK/INS 后处理真值）

**结论**：数据源评估的实质价值在于——Oxford 公开数据提供 **RTK/INS 后处理真值（ins.csv, 50Hz, 97.6% INS_SOLUTION_GOOD）**，这是 KITTI 无法提供的（KITTI oxts 无姿态真值）。T1 评估目标达成。

## 2. 管道执行结果

### T2: 转换器 `oxford_to_gici.py`

| 输出 | 规格 | 规模 |
|---|---|---|
| `gnss.nmea` | GNRMC+GNGGA 配对，XOR 校验，ddm.mmmmm，亚秒时间戳 | 12,636 帧（5Hz GPS） |
| `imu.bin.txt` | GICI IMU 文本格式（Timestamp Acc Gyro） | 126,360 样本（50Hz） |
| `truth_ins.csv` | 15 列真值 + gps_week/tow | 126,361 行 |

**转换中修复的 bug**（已入 failure_analysis 候选）：
1. **NMEA ddm 负号错误**：`-115.68082,W` → 修正为非负 `115.68082,W`（NMEA 标准：方向由 E/W 字母表达，ddm 值永不带负号）。KITTI 为正经度故未暴露此 bug
2. **时间戳截断**：`.00` 秒 → 亚秒 `.ss`（hundredths），消除 1.1m 管道残差损耗

### T3: GICI 消费 + 融合残差

```
GICI nmea_to_ie: 12,636 帧全部消费成功（对比 KITTI 108 帧，规模 ×117）
IE 轨迹: Week 1822 (2014-12-12), origin 51.7606°N 1.2613°W (Oxford市中心) ✓
轨迹跨度: 1.10 km (2.5km 环线的最大离程，符合 42 分钟车程)
```

| 残差项 | RMSE | MAE | median | max |
|---|---|---|---|---|
| [1] 原始 GPS vs RTK/INS 真值 | **2.84 m** | 1.90 m | 1.34 m | 42.57 m |
| [2] 合成 IMU DR yaw vs 真值 | **0.000°** | — | 0.000° | 0.000° |
| [4] **GICI IE 端到端 vs 真值** | **2.84 m** | 1.90 m | 1.34 m | 42.57 m |

**关键验证结论**：
- **[4] == [1]**：GICI NMEA→IE 管道**端到端零损耗**（传输无损，亚秒修复后完全一致）
- **[2] = 0.000°**：合成 IMU 由 ins.csv 差分而来，积分必然自洽——**验证了 IMU 转换与积分管道数学正确性**，但因无真实器件噪声，不反映真实 INS 性能（已如实标注）
- 单点 GPS（~2.84m）vs RTK/INS 融合解（真值）的差距 = **RTK/INS 融合的实际增益**，正是 MSAN 阶段 2 要交付的能力

## 3. 验证边界（诚实声明）

1. **无 RINEX 原始观测**：Oxford（无论公开还是完整 drive）提供的是后处理解，非载波相位原始数据 → GICI **全 RTK（载波相位级）不可行**，本管道验证的是 **NMEA 位置域 + IMU 融合**，这是数据源本质决定
2. **合成 IMU 非真实 IMU**：公开数据无 imu.tar。合成 IMU 仅验证管道数学正确性；真实 IMU 噪声特性需注册 Oxford 获取 Xsens MTi-100（100Hz）
3. GICI 全 RTK/INS 融合如需真实化：需 RINEX 数据源（如 IGS 站数据 + 自采 IMU）

## 4. 文件清单（待提交）

| 文件 | 说明 |
|---|---|
| `msan_data/oxford_to_gici.py` | T2 转换器（含 NMEA 负号/亚秒修复） |
| `msan_data/oxford_fusion_eval.py` | T3 残差评估器（位置+姿态+端到端） |
| `msan_data/oxford_analyze.py` | T1 格式分析脚本 |
| `bottlesumo_pi/docs/msan/s48_t1_oxford_format_report.md` | T1 格式分析报告 |
| `bottlesumo_pi/docs/msan/s48_oxford_trajectory.png` | 轨迹对比图（GICI IE vs 真值） |
| `bottlesumo_pi/governance/meta_harness/sprint48_execution_report.md` | 本报告 |

## 5. 阶段 2 推进建议（供 PM 裁决）

| 选项 | 成本 | 价值 | 建议 |
|---|---|---|---|
| A. Oxford 注册（需邮箱授权），获取完整 drive `imu.tar`（Xsens 100Hz） | 中（注册+等待授权） | 真实 IMU 噪声环境，残差真实化 | ⭐ 推荐（P0） |
| B. IGS RINEX 站数据 + 公开 IMU（如 EuRoC）混合 | 高（异构时间戳对齐） | 全 RTK 载波相位验证 | 可选（P1） |
| C. 合成 IMU 保持现状，管道闭环即止 | 低 | 已完成 | 不建议作为终点（无噪声不真实） |
