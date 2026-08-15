# BottleSumo TASK-005d — V9 门 aggressive 0/2 失败分析 (2026-08-05)

## Sprint 49 记录 (2026-08-09, S49_NCLT_REAL_IMU) — 真实 IMU 集成 (已执行, 待 PM 签收)

**背景**: PM 裁决 P0 = Oxford 注册获取 imu.tar (真实 Xsens IMU 噪声)。T1 注册下载,
T2 真实 IMU 集成, T3 合成 vs 真实残差对比。

**T1 路径修正 (如实上报)**: Oxford 注册要求**学术机构邮箱** (.ac/.edu) + 人工审批,
非学术邮箱标记商业咨询 (需 Oxford University Innovations 商业许可, ref PC/14257)。
当前环境无学术身份 → 注册不可行。**切换数据源**: NCLT (U. Michigan North Campus,
S3 公开免认证 ODbL, 零注册) — Microstrain GX3 真实 IMU 50Hz + RTK GPS 10Hz +
姿态真值 + SLAM 真值 + RTK 误差文件。

**结果**:
- ✅ T2: `nclt_to_gici.py` — 13,836 RTK NMEA 帧 + **269,979 真实 IMU 样本** (50Hz×94min)
- ✅ T3: GICI 消费 13,836 帧全部成功 (W1670, 42.2932N 83.7097W)
- **残差**: [a] GICI IE 端到端 **0.007m** (管道零损耗复现);
  [c] RTK vs SLAM median **2.1m** (max 750m 树冠失锁);
  [b] **真实 IMU DR yaw RMSE 107.8°** (94min) vs S48 合成 0.000°

**核心结论 (噪声影响量化)**: 真实 IMU 零偏 ~0.0005 rad/s × 5640s ≈ 160° 积分放大 →
107.8° RMSE。**这正是 GNSS/INS 融合必要性的量化证据**: 纯 IMU 94min 漂移 100°+,
GICI RTK 位置域保持 0.007m。合成 IMU 0.000° 是数学恒等式 (仅验证管道),
真实 IMU 107.8° 是物理事实 (量化噪声影响)。

**新 bug 经验**:
1. **NMEA alt=nan 崩溃**: gps_rtk fix_mode=2 帧 alt=nan → GICI 输出哨兵 (0,-90)。
   修复: NaN 守卫 (nan→0.0)。修复后 13,836 帧全部有效
2. **IE 坐标单位双标准**: IE 输出**度**, truth 弧度 → 评估器对两者都 math.degrees()
   会放大 57.3 倍 (15,217km 假误差)。教训: 跨格式坐标务必显式标注单位
3. **数据集格式验证方法论**: NCLT 论文 Table 7/8 列定义 + **数值交叉验证**
   (gyro_z 积分 vs euler yaw 差分 ratio=0.976≈1.0) 双重确认, 避免格式假设

**阶段 3 建议**: A (推荐) GICI spp_imu 估计器接入 — 纯积分 107.8° → 融合约束残差;
B (P1) NCLT 27 session 批处理; C (P2) RINEX 数据源。

## Sprint 48 记录 (2026-08-09, S48_OXFORD_PIPELINE) — Oxford GNSS/INS 管道验证 (已执行, 待 PM 签收)

**背景**: PM 裁决 P0 = Oxford Radar RobotCar 数据源评估 (宣称 S3 直连免认证)。
T1 下载+格式分析, T2 Oxford→GICI 转换器, T3 GICI 融合验证+残差。

**结果**:
- ✅ T1 下载: **PM 前提修正** — 完整 drive 在 mrgdatashare 登录墙 (注册授权制),
  **无公开 S3 bucket** (6 region 全 NoSuchBucket)。但 `downloads/sample_small.tar`
  (205MB) **公开免认证**, 含 gps.csv (5Hz 原始 u-blox) + ins.csv (50Hz NovAtel
  SPAN RTK/INS 后处理, 97.6% INS_SOLUTION_GOOD) — 真值质量超 KITTI (有姿态)
- ✅ T2 转换: `oxford_to_gici.py` — 12,636 帧 GNRMC+GNGGA NMEA + 126,360 合成 IMU
  (ins.csv 差分, 填补公开数据无 IMU 的工程路径) + truth_ins.csv
- ✅ T3 融合: **GICI nmea_to_ie 消费 12,636 帧全部成功** (KITTI 仅 108 帧, 规模 ×117),
  IE 轨迹 (51.7606°N 1.2613°W Oxford 市中心, W1822=2014-12-12) ✓
- **残差**: [4] GICI IE 端到端 RMSE **2.84m** == [1] raw GPS vs 真值 2.84m
  (**管道零损耗**); [2] 合成 IMU yaw 0.000° (差分-积分自洽, 验证数学正确性,
  但无真实噪声, 已如实标注)

**关键经验 (新 bug 发现)**:
1. **NMEA ddm 负号错误**: `-115.68082,W` → 必须非负 `115.68082,W` (NMEA 标准:
   方向由 E/W 字母表达, ddm 值永不带负号)。KITTI 为正经度故未暴露; Oxford 西经
   才触发。修复后 IE 坐标从 2.26°E (错误) 修正为 -1.2613°E (正确)
2. **NMEA 时间戳截断**: `.00` 秒 → 亚秒 `.ss` (hundredths), 消除 1.1m 管道残差损耗
   (时间对齐从整秒提升至 0.01s)
3. **GICI IE 列序**: Week GPSTime **UTCTime Longitude Latitude** H-Ell — UTCTime
   是秒单位 (非毫秒), 解析错位会把 UTCTime 当 lon 导致 7165km 假轨迹
4. **bash -c 变量展开**: PowerShell 宿主会先展开 `$d`/`$b` 导致 URL 损坏 —
   一律写脚本文件再 `bash script.sh`

**验证边界 (如实)**: Oxford 提供后处理解 (无 RINEX 载波相位) → GICI 全 RTK 不可行,
  本管道验证 NMEA 位置域 + IMU 融合 (数据源本质决定)。真实 IMU 噪声需注册拿
  imu.tar (Xsens MTi-100 100Hz)。

## Sprint 47b 补充记录 (2026-08-09, S47_FINAL_KITTI) — 数据源切换: KITTI 管道闭环 (已完成)

**PM 决策变更**: NTU4DRadLM (SharePoint 认证墙) → **KITTI Odometry (免认证)**
验证目标等价: 数据下载 → GICI-LIB 编译 → 数据管道跑通 → 残差报告。

**✅ 全链路闭环**:
- KITTI 下载: `2011_09_26_drive_0001_sync.zip` 437MB (S3 公开, 零认证, wget 断点续传)
- 转换器 `kitti_oxts_to_gici.py`: oxts 30 列 → GICI IMU 文本 + GNRMC/GNGGA NMEA
- **GICI 消费成功**: `nmea_to_ie` 官方工具解析 108 帧 → IE 轨迹 (8.4343°E 49.0150°N)
- 跨格式时间戳一致性: IMU GPS 秒 == Week 1655×604800+133360.96 ✅
- 残差: yaw RMSE **0.13°** (IMU 质量高), 位置 82.6m (简化 2D DR 漂移, 非管道缺陷)

**关键经验 (GICI NMEA 两个坑)**:
1. GICI 只 decode `GNGGA` (GN 双星座), 不认 `GPGGA` — 首个 IE 输出只有表头
2. GGA 无日期, 必须 `GNRMC` 先行提供 ddmmyy, 否则 "no date info" 被丢弃
3. format_converters 未纳入顶层 CMake — 需手动 g++ 编译 nmea_to_ie,
   链接 `-lgici -lrtklib`, librtklib.so 需 ldconfig 入系统库
4. ExecCommand 中 `cd` 不跨命令持久化 + `$(pwd)` 偶发为空 — 一律绝对路径

**验证边界 (如实)**: 完整 RTK/SPP 融合需 RINEX 原始观测 (KITTI 无), 管道验证
目标 (下载→编译→格式转换→GICI 消费→残差) 完全达成, 模态不匹配已在数据源
决策中接受。

## Sprint 47 记录 (2026-08-09, S47_MSAN_PIPELINE) — MSAN 数据管道阶段 1 (已交付/部分受限)

**背景**: PM 裁决 P0 = MSAN 阶段 1 数据管道 (NTU4DRadLM + GICI-LIB)。T1 磁盘检查,
T2 数据下载解析, T3 GICI-LIB 编译标定。约束: C 盘 ~134GB (Yellow 130GB 附近),
M2DGR (~1TB) 跳过。

**结果**:
- ✅ T1 磁盘: C 盘 **171.3GB** 可用 (实测比 PM 预估充裕), WSL 920GB — 无需清理,
  下载策略 = WSL 分区 + NTU4DRadLM sequence_00 单序列先行
- ⚠️ T2 数据: **认证阻塞 (非工程问题)** — NTU4DRadLM 短链解析为 Microsoft
  SharePoint, GICI 数据集在 OneDrive/BaiduCloud, curl/gdown/API 全部 403。
  HF 无镜像。已交付: `pipeline_validate.py` + BSX/ATX 格式验证通过 + 下载指南
  (4 替代方案: 手动下载 / KITTI / Oxford Radar / 合成数据)
- ✅ T3 编译: **GICI-LIB 编译成功** (gici_main + libgici.so, 3 targets 100%,
  依赖 Eigen3.4+Ceres+glog+OpenCV)。`./gici_main` 参数校验响应正常。
  残差报告需 RINEX 观测数据 (T2 阻塞连带)

**关键修正 (重要)**:
- **GICI-LIB 定位修正**: 真实 GICI-LIB = **GNSS/INS/Camera 集成导航库** (FGO,
  RTKLIB 继承, chichengcn/gici-open 660★), 非 S46 调研误写的 "LiDAR-惯性标定"。
  与 MSAN S3 RTK + S4 IMU 轴直接对齐 → 优先级评估不变 (P0), 用途从"标定"改为
  "RTK/INS 融合" — docs/msan/msan_initial_survey.md 已修正
- **经验**: 数据源调研应先解析最终落地 (SharePoint/OneDrive) 再承诺下载;
  外部认证 403 不是故障, 需人工下载窗口

**后续**: 数据就绪后 `./gici_main option/xxx.yaml` 跑融合管道 → 残差门禁
(仿 V9 协议)。S48 建议: PM 授权人工下载 sequence_00 或切换到 KITTI 验证管道。

## Sprint 46 记录 (2026-08-09, S46_CI_MSAN) — CI 门禁 + nano 冻结 + MSAN 调研 (已关闭)

**背景**: PM 裁决 A = nano 系列关闭 (边缘冻结 nano_s44_t1_data.pt), B = CI 每日
双轨门禁回归 (P0), C = 突破 92.5% 延后, D = MSAN 协议调研 (P1 并行)。

**结果**:
- ✅ T1 CI: `governance/ci/daily_gate_guard.sh` (full 40ep 基线 92.5% / fast 10ep
  基线 90% 统计下界 / --check 读报告) + GH Actions `schedule cron 30 2 * * *` +
  Job 9 gate-regression (<92.5% 失败) 纳入 summary。首跑 nano 37/40 + dagger 37/40。
  注意: evaluator 内置阈值 60%, 92.5% 判定在 workflow/脚本层强制执行
- ✅ T2 归档: `docs/engineering/nano_series_closeout_20260809.md` — 边缘冻结
  nano_s44_t1_data.pt (789p, 92.5%), 容量/数据/教师三维度归因完备
- ✅ T3 MSAN 调研: `docs/msan/msan_initial_survey.md` — 四轴协议 (雷达/导航/RTK/
  IMU), 试点 S1+S3, P0: NTU4DRadLM+M2DGR 数据管道 + GICI-LIB

## Sprint 45 记录 (2026-08-09, S45_NANO_DATA_SCALE) — 数据红利饱和确认 + 双轨部署 (已关闭)

**背景**: PM 裁决 P0 = 双轨部署 (nano v2 边缘 + DAgger 在线), T1 = 数据扩展
(200ep→500ep, "用 DAgger 教师收集"), T2 = 门回归。验收: 门 ≥92.5% + 220+1。

**实现**:
- T0 双轨: v9_gate_evaluator.py 新增 `--policy {nano,dagger}` (优先级 --model >
  --policy > 默认)。`--policy nano` → nano_s44_t1_data.pt (边缘), `--policy dagger`
  → chase_dqn_dagger_s40.pt (在线)
- T1 双教师对照: distill_chase_s44.py 新增 `--teacher-mode {rule,net}` +
  `collect_chase_net()` (网络 argmax rollout, 加载 DAgger 教师收集演示)

**✅ S45 实验结果 (双杠杆均无效, 92.5% 确认为 nano 硬上界)**:
| 实验 | 教师 | 数据 | acc | 门禁 | 判定 |
|------|------|------|-----|------|------|
| S44 基线 | 规则 90% | 200ep ~1150 | 94.5% | 37/40 | — |
| T1a | 规则 90% | 500ep 4101 | 96.4% | **37/40** | ✅ 数据红利饱和 |
| T1b | DAgger 92.5% | 500ep 4167 | 99.6% | **37/40** | ✅ 教师质量非瓶颈 |

三实验逐位相同 (random 7/8, aggressive 8/8, defensive 6/8, circler 8/8, counter 8/8)。
T0 双轨: nano 37/40 + dagger 37/40 路由正确。T2 回归: 220+1 全绿。

**关键结论**:
- **数据红利在 200ep 已饱和**: 500ep (2.9×数据) 零增益 — S44 的 345→1150 是
  补覆盖缺口的一次性红利, 之后边际为 0
- **教师质量不是瓶颈**: 规则教师 (90%) 与 DAgger 教师 (92.5%) 蒸馏结果逐位相同 —
  学生不继承教师上界之上, 也不被其限制 (S44 已超越教师)
- **92.5% = 789 params nano 架构硬上界**: 容量 (S44), 数据 (S45), 教师 (S45)
  三维度全部验证无效 → 剩余杠杆仅架构变更/教师集成, 或接受终局
- 双轨部署闭环: 在线 DAgger + 边缘 nano (38% 参数) 均 92.5%

## Sprint 44 记录 (2026-08-09, S44_NANO_UPGRADE) — 蒸馏数据扩展 + nano 容量提升 (已关闭)

**背景**: PM 裁决 P0 = 接受 92.5% 门禁上界 (S40 DAgger 保持部署), 转向 **nano 泛化差距**
(random 6/8 vs teacher 7/8)。T1 = 蒸馏数据扩展 (345→1000+ 样本, 聚焦 random 多样性);
T2 = nano 容量提升 (hidden 16×2=789 → 24×2=1365 params); T3 = 门禁回归 ≥90% + 220+1。
验收: T1 nano random ≥7/8; T2 nano 门禁 ≥90% (36/40)。

**实现 — distill_chase_s44.py (参数化 nano 蒸馏)**:
- 复用 `collect_chase` 13-slot 课程, 数据从 60ep (~345 样本) 扩展到 **200ep (~1150 样本)**
- NanoQNet9 可配置 hidden_dim (16→24), 输出 21 动作
- T1 实验: 200ep × hidden 16 (789 params) → `nano_s44_t1_data.pt`
- T2 实验: 200ep × hidden 24 (1365 params) → `nano_s44_t2_cap.pt`
- v9_gate_evaluator.py `_RLGateAgent._load` 改为**自适应加载** (从 state_dict 推断
  hidden_dim/state_dim), 兼容 7-dim 旧模型与 9-dim 新模型

**✅ S44 实验结果 (双实验均通过, 泛化差距闭合)**:
| 指标 | teacher | S44-T1 (data) | S44-T2 (cap) | 判定 |
|------|---------|---------------|--------------|------|
| 门禁 | 90% | **92.5% (37/40)** | **92.5% (37/40)** | ✅ ≥90% 验收 |
| random | 7/8 | **7/8** | **7/8** | ✅ ≥7/8 验收 (S38: 6/8) |
| aggressive | 8/8 | 8/8 | 8/8 | ✅ |
| defensive | — | 6/8 | 6/8 | 持平 |
| circler | — | 8/8 | 8/8 | ✅ |
| counter | — | 8/8 | 8/8 | ✅ |
| 回归 | — | 220+1 全绿 | — | ✅ T3 |

**关键洞察: 数据扩展 (T1) 单独即可达 92.5%**:
- T1 (789 params, 200ep) 与 T2 (1365 params, 200ep) 门禁完全相同 (37/40)
- **容量不是瓶颈 — 数据多样性是主导因素** (与 S38→S44 数据量 345→1150 直接对应)
- nano 门禁 92.5% **超越教师 90%**, 与 S40 DAgger 持平 — 架构上界确认,
  不再需要更大网络
- random 6/8→7/8: 数据扩展补上了 random 对手的覆盖缺口 (此前 nano 见过的
  random 轨迹不足)
- **部署候选**: nano v2 (92.5%) 与 DAgger (92.5%) 并列, 由 PM 裁决是否
  nano 替换 DAgger 或双轨并行 (nano 更轻: 789 params vs 教师 2.3k+, 适合边缘)

## Sprint 43 记录 (2026-08-09, S43_RL_AGGRESSIVE) — 更激进纯 RL (λ→0.1 + phase2 延长) (已关闭)

**背景**: PM 裁决 P0 = 路径 A 更激进纯 RL (S42 自然延伸), 路径 B 奖励塑形延后,
路径 C 接受上界备选。安全熔断: 门禁 <90% 连续 2 轮 / FW_MAX 塌缩 / 训练内-门禁
>15pp → 回滚 S40。验收: T1 defensive ≥7/8 + 门禁 ≥92.5%; T2 训练内 vs 门禁 ≤10pp;
T3 门 ≥92.5% + 回归全绿。

**T1 配置 (vs S42)**: finetune_dqn_s42.py 参数化复用, 1200ep (S42: 1000ep)
- λ-tail 0.1 (S42: 0.3) — 更深度释放教师约束
- phase2-steps 5000 (S42: 3000) — 更长纯 RL 探索窗口
- β 退火 1.0→0.1 over 2400 steps (1200ep × 2), 教师校验每 10 步 p=0.5 保留 (T2)

**❌ S43 实验结果 (失败, 门禁 85%)**:
| 指标 | S40 | S42 | S43 | 判定 |
|------|-----|-----|-----|------|
| 门禁 | 92.5% | 92.5% | **85% (34/40)** | ❌ 低于 90% 熔断线 |
| defensive | 6/8 | 6/8 | **5/8** | ❌ 退化 |
| circler | 8/8 | 8/8 | **6/8** | ❌ 转向技能受损 |
| 动作多样性 | 4 | 4 | **3** (丢动作 15 FW_LEFT_HARD) | ⚠️ |
| 训练内 vs 门禁 | 2.5pp | 2.5pp | 1.7pp | ✅ |

**根因: λ→0.1 过度释放教师约束** — Q 值漂移/技能丢失 (与 S41 Exp-B 失败同构,
教师校验防住完全崩溃但挡不住退化)。**dagger_lambda 下界 = 0.3 测绘完成**:
λ 恒 1.0 (S40) = 92.5% | λ→0.3 (S42) = 92.5% | λ→0.1 (S43) = 85% → 最优区间 λ ≥ 0.3
**安全熔断**: 门禁 85% < 90% (第 1 轮, 未连续 2 轮); 动作 3 种 (未塌缩 ≤1);
训练内-门禁 1.7pp (未超 15pp) → 未正式触发但趋势明确
**S43 结论**: 路径 A (纯 RL 系列) 完整测绘完毕 — S42 (λ→0.3) 是最优配置,
更激进 (λ→0.1) 反而退化。**路径 C 接受上界: 92.5% 为当前架构硬上界**。
S40 DAgger 保持部署。

## Sprint 42 记录 (2026-08-09, S42_RL_TAIL) — 纯 RL 后段突破教师监督上界 (进行中)

**背景**: PM 裁决 P0 = 路径 A 纯 RL 后段 (β 退火后延长自主阶段, TD 学 FW_MAX 推进),
路径 B 奖励塑形延后, 路径 C 接受上界备选。安全熔断: 门禁 <90% 连续 2 轮 /
FW_MAX 塌缩 (动作数 ≤1) / 训练内-门禁差距 >15pp → 回滚 S40。
验收: T1 defensive ≥7/8 + 门禁 ≥92.5%; T2 训练内 vs 门禁 ≤10pp; T3 门 ≥92.5% + 回归全绿。

**T1/T2 实现 — 两阶段 DAgger (finetune_dqn_s42.py)**:
- **阶段1 (0-2000 steps)**: β 1.0→0.1 退火, dagger_lambda 恒 1.0 (技能保持, 同 S40)
- **阶段2 (2000-5000 steps, 纯 RL 尾)**: β 恒 0.1 (低教师覆盖), dagger_lambda
  1.0→0.3 线性释放 (TD 主导, 教师知识边界外探索), epsilon 0.01 保持
- **T2 漂移防护**: 阶段2 每 10 步以 p=0.5 用教师动作校验 DQN (分歧则跟随教师) —
  防止 Q 值漂移 (FP-RL-005 复发), 但保留自主空间
- **关键区别 vs S41 Exp-B**: lambda 退火**晚开始** (beta 退火完成后) 且目标 0.3
  (保留 30% 教师约束) 而非同步退到 0.2 — Exp-B 失败于退火过早过猛 (后期 63%)
- smoke 验证: 两阶段切换正确 (Ep10 β=0.23 λd=1.00 → Ep20 β=0.10 λd=0.30)

