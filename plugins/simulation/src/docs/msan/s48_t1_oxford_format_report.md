# Sprint 48 T1 — Oxford RobotCar 数据下载与格式分析报告

> 日期：2026-08-09 · 分支：feature/s48_oxford_pipeline · 状态：**完成**

## 1. 数据源可达性结论（重要修正）

**PM 裁决前提 "Oxford S3 直连免认证" 部分不成立，需如实上报：**

| 探测项 | 结果 |
|---|---|
| `mrgdatashare.robots.ox.ac.uk`（完整 drive 数据） | **登录墙**（"RobotCar Dataset Downloads \| Login" 页，HTTP 200 返回 3.5KB HTML） |
| `s3://robotcar-dataset` / `radar-robotcar-dataset` 各 region 探测 | 全部 NoSuchBucket（**无公开 S3 bucket**） |
| 官方 RobotCarDataset-Scraper | 需用户名/密码（登录墙后） |
| **`robotcar-dataset.robots.ox.ac.uk/downloads/sample_small.tar`** | ✅ **公开免认证，HTTP 200，205MB 完整下载** |
| `downloads/sample.tar`（1GB 大 sample） | ✅ 公开可达（含 gps/ldmrs/lms/mono，无 imu/） |

**结论**：Oxford 完整数据集（含 IMU 原始测量）需要注册下载授权；但**公开 sample_small 已含 RTK/INS 后处理真值（ins.csv）+ 原始 GPS（gps.csv）**，足够支撑 GICI GNSS/INS 融合管道验证。

## 2. 下载清单

| 文件 | 大小 | 来源 |
|---|---|---|
| `sample_small.tar` | 205.8 MB | `https://robotcar-dataset.robots.ox.ac.uk/downloads/sample_small.tar` |
| 提取：`gps/gps.csv` | 1.52 MB | 原始 u-blox GPS（Apple 风格 12 列） |
| 提取：`gps/ins.csv` | 21.19 MB | NovAtel SPAN RTK/INS 后处理解 |

存储：`msan_data/oxford/sample_small_raw/gps/`（git 排除，见 .gitignore）

## 3. 格式分析

### 3.1 gps.csv（原始 GPS，5 Hz）

```
timestamp, num_satellites, latitude, longitude, altitude,
latitude_sigma, longitude_sigma, altitude_sigma,
northing, easting, down, utm_zone
```

- 时间戳：**微秒**（1418381153300352），与 KITTI 纳秒不同——转换需除 1e6
- 频率：5 Hz（dt=200ms，199833~200001 µs 极稳）
- 卫星数分布：2~10（主峰 6-9），有 9 条 sat=2（城市峡谷）
- 精度：lat_σ 中位 3.75 m，max 74.1 m（单点 GPS，非差分）
- 坐标：WGS84 lat/lon + ECEF 相对 northing/easting/down + UTM zone（30U）

### 3.2 ins.csv（NovAtel SPAN RTK/INS 后处理，50 Hz）

```
timestamp, ins_status, latitude, longitude, altitude,
northing, easting, down, utm_zone,
velocity_north, velocity_east, velocity_down,
roll, pitch, yaw
```

- 频率：50 Hz（dt=20ms），126,361 行
- **状态质量**：`INS_SOLUTION_GOOD` 97.6%（123,294 行）、`INS_BAD_GPS_AGREEMENT` 1.6%（2,012）、`INS_ALIGNMENT_COMPLETE` 0.8%（1,055）
- 姿态：roll ±0.05°，pitch ±0.07°（城市道路平坦），yaw 0~6.283 rad 全覆盖（往返环线）
- 速度：vel_n -11.3~+11.1 m/s（含停车/起步，全程 ~2.5 km 环线）
- **定位真值级别**：RTK/INS 融合后处理（厘米~分米级），可作为 GICI 输出残差评估真值

## 4. GICI-LIB 兼容性评估

| GICI 需求 | Oxford 对应 | 转换动作 |
|---|---|---|
| GNSS NMEA（GNGGA+GNRMC） | gps.csv lat/lon/alt+σ | `oxford_to_gici.py`：µs→GPS sec，lat/lon→ddm.ddddd，构造 XOR 校验 |
| IMU 文本（Timestamp Acc Gyro） | **⚠️ 公开 sample 缺失** | 方案 A：从 ins.csv 50Hz 位置/姿态差分合成（工程近似）；方案 B：注册拿完整 drive imu/ |
| 真值（残差评估） | ins.csv（50Hz 全状态） | 直接可用 |

**T1 验收达成**：✅ 数据下载完成（205MB sample）＋ ✅ 格式分析报告（本文件）＋ ✅ 兼容性矩阵。

## 5. 遗留问题（上报 PM）

1. **IMU 缺口**：公开数据无原始 IMU。T2/T3 可先用"ins.csv 差分合成 IMU"跑通管道（工程验证），或请求 PM 提供 Oxford 注册凭证以获取完整 drive 的 `imu.tar`（Xsens MTi-100, 100Hz）
2. **无 RINEX 原始观测**：Oxford 提供的是后处理解而非原始载波相位——GICI 全 RTK 需 RINEX，SPP/INS 融合管道不受影响
