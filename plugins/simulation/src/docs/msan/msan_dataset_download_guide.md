# MSAN 数据集下载指南 (Sprint 47 T2 交付)

**日期**: 2026-08-09
**状态**: 数据集下载受认证阻塞 — 本指南提供路径与替代方案
**磁盘预算**: C 盘 171GB 可用 (目标 ≤60GB) | WSL 920GB 可用 (推荐下载位置)

---

## 1. 数据集清单与状态

| 数据集 | 规模 | 存储 | 下载方式 | 认证状态 | 状态 |
|--------|------|------|----------|----------|------|
| **NTU4DRadLM** | ~50GB (6 序列) | rebrand.ly/ntu4dradlm → **Microsoft SharePoint** | 浏览器交互 | 🔒 403 (curl/gdown 均被拒) | ⚠️ 待手动下载 |
| **GICI-open-dataset** | ~26GB (11 子集) | OneDrive / BaiduCloud | 浏览器交互 | 🔒 403 | ⚠️ 待手动下载 |
| GICI 仓库内 GNSS 文件 | 22MB | git clone | 直下 | ✅ | ✅ 已就绪 (格式验证通过) |
| GICI-LIB 源码 | ~50MB | git clone | 直下 | ✅ | ✅ 已就绪 (编译完成) |

## 2. 已就绪组件

```
msan_data/
├── gici-open/                 # GICI-LIB 源码 + 编译产物 (build/gici_main + libgici.so)
├── gici-open-dataset/         # 数据集仓库 (标定文件 + 文档, 数据文件需外部下载)
├── pipeline_validate.py       # GNSS 辅助文件格式验证工具
└── pipeline_validation.json   # 验证结果 (BSX/ATX 解析 OK)
```

**格式验证已通过**:
- `CAS0MGXRAP_20221580000_01D_01D_DCB.BSX` (744KB) — BIA/DCB 广播星历偏差文件 ✅
- `igs14.atx` (22MB) — IGS 天线相位中心文件 ✅

## 3. 下载路径 (需人工/浏览器)

### 3.1 NTU4DRadLM (推荐, 50GB)
1. 浏览器打开 `https://rebrand.ly/ntu4dradlm` (需登录 Microsoft 账号)
2. 数据集为 6 个独立序列, 可**按序列选择性下载** (最小序列 246m/`sequence_00`)
3. 下载到 WSL 磁盘: `~/msan_data/ntu4dradlm/`
4. 推荐起始: `sequence_00` (~5GB, 单序列) 验证管道后再全量

### 3.2 GICI-open-dataset (26GB, 11 子集)
1. 见 `gici-open-dataset/README.md` 中的 OneDrive/BaiduCloud 链接
2. 数据文件含: RINEX 观测 (.obs) + 星历 (.nav) + IMU + 相机数据
3. 下载到 `msan_data/gici-open-dataset/data/` (仓库预期的相对路径)

## 4. 替代方案 (若认证持续受阻)

| 优先级 | 方案 | 说明 |
|--------|------|------|
| A | **手动浏览器下载** (推荐) | 登录账号后 wget/浏览器直接下载, 认证一次性 |
| B | **KITTI Odometry** (免认证) | 3D LiDAR + GPS/IMU, 但无 4D 雷达 — 替代验证融合管道 |
| C | **Oxford Radar RobotCar** (申请制) | 毫米波雷达全序列, 需申请表 |
| D | 合成数据 | 用 GICI 星历文件 + 模拟观测生成, 验证管道逻辑 (非真实数据) |

## 5. 管道后续步骤 (数据就绪后)

```bash
# 1. 格式解析 (已就绪, 数据到位后扩展 .obs/.nav 解析)
python3 msan_data/pipeline_validate.py

# 2. GICI-LIB 运行 (需 RINEX 观测数据)
cd msan_data/gici-open
./build/gici_main option/xxx.yaml   # 输出残差报告

# 3. 残差验收门禁: 仿 V9 协议, 标定残差 < 阈值
```

## 6. 风险

- SharePoint/OneDrive 的 403 是认证策略 (非故障): curl/gdown/API 均无法绕过
- NTU4DRadLM 50GB 全量下载会触碰 C 盘预算 → 推荐下载到 WSL 磁盘 + 单序列先行
- M2DGR (~1TB) 明确跳过 (超出磁盘预算, PM 已同意延后)

---

*维护: BottleSumo 治理智能体 | 关联: docs/msan/msan_initial_survey.md (S46 T3)*