**✅ S42 实验结果 (部分成功)**:
| 指标 | S40 | S42 | 判定 |
|------|-----|-----|------|
| 门禁 | 92.5% | **92.5% (37/40)** | ✅ 保持 |
| defensive | 6/8 | **6/8** | ❌ T1 未达 7/8 |
| 训练内 defensive | 3/6 | **4/6** (提升) | ✅ 正向信号 |
| 动作多样性 | 4 种 | 4 种 (无塌缩) | ✅ 熔断未触发 |
| 训练内 vs 门禁 | 2.5pp | 2.5pp (90% vs 92.5%) | ✅ T2 ≤10pp |
| 回归 | — | 220+1 全绿 | ✅ T3 |

**T1 结论: 纯 RL 后段方向正确但未突破 ep0/ep5**:
- 训练内 defensive 3/6→4/6 (纯 RL 尾让 DQN 在教师边界外学到部分 FW_MAX 推进)
- 但门禁 8 局协议下 ep0/ep5 仍失败 ({15:12,19:12} 纯左转 / {20:24} 纯右转) —
  与教师逐字相同, 教师监督上界在门禁统计上仍是硬约束
- 未退化 (对比 Exp-B 87.5% 崩溃) — 晚退火 + 目标 0.3 + 教师校验有效防止漂移
- **S43 候选**: (a) 更激进纯 RL (lambda→0.1, phase2 更长) (b) 奖励塑形 (路径 B)
  (c) 接受 92.5% 上界 (S40/S42 持平, 部署不变)

## Sprint 41 记录 (2026-08-09, S41_DEFENSIVE) — defensive 定向提升 + dagger_lambda 退火 (进行中)

**背景**: PM 裁决 P0 = defensive 定向提升 (6/8→8/8), P1 = dagger_lambda 退火
(1.0→0.2), β 窗口延长延后。验收: T1 defensive 8/8 + 门禁 ≥92.5%; T2 门禁 ≥92.5%
+ 防御无退化; T3 回归 220+1 全绿。

**T1 失败局分析 (✅ 关键洞察)**:
- DAgger defensive 6/8 **已超越教师 5/8** (ep2 教师输、DAgger 赢)
- 剩余 2 失败局 (ep0/ep5) 与教师动作序列**逐字相同** ({15:14,19:11} 纯左转 /
  {20:24} 纯右转, 零 FW_MAX 推进) — dagger_buffer CE 监督复制了教师失败模式
- **根因**: defensive 对手慢速 (0.40) 不主动进攻, 模型陷入纯转向打转、从不直线推进
  → 追不上/不进攻 → 超时失败。动作 15 (FW_LEFT_HARD) 只在失败局出现 (教师从不使用)
- **T1 策略**: defensive 采样加权 (课程 pool 从 2 slots → 4 slots), 更多学习机会
- **T2 策略**: dagger_lambda 1.0→0.2 线性退火 (5000 steps 内), 释放自主探索空间,
  学习教师在困难局不会的 FW_MAX 推进

**实验设计**: finetune_dqn_s41.py (s40 参数化扩展: --defensive-weight, --lambda-decay)
- Exp-A (T1): defensive-weight=4, lambda 固定 1.0
- Exp-B (T2): defensive-weight=2, lambda 1.0→0.2
- 两实验 1000ep 并行后台运行; 结果如下

**✅ S41 实验结果 (双实验均未超越 S40 92.5%)**:
| 模型 | WR | defensive | random | 备注 |
|------|-----|-----------|--------|------|
| S40 DAgger (部署) | **92.5%** | **6/8** | 7/8 | 仍最优 |
| Exp-A (defw4 .best) | 90% | 5/8 | 7/8 | 训练内 def 3/6→4/6 但门禁反降 |
| Exp-B (lam02 .best) | 87.5% | 5/8 | 6/8 | lambda 退火确认失败 |

**T1 defensive 加权 → 门禁未转化 (❌ 未达验收)**: 训练内 defensive 4/6 (67%) 提升
但门禁 5/8 低于 S40 6/8。ep0/ep5 仍教师同款失败 ({15:12,19:12} 纯左转 / {20:24}
纯右转), ep7 新增失败 ({5:1,20:18})。**加权只增加 exposure, 无法突破 dagger_buffer
复制教师失败模式的本质** — ep0/ep5 是教师 5/8 也输的困难局 (教师监督上界)
**T2 lambda 退火 (❌ 确认失败)**: 87.5%, random 6/8 退化。1.0→0.2 释放自主探索过猛,
后期失去教师约束 (训练后期 WR 从 83% 跌至 63%, .best 83% < final 倾向)。
**S41 教训**: 教师监督上界 (90%) 是 DAgger 软约束 — 要突破 defensive 困难局需:
(a) 纯 RL 阶段 (β→0 后延长自主探索) / (b) 定向奖励塑形 (直线推进正奖励) /
(c) 接受 6/8 为当前上界 (S40 已超教师 5/8)
**回归**: 220 passed + 1 skipped 全绿 (s41 脚本 + 模型未破坏任何测试)

## Sprint 40 记录 (2026-08-08, S40_DAGGER) — DAgger 在线纠正 + 训练内评估协议统一 (T0)

**背景**: PM 裁决 FP-RL-005 根因 = "混合 replay + epsilon 打断数十步时序一致轨迹"。
S39 SkillProtected 仅 40→60%。S40 P0 = DAgger 在线纠正, P1(T0) = 训练内评估协议统一
(所有后续训练脚本前置条件), T2 = 门回归验证。
验收: T0 训练内 WR vs 门禁 WR 差距 ≤10pp; T1 微调门禁 ≥90% (36/40); T2 门 ≥90% + 回归全绿。

**T0 — 训练内评估协议统一 (✅ 实现)**:
- 发现 `train.py` 的 GATE_BEHAVIORS 仅 4 策略 (缺 aggressive) — 门禁是 5 策略
- `finetune_dqn_s40.py` 新增 `GATE_MIX = [random, aggressive, defensive, circler,
  counter]` + `mixed_gate_eval()`: 5 策略 × 稳定种子 (_stable_seed, 与门禁同构),
  defensive 用 opponent_speed_scale=0.40, win 判定 = terminated and total_reward > 5
  (与 v9_gate_evaluator 逐字一致)
- **S39 教训落实**: 训练内评估不再固定单一 opponent_profile="aggressive" + 固定种子
  (S39 假阳性 97.8% vs 门禁 60% 的根因) — 训练内 WR 现在直接反映门禁混合策略表现
- smoke 验证: 5ep 后 mixed eval WR=90% (9/10) 与教师门禁 90% 吻合

**T1 — DAgger 原型 (✅ 成功, FP-RL-005 修复)**:
- `DaggerAgent(DQNAgent)`: 冻结 net.0 (fc1) + L2 技能保护 (S39 保留) +
  **教师覆盖**: 每步以概率 β 用冻结 teacher_net (BC 权重) 动作替代 DQN 动作执行 +
  **dagger_buffer** (独立 20000 槽, 存 (state, teacher_action), 不污染 DQN reward buffer) +
  混合 loss = TD (DQN replay) + dagger_lambda=1.0 * CE (dagger buffer → 拉向教师动作) + skill L2
- **β 退火**: 1.0 → 0.1 线性 (2000 steps): 早期完全教师覆盖 (保时序一致), 后期自主
- 1000ep 训练完成, **Final MixedEval WR=90.0% (27/30)** (T0 协议, 训练内可信指标)

**✅ S40 验收结果 (全部达标)**:
| 验收 | 标准 | 实测 | 判定 |
|------|------|------|------|
| T0 训练内 vs 门禁差距 | ≤10pp | \|90% - 92.5%\| = 2.5pp | ✅ |
| T1 微调门禁 | ≥90% (36/40) | **92.5% (37/40)** | ✅ |
| T2 门回归 | ≥90% | 92.5% | ✅ |
| T2 双端回归 | 220+1 绿 | 220 passed + 1 skipped | ✅ |

**门禁 per-strategy (37/40)**: random 7/8, aggressive 8/8, defensive **6/8** (+1 vs
教师 5/8), circler 8/8, counter 8/8 — **DAgger 微调超越教师 (defensive 改善)**
**动作多样性完全恢复**: {5:135, 15:14, 19:124, 20:134} 4 种动作 (与教师一致) vs
S39 塌缩 {5:309} 单一 FW_MAX
**FP-RL-005 闭环**: 恒定 40% (原) → 60% (SkillProtected) → **92.5% (DAgger)**

**根因确认**: PM 诊断正确 — 教师覆盖保留数十步时序一致轨迹 (β=1.0 早期) +
dagger_buffer CE 监督把 Q 拉向教师动作多样性, 双重机制防止 Q 塌缩。
**改进方向 (S41 候选)**: defensive 6/8 仍低于 random/circler/counter 8/8;
dagger_lambda 恒 1.0 未随 β 退火 (后期可能过度拉向教师); 更长的 β 退火窗口。

**关键 API 修正 (运维)**: 环境参数名是 `opponent_speed_scale` 非 speed_scale;
Config 无 .get() 方法 (用 quick_test()); sys.path 需含 bottlesumo_pi/ + simulation/;
PowerShell 引号嵌套继续规避 (脚本文件方式)。

## Sprint 39 记录 (2026-08-08, S39_DQN_FIX) — FP-RL-005 微调修复失败 + T2 温度扫描 null + 训练内评估协议缺陷

**背景**: PM 裁决 P0 = DQN 微调修复 (FP-RL-005), P1 = nano 蒸馏温度扫描。
T1 验收: 微调门禁 ≥90% (36/40) + 双端回归 220+1 绿; T2 验收: nano 门禁 ≥87.5%
(35/40) + random 胜率 ≥ 教师 7/8。

**T1 SkillProtectedAgent 微调 (❌ FAIL)**: 冻结 fc1 (net.0) + L2 技能保护正则
(skill_lambda=1e-3) + 低 epsilon (0.05→0.01) + 13-slot 轮转课程, 1000ep 训练。
- 训练内最终评估 WR=97.8% (88/90) — **假阳性** (见下方协议缺陷)
- 门禁实测 **WR=60% (24/40)** ≪ 90% 验收线。per-strategy: random 6/8, aggressive
  4/8 (教师 8/8!), defensive 4/8, circler 3/8 (教师 8/8!), counter 7/8
- **Q 值完全塌缩**: 309/309 步动作 = 5 (FW_MAX 全速直冲)。教师动作多样
  {5, 15, 19, 20} = FW_MAX + FW_LEFT_HARD + FW_LEFT_FAST + FW_RIGHT_FAST (追踪技能)。
  微调抹除全部转向动作 → 追不上 circler (3/8), 对冲 aggressive 劣势 (4/8)
- **对比**: 恒定 40% (FP-RL-005 原态) → 60%: SkillProtected 部分缓解, 未消除塌缩
- **训练内评估协议缺陷 (新发现, 根因之一)**: `finetune_dqn_s39.py` eval_env 固定
  `opponent_profile="aggressive"` + 固定 seed → 97.8% 是对单一对手的过拟合指标,
  门禁混合 5 策略下 aggressive 仅 4/8。**训练内评估必须用 GATE_BEHAVIORS 混合协议**,
  否则任何微调脚本都会因单一对手过拟合而误判成功
- **架构一致性确认**: 微调模型 = 教师同架构 (2069 params, net.0/2/4), 门禁
  agent_mode="rl" 真实加载 (非降级), 排除错位加载假象
- **S39 结论**: FP-RL-005 未修复。60% > 40% 说明"低 epsilon + 冻结 + L2"方向有
  微弱价值, 但 Q 值塌缩根因未解: 混合 replay + epsilon 仍打断追踪轨迹 (数十步
  时序一致行为), Q-learning max 算子将 Q 推向单一动作。剩余候选: DAgger 在线纠正
  (交互式演示纠正, 直接保留时序一致性) / per-profile Q 集成 / 或放弃 fine-tune
  维持 BC 直投 (教师 90% 已过门)

**T2 温度扫描 (⚠️ null result)**: distill_chase_s38.py 新增 `--temp` 软目标 KL
蒸馏 (F.kl_div × T²)。三温度 t050/t100/t200 (94%/93%/88.5% 蒸馏 acc):
- 门禁 **三者完全一致 35/40 (87.5%)**, random 6/8 — **argmax 表面收敛**:
  不同权重 (distinct weights) → 逐动作相同的离散策略
- 温度不移动离散动作 argmax 表面 → 随机胜率停滞 6/8 < 教师 7/8 (泛化差距未闭合)
- 验收: 门禁 ✓ (35/40 ≥ 35/40), 泛化 ✗ (6/8 < 7/8)。诚实 null 结果
- **教训**: 蒸馏温度只平滑 soft-target 分布, 对 21 离散动作的 argmax 表面几乎
  无杠杆; nano 泛化差距需别处闭合 (数据多样性 / 架构 / 奖励)

**回归**: 双端全绿 **220 passed + 1 skipped** (simulation 73 + meta_harness 134
+ dashboard 13)。a1_warmup_test.py 独立 (vision_proxy 模块, 非主套件)。

**V9 门状态**: 教师 BC 90% (36/40) 保持过门; nano 87.5% 过门; 微调 60% 未过门
但非部署候选 (部署 = 教师直投)。V9 裁决门: 10% → 60% 阈值线, 部署轨道已达标。

**运维**: 门禁报告 JSON 在 `.aionui/meta_governance/gate/v9_gate_report.json`
(旧 v11 报告需 --json 重跑覆盖); PowerShell 引号嵌套继续规避 (脚本文件方式)。

## Sprint 37 记录 (2026-08-08, S37_OBS_UPGRADE) — 观测升级 9 维 + 轮转课程 + 门回归

**背景**: PM 裁决 P0 = 观测升级 (FP-RL-003: 7 维 obs 无对手速度 → 追击技能不可学),
P1 = 轮转课程并行, T3 门 ≥60% (12/20)。

**T1 观测升级 (✅)**: obs 7→9 维 (追加对手速度投影 opp_v_forward/opp_v_right, 机器人
相对系旋转等变, 归一化 /0.6 ±1); 追加索引 7,8 零侵入 (门策略/教师/奖励只读 0..6);
Config.state_dim=9 全链传播。**观测充分性判定: obs[5]=opp_angle_rel 即指向角差,
与全知启发式信息等价 — 观测绝对充分**。

**T2 轮转课程 (✅)**: 13 槽加权 (门套件×2 + 速度阶梯×1), 每门档案 15.4% ≥ 15% 验收。

**T3 门回归 (✅ BC 轨道 / ⚠️ DQN 轨道)**: **chase-BC (全知追敌教师行为克隆, 未微调)
门胜率 77.5% (31/40) ≥ 60% 过门**; 9 维 DQN 微调 (1000ep/5000ep/chase-BC+2000ep)
三次均 40%, 逐策略完全一致。双端回归 220 passed + 1 skipped + 0 失败。

**判别实验链 (FP-RL-003 证伪)**:
- 全知追敌基线: random 10/10, circler 9/10, defensive 0/10 → 追击型物理可胜 (除 defensive)
- 反直觉变体 (诱敌/侧翼): defensive 三策略全 0/10 → **对称参数结构性不可胜**
  (0.53 vs 0.53 对冲僵持 + 边缘撤退回中逃逸) — 需物理审计或门档案复核
- 5000ep 长训练零改善 → 排除训练量
- **FP-RL-005 (新主导): DQN 微调灾难性覆盖** — BC 权重 77.5%, 微调后恒 40%;
  追击是数十步时序一致行为, 混合 replay + epsilon 打断 → 折中"对冲型"策略
- S38 修复候选: 低 epsilon 微调 + 技能保护正则 / 分策略 Q 集成 / DAgger 在线纠正

**运维新条目**: common/config.py 与 lightweight_env.py 此前未 git 跟踪 (本次首次纳入);
`Config("quick_test")` 错误用法 (位置参数→state_dim), 应 `Config.quick_test()`。

## Sprint 38 记录 (2026-08-08, S38_BC_DEPLOY) — chase-BC 直投 + defensive 物理审计 + V9 自蒸馏

**背景**: PM 裁决 P0 = chase-BC 直投 (77.5% ≥ 60% 不等微调), P1 = defensive 物理审计,
P2 = DQN 微调修复 (延后), V9 plateau 自蒸馏条件满足。

**T1 chase-BC 直投 (✅)**: 新学生 (scale 0.4 演示) 门 90.0% (36/40) ≥ 60%;
S37 77.5% → +12.5%。四策略无回归 (random 7/8 保持)。

**T2 defensive 物理审计 (✅)**: defensive 0/8 → **5/8 (62.5%)** ≥ 50% 验收。
- **FP-RL-006 修复确认**: reward_functions.py 无条件 probe 假死 bug
  (`edge_min < edge_critical/20 → -150`) 已移除 — 曾使探针先出界判负,
  追击者推挤中假死 (双输), defensive 结构性不可胜的隐藏元凶之一。
- **bait-counter 绕行诱敌 (非被动)**: defensive (STOP→edge<0.3 REVERSE→opp<0.4
  HARD_FORWARD) 接触时 81-100% 对冲 — 非纯被动, "绕行诱敌"才是真结构 →
  被动防御判负路径依据不足, 走速度不对称路径。
- **速度不对称扫参** (门协议 seed × 8, s38 学生): 0.5→0/8, 0.40→6/8, 0.35→8/8。
  机制: 追击者转向稀释有效推进 (0.30×cos 大角≈0.21) vs defensive 直线,
  直到 scale 0.4 (直线 0.212 < 0.30) 才反转。取 0.40 保留 bait-counter 战术存在。
- 训练-评估一致性: collect_chase / train.py / gate evaluator 三处 scale 统一 0.4。

**T3 V9 plateau 自蒸馏 (✅ 首次完整闭环)**: 教师 chase-BC v2 (2069 params) →
NanoQNet9 16×2 (789 params, **38%** ≤ 50% 验收) → 门 **87.5%** (35/40) ≥ 60% ✅。
nano random 6/8 vs 教师 7/8 (轻量化正常权衡, 仍过门)。

**判别实验链 (新知识)**:
- **确定性 seed 陷阱**: 门评估器 `_stable_seed(ep, name)` 确定性 → 同模型同配置
  跑出逐位相同结果。10:54:31 报告与 S37 数值逐位相同 = S37 旧报告, 非新模型;
  验证新模型必须显式跑门 (本次 23:04 run timestamp 1786201456 确认)。
- **seed 决定结论**: 诊断 seed=100-107 下 agent 对 defensive 6/8 赢, 门协议 seed 下
  0/8 — 任何防御方验证必须用 `_stable_seed(ep, "defensive")` 复现门协议。
- **BC 学生 argmax 表面收敛**: s37/s38/RCH 权重显著不同 (mean diff 0.21) 但动作序列
  逐动作一致 — BC 收敛到同一 argmax 表面 (近 FW_MAX 全冲); 用真实 env 轨迹
  + 门协议 seed 才能区分模型行为差异。
- **FP-RL-005 (未修复, 待 S39)**: DQN 微调灾难性覆盖仍在 — 本 sprint 用直投绕过
  而非修复。P2 延后至 BC 部署 + defensive 审计完成后。

**运维新条目**: 蒸馏脚本路径修正 (training/ 下需上溯 4 层才到 REPO_ROOT);
`v9_gate_evaluator._RLGateAgent._load` 需加 nano 结构兼容 (二次尝试)。

## Sprint 36 记录 (2026-08-08, S36_RL_INFRA) — RL 轨道基础设施 + 教师桥 + 门回归

**背景**: PM 裁决 S36 P0 = RL 轨道 (PyTorch DQN) — 三轴解耦证据 (reward/momentum/GRIP_DECAY
±0.005 步噪声) 证明规则层勘探饱和, V9 门 10% 需 RL 正样本。T1 训练环境 / T2 规则→RL 教师桥
(BC) / T3 门回归。V9 plateau 自蒸馏延后至 RL 过门后, Z3 I2 / Hermes B2 延后 S37。

**T1 训练环境 (✅)**: lightweight_env (Discrete(21)/7 维观测) + common/DQNAgent + train.py
对接, torch 2.13.0+cpu; 100ep 冒烟无崩溃, eval WR 53.3%→best 100%。

**T2 教师桥 (✅)**: rl/teacher_bc.py — ABDL 12 规则教师 60ep 采集 **345 演示**, BC loss
0.97→0.37, 动作复现率 88.7%。发现规则层动作多样性天花板 (仅用 5/21 动作)。预热后 DQN
100ep WR 93.3%, 500ep WR 93.3% (avgR=219.7±88.3, 13s)。

**T3 门回归 (⚠️ 部分)**: 门胜率 ABDL 10% → **RL 最佳 50% (5/10) = 5 倍提升**, 未达 60% 阈值。
plateau_explorer 按协议自动触发。双端回归 **220 passed + 1 skipped + 0 失败** 全绿。

**新失败模式 (FP-RL 系列, 三轮假设实证)**:
- **FP-RL-001 训练分布缺口**: 阶梯课程 (速度轴) 训练 → defensive/circler 0/2 (行为 OOD,
  训练中从未采样); 100ep/500ep 逐字节相同结果证明瓶颈是分布而非优化量
- **FP-RL-002 单遍阶梯灾难性遗忘 + 预算稀释**: 加门行为后单遍 hardest-first 阶梯 →
  早期技能被后期覆盖, random 2/2→0/2; 修复为轮转课程 (round-robin) 后无遗忘但总胜率仍 40%
