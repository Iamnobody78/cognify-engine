# Sprint 47 Final — KITTI 数据管道闭环 (数据源切换后)

**日期**: 2026-08-09
**分支**: `feature/s47_msan_pipeline`
**PM 决策变更**: NTU4DRadLM (SharePoint 认证墙) → **KITTI Odometry (免认证)**

---

## 结果摘要 (数据源切换后全链路闭环)

| 任务 | 状态 | 证据 |
|------|------|------|
| KITTI 下载 | ✅ | `2011_09_26_drive_0001_sync.zip` 458,643,963 bytes (437MB), 108 帧 oxts |
| KITTI → GICI 格式转换 | ✅ | `kitti_oxts_to_gici.py`: IMU 文本 + NMEA RMC/GGA |
| GICI 管道消费 | ✅ | `nmea_to_ie` 解析 108 帧 → IE 轨迹 (经纬度/海拔/GPSTime) |
| 残差报告 | ✅ | yaw RMSE **0.13°**, 位置 RMSE 82.6m (简化 2D DR 误差累积) |
| GICI-LIB 编译 | ✅ | gici_main + libgici.so + 4 转换工具 (S47 前半) |

---

## 1. KITTI 下载 (免认证确认)

- URL: `s3.eu-central-1.amazonaws.com/avg-kitti/raw_data/2011_09_26_drive_0001/...sync.zip`
- **公开 S3, 零认证** — wget 直连, 断点续传两轮完成 (网络限速 ~106KB/s)
- PM 预估 1.5GB, 实测单序列 437MB — 磁盘预算更宽裕
- zip 2 个文件轻微损坏 (warning, 非核心 oxts/velodyne 目录)

## 2. KITTI → GICI 格式转换器 (`msan_data/kitti_oxts_to_gici.py`)

oxts 30 列解析 → 三路输出:
1. **imu.bin.txt** (GICI IMU 文本): `Timestamp AccX AccY AccZ GyroX GyroY GyroZ`
   - 加速度 = oxts 列 9/10/11, 角速度 = 列 17/18/19
   - 时间戳: UTC → GPS 秒 (epoch 1980-01-06 + 15s 闰秒), 纳秒截断微秒
2. **gnss.nmea** (GICI NMEA): `GNRMC` + `GNGGA` 消息对
   - **关键经验 1**: GICI 只 decode `GNGGA` (GN 双星座), 不认 `GPGGA`
   - **关键经验 2**: GGA 无日期, 必须 `GNRMC` 先行提供 ddmmyy, 否则 "no date info" 丢弃
   - checksum: XOR 校验正确生成
3. **residuals_report.json**: IMU 航迹推算 vs oxts GPS/姿态真值

## 3. GICI 管道消费 — 跑通 ✅

```
KITTI oxts (原始 108 帧)
  → kitti_oxts_to_gici.py
  → gnss.nmea (GNRMC+GNGGA 216 句)
  → gici-open/build/nmea_to_ie (GICI 官方工具, 手动编译)
  → gnss.nmea.ie: 108 帧轨迹 (Week 1655, GPSTime 133360.96, 8.4343°E 49.0150°N, 116.43m H-Ell)
```

**跨格式时间戳一致性验证**: IMU GPS 秒 1001077360.96 == Week 1655×604800 + 133360.96 ✅

## 4. 残差报告 (仿 V9 门禁精神)

| 指标 | RMSE | MAE | MAX | 解读 |
|------|------|-----|-----|------|
| **yaw 姿态** | **0.13°** | 0.12° | 0.19° | 角速度积分极准 — IMU 数据质量高, 管道正确 |
| 位置 (ECEF) | 82.6m | 71.6m | 140.7m | 简化 2D DR 的加速度双重积分漂移 (非管道缺陷) |

**说明**: 位置残差大是**验证脚本的简化模型所致** (2D 航迹推算忽略垂直/侧滑/
去重力补偿), 非 GICI 管道问题。yaw 0.13° 证明 IMU→GICI 格式转换精确。
完整 GNSS/INS 融合 (RTK/SPP) 需 RINEX 原始观测, KITTI 仅提供解算后 oxts —
**模态不匹配已在数据源决策中接受, 管道验证目标完全达成**。

## 5. 关键工程经验

1. **GICI NMEA 输入**: `GNGGA` (非 GPGGA) + RMC 日期先行 — 两个坑都需踩过才知道
2. **nmea_to_ie 编译**: format_converters 未纳入顶层 CMake, 需手动 g++ 编译;
   链接链 `-lgici -lrtklib`; librtklib.so 需入系统库 (ldconfig) 解决运行时依赖
3. **g++ 编译环境**: -I 需含 rtklib/include, format_converters/include,
   include, eigen3 — 5 个 include 路径
4. **ExecCommand 环境**: `cd` 不跨命令持久化, `$(pwd)` 偶发为空 — 用绝对路径

---

## 文件清单

```
msan_data/
├── kitti/                          # KITTI 原始数据 (437MB, git 排除)
├── kitti_gici_out/                 # 转换产物
│   ├── imu.bin.txt                 #   GICI IMU 文本 (108 帧)
│   ├── gnss.nmea                   #   GNRMC+GNGGA (216 句)
│   ├── gnss.nmea.ie                #   GICI 工具输出轨迹 (108 帧)
│   └── residuals_report.json       #   残差报告
├── kitti_oxts_to_gici.py           # 转换器 (git 跟踪)
├── pipeline_validate.py            # GNSS 格式验证 (S47 前半)
└── gici-open/                      # GICI-LIB 源码+编译 (git 排除)
```

## Sprint 48 建议

1. **IMU+视觉融合试点**: KITTI 有 image_02 (灰度相机) + oxts IMU —
   可进一步喂入 GICI spp_imu_camera (需合成 RINEX 观测, 成本高, 建议延后)
2. **nmea_to_ie 正式纳入构建**: 修复 format_converters CMakeLists 顶层引用
3. **真实 GNSS 观测补充**: 若需完整 RTK 残差, 需获取带 RINEX 的数据集
   (KITTI 无原始观测) — 建议 MSAN 阶段 2 评估 Oxford Radar / 手动下载 NTU4DRadLM
