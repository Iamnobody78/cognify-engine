# Sprint 47 执行报告 — MSAN 数据管道阶段 1

**日期**: 2026-08-09
**分支**: `feature/s47_msan_pipeline`（基于 main + sprint46-closed tag）
**PM 裁决**: MSAN 阶段 1 数据管道 P0 | 突破 92.5% 延后 | CI 扩展延后

---

## 结果摘要

| 任务 | 验收标准 | 实测 | 判定 |
|------|----------|------|------|
| **T1** 磁盘容量检查 | C 盘 ≥ 60GB 可用 | **171.3GB 可用** (C:) + **920GB** (WSL) | ✅ PASS |
| **T2** NTU4DRadLM 下载解析 | 数据下载完成 + 解析工具就绪 | ⚠️ 下载受认证阻塞 (SharePoint 403); 解析工具 + GNSS 格式验证就绪 | ⚠️ 部分 (管道就绪) |
| **T3** GICI-LIB 编译标定 | 标定管道跑通 + 残差报告 | ✅ 编译完成 (gici_main + libgici.so); ⚠️ 残差报告需真实观测数据 (认证阻塞) | ⚠️ 部分 (编译完成) |

---

## T1: 磁盘容量检查 — PASS

| 卷 | 容量 | 剩余 | vs 预算 |
|----|------|------|---------|
| C 盘 (Windows) | 476GB | **171.3GB** | ✅ > 60GB (NTU4DRadLM 50GB + 处理空间 + 余量) |
| WSL 根分区 | 1007GB | **920GB** | ✅ 充裕 (推荐下载位置) |

**结论**: 无需 SRS 清理。NTU4DRadLM 完整包 (50GB) 下载预算满足。
**关键决策**: 数据集下载到 **WSL 分区** (920GB) 而非 C 盘, 避免 C 盘压力。
**约束确认**: M2DGR (~1TB) 超出预算 — 遵循 PM 建议, 延后至阶段 2 评估, 本次跳过。

## T2: NTU4DRadLM 下载与解析 — ⚠️ 部分 (管道就绪, 下载受认证阻塞)

### 已交付
- **数据管道基础设施**: `msan_data/` 目录 + `pipeline_validate.py` 解析工具
- **GNSS 辅助文件格式验证通过**:
  - `CAS0MGXRAP_*.BSX` (744KB, BIA/DCB 广播星历) → 解析 OK ✅
  - `igs14.atx` (22MB, IGS 天线文件) → 解析 OK ✅
- **下载指南**: `docs/msan/msan_dataset_download_guide.md` (含 4 个替代方案)

### 阻塞项 (如实报告)
- NTU4DRadLM 下载链接 `rebrand.ly/ntu4dradlm` 解析为 **Microsoft SharePoint** —
  curl/gdown/API 均返回 403 (认证策略, 非故障)
- GICI-open-dataset 同样托管于 OneDrive/BaiduCloud (403)
- 无法无人值守下载 — 需要浏览器手动下载 (登录账号)
- 已提供替代方案: 手动下载 / KITTI (免认证) / Oxford Radar (申请制) / 合成数据

## T3: GICI-LIB 编译与标定管道 — ⚠️ 部分 (编译完成, 残差需数据)

### 已交付 — 编译成功 ✅ (重要里程碑)
```
msan_data/gici-open/build/
├── gici_main        (可执行, 参数校验响应正常)
└── libgici.so       (核心库)
```
- 依赖: Eigen 3.4 + Ceres + glog/gflags + OpenCV + Boost (apt 安装)
- 编译: 3 targets 全部 100% (svo, gici, gici_main)
- 验证: `./gici_main` 正确响应参数校验 (二进制可执行确认)
- 源: `chichengcn/gici-open` (660★) — **GNSS/INS/Camera 集成导航库** (RTKLIB 继承)
- **修正**: S46 调研中 GICI-LIB 描述为 "LiDAR-惯性标定" 有误 — 实为
  **GNSS/INS/Camera 融合导航** (与 MSAN S3 RTK + S4 IMU 轴直接对齐)

### 阻塞项
- 标定管道完整跑通需 RINEX 观测数据 (.obs) — 属 T2 数据集 (认证阻塞)
- 残差报告待数据就绪后执行: `./build/gici_main option/xxx.yaml`

---

## 核心洞察

1. **MSAN 数据管道第一阶段受外部认证约束** — 这是网络/账号层阻塞, 非工程问题。
   所有可程序化执行的工程交付 (工具链/编译/格式验证/文档) 已完成
2. **GICI-LIB 定位修正**: 真实 GICI-LIB = GNSS/INS/Camera 集成导航 (RTKLIB 继承),
   非 LiDAR 标定库 → 与 MSAN 的 RTK (S3) + IMU (S4) 轴直接对齐, 优先级评估不变
3. **磁盘预算充足**: C 盘 171GB 无需清理, 下载策略为 WSL 分区 + 单序列先行

## Sprint 48 建议 (供 PM 裁决)

1. **人工下载窗口**: 需 PM/人工登录 Microsoft 账号手动下载 NTU4DRadLM
   `sequence_00` (~5GB 单序列) 到 WSL — 之后管道即可全自动跑通
2. **替代数据集**: 若认证持续受阻, 授权切换到 KITTI Odometry (免认证,
   3D LiDAR+GPS/IMU) 验证融合管道逻辑
3. **残差门禁**: 数据就绪后, 仿 V9 协议设标定残差阈值门禁

---

## 工作文件

- `msan_data/pipeline_validate.py` + `pipeline_validation.json` (格式验证)
- `msan_data/gici-open/` (源码 + build 产物)
- `docs/msan/msan_dataset_download_guide.md` (下载手册)
- `docs/msan/msan_initial_survey.md` (S46 T3, 含 GICI-LIB 定位修正)