- **FP-RL-003 观测表征上限 (主导假设)**: 7 维观测无对手速度/朝向, 单帧 MLP 无法稳定学习
  追击技能 — "等对手来撞"型 (aggressive/counter) 全赢, "需主动追逐"型 (random/defensive/
  circler) 全输; 奖励已有接近塑形 (排除奖励稀疏) → S37 P0 = 观测升级 (opp_vx/vy → 9-10 维)

**运维确认**: RULE-PR-002 第五次应验 (PYTHONPATH 前置赋值 vs export 写法不一致, 统一前置
赋值); PEP 668 (torch 需 --break-system-packages); pytest anyio 插件冲突 → -p no:anyio。

## Sprint 35 记录 (2026-08-08, S35_SYMBOLIC_EXPLORATION) — Z3 第四层防护 + 新领域勘探

**背景**: PM 裁决 S35 T1 = Z3 符号验证集成 (P0, 第四层防护), T2 = 奖励/物理参数域勘探
(P1, 并行), V9 门 plateau_explorer 自蒸馏与 Hermes B2 延后。

**T1 第四层防护 (SYMBOLIC_PROOF_FAIL)**: 新增 symbolic_verify.py — ABDL 条件→SMT-LIB 翻译,
不变量 I1 (∀输入点∈物理定义域, 至少一条规则匹配) + 新增空洞查询 (∃x: 基线有匹配 ∧ 候选无匹配,
数学精确的覆盖包含验证)。集成于 precheck_topology_validity (S32 之后), 3 层经验验证 → 4 层
(经验 + 数学证明)。**核心发现**: S34 合入后的 12 规则基线存在 S32 单维投影盲区的真实联合空洞
(opp_found=False ∧ edge∈(0.6,0.8] — CAUTIOUS-EDGE 删除后留下的真空; D4-3 "邻居完全吸收"
在数学级被证伪为"部分吸收")。探针候选 mh_rules_close_edge_030 (CLOSE-PUSH edge 0.65→0.30
收窄): S32 放行, **Z3 稳定拦截 3/3 轮** — 验收①达成, 验证延迟 0.027s/候选 ≪ 5s 线。

**T2 新领域勘探 (GRIP_DECAY 双向)**: 动量轴 (ROUND 2 0.90/0.875 被支配) 已证伪 → 选未勘探
GRIP_DECAY: grip_020 (0.10→0.20) / grip_000 (0.10→0.0) 双候选均 INCONCLUSIVE (Q≈0.00,
avg_steps 21.4 持平)。与动量轴、奖励轴 (ROUND 10 push_threshold) 汇聚为同一结论: **外层参数轴
对规则引擎解耦** — 规则 avg_steps 由拓扑分支结构决定, 外层扰动在 ±0.005 步噪声内。

**失败模式**: 无新 FP (T1/T2 均为执行类 + 探针验证)。运维确认:
- RULE-PR-002 (WSL 长 Python 命令用脚本文件) 第四次应验 — PowerShell 引号嵌套解析失败 ×1。
- PEP 668: WSL Ubuntu python3.14 系统级 pip 需 --break-system-packages (z3-solver 5.0.0.0)。
- **集成回归教训**: 新防护必须与既有预检 (S32) 保持相同"跳过语义" — 初次集成无 involved-guard,
  mock 场景 (裸文本 `dist < 0.20` 无 sensor()) 被真实 ABDL 锚点检查误拦截 → 加
  "无数值传感器条件变更则跳过" guard (与 S32 一致) 后 215/215 全绿。FP 类同 S32 集成期。

**V9 门**: 胜率仍 10% (1/10)。T2 三轴 (reward/momentum/GRIP_DECAY) 解耦证据支持 PM 预判 —
规则空间收敛 + 外层参数解耦 → V9 门需 RL 轨道 (PyTorch) 提供正样本, 规则勘探已到边际。

## Sprint 34 记录 (2026-08-08, S34_RULE_PRUNE_DISTILL) — 候选 G 合入主规则 + D5 蒸馏入库

**背景**: PM 裁决 S34 P0 = 候选 G 合入主规则 (CAUTIOUS-EDGE 移除, 8→7 规则精简),
P1 = D5 高价值规则蒸馏 (conf≥0.3 入库 engineering_rules.md), P2 = Hermes B2 (延后 S35)。

**P0 候选 G 合入 (simulation_rules.abdl)**: CAUTIOUS-EDGE 块 (SIM-HEUR-CAUTIOUS-EDGE,
L137-144) 物理删除 — 13→12 条规则 id, CAUTIOUS 出现次数 0, git diff 9 行纯删除
(字节级 WSL python3 编辑, 无行尾污染)。基线验证 (outer_loop --iterations 3 --tag
S34_G_MERGE): avg_steps=21.4 / winrate=1.0 / rules 触发 214, 与 S33 完全一致 —
CAUTIOUS-EDGE 的 13 次触发被邻居 (CLOSE-PUSH<0.65 + FLANK<0.80) 无损吸收, D4-3 冗余
判定在物理删除后成立。全部已知候选判定干净复现 (topo_A INC / topo_B REGRESSION /
候选 C TOPO-PRECHECK-FAIL / mapping_001 REGRESSION / mapping_002 INC /
physics_seed_001 REGRESSION / seed_002-003 INC / action_map_001 REGRESSION),
无锚点崩溃无预检混淆。探索饱和 3 轮无有效结果 (规则空间已固定, 预期行为)。

**P1 D5 蒸馏入库 (engineering_rules.md 高置信度规则章节)**: 三强规则
(RULE-HC-001 topo_B 0.48 / RULE-HC-002 mapping_001 0.30 / RULE-HC-003 topo_A 0.26)
写入 governance/dashboard/engineering_rules.md。验证: 12 规则基线下重跑
distill_loop --recalibrate, 三强规则置信度稳定复现 (0.48/0.30/0.26, 零漂移) —
蒸馏入库不产生副作用。副作用路径确认: distill_loop 不消费 engineering_rules.md
(HC 规则为后续候选生成的治理指导, 非管道输入), cell_learner 写 meta_engineering_rules.md
为另一文件 — 治理规则库与管道零耦合。

**失败模式**: 本 Sprint 无新 FP (P0/P1 均为执行类任务)。运维确认: RULE-PR-002
(WSL 长 Python 命令一律脚本文件方式) 第三次应验 — PowerShell 引号嵌套解析失败 ×2
(重跑 recalibrate 管道时)。CRLF 维护: engineering_rules.md 经 WSL python3 字节级
插入 HC 章节, git diff 干净无行尾污染。

## Sprint 33 记录 (2026-08-08, S33_CAND_G_DISTILL) — 候选 G 冗余确认 + D5 校准

**背景**: PM 裁决 S33 P0 = 候选 G CAUTIOUS-EDGE 移除评估 (D4-3 依据, 预检层已稳定)。
P1 = 自蒸馏 D1/D2 迭代 (D5 置信度校准)。

**P0 候选 G (variants.mh_rules_topo_G + ROUND 13)**: 注释化 SIM-HEUR-CAUTIOUS-EDGE
整块 (拓扑级文本变更, S29 禁令合规)。预检: 锚点唯一 + **覆盖预检放行** (移除后 edge
维度无空洞, 0.55-0.78 被 CLOSE-PUSH<0.65+FLANK<0.80 覆盖)。
验证 (outer_loop --round 13, 3 轮一致): **INCONCLUSIVE (Q=0.00), avg_steps 21.4→21.4
(变化 0), 触发 214→214 (13 次 CAUTIOUS-EDGE 被邻居无损吸收)** → D4-3 冗余判定实证
成立, S34 可合入主规则。topo_A SUSPICIOUS 复现, mapping_001 REGRESSION 第四次复现。

**P1 D5 校准 (distill_loop.recalibrate_rules)**: 基于 M2 四通道信号 (|Q|*10+|Δ熵|*20,
失敏×0.6) 对 D1/D2 规则置信度降序重排, 重复 id 取最强信号。输出 349 记录:
D1 排序 topo_B(0.48) > mapping_001(0.30) > topo_A(0.26), no-op 候选地板 0.05。
**校准有效性**: 熵响应与置信度单调对应 (0.024→0.48 > 0.015→0.30 > 0.013→0.26)。

**验证**: 134/134 全绿。治理产出: CAUTIOUS-EDGE 冗余闭环 (D4-3 预测→候选 G 实测→
S34 合入), D5 校准机制入库 (后续筛选 conf≥0.3 高价值规则)。

## Sprint 32 记录 (2026-08-08, S32_COVERAGE_DISTILL) — FP-NEG-005 修复: 覆盖连续性预检

**背景**: PM 裁决 S32 P0 = M2.2 覆盖连续性预检升级 (FP-NEG-005: topo_D 收窄制造
(-15,-10)∪(10,15) 覆盖空洞, M2.2 priority 预检无法捕获)。P1 = 基于 S31 三大治理发现的
自蒸馏迭代 (V9 门触发后首轮)。

**P0 实现 (evaluator_diff_test.coverage_continuity_check)**:
- 维度投影覆盖分析: 解析规则文本中 angle/dist/edge 三个数值维度的全部触发闭区间
  (`<`/`<=`/`>`/`>=`/`BETWEEN`) -> 合并覆盖并集 -> 检测无规则覆盖的连续空洞
- 模拟应用 entries diff 后对比基线: **仅拦截新增空洞** (变更前有覆盖、变更后无覆盖)
- 串联进 precheck_topology_validity 第 0 步 (priority 检查之前)
- 判别验证 (S31 真实候选): topo_D 拦截 COVERAGE_GAP / topo_E (0.55-0.60 被
  CLOSE-PUSH <0.65 覆盖) 放行 / topo_F (stuck 不在投影维度) 放行 / topo_A (扩宽) 放行
- 管线级验证: outer_loop --round 12 中 topo_D 3 轮全部 TOPO-PRECHECK-FAIL (0 次评估)

**P1 实现 (distill_loop.distill_d4)**: S31 三大治理发现编码为结构化规则 —
D4-1 覆盖预检 (条件域收窄须验证邻居覆盖) / D4-2 慢局归因修正 (FLANK 高频重复非 stuck
死锁, 干预点=触发次数上限) / D4-3 冗余分支识别 (触发域⊆邻居且移除步数变化≤1 → 候选 G)。

**验证**: 134/134 全绿 (原 128 + 6 新测试, 集成测试 mock_1 收窄改扩宽适配)。
提交 07edbe2。FP-NEG-005 已闭环 (预检可拦截同构损坏)。

## Sprint 31 记录 (2026-08-08, S31_TOPO2_BRANCH_HIST) — 拓扑第二波: 覆盖真空新失败机制 + 假设证伪

**背景**: PM 裁决 S31 P0 = 基于 FP-NEG-004 的 branch_hist 修正归因执行规则拓扑第二波。
M2 四通道就绪 (S30), 三个正交候选 D/E/F 针对 FLANK 67.3% 高占比的三种假设:
触发域收窄 (D) / 交替死循环打断 (E) / stuck 退出机制 (F)。ROUND 12 专用分支。

**验证 (outer_loop --iterations 5 --round 12 --tag S31_TOPO2, 3 轮探索饱和提前终止, 确定性一致)**:
| 候选 | 判定 | Q | avg_steps | 关键机制 |
| :--- | :--- | :--- | :--- | :--- |
| mh_rules_topo_D (FLANK ±10→±15) | **REGRESSION** | **-0.53** | 21.4→34.1 | **覆盖真空** (-15,-10)∪(10,15) 无规则覆盖, 裸 abdl 分支 92 次 |
| mh_rules_topo_E (CAUTIOUS-EDGE 0.55→0.60) | INCONCLUSIVE (no-op) | — | identical | 0.55~0.60 区间未被采样 → 交替死循环假设证伪 |
| mh_rules_topo_F (FLANK + stuck<3) | INCONCLUSIVE (no-op) | — | identical | stuck_counter 恒<3 → 非 stuck 死锁, 归因修正 |
| mh_rules_topo_A (回放) | SUSPICIOUS (Q=0.02) | +0.02 | 60→59 | CAUTIOUS-EDGE 13→0 消失 → 近似冗余分支 |
| mh_mapping_001 (回放) | REGRESSION | -0.17 | 21.4→29.3 | 第三次复现 (S27v3/S29/S31) |

**FP-NEG-005 (新): M2.2 预检盲区 — 覆盖连续性**。topo_D 通过 M2.2 priority 预检 (无
priority 变更) 却制造条件域收窄后的覆盖空洞 (-15,-10)∪(10,15), ABDL 落入无命名默认
分支导致 +59% 步数恶化。**M2.2 只检测 priority 重排的胜者集合变化, 不检测条件域收窄
的覆盖断裂** → 升级方向: 解析邻居规则触发域, 检测收窄后空洞区间 (S32 候选 G 前预检升级)。

**FP-NEG-006 (归因修正闭环)**: ep7 交替死循环 (FLANK-RIGHT 45 + CAUTIOUS-EDGE 13) 的
真实机制 = FLANK 在 edge∈[0.60,0.80) 且角度未收敛时的**正常高频重复** (stuck 恒<3,
0.55~0.60 区间空采样)。干预点修正: FLANK 触发次数上限, 而非 stuck 传感器。

**验收**: ① 3 候选 branch_hist 预期 ✅ ② 判定分布显著变化 (D -0.53 新机制 / A 回放
INCONCLUSIVE→SUSPICIOUS M2 捕获 / E-F 双 no-op 证伪) ✅ ③ 128/128 全绿 ✅。
V9 门: 0 PASSED / 3 轮 → 触发条件满足 (plateau_explorer 自蒸馏正式排期)。

## Sprint 30 记录 (2026-08-08, S30_M2_UPGRADE) — M2 四维融合: FP-NEG-004 编码为硬信号

**背景**: PM 裁决 S30 P0 = M2 评估器信号融合升级。FP-NEG-004 教训 (branch_hist 逐局验证)
从"分析原则"升级为"评估器硬信号"; S29 候选 C no-op 从"后验发现"升级为"预检拦截"。

**M2.1 四通道设计 (evaluator_diff_test.py)**:
```
Q = 0.35*steps_eff + 0.35*layer_signal + 0.30*branch_signal
branch_signal = branch_hist 熵变化 (每 episode 归一化分布熵)
  熵坍缩 -> 负向 (死循环风险, S29 候选 A 的 FLANK-RIGHT:45 坍缩)
  熵升 -> 仅当效率同步提升时正向 (方向约束)
  无分支语义层 (physics/reward/gate) -> 权重回退三通道 (Sprint 24 行为保持)
```
**方向约束实证 (S30 M2.3 候选 B)**: dist>=0.3 触发域扩大 -> branch_hist 熵升 +0.024
但 avg_steps 21.4->24.8 恶化 — 熵升是抖动而非分支利用改善。若熵升计正,
Q=-0.16 会被抵消为 -0.075 (滑出 REGRESSION 阈值)。修复: 熵升 + 效率未升 -> 计中性
+ 权重回退 (M2_W_BRANCH 按 1:1 回退给 steps/layer), 恢复 Q=-0.16 REGRESSION。

**M2.2 拓扑预检设计**: priority 重排未跨越任何邻居规则 -> resolve_top() 胜者集合
不变 -> 结构性 no-op 拦截, 不进入评估循环。数学基础: ABDL 引擎按 priority 降序
排序后取最高; priority 变更只有在区间 (min,max) 内存在其他规则 priority 时才
改变胜者集合。

**判定分布变化 (S29 -> S30, 3 轮确定性一致)**:
| 候选 | S29 旧判定 | S30 新判定 | 机制 |
| :--- | :--- | :--- | :--- |
| mh_rules_topo_A | INCONCLUSIVE (Q=0.00) | SUSPICIOUS (Q=0.02) | 熵通道捕获 CLOSE-PUSH 2->12 次触发 |
| mh_rules_topo_B | REGRESSION (Q=-0.16) | REGRESSION (Q=-0.16) | 方向约束 + 权重回退 |
| mh_rules_topo_C | INCONCLUSIVE (10 episodes) | TOPO-PRECHECK-FAIL (0 次) | 预检拦截 |
| mh_mapping_001 | REGRESSION (Q=-0.17) | REGRESSION (Q=-0.17) | 熵降 -0.034 负向一致 |

**验收**: mapping 层饱和失敏可正确解读 (候选 A 不再淹没在近零信号);
候选 C 预检拦截节省评估预算; 128/128 全绿 (9 新增测试)。

## Sprint 29 记录 (2026-08-08, S29_RULE_TOPOLOGY_DISTILL) — 规则拓扑首探: 0 PASSED, FP-NEG-004 入库

**背景**: PM 裁决 S29 三方向并行——①规则拓扑探索（P0，解 RULES CLOSED 禁令，拓扑级文本变更替代参数级 bump，
规避 FP-MC-020 根因）②M2 融合升级（⏸ 延后）③plateau_explorer 自蒸馏（并行，distill_loop.py 已运行）。
ROUND 11 专用分支：拓扑候选优先 + mh_mapping_001 交叉验证。

**三个拓扑候选（文本级变更，无参数级 bump）**：
| 候选 | 变更 | 拓扑意图 | 可达性 |
| :--- | :--- | :--- | :--- |
| mh_rules_topo_A | CLOSE-PUSH edge 0.65→0.80 | 填充 L2 空洞（60 步贴边局） | ✅ FP-NEG-002 无死路径 |
| mh_rules_topo_B | OPPONENT-FOUND dist>0.6→>=0.3 | 触发域重组（近距离接管） | ✅ |
| mh_rules_topo_C | SPEED-ADAPT priority 300→350 | 优先级重排（时间压力优先） | ✅ |

**验证结果（outer_loop --iterations 5 --round 11，3 轮探索饱和提前终止，确定性可复现）**：
| 候选 | 判定 | Q | avg_steps | 逐局 steps | 机制 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| mh_rules_topo_A | INCONCLUSIVE | 0.00 | 21.4→21.3 | [6,8,7,19,42,49,12,**59**,5,6] | 60→59 仅 -1：**假设证伪** |
| mh_rules_topo_B | REGRESSION | -0.16 | 21.4→24.8 | [6,8,7,19,**52,73**,12,60,5,6] | 触发 214→248（+34） |
| mh_rules_topo_C | INCONCLUSIVE | — | 21.4→21.4 | identical（逐位相同） | **no-op（FP-MC-014 类）** |
| mh_mapping_001 | REGRESSION | -0.17 | 21.4→29.3 | [6,12,10,29,41,47,**74**,57,11,6] | 动作熵 0.831→0.865 |

**FP-NEG-004（规则拓扑负样本，三条因果）**：
1. **候选 A 假设证伪（最重要）**：基线第 8 局 60 步（circler）的真实 branch_hist =
   **FLANK-RIGHT:45 + CAUTIOUS-EDGE:13 + CLOSE-PUSH:2**——主导分支是侧翼死循环而非"edge∈[0.65,0.80)
   空洞无 L2 接管"。edge 0.65→0.80 只让 60→59 步（+1 次 CLOSE-PUSH 触发），空洞假设的失败模式归因错误。
   **教训：拓扑候选的动机必须用 branch_hist 逐局验证，不能凭 avg_steps 推断失败模式**（S29 前假设
   "60 步=空洞"未查分支分布）。
2. **候选 B 优先级抢占（REGRESSION 机制）**：OPPONENT-FOUND（p700）触发域扩至 dist>=0.3 后，
   在 dist∈[0.3,0.6) 区间抢占 CLOSE-PUSH（p500）/FLANK（p480/470）的领地——p700>p500 优先级
   遮蔽重现（F-100 同构），近距离用 `_pursue_opponent`（≤0.38m/s）对抗 CLOSE-PUSH 直推（FW_MAX）→
   defensive 对局 42→52、49→73 步拖长。**教训：触发域扩展必须检查与相邻高优先级规则的领地重叠**
   （优先级抢占是 F-100 修复后首次被拓扑级变更重新触发）。
3. **候选 C no-op（priority 重排需跨越邻居）**：SPEED-ADAPT 300→350 在优先级全序中仍是
   （700/600/590/500/480/470/350/250/200/150）的第 7 位——**没有跨越任何邻居规则**（350 仍 > 250
   且 < 470），resolve_top() 的决策点完全不变 → identical:true。**教训：priority 重排必须跨过至少
   一个其他规则的优先级才构成拓扑变更；同区间内数值微调是 no-op**（与 FP-MC-014 no-op 判定同根，
   但这里是结构性的——ABDL 引擎按 priority 降序 resolve_top()，同序位变更不改变选择）。

**mh_mapping_001 交叉验证（REGRESSION 复现）**：flank 0.20→0.15 大幅收窄 → 步数 +37%
（21.4→29.3，S27 v3 同构）——mapping 层距离轴 0.20 单峰最优第三次确认（S26D 0.18 INCONCLUSIVE /
S27v2 0.25 REGRESSION / S27v3 0.15 REGRESSION / S29 0.15 REGRESSION）。

**Sprint 29 结论**：
- **0 PASSED** → V9 门触发条件（3 轮无 PASSED）满足；P2-V4 探索饱和门按设计提前终止（3/5 轮）
- 规则拓扑探索获得**负空间图谱**：空洞假设证伪（A）+ 优先级抢占负样本（B）+ 邻居跨越规则（C）
- 自蒸馏产物：`experience/distill_rules_20260808_170729.json`（66 D1 / 124 D2 / 253 blocked，
  action_map 3 REGRESSION、mapping 48 INCONCLUSIVE/9 REGRESSION/45 SUSPICIOUS、physics 66/42/21、
  rules 10/9/0）
- 待 PM 裁决：M2 融合升级（S29 后延后项）现在具备前置证据——mapping 48 INCONCLUSIVE + 45 SUSPICIOUS
  的饱和失敏是 M2 重构的核心依据

## Sprint 28 记录 (2026-08-08, S28_SPEED) — 轮速增益 REGRESSION 负样本 + action_map 层建立

- **A1（PM 裁决 P0：TURN_*_MED 轮速增益 0.6→0.8）**：
  | 轮次 | winrate | avg_steps | 判定 |
  | :--- | :--- | :--- | :--- |
  | ROUND 1 | 1.00→0.90 | 21.4→17.7 | REGRESSION |
  | ROUND 2 | 1.00→0.90 | 21.4→17.7 | REGRESSION |
  | ROUND 3 | 1.00→0.90 | 21.4→17.7 | REGRESSION |
  3 轮完全可复现 → **PM 验收条件"3 轮仍无 PASSED"满足 → 触发 V9 门**。
- **FP-NEG-003（轮速增益负样本，重要）**：TURN_*_MED 0.6→0.8 轮速幅值 +33%。
  - avg_steps 21.4→17.7（-17.3%）说明**有真实行为影响**（非 no-op，非死代码扰动），
    但 winrate 1.00→0.90（-10%）——中速转向加速导致**弧线过冲**：flank 分离态
    （abdl_action_bridge.py:217/225 返回 TURN_*_MED）转向到位更快但越过最佳推力角，
    贴边对局（F-106 侧接触锁定）在 17.7 步提前结束，部分本可推进制胜的对局转为坠落。
  - 与 FP-NEG-001（动量 1.20）**同构**：都是"执行层参数放大 → 行为加速但物理包线失稳"。
    动量轴可行域上界 ≈1.10；轮速轴可行域上界 ≈0.70（0.6 基线 → 0.8 越界）。
  - 复用价值：**轮速类扰动建议 clamp ≤ 0.70**；M3 bump 放大轮速类参数时须检查转向物理包线。
- **架构扩展（action_map 层）**：wheel_to_discrete.py 原不在 HARNESS_FILES 五层内，
  S28 新增第六层 `"action_map": "simulation/wheel_to_discrete.py"`（variants.py + outer_loop.py
  双端同步）。机制验证：snapshot/restore/apply 白名单按 HARNESS_FILES 展开自动覆盖新层；
  ROUND 1 候选循环加入 action_map；D2_PRIOR 与 SEED_PERTURBATION_THRESHOLDS 同步新增条目；
  meta_harness 119/119 全绿。**教训：凡 PM 指令指向的文件，先确认是否在 HARNESS_FILES 内，
  不在则需先建层再扰动**（否则 apply_precheck 白名单拒绝 = 作用域越界）。
- **因果推理（与 S27 三轴图谱联动）**：轮速增益是"行为放大器"——它放大的是**现有策略的执行速度**，
  不改变策略拓扑。当前制胜策略（flank 0.20 弧线 + CLOSE-PUSH 直推）已处于物理包线边缘，
  任何执行层加速（动量/轮速）都先触碰包线失稳而非提升胜率。这与 S27"mapping 层无正扰动空间"
  结论一致：**当前 harness 拓扑下，行为参数正扰动空间已耗尽（角度饱和/距离单峰/动量上界/轮速上界），
  唯一剩余方向是规则拓扑变更（RULES CLOSED 禁令内不可行）或评估器信号融合升级**。

## Sprint 27 记录 (2026-08-08, S27_REWARD_AXIS) — 换锚点三轴图谱 + FP-NEG-002 死代码扰动识别

- **A1 换锚点首探（PM 裁决）**：mapping 锚点从角度阈值轴 → 追敌直冲窗 `dist<0.22`（距离阈值类）。
  结果：**INCONCLUSIVE — identical:true（baseline 与 candidate 逐位相同）**。
- **FP-NEG-002（死代码扰动，重要因果发现）**：`_pursue_opponent` 直冲窗 `abs_angle<15 and dist<0.22`
  是 **rules 层前提造成的死代码**——ABDL 规则 `SIM-TACTIC-OPPONENT-FOUND`（priority 700）要求
  `sensor(opponent_dist) > 0.6` 才触发 `PolicyPursueOpponent`，而直冲窗要求 dist<0.22——**两条距离
  条件互斥，直冲窗分支永远不会执行**。
  教训：**S24 RULES CLOSED 后，mapping 层扰动必须做"规则前提可达性"检查**——候选锚点所在分支的
  触发前提（rules 层条件）与锚点自身的数值条件不能互斥，否则是死代码扰动（零行为影响）。
- **flank 距离轴双侧实证（0.20 是单峰最优）**：
  | 扰动 | 方向 | Q | avg_steps | 判定 |
  | :--- | :--- | :--- | :--- | :--- |
  | S26 D: 0.20→0.18 | 微收窄 | 0.00 | 21.4→21.4 | INCONCLUSIVE |
  | S27 v2: 0.20→0.25 | 放宽 | -0.17 | 21.4→18.3 | REGRESSION |
  | S27 v3: 0.20→0.15 | 大幅收窄 | -0.17 | 21.4→29.3 | REGRESSION |
  **因果**：放宽→分离态过早放弃弧线（FW_*_HARD）→推进力不足→winrate 降；
  收窄→更多弧线锁定侧接触→效率降（步数 +37%，弧线 0.29m 轨道 vs 0.15m 接触半径失配）。
  **0.20 是当前工作树制胜策略的局部最优**——mapping 层距离轴无正扰动空间。
- **规则拓扑（活路径 vs 死路径）**：
  | ABDL 规则 | 前提 | bridge 方法 | 可达性 |
  | :--- | :--- | :--- | :--- |
  | SIM-TACTIC-OPPONENT-FOUND (700) | dist>0.6 | `_pursue_opponent`（含直冲窗 dist<0.22） | **死**（前提与内部条件互斥） |
  | SIM-ADVANCED-CLOSE-PUSH (500) | dist<0.6, \|angle\|<10 | `PolicyRushPush` → FW_MAX | 活（无内部参数） |
  | SIM-ADVANCED-FLANK-RIGHT (480) | dist<0.6, angle<-10 | `_flank`（abs(angle)>40 + dist<0.20） | 活（双侧 REGRESSION 界定 0.20 最优） |
  | SIM-ADVANCED-FLANK-LEFT (470) | dist<0.6, angle>10 | `_flank` | 活（同上） |
- **PM 推荐锚点否决（因果核查）**：`V9_WINRATE_THRESHOLD`（evaluator_v9.py:32，评估器及格线非行为
  参数，不在 HARNESS_FILES 四层中）；`PUSH_REWARD_SCALE`（代码库零命中，虚构参数）；
  `reward_functions.py` 默认值（env 构造显式传参 `V10Reward(edge_penalty_weight=71.6, push_threshold=0.28)`
  遮蔽默认值 + 规则引擎非奖励驱动 → no-op，ROUND 10 证伪预判一致）。
- **Sprint 27 第三轴候选**：TURN_*_MED 轮速增益（ACTION_MAP: TURN_R_MED (0.0,-0.6)→(0.0,-0.8),
  wheel_to_discrete.py:84）——mapping flank 分离态收敛（217/225 行 TURN_*_MED）+ physics
  heuristic 搜索旋转（162 行）的跨层联动锚点，是 PM"转向增益"指令的真实形态。

## Sprint 26 记录 (2026-08-08, S26_PASS) — A1 扰动阶梯实证 + physics_001 负样本入库

- **A1（PM 裁决 P0 → 兜底）**：mapping 角度阈值扰动阶梯验证——S25 起 Q 随幅度单调微增但线性饱和：
  | 档位 | 应用值 | Q | 判定 |
  |------|--------|-----|------|
  | S25: -5° | 40→35 | 0.02 | SUSPICIOUS |
  | S26 P0: -8° | 40→32 | 0.03 | SUSPICIOUS |
  | S26 兜底: -10° | 40→30 | 0.04 | SUSPICIOUS |
  敏感性 = **0.005 Q/度**。外推 Q=0.15 需 ~30° 总扰动（40→10），必翻转 REGRESSION。
  **根因：非幅度不足，而是角度阈值锚点行为影响力饱和**（10 局中 `abs(angle) > 30` 触发面窄，熵 Δ 仅 +0.015）。
  A 验收未达（mapping 层无 PASSED）；P2-V4 探索饱和门按设计触发（3 轮无有效结果停止）。
  教训：**扰动阶梯应先测斜率再定档**——斜率平缓（<0.01 Q/°）时加码是低效搜索，应换锚点（如 reward 权重/转向增益）而非继续加大。
- **路径澄清（因果推理）**：`_gen` 候选（mh_mapping_001）**不走 M3 bump**（bump 仅在 `_seed_variants` 内部）；
  S25 外环实际应用 40→35（非 40→32）。PM 的 -8° 指令对 `_gen` 路径是真实变化；对 seed 路径（有 bump，阈值 8.0）
  为 no-op（mag=8 不触发）。外环 mapping 候选来自 `_gen`，physics 候选来自 `_seed_variants`——两条生成路径必须分别校准。
- **FP-NEG-001（PM 任务 C：physics_001 动量 1.20 负样本）**：
  - 扰动：`momentum = net * TIMESTEP * 1.00` → `1.20`（动态锚点 +0.05×4 bump 放大）
  - 结果：**winrate 1.00→0.90（-10%），avg_steps 21.4→17.2（-19.6%），3 轮可复现**
  - 判定：REGRESSION（Q≤-0.15 档）
  - 失败模式：**动量过冲**——1.20 倍动量使机器人转向角速度超出物理稳定包线，弧线中段失位，
    提前接触但推力向量切向分量增大 → 有效推挤距离缩短 → 提前坠落/步数骤降。
  - 复用价值：动量轴可行域上界 ≈ 1.10（1.0→1.05 为 SUSPICIOUS 安全区，1.20 越界）；
    后续动量类扰动应 clamp ≤ 1.10 或在 bump 放大时检查物理包线。
- **双端回归全绿**：mh_physics_seed_002/003（GRIP_DECAY 0.30、二次抓地延续）与 mapping_002
  均为 INCONCLUSIVE（Q≈0，无行为影响）——S25 主分支未受 S26 扰动回归影响。

## Sprint 25 记录 (2026-08-08, S25_SEED_FIX) — FP-MC-017 复发根治 + 种子层信号枯竭修复

- **FP-MC-017 复发（第 3 次）**：3 个种子静态锚点随工作树演进全部失效——
  physics seed_1（`TIMESTEP * 0.8` → 实际 `momentum = net * TIMESTEP * 1.0`）、
  physics seed_2（线性抓地 → 二次形式）、mapping seed_1（`abs(angle) > 45` → `> 40`）。
  根因：S19 动态适配只覆盖了 code_agent_proposer 的生成路径，`_SEED_PARAMS` 静态锚串未随工作树演进。
- **根治**：`anchor="regex"` 动态锚点——正则解析工作树当前值，new 由 cur 计算（mapping -5°、动量 +0.05、
  GRIP_DECAY +0.05），diff 永不脱节。种子数：physics 1→3/轮（A1 验收 ≥3 达成）。
- **信号恢复**：REGRESSION 首现（physics_001 动量 1.0→1.20，winrate 1.00→0.90，3 轮复现）；
  SUSPICIOUS（mapping_001 Q=0.02，steps_eff=+0.037）；INCONCLUSIVE（3 项无行为影响）——
  判定三态共存，种子层信号枯竭解除（A2/A3 验收达成）。
- 教训：**静态锚串是债务**——凡锚定工作树的种子/模板必须动态解析（regex 锚点或 apply_precheck 预检双保险）。

## Sprint 23 记录 (2026-08-08) — FP-MC-020 根因修正 (D2 重校准)

- FP-MC-020 归因修正：非"扰动过激/阈值未回标"，实为**参数语义混用**——bump_magnitude 将层默认 abs 阈值
  （8°/10°）误用于 0-1 归一化参数 edge_proximity（0.80-8=-7.20 恒 True）→ 无条件转向 → edge-loops。
- 修复：_SEED_PARAMS 参数级 perturb 配置 + 符号安全网（跨符号拒绝）+ bump 内部验证 cfg 传参 bug。
- S23_RECAL2：REGRESSION 严重度 0.50→0.90（edge_proximity 0.80→0.64 域内），meta_harness 101/101。

> 项目切换: 本文件从 AST Guard 转向 BottleSumo lightweight_env 门评测。
> 起点: V9 门 6/10 (aggressive 0/2), 前 4 次 ABDL 规则编辑全部无效 (0/2 不变)。

### Meta-Harness 轮次记录 (20260806_120419) — mh_physics_seed_002
- 假说: 抓地衰减线性→二次 (F-103/F-104)
- 证据链: F-103, F-104 | 血缘: SEED_TEMPLATE (磁盘文件缺失降级)
- 结果: score=1.0 passed=True (wall 1.4s, steps 259)

### Meta-Harness 轮次记录 (20260806_121329) — mh_physics_008
- 假说: grip decay 二次→三次 (seed_002 新轴延续): 边缘区抓地损失更快, 内圈高抓地权重进一步上升; 若增益 <1 步则 grip 轴趋饱和, 宣告新轴闭合, 转向角度/奖励函数轴
- 证据链: F-103, F-104 | 血缘: 2e33751 (seed_002 轴延续: grip 二次→三次)
- 结果: score=1.0 passed=True (wall 1.5s, steps 259)

### Meta-Harness 轮次记录 (20260806_121329) — mh_rules_007
- 假说: FLANK 15°→10° 纯角度下探 (对照 A): 12° 持平后探平台期外, 接近 CLOSE-PUSH ±10° 窗; 测试角度杠杆在窗口外是否重新获得收益; 零新魔数 (F-106)
- 证据链: F-106 | 血缘: 2e33751 -> mh_rules_007
- 结果: score=1.0 passed=True (wall 1.5s, steps 258)

### Meta-Harness 轮次记录 (20260806_121329) — mh_combined_005
- 假说: 组合变体: grip 三次 + FLANK 10° — 在新点 (cubic, 10°) 完成因子设计; 若加性成立: 259 + Δ(cubic) + Δ(10°); 目标 < 259 步
- 证据链: F-103, F-104, F-106 | 血缘: 2e33751 (grip 三次 + FLANK 10°)
- 结果: score=1.0 passed=True (wall 1.4s, steps 258)

### Meta-Harness 轮次记录 (20260806_122501) — mh_rules_001
- 假说: 近战接战窗 ±15°→±10°: 对手侧滑角度大时推迟全力推挤, 避免推力打在切向分量 (F-100 遮蔽修复后的剩余浪费)
- 证据链: F-100 | 血缘: 970c209 -> mh_rules_001
- 结果: score=1.0 passed=True (wall 1.4s, steps 214)

### Meta-Harness 轮次记录 (20260806_123511) — mh_rules_008
- 假说: FLANK 10°→8° 纯角度下探 (PM 裁决 2A): 死区扩展到 (8°,10°)∩edge∈[0.65,0.80); CLOSE-PUSH 窗 = ±15° (磁盘实读) 非 PM 前提 ±10° — 重叠带 (8°,15°) 由 p500 单一赢家接管 → 无行为颠簸; 若 8° 增益收窄则角度轴趋饱和 (OBS-007 斜率 -0.17), 若 >260 立即回滚锁定 10° 为最佳切角
- 证据链: F-106 | 血缘: 9107662 -> mh_rules_008 (角度轴延续)
- 结果: score=1.0 passed=True (wall 1.4s, steps 214)

### Meta-Harness 轮次记录 (20260806_123940) — mh_reward_001
- 假说: 奖励轴证伪测试 (PM 裁决 2C): push_threshold 0.2→0.285 (文件头自述 BayesOpt 最优值)。预判: 规则引擎非奖励驱动 + env 显式传参遮蔽默认值 → 214 持平 (奖励幅值对步数指标解耦)。持平 → 关闭规则引擎奖励轴, 记录奖励轴仅对 RL 轨道有效; 非持平 → 奖励回馈终止逻辑的隐藏路径
- 证据链: F-104 | 血缘: 69abd93 -> mh_reward_001 (奖励轴首探, 证伪测试)
- 结果: score=1.0 passed=True (wall 1.9s, steps 214)

### Meta-Harness 轮次记录 (20260807_005518) — ca_rules_01
- 假说: 增加 grip decay 以提高在接近边缘时的响应速度和安全性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史缺陷库中提到探针越界误判坠台，增加 grip decay 可能会减少这种误判
- 结果: score=1.0 passed=True (wall 2.1s, steps 214)

### Meta-Harness 轮次记录 (20260807_105203) — ca_rules_01
- 假说: 降低 grip decay 值以减少对边缘的依赖, 提高灵活性和适应性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史候选中提到探针越界误判坠台的问题, 调整 grip decay 可能有助于改善这一问题
- 结果: score=1.0 passed=True (wall 3.8s, steps 214)

### Meta-Harness 轮次记录 (20260807_105355) — ca_rules_01
- 假说: 增加 grip decay 以提高在边缘附近的稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 缺陷，探针越界误判坠台。增加 grip decay 可能减少此类误判，提高整体稳定性。
- 结果: score=1.0 passed=True (wall 2.5s, steps 214)

### Meta-Harness 轮次记录 (20260807_110000) — ca_rules_01
- 假说: 降低 grip decay 值以减少滑动风险, 提高相扑稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 缺陷库项, 探针越界误判坠台。降低 grip decay 可能会减少滑动风险，提高机器人在边缘附近的稳
- 结果: score=1.0 passed=True (wall 6.8s, steps 214)

### Meta-Harness 轮次记录 (20260807_113821) — ca_rules_01
- 假说: 增加 grip decay 值以提高在接近边缘时的反应速度和稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史缺陷库中提到探针越界误判坠台，调整 grip decay 可能减少此类错误，并提升整体策略执行效率
- 结果: score=1.0 passed=True (wall 6.4s, steps 214)

### Meta-Harness 轮次记录 (20260807_120927) — ca_physics_001
- 假说: 降低 grip decay 以减少在边缘附近的锁定
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据历史经验 F-104，探针越界误判坠台。降低 grip decay 可能有助于解决此问题。
- 结果: score=1.0 passed=True (wall 5.6s, steps 214)

### Meta-Harness 轮次记录 (20260807_121548) — ca_physics_001
- 假说: 增加 grip decay 以提高在边缘附近的稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史经验表明，增加 grip decay 可以改善在边缘附近的稳定性。
- 结果: score=1.0 passed=True (wall 2.7s, steps 214)

### Meta-Harness 轮次记录 (20260807_122213) — ca_physics_001
- 假说: 降低 grip decay 以减少在边缘附近的锁定风险
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史经验 F-104 显示探针越界误判坠台，降低 grip decay 可能减少这种误判
- 结果: score=1.0 passed=True (wall 2.7s, steps 214)

### Meta-Harness 轮次记录 (20260807_123811) — ca_rules_01
- 假说: 增加 grip decay 以提高在边缘附近的稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史经验表明增加 grip decay 可提升机器人在边缘的稳定性，减少探针越界误判坠台的问题。
- 结果: score=1.0 passed=True (wall 6.5s, steps 214)

### Meta-Harness 轮次记录 (20260807_124621) — ca_rules_01
- 假说: 降低 grip decay 以减少在边缘附近的稳定性, 避免过早减速
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史经验表明增加 grip decay 导致越界误判坠台，降低该值可以优化边缘行为
- 结果: score=1.0 passed=True (wall 2.7s, steps 214)

### Meta-Harness 轮次记录 (20260807_125247) — ca_physics_001
- 假说: 增加 grip decay 以提高在边缘附近的稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史经验表明，增加 grip decay 可以提高在边缘附近的稳定性，减少探针越界误判坠台的问题。
- 结果: score=1.0 passed=True (wall 4.5s, steps 214)

### Meta-Harness 轮次记录 (20260807_125911) — ca_rules_01
- 假说: 降低 grip decay 以减少在边缘附近的锁定
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史记录 F-104 表明探针越界误判坠台，降低 grip decay 可能减少此类情况。
- 结果: score=1.0 passed=True (wall 2.9s, steps 214)

### Meta-Harness 轮次记录 (20260807_130543) — ca_rules_01
- 假说: 增加 grip decay 以提高在边缘附近的稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据历史经验 F-104，探针越界误判坠台的问题可以通过增加 grip decay 来解决。
- 结果: score=1.0 passed=True (wall 2.8s, steps 214)

### Meta-Harness 轮次记录 (20260807_133544) — ca_rules_01
- 假说: 降低 grip decay 以减少在边缘附近的锁定
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的历史缺陷记录，探针越界误判坠台问题可能与 grip decay 设置过高有关。调整为较低值有助于提高
- 结果: score=1.0 passed=True (wall 4.8s, steps 214)

### Meta-Harness 轮次记录 (20260807_135510) — ca_rules_01
- 假说: 增加 grip decay 以提高在边缘附近的稳定性和控制精度
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 缺陷库项，探针越界误判坠台。增加 grip decay 可能减少此类误判，提高整体稳定性
- 结果: score=1.0 passed=True (wall 4.7s, steps 214)

### Meta-Harness 轮次记录 (20260807_140338) — ca_rules_01
- 假说: 降低 grip decay 以减少对边沿的依赖, 提高灵活性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 通过降低 grip decay 的默认值, 可使机器人在接近边缘时更快地调整策略, 减少误判坠台的情况。
- 结果: score=1.0 passed=True (wall 3.7s, steps 214)

### Meta-Harness 轮次记录 (20260807_141156) — ca_rules_01
- 假说: 增加Grip Decay值以提高对边缘的敏感度和反应速度
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据历史缺陷库中的F-104，探针越界误判坠台。通过增加Grip Decay值可以更早地检测到边缘并采取措施，减少误判
- 结果: score=1.0 passed=True (wall 4.5s, steps 214)

### Meta-Harness 轮次记录 (20260807_142023) — ca_rules_01
- 假说: 降低 grip decay 以适应更滑的边缘环境
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史轨迹显示探针越界误判坠台，调整 grip decay 可能减少此类错误
- 结果: score=1.0 passed=True (wall 2.8s, steps 214)

### Meta-Harness 轮次记录 (20260807_143716) — ca_rules_01
- 假说: 增加 grip decay 值以提高在边缘时的抓握稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，适当增加 grip decay 可能减少此类错误
- 结果: score=1.0 passed=True (wall 6.0s, steps 214)

### Meta-Harness 轮次记录 (20260807_150454) — ca_rules_01
- 假说: 增加 grip decay 以减少在边缘附近时的抓取力, 提高安全性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史缺陷库 F-104 指出探针越界误判坠台问题, 增加 grip decay 可以减少边缘附近的风险。
- 结果: score=1.0 passed=True (wall 6.2s, steps 214)

### Meta-Harness 轮次记录 (20260807_151804) — ca_rules_01
- 假说: 降低 grip decay 以减少早接触时的滑动风险，提高稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史缺陷库中提到探针越界误判坠台的问题，通过降低 grip decay 可能可以更好地控制接近边缘的行为
- 结果: score=1.0 passed=True (wall 7.1s, steps 214)

### Meta-Harness 轮次记录 (20260807_152832) — ca_rules_01
- 假说: 增加 grip decay 值以提高在边缘时的抓取稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 缺陷库，探针越界误判坠台。增加 grip decay 可能减少因越界导致的坠台概率
- 结果: score=1.0 passed=True (wall 7.2s, steps 214)

### Meta-Harness 轮次记录 (20260807_153503) — ca_rules_01
- 假说: 降低Grip Decay值以减少在边缘附近的滑动
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据缺陷库中的F-104，探针越界误判坠台。降低Grip Decay值可以更好地控制机器人在边缘的稳定性
- 结果: score=1.0 passed=True (wall 3.9s, steps 214)

### Meta-Harness 轮次记录 (20260807_154204) — ca_rules_01
- 假说: 增加 grip decay 以减少对边缘的粘附, 提高灵活性和机动性
- 证据链: F-104: 探针越界误判坠台 | 血缘: code_agent(qwen2.5:7b) 通过降低 grip decay 的初始值, 可能会减少机器人在接近边缘时因粘附而导致的坠台问题
- 结果: score=1.0 passed=True (wall 2.1s, steps 214)

### Meta-Harness 轮次记录 (20260807_154912) — ca_rules_01
- 假说: 降低 grip decay 以减少在边缘附近不必要的减速, 提高机动性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史候选 v9_baseline_418 使用了较低的 grip decay 值, 并且 F-104 指出探针越界误判坠
- 结果: score=1.0 passed=True (wall 2.5s, steps 214)

### Meta-Harness 轮次记录 (20260807_155537) — ca_rules_01
- 假说: 增加 grip decay 以提高在接近边缘时的响应速度和安全性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，适当增加 grip decay 可能减少此类错误，并提高相扑机器人的整体稳定性
- 结果: score=1.0 passed=True (wall 2.2s, steps 214)

### Meta-Harness 轮次记录 (20260807_163207) — ca_rules_01
- 假说: 增加 grip decay 以提高在边缘附近的稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 缺陷库项，探针越界误判坠台。增加 grip decay 可能减少这种误判，提高机器人在边缘附近的稳定性
- 结果: score=1.0 passed=True (wall 3.2s, steps 214)

### Meta-Harness 轮次记录 (20260807_164019) — ca_rules_01
- 假说: 降低 grip decay 以减少对边缘的依赖, 提高机动性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 通过调整 grip decay 的初始值, 可能使机器人在接近边缘时更快地做出反应, 减少因误判而坠台的风险。
- 结果: score=1.0 passed=True (wall 2.9s, steps 214)

### Meta-Harness 轮次记录 (20260807_164632) — ca_rules_01
- 假说: 增加 grip decay 以提高在边缘附近的策略敏感度
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，增加 grip decay 可能减少此类错误，并提高对边缘的感知
- 结果: score=1.0 passed=True (wall 2.1s, steps 214)

### Meta-Harness 轮次记录 (20260807_165240) — ca_rules_01
- 假说: 降低Grip Decay值可以更早触发边缘规避策略，提高相扑机器人在接近边缘时的反应速度和安全性。
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据缺陷库中的F-104，探针越界误判坠台问题可能与Grip Decay值过高有关。降低此值可以更早触发边缘规避策略，减
- 结果: score=1.0 passed=True (wall 2.1s, steps 214)

### Meta-Harness 轮次记录 (20260807_165907) — ca_rules_01
- 假说: 提高 grip decay 值以更好地适应环境变化
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，提高 grip decay 可能减少此类错误
- 结果: score=1.0 passed=True (wall 2.1s, steps 214)

### Meta-Harness 轮次记录 (20260807_171319) — ca_rules_01
- 假说: 降低 grip decay 值以减少对边沿的依赖性，提高机动灵活性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，降低 grip decay 可能会减少因误判而提前死亡的情况
- 结果: score=1.0 passed=True (wall 3.1s, steps 214)

### Meta-Harness 轮次记录 (20260807_172136) — ca_rules_01
- 假说: 增加 grip decay 以提高在边缘附近的响应速度和安全性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史缺陷库中提到探针越界误判坠台，适当增加 grip_decay 可能减少此类问题。
- 结果: score=1.0 passed=True (wall 2.1s, steps 214)

### Meta-Harness 轮次记录 (20260807_172743) — ca_rules_01
- 假说: 提高边缘检测阈值以减少不必要的紧急避险动作，从而优化策略执行效率和能耗
- 证据链: F-103 | 血缘: code_agent(qwen2.5:7b) 历史轨迹显示频繁的紧急避险可能导致策略执行混乱，调整阈值可以减少此类事件
- 结果: score=1.0 passed=True (wall 1.9s, steps 214)

### Meta-Harness 轮次记录 (20260807_173349) — ca_rules_01
- 假说: 降低 grip decay 以减少过早规避, 提高激进策略效果
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题, 适当降低 grip decay 可能有助于机器人更准确地判断何时需要规避边缘
- 结果: score=1.0 passed=True (wall 1.9s, steps 214)

### Meta-Harness 轮次记录 (20260807_174011) — ca_rules_01
- 假说: 提高Grip Decay阈值以增强对边缘的敏感度和反应速度
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据历史缺陷库，探针越界误判坠台。增加Grip Decay阈值可以更早触发策略响应，减少误判
- 结果: score=1.0 passed=True (wall 1.8s, steps 214)

### Meta-Harness 轮次记录 (20260807_184621) — ca_rules_01
- 假说: 提高 grip decay 以更好地适应边缘滑动情况
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，增加 grip decay 可能减少此类错误
- 结果: score=1.0 passed=True (wall 3.4s, steps 214)

### Meta-Harness 轮次记录 (20260807_185755) — ca_rules_01
- 假说: 降低Grip衰减以增加抓取稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据缺陷库中的F-104，探针越界误判坠台。降低Grip衰减可以减少因探针误判导致的坠台概率
- 结果: score=1.0 passed=True (wall 5.3s, steps 214)

### Meta-Harness 轮次记录 (20260807_190424) — ca_rules_01
- 假说: 增加 grip decay 以提高在边缘附近的稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，增加 grip decay 可能减少此类错误
- 结果: score=1.0 passed=True (wall 4.4s, steps 214)

### Meta-Harness 轮次记录 (20260807_192735) — ca_rules_01
- 假说: 降低Grip Decay值以减少对边缘的依赖性，提高灵活性和适应性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据历史缺陷库中的F-104，探针越界误判坠台。通过降低Grip Decay值，可以减少机器人在边缘时的锁定状态，提高其
- 结果: score=1.0 passed=True (wall 2.5s, steps 214)

### Meta-Harness 轮次记录 (20260807_193346) — ca_rules_01
- 假说: 提高 grip decay 以更好地适应边缘滑动情况
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，增加 grip decay 可能减少此类错误
- 结果: score=1.0 passed=True (wall 2.8s, steps 214)

### Meta-Harness 轮次记录 (20260807_193951) — ca_rules_01
- 假说: 提高边缘接近阈值以减少不必要的紧急避险动作，从而优化策略执行效率和稳定性
- 证据链: F-103 | 血缘: code_agent(qwen2.5:7b) 历史轨迹显示频繁的紧急避险可能导致策略执行不稳定，适当提高阈值可以减少此类事件，提升整体表现
- 结果: score=1.0 passed=True (wall 3.6s, steps 214)

### Meta-Harness 轮次记录 (20260807_194601) — ca_rules_01
- 假说: 降低 grip decay 以减少过早规避, 提高激进策略效果
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题, 可能是 grip decay 过大导致的。降低此值可以观察是否改善该问题并提
- 结果: score=1.0 passed=True (wall 2.4s, steps 214)

### Meta-Harness 轮次记录 (20260807_195230) — ca_rules_01
- 假说: 提高 grip decay 以更早触发防御策略
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 缺陷，探针越界误判坠台。降低 grip decay 可使机器人更早采取防御措施，减少误判
- 结果: score=1.0 passed=True (wall 4.6s, steps 214)

### Meta-Harness 轮次记录 (20260807_214904) — ca_rules_001
- 假说: 增加 grip decay 值以提高在边缘时的抓取稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，适当增加 grip decay 可能减少此类错误
- 结果: score=1.0 passed=True (wall 4.6s, steps 214)

### Meta-Harness 轮次记录 (20260807_215536) — ca_rules_002
- 假说: 降低 grip decay 值以减少在边缘附近的滑动
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，降低 grip decay 可能会减少机器人在接近边缘时的滑动，从而提高稳定性
- 结果: score=1.0 passed=True (wall 2.8s, steps 214)

### Meta-Harness 轮次记录 (20260807_220204) — ca_rules_002
- 假说: 提高 grip decay 以更好地适应边缘滑动情况
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，增加 grip decay 可能减少此类错误
- 结果: score=1.0 passed=True (wall 1.9s, steps 214)

### Meta-Harness 轮次记录 (20260807_220824) — ca_rules_007
- 假说: 降低Grip Decay值以减少对边缘的依赖性，提高灵活性和适应性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据缺陷库中的F-104，探针越界误判坠台。通过降低Grip Decay值，可以减少在接近边缘时的过度反应，提高策略的灵
- 结果: score=1.0 passed=True (wall 2.0s, steps 214)

### Meta-Harness 轮次记录 (20260807_221451) — ca_rules_007
- 假说: 增加 grip decay 值以提高在边缘附近的稳定性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，适当增加 grip decay 可能减少此类错误
- 结果: score=1.0 passed=True (wall 2.2s, steps 214)

### Meta-Harness 轮次记录 (20260807_224459) — ca_rules_007
- 假说: 降低 grip decay 值以减少在边缘附近的滑动
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 缺陷，探针越界误判坠台。降低 grip decay 可能会减少这种误判
- 结果: score=1.0 passed=True (wall 3.9s, steps 214)

### Meta-Harness 轮次记录 (20260807_225210) — ca_rules_008
- 假说: 提高 grip decay 值以增强对边缘的敏感度和反应速度
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，增加 grip decay 可能减少此类错误，并提高整体表现
- 结果: score=1.0 passed=True (wall 2.1s, steps 214)

### Meta-Harness 轮次记录 (20260807_225827) — ca_rules_001
- 假说: 降低 grip decay 值以减少在接近边缘时的滑动
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 缺陷，探针越界误判坠台。降低 grip decay 可能会改善这一问题，并提高相扑机器人的稳定性
- 结果: score=1.0 passed=True (wall 2.4s, steps 214)

### Meta-Harness 轮次记录 (20260807_230452) — ca_rules_001
- 假说: 增加 grip decay 值以提高在接近边缘时的响应速度和安全性
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据 F-104 的探针越界误判坠台问题，适当增加 grip decay 可能减少此类错误，并提升整体稳定性
- 结果: score=1.0 passed=True (wall 11.3s, steps 214)

### Meta-Harness 轮次记录 (20260808_001237) — ca_reward_001
- 假说: 降低危险区边缘的惩罚力度，使机器人在接近危险区域时有更多时间调整策略，从而减少恐慌行为。
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 通过降低 EDGE_DANGER 的值，可以为机器人提供更多的早期预警时间，使其能够更平滑地学习如何避免危险区域，而不是
- 结果: score=1.0 passed=True (wall 5.2s, steps 214)

### Meta-Harness 轮次记录 (20260808_001644) — ca_reward_001
- 假说: 降低警告区边缘的惩罚力度, 鼓励机器人更早避开危险区域
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 通过减少3-6cm范围内的惩罚, 可能会减少误判坠台的情况, 提高机器人的生存率
- 结果: score=1.0 passed=True (wall 2.1s, steps 214)

### Meta-Harness 轮次记录 (20260808_003441) — ca_reward_001
- 假说: 降低警告区阈值, 增加早期预警效果
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 通过提前给予较小的惩罚, 可能使机器人更早地意识到边缘威胁并采取措施
- 结果: score=1.0 passed=True (wall 3.5s, steps 214)

### Meta-Harness 轮次记录 (20260808_004104) — ca_reward_001
- 假说: 降低警告区边缘的惩罚可以减少机器人在接近边界时的犹豫，从而提高接战效率。
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 历史缺陷库中提到探针越界误判坠台的问题，适当降低警告区的惩罚可以在不立即终止比赛的情况下给予机器人更多时间做出反应。
- 结果: score=1.0 passed=True (wall 2.3s, steps 214)

### Meta-Harness 轮次记录 (20260808_004832) — ca_reward_001
- 假说: 降低警告区边缘的惩罚力度, 鼓励机器人更早地避开危险区域
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 通过减少3-6cm范围内的惩罚, 可能会减少误判坠台的情况, 提高机器人的生存率
- 结果: score=1.0 passed=True (wall 3.8s, steps 214)

### Meta-Harness 轮次记录 (20260808_005805) — ca_reward_001
- 假说: 增加边缘警告区的惩罚力度，使机器人更早意识到危险区域并采取措施远离
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据历史缺陷库中的 F-104，探针越界误判坠台。提高边缘警告区的惩罚可以减少误判，使机器人更早避开危险区域
- 结果: score=1.0 passed=True (wall 1.8s, steps 214)

### Meta-Harness 轮次记录 (20260808_012430) — ca_mapping_001
- 假说: 降低触发硬转向的阈值, 提高在近距离时的灵活性和反应速度
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 通过减少误判坠台的情况, 增加了机器人在狭窄空间中的机动性
- 结果: score=1.0 passed=True (wall 2.1s, steps 214)

### Meta-Harness 轮次记录 (20260808_013047) — ca_mapping_001
- 假说: 降低触发硬转向的阈值, 提高在近距离时的灵活性和反应速度
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 根据历史缺陷库中的 F-104，探针越界误判坠台。降低触发硬转向的阈值可以减少误判，提高在近距离时的灵活性和反应速度
- 结果: score=1.0 passed=True (wall 2.4s, steps 293)

### Meta-Harness 轮次记录 (20260808_013547) — ca_reward_001
- 假说: 降低警告区阈值, 减少边缘恐惧
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 通过减少3-6cm范围的惩罚, 可能会减少机器人在接近边缘时的恐慌行为
- 结果: score=1.0 passed=True (wall 2.2s, steps 293)

### Meta-Harness 轮次记录 (20260808_014254) — ca_reward_001
- 假说: 降低警告区边缘的惩罚力度, 鼓励机器人更早避开危险区域
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 通过减少3-6cm范围内的惩罚, 可能会减少误判坠台的情况, 提高机器人的生存率
- 结果: score=1.0 passed=True (wall 2.7s, steps 293)

### Meta-Harness 轮次记录 (20260808_014750) — ca_mapping_001
- 假说: 降低侧接触触发阈值, 提高急转弯反应速度
- 证据链: F-104 | 血缘: code_agent(qwen2.5:7b) 通过减少误判为探针越界的侧接触情况, 可能提高相扑机器人的急转弯响应速度和准确性
- 结果: score=1.0 passed=True (wall 2.1s, steps 293)

## F-100: ABDL 优先级遮蔽 (OPPONENT-FOUND p700 吞掉近战规则)
**证据链**: `opponent_found = opp_dist < max_dist-0.1 = 3.9` (2.0m 场地永远为 True);
引擎 `results.sort(key=-priority)` → p700 OPPONENT-FOUND 在 edge_prox<0.5 时全场地遮蔽
CLOSE-PUSH p500 / FLANK p480/470 → 近战实际运行 `_pursue_opponent` (≤0.38 m/s) 对抗
对手 0.53 → 每次推挤都输。**为什么 4 次规则编辑无效**: 全改在被遮蔽的规则上。
**修复**: OPPONENT-FOUND 增加 `AND opponent_dist > 0.6` (远距追逐语义)。

## F-101: 对手观测坐标系反了 (机器人帧传给对手)
**证据链**: `_move_opponent` 调 `self._get_obs()` (机器人帧); aggressive 的 obs[5]
是"机器人航向→对手"的夹角,却用来决定对手自身转向 → 对手从机器人右侧接近时
**转身逃离**。**修复**: `_get_obs_for(x,y,theta,other)` 按姿态参数化,对手看自己的帧
(实证: 对手视角夹角 1.16° 正确对脸 vs 修复前机器人帧 176.87° 背对)。

## F-102: OpponentStrategies 动作常量整表错误 (对照 Action 枚举)
**证据链**: ACTION_REVERSE=12 实为 TURN_R_HARD(原地右旋); ACTION_RIGHT=8 实为
TURN_L_MED(**左转**); ACTION_STOP=10 实为 TURN_R_MILD(旋转); ACTION_SPIN=15 实为
FW_LEFT_HARD(前弧); circler 用 6=REV_SLOW(每 20 步倒车!)。
**修复**: 6/10/0/9 + aggressive 死区 0.2°(实际从不冲锋)→10° + circler 13/16 +
启发式回退同样修正。

## F-103: 对称碰撞 = 等速对顶永久僵局 (物理层)
**证据链**: 纯 ram 控制 "5/5 胜" 全部是 240 步超时 (total>200 奖励通胀误判);
`push = overlap*0.5` 双方等量 → 0.53 vs 0.53 对顶无净位移, 240 步内无人出界。
**修复**: 驱动-对-驱动推力模型 — 轮推力×抓地力, 抓地力在 r>0.32 线性衰减
(DOHYO_SAFE_RADIUS→RIM, 真实相扑边缘打滑)。推进更狠/立足更稳者赢得地面。

## F-104: 探针越界误判坠台 (奖励层 7.5cm 提前死亡)
**证据链**: V10Reward `edge_min < 0.05` 以传感器探针(中心前 7.5cm)为准 →
中心 r>0.325 即判死, 而 r=0.40 才是真边缘 → 机器人 75% 机身仍在台上却被 -150。
**修复**: env 传权威 `robot_out_of_bounds` (中心 `_is_on_dohyo`), 探针检查降级为兜底。

## F-105: 出生朝向不对称
**证据链**: 对手出生总面向机器人; 机器人随机航向 → ~50% 局先转身 177°
(纯转 = 零推力) → 冲锋型对手 7 步内把转向中的机器人推出。
**修复**: 机器人出生也面向对手 (真实相扑开球)。

## F-106: 侧接触锁定
**证据链**: FW_*_HARD 弧线轨道半径 0.29m > 接触半径 0.15m → 机器人绕对手公转,
角度卡在 -37° 永不归零 → 双双漂向边缘, 机器人先触线。
**修复**: 混合侧翼 — dist<0.20 (对手压进) → 弧线保推力; dist≥0.20 (对手退缩) →
原地纯转收敛; >45° → TURN_*_HARD 快速对准。

## Meta-Harness P1 ROUND 1 (2026-08-05, 规范记录)

### Meta-Harness 轮次记录 (20260805_235930) — mh_rules_001
- 假说: 近战接战窗 ±15°→±10°: 对手侧滑角度大时推迟全力推挤, 避免推力打在切向分量 (F-100 遮蔽修复后的剩余浪费); v11 窗与 970c209 实测 10/10 基线兼容
- 证据链: F-100 | 血缘: 970c209 -> mh_rules_001
- 结果: score=1.0 passed=True (wall 2.2s, steps 461)

### Meta-Harness 轮次记录 (20260805_235930) — mh_mapping_001
- 假说: 侧翼大偏航分档 45°→40°: 更早切 TURN_*_HARD 快速重对准, 减少弧线侧滑的无效推力 (F-106 侧接触锁定 -37° 收敛); 左右侧翼分支同步修改
- 证据链: F-106 | 血缘: 970c209 -> mh_mapping_001
- 结果: score=1.0 passed=True (wall 1.7s, steps 372)

### Meta-Harness 轮次记录 (20260805_235930) — mh_physics_001
- 假说: 推力碰撞动量系数 0.8→0.85: 略增推挤效率, 压缩 0.53 vs 0.53 对称僵局窗口 (F-103); 结果速度仍远低于 0.534 m/s 物理上限
- 证据链: F-103 | 血缘: 970c209 -> mh_physics_001
- 结果: score=1.0 passed=True (wall 1.7s, steps 365)

## Meta-Harness P1 ROUND 2/3 (2026-08-06, 规范记录)

### Meta-Harness 轮次记录 (20260806_001905) — mh_physics_002
- 假说: 动量梯度 0.85->0.900: 继续压缩对称僵局窗口 (F-103); 若 >370 步反弹则触发 PM 硬性回滚条件 (回滚至 0.85)
- 证据链: F-103 | 血缘: 2181108 (动量 0.85->0.9)
- 结果: score=1.0 passed=True (wall 2.0s, steps 360)

### Meta-Harness 轮次记录 (20260806_001905) — mh_physics_003
- 假说: 二分插值 0.875 (0.85 与 0.90 中点): 测绘帕累托前沿精确曲率 — 若逼近 360 步, 说明最优在 0.86~0.88 陡峭效率悬崖 (PM 裁决 1)
- 证据链: F-103 | 血缘: 2181108 (动量 0.85->0.875)
- 结果: score=1.0 passed=True (wall 1.8s, steps 362)

### Meta-Harness 轮次记录 (20260806_001905) — mh_rules_002
- 假说: Circler 切线接近角: FLANK 角度阈值 18°→15° (复用 CLOSE-PUSH 窗值, 零新魔数): 更早切入弧线对手的切向路径, 压缩 67.5 步拖长对局 (F-106 框架)
- 证据链: F-106 | 血缘: 970c209 -> mh_rules_002
- 结果: score=1.0 passed=True (wall 1.4s, steps 290)
- **帕累托突破**: 371→290 步 (21% 压缩), 确定性 2× 复验一致 (random 8.5/aggressive 14/defensive 50/circler 66/counter 5.5)

### Meta-Harness 轮次记录 (20260806_002542) — mh_combined_001
- 假说: 正交叠加: 基线 FLANK 15° (d8ad9d7 已保留) + 动量 0.85→0.90 — 探索线性物理收益与角度杠杆的乘法效应; 目标 < 290 步 (PM 裁决 1)
- 证据链: F-103, F-106 | 血缘: d8ad9d7 (动量 0.85->0.9)
- 结果: score=1.0 passed=True (wall 1.6s, steps 288)
- **叠加性质判定**: 独立收益应为 279 步, 实际 288 步 → ~9 步重叠, **微弱加性而非乘法放大** (诚实科学报告, 不因"突破"叙事掩盖)
- **突破性早期停止已触发**: 288 < 290 (PM 裁决), ROUND 3 对照评估 (mh_physics_004 / mh_rules_003) 未执行, 直接进入 ROUND 4 精细化搜索

## Meta-Harness P1 ROUND 4 (2026-08-06, 精细化搜索 — 无帕累托改进)

### Meta-Harness 轮次记录 (20260806_003847) — mh_combined_002
- 假说: 精细化正交叠加: FLANK 15°→14° + 动量 0.90→0.89 (PM 建议方向 14°+0.89) — 在 mh_combined_001 (288) 邻域做 2×2 因子微扰, 探测前沿曲率与加性边界; 目标 < 288 步
- 证据链: F-103, F-106 | 血缘: 9c6fd50 (FLANK 15°→14° + 动量 0.9→0.89)
- 结果: score=1.0 passed=True (wall 2.7s, steps 289) — 被支配 (+1)

### Meta-Harness 轮次记录 (20260806_003847) — mh_rules_004
- 假说: FLANK 15°→14° 纯角度微扰 (对照 A): 角度是否仍是主杠杆? 15°→14° 逐度边际测绘 (290→288 增益是否延续); 复用既有角度刻度, 零新魔数 (F-106 框架)
- 证据链: F-106 | 血缘: 9c6fd50 -> mh_rules_004
- 结果: score=1.0 passed=True (wall 1.5s, steps 288) — **持平** (288=288, 无质量/效率改进, 未保留; 引擎自动标记"被支配"不准确, 规范记录为持平)

### Meta-Harness 轮次记录 (20260806_003847) — mh_physics_005
- 假说: 动量 0.90→0.89 纯物理微扰 (对照 B): 0.90 是否为局部峰? 若 0.89 步数 > 360 说明 0.90 附近为最优邻域; 完成 2×2 因子设计 (14°/15° × 0.89/0.90) 验证加性边界的局部稳定性
- 证据链: F-103 | 血缘: 9c6fd50 (动量 0.9->0.89)
- 结果: score=1.0 passed=True (wall 1.4s, steps 289) — 被支配 (+1)

### ROUND 4 结论 (2×2 因子表, 基线 = FLANK 15°+动量 0.90 = 288)
| | 动量 0.90 | 动量 0.89 |
|---|---|---|
| FLANK 15° | **288 (基线/前沿)** | 289 (mh_physics_005) |
| FLANK 14° | 288 (mh_rules_004) | 289 (mh_combined_002) |
- **288 确认为局部盆地**: 四个邻域点全部 ≥ 288; 动量 0.89 负增益 (+1), FLANK 14° 中性 (0)
- 加性再次验证: 14°(0) + 0.89(+1) = 组合(+1) ✓
- **无帕累托改进** — 前沿连续第 1 轮未改进 (终止条件计数 1/2; 解冻 TASK-005f 条件计数 1/3)
- 后续候选: 动量 0.95 (ROUND 3 遗留队列, 未评估); FLANK 13° 角度阶梯延续; 组合 13°+0.95

## Meta-Harness P1 ROUND 5 (2026-08-06, 动量阶梯突破 — 新前沿 286)

### Meta-Harness 轮次记录 (20260806_004438) — mh_physics_006
- 假说: 动量 0.90→0.95 (ROUND 3 遗留 mh_physics_004): 动量阶梯在 FLANK 15° 处单调 (0.85→290, 0.89→289, 0.90→288), 向 1.0 硬上限推进; 若 <288 步则动量仍是主梯度
- 证据链: F-103 | 血缘: 7e74be7 (动量 0.9->0.95)
- 结果: score=1.0 passed=True (wall 1.5s, steps 286)
- **帕累托突破**: 288→286, **2× 确定性复验一致** (286=286); 引擎保留, 已应用到工作树
- 逐策略: random 8.0, aggressive 13.5, defensive 50, circler 66, counter 5.5
  (动量 0.95 主要压缩 random/aggressive 各 0.5 步均值)

### Meta-Harness 轮次记录 (20260806_004438) — mh_rules_005
- 假说: FLANK 15°→13° 纯角度微扰 (对照 A): 14° 处增益归零 (288 持平), 13° 是恢复坡度 (更早切入) 还是进入平台期; 零新魔数 (F-106)
- 证据链: F-106 | 血缘: 7e74be7 -> mh_rules_005
- 结果: score=1.0 passed=True (wall 1.5s, steps 288) — 持平 (角度阶梯 13°-15° 平台期)

### Meta-Harness 轮次记录 (20260806_004438) — mh_combined_003
- 假说: 组合变体: FLANK 13° + 动量 0.95 — 在 (13°, 0.95) 新点完成因子设计; 若加性成立: 288 + Δ(0.95) + Δ(13°); 目标 < 288 步
- 证据链: F-103, F-106 | 血缘: 7e74be7 (FLANK 15°→13° + 动量 0.9→0.95)
- 结果: score=1.0 passed=True (wall 2.0s, steps 286) — **持平** (286=286 与 mh_physics_006 并列, 引擎按顺序保留 physics; 加性第 4 次验证: 0.95(-2) + 13°(0) = 组合(-2) ✓)

### ROUND 5 结论
- **新帕累托前沿: 286 步 (FLANK 15° + 动量 0.95, mh_physics_006)** — 动量阶梯仍单调, 无饱和
- 角度阶梯平台期: 15°=14°=13° → 288 (角度贡献饱和, 不再扩展)
- 终止条件计数归零 (前沿改进); TASK-005f 解冻计数归零
- ROUND 6 候选: 动量 0.95→1.0 (**硬上限探针**, PM 裁决 2 明确: 动量达 1.0 且边际 <1% 才解冻视觉);
  FLANK 13°→11° (平台期下探); 组合 11°+1.0

## Meta-Harness P1 ROUND 6-A (2026-08-06, 意外重跑 ROUND 1 计划 — 交互增益发现)

### 事件背景 (诚实 provenance)
- `--tag ROUND6` 的轮次推断表缺失 "6" → 误执行 ROUND 1 计划 (rules_001 / mapping_001 / physics_seed_001)
- 该缺陷已修复 (推断表加入 "6"); 但意外重跑在**改进基线** (286) 下暴露了跨基线交互增益
- physics_seed_001 未生成: 其 diff old (动量 0.8) 不在磁盘 (当前 0.95), 磁盘自适应守卫按设计跳过

### Meta-Harness 轮次记录 (20260806_005025) — mh_rules_001 (重跑)
- 假说: 近战接战窗 ±15°→±10°: 对手侧滑角度大时推迟全力推挤, 避免推力打在切向分量 (F-100 遮蔽修复后的剩余浪费)
- 证据链: F-100 | 血缘: 970c209 -> mh_rules_001
- 结果: score=1.0 passed=True (wall 1.6s, steps 351) — 被支配 (仍劣于基线 286; ROUND 1 时为 461)

### Meta-Harness 轮次记录 (20260806_005025) — mh_mapping_001 (重跑, 帕累托突破)
- 假说: 侧翼大偏航分档 45°→40°: 更早切 TURN_*_HARD 快速重对准, 减少弧线侧滑的无效推力 (F-106 侧接触锁定 -37° 收敛); 左右侧翼分支同步修改
- 证据链: F-106 | 血缘: 970c209 -> mh_mapping_001
- 结果: score=1.0 passed=True (wall 1.8s, steps 262) — **帕累托突破** (286→262, -8.4%, 全场最大单步增益)
- **2× 确定性复验: 262 = 262 完全一致**; 引擎保留, 已应用到工作树 (abdl_action_bridge.py)
- 逐策略 (262): random 8.0, aggressive 13.5, **circler 57.0 (-9)**, **defensive 47.0 (-3)**, counter 5.5
  → 40° 硬转阈值精准压缩 F-106 弧线侧滑无效推力 (circler 66→57)

### ROUND 6-A 结论
- **新帕累托前沿: 262 步 (FLANK 15° + 动量 0.95 + 侧翼硬转 40°, mh_mapping_001)**
- **交互增益**: mapping_001 在旧基线 371 时 = 372 (中性), 新基线 286 下 = 262 — 收益依赖
  FLANK 15°+动量 0.95 的改进基线 (更早硬转与更激进切角的协同)
- **方法论教训**: 线性逐轮保留会漏掉跨基线交互收益 → 建议定期对全变体注册表做
  "重资格扫描" (re-qualification sweep); ROUND 1 时对 mapping_001 的"被支配"裁决在当时
  的基线下是正确的, 但不应视为永久失效
- ROUND 6 正式计划 (动量 1.0 硬上限 + FLANK 12° + 组合 12°+1.0) 将在新基线 262 上执行

## Meta-Harness P1 ROUND 6 (2026-08-06, 动量 1.0 硬上限 — 新前沿 260)

### Meta-Harness 轮次记录 (20260806_115924) — mh_physics_007
- 假说: 动量 0.95→1.0 (硬上限探针): 动量阶梯单调 (0.89→289, 0.90→288, 0.95→286), 1.0 为物理层硬上限; 若 >=262 步则动量收益饱和 (<1% 边际), 触发 PM 裁决 2 的 TASK-005f 视觉解冻评估条件
- 证据链: F-103 | 血缘: 1517a2e (动量 0.95->1.0)
- 结果: score=1.0 passed=True (wall 2.1s, steps 260)
- **帕累托突破**: 262→260, **2× 确定性复验一致** (260=260); 引擎保留, 已应用到工作树
- **动量轴穷尽**: 1.0 = 物理层硬上限, 最后一次增量边际 2/262 = 0.76% < 1% → **TASK-005f 视觉解冻评估条件 (PM 裁决 2) 已触发**

### Meta-Harness 轮次记录 (20260806_115924) — mh_rules_006
- 假说: FLANK 15°→12° 纯角度微扰 (对照 A, ROUND 3 遗留 rules_003): 13°-15° 平台期 (全部 288), 12° 探平台边缘 — 接近 CLOSE-PUSH 15° 窗, 测试角度杠杆是否在窗口边界重新获得收益; 零新魔数 (F-106)
- 证据链: F-106 | 血缘: 1517a2e -> mh_rules_006
- 结果: score=1.0 passed=True (wall 1.6s, steps 262) — 持平 (平台期延续: 12°-15° 全部同值)

### Meta-Harness 轮次记录 (20260806_115924) — mh_combined_004
- 假说: 组合变体: FLANK 12° + 动量 1.0 — 在 (12°, 1.0) 新点完成因子设计; 若加性成立: 262 + Δ(1.0) + Δ(12°); 目标 < 262 步
- 证据链: F-103, F-106 | 血缘: 1517a2e (FLANK 15°→12° + 动量 0.95→1.0)
- 结果: score=1.0 passed=True (wall 1.7s, steps 260) — **持平** (260=260 与 mh_physics_007 并列, 引擎按顺序保留 physics; 加性第 5 次验证: 1.0(-2) + 12°(0) = 组合(-2) ✓)

### ROUND 6 结论
- **新帕累托前沿: 260 步 (FLANK 15° + 动量 1.0 + 侧翼硬转 40°, mh_physics_007)**
- **动量轴穷尽 (硬上限 1.0, 边际 0.76% < 1%)** → 触发 PM 裁决 2 的 TASK-005f 视觉解冻评估
- 角度阶梯平台期延续: 12°-15° 全部同值 (角度杠杆饱和)
- 加性第 5 次验证 ✓ — 弱加性假设在 (12°,1.0) 仍成立
- 全场演进: 371 → 365 → 290 → 288 → 286 → 262 → **260** (总压缩 -30%)
- ROUND 7 候选: 角度下探 10° (平台边缘更远处); 其他轴探索 (奖励函数/引擎) 建议先做
  **re-qualification sweep** (重扫全变体注册表, 验证交互增益在 260 基线下是否持续)

## 结果
V9 门 6/10 → **10/10** (aggressive 2/2, defensive 2/2, circler 2/2, random 2/2,
counter 2/2), 全部真实出界终结。提交 970c209。

---

## Meta-Harness P1 ROUND 6-B (2026-08-06, re-qualification sweep — 新正交轴 259)

### 背景
ROUND 6-A 教训 (跨基线交互增益: mh_mapping_001 在 371 基线中性、在 286 基线 = 262):
线性逐轮保留会漏掉交互收益 → 实现 `--sweep` (重扫全变体注册表) 并在 260 基线上首跑。

### sweep 执行记录 (基线 260)
| 候选 | 结果 | 判定 |
|------|------|------|
| mh_rules_001 (规则 ±10°) | 343 | 被支配 (远劣于基线) |
| mh_mapping_002 (45°→40°) | 跳过 | diff 3× 匹配 vs 期望 1 (映射层多处出现, 磁盘感知跳过) |
| mh_physics_seed_001 (动量 0.8→0.85) | 跳过 | diff 0.8 不在磁盘 (动量已在 1.0) |
| **mh_physics_seed_002 (抓地衰减 线性→二次)** | **259** | **击败基线 260, 保留到工作树** |
| mh_combined_001 (FLANK 15°+动量 0.90) | 264 | 被支配 (260 基线下的历史组合) |
| mh_rules_003 (FLANK 12°) | 260 | 持平 |

### seed_002 因果推理 (为什么它赢了?)
- **改动内容**: `(DOHYO_RADIUS - r) / DOHYO_EDGE_ZONE` → 同式平方 — 边缘抓地衰减从线性变为二次。
- **物理语义**: 二次衰减使机器人离开中心后抓地损失更快 → 边缘区推力效率下降 → 内圈高抓地区
  的博弈权重上升 → 在保持 10/10 胜率 (score 1.0 PASS) 前提下压缩总步数。
- **为何历轮计划漏掉它**: 历轮全部沿 momentum / FLANK / mapping 三轴搜索; grip decay 形状
  是**第四个正交轴**, 从未进入任何 ROUND 计划 — 它藏在 seed 降级模板里 (血缘 SEED_TEMPLATE,
  早期磁盘正则失配时的兜底生成物), 只有全注册表重扫才能发现。

### 硬上限合规裁决 (关键)
**momentum 是否越界? 否。** git diff (工作树 vs 4f031a3) 证实 lightweight_env.py 唯一改动为
抓地衰减平方化; `momentum = net * TIMESTEP * 1.0` 行与 ROUND 6 提交完全一致 — 1.0 硬上限
未被触碰。259 步来自新正交轴, 而非动量越界。

### 确定性复验
sweep 单发 259 → 2× 门评测复验: RUN1=259, RUN2=259, identical=True (gate_exit 0, score 1.0 PASS)。

### ROUND 6-B 结论
- **新帕累托前沿: 259 步** (抓地衰减二次 + 动量 1.0 + FLANK 15° + 侧翼硬转 40°)
- **sweep 机制首杀**: ROUND 6-A 教训的制度化工具立即产出收益 → 成为常设流程
  (每轮前沿变更后重扫全注册表)
- 全场演进: 371 → 365 → 290 → 288 → 286 → 262 → 260 → **259** (总压缩 -30.2%)
- ROUND 7 候选: grip decay 三次方/阶梯化下探 (新轴继续), 角度 10° 下探, 或奖励函数新轴

---

## Meta-Harness P1 ROUND 7 (2026-08-06, 角度平台期外突破 258, grip 轴闭合)

### 背景
ROUND 6-B 之后基线 = 259 (grip 二次 + 动量 1.0 + FLANK 15° + mapping 40°)。ROUND 7
三候选因子设计: 主攻手 = grip 二次→三次 (新轴延续); 对照 A = FLANK 15°→10° (平台期外);
对照 B = 三次+10° 组合 (新点因子设计)。目标 < 259。

### 结果
| 变体 | 步数 | 判定 |
|------|------|------|
| mh_physics_008 (grip 二次→三次) | 259 | **持平** — grip 轴饱和 |
| **mh_rules_007 (FLANK 15°→10°)** | **258** | **新前沿** |
| mh_combined_005 (三次+10°) | 258 | 与 rules_007 并列 (早停触发) |

### 因果推理 (为什么 FLANK 10° 赢而 grip 三次不赢?)
1. **grip 三次 (0 增益)**: 二次衰减已捕获该轴全部收益; 三次方在 clamp [0,1] 下的额外形状
   变化对推力分布无影响 (安全区内全 clamp 到 1.0, 边缘区内二次已足够陡) → **轴闭合宣言**:
   grip decay 线性→二次→三次方向探索完毕, 不再投入。
2. **FLANK 10° (-1 步)**: 关键在**近缘死区** — 规则引擎优先级 CLOSE-PUSH (p500) >
   FLANK-RIGHT (p480) > FLANK-LEFT (p470)。重叠带 (10°,15°) 且 edge<0.65 时 CLOSE-PUSH
   优先接管 → 无行为歧义。**死区 = 角度 (10°,15°) ∩ edge∈[0.65, 0.80)**: FLANK 15° 边界外
   无规则触发, 机器人在近缘带内不重新对齐 → 侧滑无效推力 (F-106) 持续。FLANK 10° 提前
   接管该死区 → 近缘快速重新对齐 (random 7.5→7.0, circler 57.0→56.5) → 少 1 步。
3. **角度响应非单调**: 12°-15° 全 288 是局部平台期, 10° 突破 — 平台期内角度杠杆为 0,
   平台期外重新激活。**教训: 平台期不代表轴枯竭, 需要边界外探针** (与 ROUND 4 局部盆地
   确认互补: 盆地邻域内微扰 → 确认局部最小; 平台期外探针 → 找到新下坡)。

### 加性第 6 次验证
259 + Δ(cubic)=0 + Δ(10°)=-1 = 258 ✓ (组合与 10° 单独完全一致)。微弱加性规律第 6 次
复现 — 收益源正交时叠加, 重叠时弱化, 从不超加性。

### 确定性复验
mh_rules_007 单发 258 → 2× 门评测: RUN1=258, RUN2=258, identical=True (gate 0, 10/10, score 1.0)。

### ROUND 7 结论
- **新帕累托前沿: 258 步** (FLANK 10° + grip 二次 + 动量 1.0 + mapping 40°)
- grip 轴闭合 (259→259); 角度轴在平台期外重新激活
- 全场演进: 371 → 365 → 290 → 288 → 286 → 262 → 260 → 259 → **258** (总压缩 -30.5%)
- ROUND 8 候选: 角度 8° 下探 (F-106 零新魔数; 注意 10° 已贴近 CLOSE-PUSH 窗界),
  258 基线再 sweep, 或奖励函数新轴

---

## 元观察 OBS-007 (2026-08-06 PM 归档裁决) — 边际收益指数衰减, 收敛预测

**归档来源**: PM 正式裁决 3 (对"连续 6 轮帕累托改进"的元认知记录, 强制归档)

**数据**: 连续 6 轮帕累托改进 371→258, PM 口径边际收益序列 (-81, -4, -2, -2, -1, -1):

| 轮 | 前沿 | Δ步 | 口径 |
|----|------|-----|------|
| ROUND 1 | 371→365 | -6 | 平台期 |
| ROUND 2 | 365→290 | -75 | **结构性突破** (PM 口径 -81 含 ROUND 1 后基线修正) |
| ROUND 3 | 290→288 | -2 | 平台期 |
| ROUND 5 | 288→286 | -2 | 平台期 |
| ROUND 6-A | 286→262 | -24 | **结构性突破** (跨基线交互) |
| ROUND 6 | 262→260 | -2 | 平台期 |
| ROUND 6-B | 260→259 | -1 | 平台期 |
| ROUND 7 | 259→258 | -1 | 平台期 |

> 平台期口径: (-2, -2, -2, -1, -1) — 指数衰减; 结构性突破 (ROUND 2 -75, ROUND 6-A -24)
> 是跨基线交互/新轴激活事件, 与稳态递减正交。

**PM 预测 (归档)**: 当前斜率 ≈ -0.17 步/轮, 预计 ROUND 10-12 触及噪声层 (±1 步)。
届时 **Sprint 5 应宣告自然收敛**, 无论 TASK-005f 是否解冻。

**与 TASK-005f 3-2-1 触发器交叉验证**: 3 轮无前沿 (ROUND 8-10) ≈ ROUND 10-12 噪声层
预测窗口 → 双机制收敛信号一致。

---

## Meta-Harness P1 ROUND 8-A (2026-08-06, sweep 巨型跨基线交互 — 完美铺砖 214)

### 背景
PM 裁决 2B 强制并行: 258 基线 `--sweep` 重扫全注册表 (含 ROUND 1-7 所有被支配变体)。
裁决条款: "若 sweep 发现 >258 的候选, 立即中断角度轴探索, 优先验证 2× 复现性"。

### sweep 结果 (基线 258, 6 候选)
| 候选 | 结果 | 判定 |
|------|------|------|
| mh_combined_001 (15°+0.90) | 待统计 | — |
| mh_mapping_002 (45°→40°) | 跳过 (diff 3× 匹配) | — |
| mh_physics_008 (grip 三次) | 259→258 基线待统计 | — |
| mh_physics_seed_001 (0.8) | 跳过 (不在磁盘) | — |
| mh_physics_seed_002 (grip 二次) | 与基线重复 | — |
| **mh_rules_001 (CLOSE-PUSH ±15°→±10°)** | **214** | **击败基线 258 → 保留到工作树** |

### 因果推理 (为什么 343 → 214 的大反转?)
mh_rules_001 的 diff 是 **CLOSE-PUSH 近战窗 ±15°→±10°** (非 FLANK)。其价值完全取决于
FLANK 阈值 — 教科书级跨基线交互:
- **260 基线 (FLANK 15°)**: CLOSE-PUSH ±10° + FLANK 15° → **(10°,15°) 死区无人接管** →
  机器人在该角度带不动作 → 343 步 (灾难)。这是 260 sweep 中被支配的原因。
- **258 基线 (FLANK 10°)**: CLOSE-PUSH ±10° + FLANK ±10° → **完美空间铺砖**:
  |angle|≤10° → CLOSE-PUSH (p500); |angle|>10° → FLANK (p480/470)。零重叠零死区,
  优先级永不冲突 → 214 步。

### 分策略解剖 (收益全部来自 circler)
| 策略 | 258 | 214 | Δ |
|------|-----|-----|---|
| random | 7.0 | 7.0 | 0 |
| aggressive | 13.0 | 13.0 | 0 |
| defensive | 47.0 | 45.5 | -1.5 |
| circler | 56.5 | **36.0** | **-20.5** |
| counter | 5.5 | 5.5 | 0 |

机制: 绕圈手以宽角轨道运动。±10° 铺砖下, 10°-15° 带从 CLOSE-PUSH (p500 优先, 切向
推力浪费, F-106) 转为 FLANK (高效重新对齐) → 绕圈拦截提速。**F-106 切向浪费修复对
circler 场景的彻底兑现**。PM 关注的 defensive (45.5, -1.5) 与 aggressive (13.0, 0)
几乎不变 — 8° 切角对慢速对手无显著影响, 验证了 PM 裁决 2 搁置 8° 的正确性。

### 裁决合规
- ✅ 中断角度 8° 探索 (mh_rules_008 未评估, 按 PM 裁决 2B 优先验证 sweep 候选)
- ✅ 2× 确定性复验: 214=214, gate 0, passed True, score 1.0
- ✅ 角度 8° 候选待 214 基线重新资格化 (跨基线教训: 基线变更后所有历史变体需重扫)

### ROUND 8-A 结论
- **新帕累托前沿: 214 步** (CLOSE-PUSH ±10° + FLANK 10° + grip 二次 + 动量 1.0 + mapping 40°)
- **跨基线交互增益第二次巨额兑现** (首次 ROUND 6-A: -24; 本次 -44): sweep 制度化核心价值实证
- **OBS-007 预测修正**: 斜率 -0.17 步/轮预测在 ROUND 8 即被结构性突破打断 — 说明
  交互增益 (非单调结构) 会重置衰减曲线, 收敛预测需按"平台期口径"重新计时
- 全场演进: 371 → 365 → 290 → 288 → 286 → 262 → 260 → 259 → 258 → **214** (总压缩 -42.3%)
- ROUND 9 候选: 214 基线再 sweep (常态化); 角度 8° 重新资格化; 奖励轴 (mh_reward_001 模板已预生成)

---

## Meta-Harness P1 ROUND 8-B (2026-08-06, P0 全量 sweep + P1 角度资格化 — 214 保持)

### PM 裁决执行清单
1. **MFHS v1.0 元提示词装载** ✅ — `.aionui/meta_prompts/multi_framework_harness_synthesizer_v1.md` + manifest.json (active_protocol 切换)
2. **引擎升级** ✅ — `--auto-sweep` (每轮末尾轻量重扫未采用候选) + `--baseline N` (指定基线) + `--clamp` (D4 边界自限) + 潜伏注册表 `append_latent`
3. **OBS-007 双模式收敛规则** ✅ — 连续轴优化 → 指数衰减; 结构重组 (sweep/交互) → 突变-重组模型 (平均 5-8 轮一次); 3-2-1 触发器"3 轮无进展"仅计连续轴轮次

### P0: 214 基线全量 sweep (PM 裁决, 关注 mh_combined_001 负协同)
| 候选 | 结果 | 判定 |
|------|------|------|
| **mh_combined_001 (15°+0.90)** | **221** | **>214 → 负协同证据成立** (旧组合被 10°+1.0 前沿支配; 264@260 → 221@214 随基线改善但从未追上; 组件已过时) |
| mh_physics_008 (grip 三次) | 214 | 持平 — grip 轴跨基线零贡献, 闭合确认 |
| mh_rules_seed_001 | 跳过 | diff (±15 窗) 已被 mh_rules_001 并入基线 |
| mh_mapping_002 | 跳过 | dist<0.20 3× 匹配 |
| mh_physics_seed_001 | 跳过 | 0.8 不在磁盘 |
| mh_physics_seed_002 | 跳过 | grip 线性子串 2× 匹配 |

**结论: 无候选击败 214** → 进入 P1。

### P1: 角度 8° 重新资格化 (mh_rules_008, FLANK 10°→8°)
**= 214 持平**。8° 在铺砖基线上行为中性 — (8,10)∩edge∈[0.65,0.80) 死带 (CLOSE-PUSH 需 edge<0.65,
FLANK 需 >10°) 在种子局中不可达或影响为零。按 PM 裁决 (仅 <214 才推进 5°): **不触发 5° 探针,
FLANK 10° 锁定为最佳切角, 角度轴饱和**。

### 引擎升级验证 (PM ROUND 9 架构指令)
- `--auto-sweep`: 本轮 ROUND 8 单候选轮未触发 (无未采用候选); 机制已就位 (快照轮末状态 → 重扫 → 恢复)
- `append_latent`: 潜伏注册表已记录 mh_combined_001 (221) + mh_physics_008 (214)
- `--baseline N` 解析: `--baseline 214` 正确接收 int 值
- MFHS 四域联检 (本轮): D4 边界 — FLANK 8° > 角度下限 5° ✅ 未触碰; 动量 1.0 硬上限未触碰 ✅

### ROUND 8-B 结论
- **前沿保持 214** (CLOSE-PUSH ±10° + FLANK 10° + grip 二次 + 动量 1.0 + mapping 40°)
- 角度轴饱和 (10° 最佳切角); grip 轴闭合确认 (跨基线); 动量轴闭合 (硬上限)
- 潜伏注册表机制上线 — 系统性捕获"潜伏变体" (PM 架构指令), 无需等待新前沿
- ROUND 10 候选: 奖励轴启用 (mh_reward_001, F-104 修复后首个全新维度); 或 214 基线三轮后 auto-sweep 复查

---

## Meta-Harness P1 ROUND 10 (2026-08-06, 奖励轴证伪测试 — 轴关闭)

### 背景
PM 裁决 2C 排期: 奖励轴 = ROUND 10 (P0/P1 无新前沿, 不提前扰动)。mh_reward_001 为
预生成模板的首次实例化 — **证伪测试**设计 (预判持平, 用数据决定轴去留)。

### 候选: mh_reward_001 (push_threshold 0.2→0.285)
- 改动: reward_functions.py `push_threshold: float = 0.2` → `0.285`
  (文件头自述 BayesOpt 最优 0.285m — F-106 零新魔数)
- 结果: **214 持平** (214=214, gate 0, 10/10)

### 因果推理 (为什么奖励改动无效 — 三层解耦)
1. **规则智能体非奖励驱动**: ABDL 规则 (simulation_rules.abdl → abdl_action_bridge.py)
   按优先级选离散动作; 奖励信号不参与动作选择。
2. **终止只看出界**: env.step() 中 done = robot/opp out_of_bounds 事件; 奖励幅值
   不改变 done 逻辑。
3. **env 显式传参遮蔽默认值**: `V10Reward(edge_penalty_weight, push_threshold)` 由
   env 构造参数传入 → reward_functions.py 的默认值改动完全惰性。

### 轴关闭裁决
- **奖励轴对规则 harness 引擎关闭**: 改奖励幅值不可能改变步数指标 (证伪完成)。
- 奖励优化仅对 **RL 训练轨道**有效 (那里智能体确实优化奖励信号) — 跨轨道差异记录。
- 若未来启用 RL 轨道 (TASK-005f 解冻后的视觉/RL 方向), 此轴重新开放。

### 四轴全闭总表
| 轴 | 闭合点 | 证据 |
|----|--------|------|
| 动量 | 1.0 (硬上限) | ROUND 6: 边际 0.76% <1% |
| grip | 二次 | ROUND 7: 259=259; ROUND 8-B: 214=214 |
| FLANK 角度 | 10° (最佳切角) | ROUND 8-B: 8°=214 持平 |
| 奖励 | 解耦 (规则引擎) | ROUND 10: 0.285=214 持平 (三层解耦) |

### ROUND 10 结论
- **前沿保持 214**; 四轴全闭 → 规则 harness 引擎进入"微扰收敛区"
- 剩余候选轴: 规则距离阈值 (0.6/0.65/0.80) 微扰、新规则 (边缘预防, 但 F-106 要求零新魔数)
- 3-2-1 触发器计数: ROUND 8-B P1 (8° 持平, 连续轴) + ROUND 10 (奖励, 新轴测试) —
  距 3 轮无进展触发还剩 1-2 轮连续轴轮次; OBS-007 预测 ROUND 10-12 触及噪声层
- **全场演进: 371 → 214 (总压缩 -42.3%), 14 个提交, 6 个新前沿**


---

## ROUND 11 — RULES 关闭 + TASK-005f 视觉轨道 (2026-08-06, PM 裁决 3/3)

### 规则层裁决
- **RULES 引擎正式 CONVERGED/CLOSED**: 214 步前沿稳定, 四轴全闭 (动量 1.0 硬上限 / grip 二次 / FLANK 10° / 奖励解耦)。
- **禁止**: ROUND 11 起任何规则层新候选 (含距离阈值 0.6/0.65/0.80 微扰——会污染映射结果)。
- **3-2-1 触发确认**: ROUND 8-B P1 (8° 持平) + ROUND 10 (奖励持平) + ROUND 11 (RULES 关闭) = 3 轮无进展 → **TASK-005f 解冻 → ACTIVE**。

### F-107 (新): Rerun Web Viewer wasm 交互自动化不可靠
**触发**: 尝试在 :9090 wasm 查看器中自动选择 recording (点击 logo 开面板 → 点卡片) 无法稳定打开 bottlesumo_vision_probe 场景。
**根因**: Rerun Web Viewer 是 wasm/egui/wgpu 应用, DOM 无文本, 仅 canvas; 合成 PointerEvent 部分有效 (开面板) 但卡片选择不可靠。
**证据**: 多次尝试后 97.7% 暗屏, 无场景实体; 但 gRPC ReadMessages [200] + .rrd stats (11 entity paths, 20+ 帧) 证明数据已摄入管道。
**修复 (工具优先)**: 放弃 wasm 交互死磕。采纳 G3CA v1.1 工具优先原则 + 双通道验证:
1. gRPC/.rrd 磁盘证据 (已获证)
2. Phase A2 帧落盘 PNG (vision_probe.py --save-frames) 作为 GUI 可见终裁证据
**教训**: 治理规则要求"GUI 可见", 但 wasm 自动化不可靠时不硬啃——用磁盘 PNG 满足 P4 精神, 不伪造截图。

### ROUND 11 干跑结论 (交付物 b)
- `outer_loop.py --vision-probe aggressive` 成功: 30 帧 (4 方向边缘热图 + 对手向量叠加) 经 gRPC 摄入 :9090 画布 (app bottlesumo_vision_probe)。
- 探针脚本 `([Action.CREEP_FWD]*5 + [Action.TURN_R_HARD]*1) * 5` 全 4 profile 存活 30+ 帧。
- RULES 214 步基线未受任何扰动 (零规则层候选)。

### 协议装载 (交付物 a)
| 协议 | 签名 | R-I-C-E / 核心 | 状态 |
|------|------|---------------|------|
| EVAI 整合器 | EVAI-INT | Retrieve/Inspect/Configure/Execute + L1-L6 资源索引 | ACTIVE |
| EVAI 动作适配器 | EVAI-V1R | Recognize/Interpret/Command/Execute (TASK-005f 运行时) | ACTIVE |
| EDTA | EDTA-V1 | 四支柱验真 P1/P2/P3/P4 | ACTIVE |
| G3CA | G3CA-ARCH | P-E-R 循环 + 工具优先原则 (v1.1) | ACTIVE |

### 路线图
- `docs/architecture/ROADMAP_v2.md`: 三层架构 (感知/决策/执行) + Phase A/B/C 三阶段集成。
- TASK-006 (视觉-物理融合标定) / TASK-007 (GUI 截图自动调参) RESERVED。


---

## Sprint 12 — meta_config 门裁决验收 (2026-08-07, P2-V4)

### 背景
PM 裁决: `--meta-config` (P2-V4 门裁决) 优先于自蒸馏。Sprint 12 首项: target_priority
轮换 (physics → reward → bridge), 验收标准: 至少 1 轮帕累托改进。

### F-108 (新): meta_config.is_invalid() 缺陷 — 门裁决永不触发
**触发**: `--meta-config --iterations 5` 首轮运行 0 条门裁决 (meta_decisions.jsonl 空)。
**根因**: `is_invalid()` 原判定 `steps > STEPS_BASELINE` (严格大于) → 持平 (score=1.0/214 步)
被判为"有效" → 无效轮次永不计数 → 门裁决 (连续 2 轮无效) 永不触发 → 自指改进空转。
**修复**: `steps >` → `steps >=` (持平/更差 = 无效 = 触发门裁决)。单测 6/6 PASS。
**教训**: 边界判定 (严格大于 vs 大于等于) 在门裁决/终止类逻辑中是功能性差异, 不是风格问题。
**证据**: meta_config.py docstring 更新 + test_meta_config.py 新增持平用例。

### 门裁决轮换轨迹 (修复后 5 轮)
| 轮次 | target_priority | temp | thr | 注入 chars | score | 步数 |
|------|-----------------|------|-----|-----------|-------|------|
| R1 | physics | 0.3 | 0.45 | (首轮无裁决) | 1.0 | 214 |
| R2 | physics | 0.3 | 0.50 | 327 | 1.0 | 214 |
| R3 | physics+reward | 0.2 | 0.55 | 364 | 1.0 | 214 |
| R4 | 全物理层 | 0.1 | 0.60 | 364 | 1.0 | 214 |
| R5 | physics | 0.1 | 0.65 | 364 | 1.0 | 214 |

**结论**: 5 轮均 score=1.0/214 步持平, **无帕累托改进**。候选全部围绕 F-104 grip decay
微调 (grip_decay 0.080→0.082/0.084/0.086 等), 命中规则轨 214 步帕累托终点 — LLM 在既有
特征空间内无法突破。**触发条件满足**: plateau_explorer 自蒸馏评估 (P1-3 服务器实际调用
≥5 轮有效候选 + 连续无改进) → 待 PM 授权。

### F-109 (基线债务, 非 Sprint 12 引入): MuJoCo/lightweight reset 随机序列不一致
**触发**: WSL 全量 pytest (72 passed + 1 failed), `test_edge_obs_matches_lightweight_elementwise`
失败: idx 4 (opp_dist) Mj=0.264 vs Lw=0.137, 差 0.127。
**验证**: `git stash` 干净 HEAD 上重跑该测试 — **同样失败** → 基线既有问题, 与 Sprint 12 无关。
**根因**: 两后端 reset 的随机消费序列不同 —
- lightweight: `[robot_x, robot_y, angle_to_robot, dist, opp_jitter, robot_jitter]`, robot 面向对手;
- mujoco: `[rx, ry, rth, ang, dist, opp_jitter]`, rth 为 0..2π 随机朝向。
第 3 个随机值语义不同 (lightweight=angle_to_robot vs mujoco=rth), 导致 dist 消费错位 → 同 seed 下对手距离不同。
**影响**: 仅 WSL mujoco 侧 1 个测试; Windows 主环境 57/57 零回归 (Sprint 12 变更集未触碰 simulation/)。
**处置**: 记录为治理债务, 排期修复 (mujoco reset 对齐 lightweight 的 robot 面向对手语义) — **PM 裁决 (Sprint 13 签收): 与 F-110 合并为 Sprint 14 "数据质量治理" 统一处理**。


## Sprint 13 — MCP 采纳 (2026-08-07, 方向 A)

### A3 试点场景验收 (COMPLETE)
三场景端到端外部进程调用全部 PASS (HTTP 直连三台独立部署服务器):
1. **scenario1_retrieval_report.py**: semantic_retrieval 检索历史实验报告, 2 查询命中 4 条
   (hypotheses 0.5624/0.5473 + pareto_frontier 0.4934/0.4773)
2. **scenario2_snapshot_audit.py**: environment_bootstrap 快照一致性审计,
   git_head 11e46e0 vs local 11e46e031d50 MATCH, 关键字段完整
3. **scenario3_hypothesis_summary.py**: meta_cognition 假设统计汇总,
   5 条假设记录 (active=0), meta_config_status 返回温度 0.1/阈值 0.65/调整 4 次

### F-110 (新发现, Sprint 13 A3): hypotheses.jsonl 编码乱码 + 字段映射缺失
**触发**: scenario3 中 hypothesis_stats 返回 5 条假设 id="?"/target=""/attempts=0,
hypothesis 文本为乱码 (`?颲寧?璉瘚...`)。
**根因 (两层)**:
- **编码**: hypotheses.jsonl 中中文假设文本为乱码 — Sprint 12 5 轮运行期间 LLM 响应
  以错误编码 (cp950/GBK 误写) 落盘, UTF-8 读取失效。根因疑在 code_agent_proposer 的
  hypothesis 提取/落盘路径 (Windows 侧 print/encoding 默认值)。
- **字段**: hypotheses.jsonl 记录仅有 {ts, variant_id, layer, hypothesis, outcome,
  score, confidence}, 无 id/attempts/target 字段; meta_cognition_server.hypothesis_stats
  聚合时 `h.get("id","?")`/`h.get("attempts",0)` → 展示为占位符。
**影响**: meta_cognition 工具的假设命中率/置信度统计失真 (attempts 恒 0),
影响 A4 使用数据反馈的准确性。
**处置**: ①应急: scenario3 已按列表结构兼容 (PASS); ②根修: 检查
code_agent_proposer.py 的 hypotheses 落盘编码 (统一 UTF-8 + errors="replace");
③字段对齐: hypothesis_stats 从 variant_id 派生 id, 从 score.winrate/steps 派生
attempts/hits (或落盘时补写)。**PM 裁决 (Sprint 13 签收): 与 F-109 合并为
Sprint 14 "数据质量治理" 统一处理; A4 统计期间标注"假设数据质量待修正"免责声明**。


## Sprint 14 — 数据质量治理 (2026-08-05, F-109 + F-110)

### F-109 修复 (RESOLVED): mujoco reset RNG 序列对齐 lightweight
**修复** (`simulation/mujoco_env.py`):
- reset 随机消费顺序改为 lightweight 相同序列: `[rx, ry, angle_to_robot, dist,
  opp_jitter, robot_jitter]`（原 `[rx, ry, rth_random, ang, dist, opp_jitter]`
  第 3 个值语义不同导致 dist 消费错位）。
- robot 面向对手: `rth = atan2(oy - ry, ox - rx) + jitter`（对齐 lightweight
  "robot 面向对手"语义）。
**验证**:
- `test_edge_obs_matches_lightweight_elementwise` **PASS**（原失败, 差 0.127 → 对齐）。
- 关联失败 `test_edge_sensors_are_directional` 因语义变更新失败: robot 面向对手后
  FW_MAX 几步撞对手终止, 60 步内无法到达 rim 制造探头出盘方向性; 且纯旋转无效
  (四探头对称, 旋转仅交换标签, 不产生差异 — 多 seed 扫描证实)。
- **测试修复**: 改为 docstring 允许的 qpos 状态注入路径 — 直接放置 off-center 位姿
  (0.36, 0) 面向 +x rim: front 探头 0.435 > DOHYO_RADIUS 0.40 → 0.0, back 探头
  0.285 < 0.40 → 0.19, 确定性断言 front < back 且四值非全等。**PASS**。
- WSL mujoco 侧全量回归 **73/73 全绿**（含新方向性测试）。
**经验 (可迁移)**: 修复 RNG/状态对齐时, 关联测试若依赖"运动轨迹到达特定状态",
须检查语义变更是否破坏轨迹可达性; 传感器/方向性类测试应优先用状态注入
(teleport) 而非运动驱动, 使测试意图 (传感器响应) 与运动机制解耦。

### F-110 修复 (RESOLVED): hypothesis_stats 按 variant_id 聚合
**修复** (`governance/meta_harness/mcp_servers/meta_cognition_server.py`):
- hypothesis_stats 从逐行输出 (读不存在的 id/attempts/hits → 占位符) 改为按
  variant_id 聚合: id 从 variant_id 派生, attempts=记录数, hits=confirmed 数,
  confidence=hits/attempts。
**验证**: `_verify_f110.py` PASS — ca_rules_01 39 尝试/39 命中, 字段完整。
**编码澄清**: PowerShell `Get-Content` 默认 cp950 解码 UTF-8 文件产生显示乱码
(伪影), Python UTF-8 严格解码验证 hypotheses.jsonl 758 个中文字符全部合法 —
真实缺陷仅为字段映射, 无编码损坏。


## SEED-ROUND-1 (2026-08-05): MCP 监控仪表板失败模式 (FP-FS)

| 模式 | 表现 | 根因 | 对策 (规则) |
| :--- | :--- | :--- | :--- |
| FP-FS-001 数据格式假设 | seed 加载 TypeError: float(dict) | hypotheses `score` 是 dict `{'winrate':..,'steps':..}`、`ts` 为 `YYYYMMDD_HHMMSS` 非 ISO | 先侦察字段再解析 (RULE-FS-001) |
| FP-FS-002 内存库连接隔离 | 多请求看到空表/数据不一致 | SQLite `:memory:` 每连接独立 | StaticPool 共享连接 (RULE-FS-002) |
| FP-FS-003 测试基础设施陷阱 | conftest 导入失败 / sessionmaker.remove() 不存在 | pytest conftest 非模块；sessionmaker 无 remove | fixture 化 + db.close() (RULE-FS-003, TS-002) |
| FP-FS-004 精度截断 | success_rate 断言差 2.3e-05 失败 | round(x,4) 截断 | 6 位小数 + 容差匹配 (RULE-FS-004, TS-003) |

**分类统计**: 4 次失败全部为「实现错误-数据格式假设」(3) 与「测试基础设施」(1)，无规格缺陷
→ 说明 Phase S 规格覆盖良好；TDD 测试先行有效拦截了聚合错误。


## Sprint 15 (2026-08-05): 元认知闭环失败模式 (FP-MC)

| 模式 | 表现 | 根因 | 对策 |
| :--- | :--- | :--- | :--- |
| FP-MC-001 浅拷贝污染 | adapt_params 修改了全局 PARAM_BOUNDS，后续断言 0.8>0.8 恒败 | `dict(PARAM_BOUNDS)` 浅拷贝，嵌套 dict 共享引用 | **deepcopy** 保护全局配置 (类模板) |
| FP-MC-002 浮点精度 | 0.7+0.1=0.7999... 断言失败 | IEEE 754 二进制浮点 | round(x,2) 归一化 |
| FP-MC-003 绑定方法比较歧义 | 三元表达式 `detect is self._detect_latency` 失效 | 绑定方法每次访问生成新对象 | 显式调用三检测器 |
| FP-MC-004 规则编号跳号 | 批次内 3 条规则全为 RULE-MC-001 | `_next_rule_id()` 循环内重复调用，文件未更新前都读到同值 | 批次一次性确定起始编号并递增 |

**分类统计**: 4 次失败全部为「实现错误-语言语义」(浅拷贝/浮点/绑定方法) 与「实现错误-编号生成」，
测试先行拦截了所有集成缺陷；元认知模块本身设计（触发器/阈值/策略映射）无缺陷。

| FP-MC-005 测试落库污染 DECISION_LOG | 运行 test_metacognition_loop.py 后，S16 启动时 load_meta_config() 从 meta_decisions.jsonl 尾部恢复了测试写入的 new_config（target_priority=单 bridge、temp=0.1、thr=0.5），覆盖了新领域配置 | 测试直接调用真实模块（gap_function/meta_config 的 record_decision），DECISION_LOG 指向真实路径，测试产生的 monitoring/gap/learning 记录混入运行状态 | 测试 fixture 将 DECISION_LOG 重定向到 tmp 路径（隔离）；S16 实际以 bridge-only 启动但 P2-V4 门会轮换到 reward-only，两领域均被覆盖 |

**分类统计（Sprint 15 修正）**: FP-MC-001..004 为「实现错误-语言语义/编号生成」；**FP-MC-005 为「测试隔离缺陷」**——测试与运行状态共享持久化文件，属测试基建债务，修复方向为 fixture 隔离，不影响元认知模块设计。

## Sprint 16 (2026-08-05): 元认知闭环迁移 reward/action 层 (FP-MC)

S16 目标：将元认知闭环从已饱和 physics 层迁移至未饱和 reward/action 层（targets=`simulation/reward_functions.py` + `core/meta_language/abdl_action_bridge.py`），验证 Gap Function 在真实缺口上触发 adjust/switch_strategy。以下 7 个失败模式全部出现在 S16 探索启动阶段（7 次重启尝试），均已修复并验证。

| 模式 | 表现 | 根因 | 对策 |
| :--- | :--- | :--- | :--- |
| FP-MC-006 LLM 超时未捕获 | urlopen TimeoutError 直接冒泡致 outer_loop 崩溃；OLLAMA_TIMEOUT_S=480s 对 CPU 推理（size_vram=0）过短 | call_ollama 无异常包装；propose 无降级路径 | LLMTimeoutError 包装 + propose 重试 1 次后返回空候选（本轮跳过，元认知正常记录无效轮）+ 超时 480s→900s |
| FP-MC-007 检索历史主导致领域越界 | targets 已切 reward+bridge，LLM 仍顽固提议 physics——检索注入的 5 条 hyps + hist 候选全为 physics | 历史候选/检索 hits/MCP 上下文在领域迁移时主导 LLM，prompt 无硬约束 | resolve_diff 增加 allowed_targets 白名单参数，越界 diff 直接拒绝 |
| FP-MC-008 resolve_diff 传参 NameError | `targets` 是 build_system_prompt 局部变量，propose 作用域不存在 → NameError 崩溃 | 变量作用域泄漏 | 在 `mc = meta_config or {}` 后定义 `targets = mc.get("target_priority") or [...]` |
| FP-MC-009 build_user_prompt 硬编码 | `keep = ("rules","physics")` 硬编码叠加输出 schema 固定 "rules\|physics"——LLM 根本没看过 reward/bridge 源码，无法产出有效 diff | prompt 模板未随 targets 动态化 | build_user_prompt 按 targets 动态注入领域摘录 + schema 层枚举按 targets 顺序 |
| FP-MC-010 领域迁移三重过滤 | physics 历史候选/hyps/MCP 上下文三者同时主导 LLM 决策 | 上下文污染无过滤层 | hist 候选按 targets 过滤 + 检索 hits 过滤 + MCP 上下文抑制（仅默认目标注入） |
| FP-MC-011 schema 顺序 + 常量锚点 | schema 按 HARNESS_FILES 顺序（mapping 排 reward 前）致 LLM 聚焦难锚定的 bridge；LLM 不理解唯一性（持续输出 dist 类重复 anchor） | 顺序即注意力；无锚点引导 | schema 按 targets 顺序（reward 优先）+ 常量锚点策略提示（EDGE_* 等唯一常量）+ 摘录常量优先 + 重试原因可观测性打印 |
| FP-MC-012 重复 anchor 全替换 | bridge 层 `dist < 0.20` 出现 3 次，expected=1 导致唯一性拒绝死循环（重试 3 次全败，ROUND 整轮作废） | 唯一性校验假设 anchor 全局唯一，但 bridge 3 角色共享逻辑 | expected 自适应：anchor 实际出现 N 次时接受 N 处全替换；提示词声明该行为 |
| FP-MC-013 形态 B 缺对称自适应 | S16 ROUND 4: ca_mapping_001 (bridge) 被拒 "old 匹配 1 次(<期望 3)"——LLM 从重试提示得知 `dist < 0.20` 出现 3 次声明 expected=3，但其生成的 old 是带上下文的完整行（3 处上下文不同）实际仅精确匹配 1 处 → 拒绝 → 重试 3 次全败 → 超时降级，整轮作废 | FP-MC-012 只给形态 A (anchor) 加了自适应，形态 B (old 直接给出) 仍是硬性 `cnt < expected 拒绝` | 形态 B 对称自适应：old 为精确串，磁盘实际匹配 cnt 处就替换 cnt 处，expected 仅作意图参考；保留 cnt==0 拒绝（幻觉防护）。验证：`old="if dist < 0.20:"` 声明 expected=3 实际匹配 2 处 → 接受并自适应 2 |
| FP-MC-014 评估器对 no-op 改动满分 | ca_reward_001 修改 EDGE_DANGER 3.0→2.5、EDGE_WARNING 6.0→2.0 通过评估 (score=1.0/214) 并被接受——但静态分析确认 `self.edge_danger/warning/caution/safe` 仅在构造函数赋值 (56-59 行)，compute_edge_reward 区带边界硬编码 (0.15/0.30/0.50)，**常量从未被消费 → 改动无任何行为影响 (no-op)**，且引入语义倒置 (warning 2.0 < danger 2.5) | ①FP-MC-011 "常量锚点引导"诱导 LLM 修改看起来唯一的 EDGE_* 常量，但未验证常量是否在计算路径被引用；②评估器只测行为指标 (winrate/steps)，对 "修改是否生效" 无感知——score=1.0 是基线水平而非改善 | 候选评估前增加「影响验证」：静态引用图检查被修改符号是否被计算路径读取（参考 grep self.edge_* 仅 4 处赋值）；或差分测试（改动前后同输入输出是否变化）。评估报告需标注 no-op 候选 |
| FP-MC-015 逻辑恒 False 改动通过全链路 | S16 R8: ca_mapping_001 修改 `if dist < 0.20:` → `if dist < dist < 0.15:`——Python 链式比较 `dist < dist` 恒 False → 接触判定分支永不触发 (FW_RIGHT_HARD 永不执行)，实际行为已改变且是 bug。但通过 resolve_diff (字符串匹配通过) + 评估 (10/10 winrate 满分) + 行为验证 (confirmed) | ①LLM 生成语义恒 False 的合法语法；②resolve_diff 只做字符串匹配不做语义检查；③评估器 winrate 在"基线本来就全胜"场景完全失敏——改动前后都是 10/10，无法区分好坏 (与 FP-MC-014 同根: 评估指标无分辨力) | ①评估器需基线对照：改前改后跑同一批种子，winrate/steps 无变化 → 判定无效候选 (同 FP-MC-014 差分测试)；②提示词声明禁止生成含自引用比较 (x < x) 的代码；③resolve_diff 可加简单启发式 (old==new 或含 `x < x` 模式拒绝) |

| FP-MC-016 测试污染运行时审计日志 | S18: run_round 集成测试未 mock `_record_diff_decision`，导致 mock 候选 (mock_0/1/2) 的 diff_gate 记录真实写入 meta_decisions.jsonl（27 条污染） | 测试隔离缺陷：mock 了评估/快照/恢复/apply，却遗漏了"记录副作用"函数——审计日志是共享持久化文件，测试与运行状态耦合（与 FP-MC-005 同根） | fixture 统一 mock `_record_diff_decision`（测试隔离）；清理脚本移除 mock_* 记录；规则沉淀：**凡测试涉及写持久化文件的辅助函数，一律在 fixture 层隔离** |
| FP-MC-017 静态种子模板与工作树脱节 | S19: `_seed_variants` 降级路径用静态历史模板（基于旧 HEAD 970c209），工作树演进后锚点必失效——5 轮 apply 成功率 0%。三类失效实证：A 锚点缺失（`BETWEEN(opponent_angle,-15,15)`/`TIMESTEP*0.8` 当前 0 处）；B 多匹配（`dist<0.20` 3 处但默认 expected=1）；C 死锚点（physics 动量演进到 `TIMESTEP*1.0`） | 生成层与工作树耦合缺陷：模板基于历史文本而非当前磁盘状态，`if "..." in text` 存在性检查 ≠ 恰好匹配 expected 次 | `_seed_variants` 重写为动态适配（`text.count(old)` 感知真实工作树，存在才生成+声明真实 expected，缺失跳过）；`mh_mapping_002` diff 声明 `expected=text.count()`；新增 `apply_precheck` dry-run 预检（锚点计数+作用域白名单+目标存在，失败记录 `apply_precheck_failed` 到 meta_decisions.jsonl）——S19_VERIFY apply 成功率 0%→100% |
| FP-MC-018 恒 False 候选占用评估预算 | S18/S19 验证轮：恒 False 候选（自引用 `dist < dist`、空条件 `if:`、字面量 `if 0:`）能通过 resolve_diff 字符串匹配与 apply_precheck 锚点校验，进入评估后才被差分门禁拦截（SUSPICIOUS/INCONCLUSIVE）——评估预算浪费，且与 FP-MC-015（逻辑恒 False 满分通过）同根 | 字符串匹配无语义检查；恒 False 检测依赖事后差分门禁而非事前静态预检 | Sprint 20 P1 三层防御：共享检测器 `detect_always_false`（自引用比较/空条件/恒 False 字面量三类正则，负向前瞻防 `0.5` 真值误报）→ 生成层 `resolve_diff` 三形态 append 前拦截（带病候选不进 apply）+ 运行时 `apply_precheck` **先于锚点计数**拦截（expected 正确也拒，记录 `apply_precheck_failed`）。验证：meta_harness 48→65 全绿，S20_P2DATA 真实运行零误报（无 apply_precheck_failed），恒 False 前移至 apply 前拦截 |
| FP-MC-019 蒸馏规则未被生成路径消费（闭环断点） | Sprint 21 P2 M1+M3：distill_loop D2 蒸馏出扰动先验（角度≥10°/阈值≥20%/系数≥0.2，依据 10 条 rules 层 INCONCLUSIVE），但真实运行候选源是 `_seed_variants` 种子（模板小幅扰动如 BETWEEN(-10,10)→(-8,8) 仅 2°），不走 LLM prompt——M3 的 `build_system_prompt` 提示与 D2 规则均未覆盖种子路径；S21_M1M3 判定分布与 S19/S20 完全同构（9/9 全拦截，三轮 27 次评估零 PASSED） | 生成层双路径（LLM 提议 vs 模板种子）提示/规则注入不对称：修复只落在 LLM 路径，种子路径扰动幅度由参数模板硬编码决定 | **Sprint 22 M3 扩展已修复**：`SEED_PERTURBATION_THRESHOLDS` + `perturbation_magnitude` + `bump_magnitude` 下沉至 `_seed_variants`（不足则保持方向加大至达标，无法解析则跳过）；S22_SEED 判定分布打破同构——rules 层 INCONCLUSIVE 10/10 → **0**，REGRESSION 首现（winrate 1.00→0.50），meta_harness 99/99 |
| FP-MC-020 扰动过激（语义破坏：abs 阈值误用于 0-1 参数） | Sprint 22 M3 扩展后：rules 层 3/3 候选全部 REGRESSION（winrate 1.00→0.50，steps 433，avg_steps 21.4→43.3）；确定性复现 + 行为指纹定位：失败 episode 中 SIM-HEUR-CAUTIOUS-EDGE 触发 30-46 次（edge-loops） | **Sprint 23 根因修正（快照证明，推翻初始归因）**：并非"10° 阈值过高/不对称窗"——`bump_magnitude` 将层默认 abs 阈值（10°/8°）应用到 0-1 归一化参数 `edge_proximity`（0.80 → 0.80-8.0 = **-7.20**）→ 恒 True 条件 → 无条件转向 → edge-loops → winrate 0.50；D2 先验表阈值缺参数级语义（abs vs rel 混用） | **Sprint 23 已修复（D2 校准）**：①参数级扰动配置 `_SEED_PARAMS[param]["perturb"]`（每个参数声明正确的 mode/threshold/unit/kind）；②符号安全网（正值不得 bump 为负值，破坏恒 True 语义的 bump 拒绝）；③修复 bump 内部验证未传 cfg 的 bug（rel 误用 abs 阈值）；④BETWEEN 对称双侧处理保持 ± 对称。验证：S23_RECAL2 REGRESSION 严重度 0.50→0.90（1.00→0.90），edge_proximity 正确 bump 至 0.64（域内），meta_harness 101/101 |

**分类统计（Sprint 23 修正）**: FP-MC-006 为「容错缺失」、FP-MC-007/009/010/011 为「上下文/提示工程」、FP-MC-008 为「作用域缺陷」、FP-MC-012 为「假设过强」、**FP-MC-013 为「修复不完整/分支不对称」**、**FP-MC-014 为「评估盲区/虚假正信号」**、**FP-MC-015 为「评估失敏/逻辑损坏漏检」**、**FP-MC-016 为「测试隔离缺陷/审计日志污染」**、**FP-MC-017 为「生成层与工作树脱节/静态锚点失效」**、**FP-MC-018 为「语义检查缺失/恒 False 候选后置拦截」**、**FP-MC-019 为「蒸馏闭环断点/生成双路径注入不对称」**、**FP-MC-020 为「参数语义混用/abs 阈值误用于 0-1 参数（符号破坏）」（Sprint 23 根因修正：非阈值回标缺失，而是扰动配置缺参数级语义——修复为参数级 perturb + 符号安全网）**。S17 差分测试框架已验证三态判定（INCONCLUSIVE/SUSPICIOUS/PASSED-REGRESSION）；S18 差分门禁已集成 outer_loop（Pareto 保留前强制质量门）：候选 diff 应用后自动 baseline→diff→verdict，REGRESSION 拒收 / SUSPICIOUS 转人工（meta_decisions.jsonl）/ INCONCLUSIVE 不入 Pareto，仅 PASSED 进入保留流程——FP-MC-014/015 的「无操作满分」「逻辑损坏满分」漏洞已在保留链路上封死；S19 候选生成动态适配工作树（apply 成功率 0%→100%），FP-MC-017 的「静态锚点失效」在生成源头消除，配合 `apply_precheck` dry-run 预检（`apply_precheck_failed` 可追溯）形成生成侧第二道防线；S20 P1 恒 False 检测（自引用比较/空条件/恒 False 字面量）形成第三道防线——生成层 `resolve_diff` 三形态拦截 + 运行时 `apply_precheck` 先于锚点计数拦截，FP-MC-018 的「恒 False 候选后置拦截」前移至 apply 前（评估预算零浪费），P2 蒸馏数据收集（S20_P2DATA）9/9 全拦截无 PASSED 触发自蒸馏设计；S21 P2 M1+M3（distill_loop 数据管道 + 扰动先验）已实现，M1 蒸馏实证层×判定强相关（rules→INCONCLUSIVE 10/10 扰动不足、mapping/physics→SUSPICIOUS 18/18 全饱和失敏）；S22 M3 扩展（`_seed_variants` 扰动幅度校验：SEED_PERTURBATION_THRESHOLDS + perturbation_magnitude + bump_magnitude，与 D2_PRIOR 同源）——FP-MC-019 闭环断点修复：S22_SEED 判定分布打破同构（rules 层 INCONCLUSIVE 10/10→0，REGRESSION 首现 winrate 1.00→0.50 被门禁正确拒收）；S23 D2 校准（FP-MC-020 根因修正）：参数级扰动配置（abs/rel 按参数语义声明）+ 符号安全网（0-1 参数不落负值）+ bump cfg 传参修复 + BETWEEN 对称双侧——S23_RECAL2 REGRESSION 严重度 0.50→0.90（winrate 1.00→0.90，edge_proximity 域内 0.64），meta_harness 101/101，rules 层阈值重标定至 8-12° 安全区间；mapping/physics 饱和失敏（累计 24 条 SUSPICIOUS）为 M2 评估层重构的决策依据（Sprint 24 候选，待 PM 裁决）。

**运维规则沉淀**: 修改 proposer 代码后必须确认无旧进程存活再重启——第 6 次运行进程在 FP-MC-012 落盘前（00:16）启动，ROUND 3 仍在用旧唯一性逻辑（期望 1），修复未生效即失败。代码修复与进程生命周期必须同步。
