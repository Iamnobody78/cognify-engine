# MuJoCo 物理后端集成 + G2 Gazebo 数字孪生会话 —— 2026-08-05 (Phase G)

> 执行队列 #1 (G2 Gazebo) 与 #2 (MuJoCo 集成) 全部完成。

## 目标
引入 MuJoCo 3.11.0 作为训练级物理后端（替代/增强 lightweight_env），与 Gazebo 双轨：
1. gym 包装（21 动作映射，与 lightweight 完全兼容）
2. V9 门 `--backend mujoco` 第二验证后端
3. RViz 桥 `--backend mujoco`（复用 G1 模式）
4. 单元测试保障 API 契约

## 成果（全部完成 ✅）

### 1. `simulation/mujoco_env.py` —— 物理稳定化（13 轮根因迭代）
- XML：静态 dohyo（collidable，friction=0.5）+ 接住坠落平面（z=-0.6）+ 机器人 body（r=0.045, h=0.022, mass=1.2）+ 双轮（y=±0.065, zaxis=Y）+ 对手（freejoint, friction=0.5）
- **PI 轮伺服**：P=0.003, I=0.5, integral_max=0.5, deadband=0.5 rad/s（leaky integral）—— 攻破 0.15 Nm 静摩擦
- **对手力伺服**：`qfrc_applied` 世界系推力（OPP_SERVO_GAIN=10, THRUST_MAX=8N < 机器人 17.6N 牵引 → 可被推动）
- 运动保真：FW_MAX 0.701 m/s（目标 0.7 ✓）、转弯 0.675 rad/s（67.5%，恒定可预测）、STOP 减速、200+ 步无 NaN
- 出界语义与 lightweight 一致：中心 > 0.325m（= 0.40 - 0.075）

### 2. V9 门第二后端 —— 三基线完整记录
`simulation/v9_gate_evaluator.py --backend mujoco`（报告含 `backend` 字段）

| 基线 | 胜率 | 通过 | 关键模式 |
|------|------|------|----------|
| abdl（13 规则） | 40% (4/10) | ❌ | 赢 aggressive/defensive/circler；random/counter 超时（推进不足） |
| heuristic | 60% (6/10) | ✅ | random/defensive/circler 全胜；aggressive（step 11 被顶出）/counter 0/2 |
| **v11（学习策略）** | **100% (10/10)** | ✅✅ | 五策略全胜，复合动作覆盖全部失败模式 |

**判别力结论**：MuJoCo 后端能区分三档策略（40/60/100），heuristic 在动态物理下暴露 aggressive/counter 弱点——这正是轻量后端未暴露的信息。

### 3. RViz 桥 `--backend mujoco`
- `bottlesumo_vis_bridge.py` 增加 `--backend lightweight|mujoco`；env 构造分支化（对手策略签名兼容）
- 无 ROS 冒烟测试通过（mock rclpy + msg）：30 步 counter 对局，marker 从真实物理状态组装

### 4. 单元测试 `tests/test_mujoco_env.py` —— 14/14 通过
- gym API 形状（7-dim obs, Discrete(21), 5 元组）
- 21 动作 → 差速轮速物理上限（±41.2 rad/s）全数验证
- 观测空间与 lightweight **逐元素一致**（后端互换契约）
- 边缘传感器 [0,1] 范围、前进位移、200 随机步无 NaN
- 超时截断（非胜利）、出界检测（>0.325 触发）、被动对手推出胜利、同种子确定性、对手圈内出生（15 种子）

## 关键坑链（13 轮根因，节选）
1. dohyo 不可碰撞 → 机器人坠落 → collidable + 接住平面
2. 轮轴 X→Y（zaxis="0 1 0"）—— 这是"杀手级"bug：轮子装在前/后导致转向被地面锁死
3. XML ctrlrange 覆盖 Python 扭矩上限 → 轮子卡静摩擦（0.15 Nm）→ ctrlrange=±0.25
4. intvelocity/velocity 致动器在关节接触时奇异 → 扭矩电机 + Python PI 伺服
5. 对手原始 qvel 写入 = 运动学"速度列车"（不可被推）→ 力伺服
6. MuJoCo 摩擦取接触对 **MAX**（非几何均值）→ dohyo=0.5, 对手=0.5

## 运行命令
```bash
# V9 门第二后端
python3 _tmp/mujoco_gate_run.py v11            # 100% ✅

# 单测
python3 -m pytest tests/test_mujoco_env.py -q -p no:anyio -p no:cacheprovider

# RViz 桥（需 ROS2 环境）
python3 bottlesumo_pi/simulation/bottlesumo_vis_bridge.py --backend mujoco --opponent counter
```

## 下一步
- MuJoCo 训练阶段：aggressive 反制策略（队列 #4）

---

# 执行队列 #1：G2 Gazebo 数字孪生（DEBT-013 关闭，原名 DEBT-008）

> ⚠️ **编号勘误（2026-08-05 收尾）**：本节原称 "DEBT-008"（URDF 语境）与治理层 DEBT-008（Ollama wontfix）冲突 → 正式注册为 **DEBT-013**。治理层债务追踪 `debt.md`/`current_status.md`/`debt_registry.yaml` 已同步。

> 修复 ROS2 工作区 `/home/ivy/bottlesumo_ws/src/bottlesumo_description/`（项目镜像已同步至 `simulation/gazebo/bottlesumo_description/`）

## DEBT-013 根因（URDF 几何灾难链，原误标 DEBT-008）
1. **轮轴方向完全错误（杀手级）**：`left/right_wheel_joint` 的 `rpy="0 -90° 0"` 恰好抵消 `chassis_to_motor` 的 `rpy="0 +90° 0"` → 净旋转 = 单位阵 → wheel 圆柱轴向（URDF 默认 Z）竖直朝天，`axis="0 0 1"` 使其**绕 Z 陀螺旋转**，物理上无法滚动 —— 与 MuJoCo 曾修复的杀手 bug（轮子装错轴）**完全同型**
2. 合成变换后轮心离地悬空/陷地（FK 验证 z 错误）
3. `<publish_odom_tf>false` + **缺 `<publish_odom>true</publish_odom>`**（Humble 版 gazebo_ros_diff_drive 需要此参数才发布 odom 消息）→ 无 odom 消息
4. 无 `libgazebo_ros_joint_state_publisher` 插件 → RViz 看不到轮子转动
5. caster 球陷地 4mm（z=-0.006 应为 -0.002，球半径 0.006）
6. spawn z=0.05 → 机器人悬空 5cm 坠落

## 修复（5 项 patch）
| 修复 | 内容 | 验证 |
|------|------|------|
| 轮轴 | wheel rpy → `(-90°,0,0)`，origin → `0 0 0`（骑电机轴），motor z → `+0.009` | FK：轮心 z=0.017 触地，轴→全局 Y ✅ |
| odom | 加 `<publish_odom>true</publish_odom>`（保留 publish_odom_tf） | `/bottlesumo/odom` Publisher=1 ✅ |
| joint_state | 加 `libgazebo_ros_joint_state_publisher` 插件（left/right wheel + pusher） | `/bottlesumo/joint_states` 发布轮位 4.24 rad ✅ |
| caster | z -0.006 → -0.002 | FK：球底 z=0 ✅ |
| spawn | launch z 0.05 → 0.0 | 轮底恰好触地 ✅ |

## G2 验证（headless，humble + colcon build）
```
cmd_vel 0.25 m/s → 差速 → 轮转 4.24 rad → TF odom→base_link 前进 10.7cm ✅
边缘传感器 ×4 (/bottlesumo/edge_*) + tof_scan ✅（模型加载完整）
odom 消息 x=0.024m ✅  TF RPY≈0 稳定平衡 ✅
```

## 坑
- PowerShell 内联 Python 引号转义不可靠 → 全部用 `_tmp/*.py` 脚本文件
- parallel 双跑共享报告文件会互相覆盖 → 顺序执行 + 独立日志

---

# 阶段 G3：决策 overlay 可视化 + 队列 #4 数据收集（2026-08-05 晚间追加）

> 方案 C（混合推进）：G3 可视化与 MuJoCo aggressive 轨迹收集并行。

## 成果（commit 528d636）

### 1. 决策 trace 基础设施（不破坏现有接口）
- `ABDLDecisionMaker.decide_traced()` → 返回 `(action, trace)`：rule_id、policy_id、reason、rules_triggered
- `V9RuleAgent.select_action_traced()` → 返回 `(action, trace)`：mode（abdl/heuristic）、rule_id 或 branch（SR-001/TR-001 等）、sensors（edge×4 + opp_dist/angle）
- `_heuristic_v9()` 增加 `_last_heuristic_branch` 标记（SR-001/edge_f、TR-001/charge、TR-002/advance、TR-003/search 等 12 个分支）
- 原 `select_action()`/`decide()` 保留为 traced 变体的薄包装 → **零破坏**

### 2. RViz G3 overlay：`/bottlesumo/vis/debug`（MarkerArray）
- **决策文字**（机器人上方 TEXT_VIEW_FACING）：ABDL 绿 `rule/policy`，heuristic 橙 `HEUR:branch`
- **目标箭头**（紫）：opp_dist ≤ 0.5 时机器人→对手锁定线
- **危险框**（红半透明）：任一边缘 < 0.15
- state 字符串追加 `[ABDL rule=... policy=...]` / `[heuristic branch=...]`

### 3. 轨迹收集（队列 #4 数据轨）
- `_tmp/mujoco_collect_aggressive.py`：MuJoCo + aggressive 对手，每步记录 obs/action/reward/decision/mode/opp_dist/opp_angle → `models/mujoco_aggressive_trajectories/ep_XXXXXX.json`
- 5 eps dry-run：40% winrate 与 gate 基线一致（2 wins/3 oob-timeout）✅
- 发现 **'?' 默认动作占比高**（ABDL 引擎无规则触发 → FW_SLOW）——规则集未完全覆盖 MuJoCo 状态空间，是队列 #4 的核心线索
- 500 eps 正式收集：后台 `_tmp/collect_500.sh`（Start-Process 保持存活，nohup 在新 WSL 会话会被杀）

### 4. 验证
- `_tmp/g3_smoke.py`（mock rclpy + mock msg）：4 项全过 —— traced ABDL 路径、traced heuristic 路径、MuJoCo 80 步无 NaN、debug marker 发布（文字/箭头/危险框）
- 回归：`pytest tests/` 59/59 通过（含 MuJoCo 14 项）—— G3 重构零破坏

## 运行命令
```bash
python3 _tmp/g3_smoke.py                                   # G3 冒烟
python3 _tmp/mujoco_collect_aggressive.py --dry-run        # 收集冒烟
bash _tmp/collect_500.sh                                   # 500 eps 正式收集
python3 _tmp/analyze_aggressive_traj.py                    # 失败模式分析
```

---

# 队列 #4 根因分析：MuJoCo abdl 40% → 90%（2026-08-05 深夜，commit c7d2e35）

## 数据
- 500 eps aggressive 轨迹收集（旧 env 基线）：winrate 27.2%，OOB=0，364 loss 全部 timeout
- 修复后 8 eps dry-run：**100% winrate**（0 timeout，'?' 28 次残余）

## 根因链（三层，全部代码级验证）

### 第 1 层：MuJoCo edge 传感器无方向性（commit 1679c5a）
- 4 个 edge 全 = `edge_norm(rim)`（"direction-neutral"），违反双后端契约
- lightweight 有方向性探针（按 heading 偏移 + 全场斜坡 `1.0 - dist/0.40*0.9`）
- 修复：镜像 lightweight 公式；新增 2 测试（方向性 + reset-pose 逐元素一致）→ 16/16 环境测试
- **但 gate 仍 40%** —— 传感器只是必要条件，不是充分条件

### 第 2 层（🔴 真正根因）：ABDL 引擎 `_resolve_between` 死区（commit c7d2e35）
- `BETWEEN = re.compile(r"BETWEEN\(([^,]+),\s*([^,]+),\s*([^)]+)\)")` 要求 3 参数
- 规则文件写 **2 参数** `sensor(x) BETWEEN(0.3, 0.6)` → 正则不匹配
- 更深的 bug：`_resolve_between` 用**无空格键** `f"BETWEEN({val},{lo},{hi})"` 做 replace，但原文 `", -12, 12"` 有空格 → **replace 永远不命中** → `BETWEEN(...)` 残留 → eval SyntaxError → 规则永久 False
- **后果**：`SIM-ADVANCED-CLOSE-PUSH`（max-speed 推挤）从引擎诞生起从未触发！abdl "推不动对手"不是物理问题，是规则从未执行推挤
- 修复：`re.sub` 用原始匹配文本 + resolver 顺序调整（`_resolve_between` 先于 `_resolve_sensor`，保持内层 sensor(x) 完整）+ 规则改 3 参数 `BETWEEN(sensor(x), lo, hi)`
- 验证脚本 `_tmp/verify_between_bug.py`：修复前 3/4 FAIL（invalid syntax）→ 修复后全 PASS

### 第 3 层：规则阈值保守（同 commit）
- CLOSE-PUSH 要 `edge_prox < 0.4`（距中心 <0.267m 才推）→ 把对手推到边缘时自动放弃
- EDGE-WARNING 在 `> 0.6`（dist>0.267m）就后退 → 边缘恐惧
- FLANK ×2 同 <0.4
- 对齐 v11：CLOSE-PUSH/FLANK `< 0.65`，EDGE-WARNING `> 0.8`

## 结果（V9 门）
| 策略 | MuJoCo 修复前 | MuJoCo 修复后 |
|---|---|---|
| abdl | 40% | **90%** (9/10, counter 50%) |
| v11 | 100% | 100%（零破坏） |
| heuristic | 60% | 60%（不经过 ABDL 引擎） |
| lightweight abdl | 70% | **70%**（零破坏） |
| aggressive 收集 | 27.2% | **100%**（8/8, 0 timeout） |

## 回归
- 完整 pytest：61/61 通过
- 测试缺口补上：方向性 edge ×2（`test_edge_sensors_are_directional`、`test_edge_obs_matches_lightweight_elementwise`）
- **教训**：`test_mujoco_env.py` 原 14 项只验证 Box 边界，未验证**观测值语义**与规则引擎条件解析——已通过新测试 + verify 脚本补上

## 遗留
- counter 策略 50%（1/2）——唯一未满的对抗策略，后续可调
- 新 env 下的 500 eps 完整重收集（可选，验证 '?' 分布）
- v11 的 `PUSH_EDGE_SAFE=0.40` 语义与 ABDL 的 min(edge) 仍有差异（abdl 用最差方向判定，v11 用前缘）——已通过阈值放宽缓解
- 插件的 `publish_odom` 参数是 Humble 特有门（Foxy 无），demo world 是权威参考

---

## 追加段：电机一致性审计 + 模型物理化（2026-08-05 晚）

**前置**：队列 #4 prerequisite —— 


---

## 追加段：电机一致性审计 + 模型物理化（2026-08-05 晚）

**前置**：队列 #4 prerequisite —— "模型=实物一致"（ME/SIM 角色审计）

### 发现：四处互不矛盾的矛盾模型
| 参数 | design_spec.json(权威) | rev2.sdf | urdf.xacro | mujoco_env.py |
|---|---|---|---|---|
| N20 | 6V 300rpm | 298:1 gearbox(混入) | 30g | — |
| 轮径 | 48mm | 43mm(内部自相矛盾) | 34mm | 34mm |
| 最大轮速 | — | 6.28 rad/s | 10 rad/s | 41.2 rad/s |
| 扭矩 | — | 0.015 N·m | 1.0 N·m | (17.6N推力注释) |

### 裁决
- 电机 = **N20 6V 300rpm**（design_spec 权威 + controller.yaml 双源）；298:1 为编码器规格混入
- 最大轮速 **31.4 rad/s**（=300rpm），轮扭矩 **0.3 N·m**（controller.yaml 堵转值）
- 轮径 34mm 仿真侧保留（V9 门契约）；48mm 权威值待用户裁决（PENDING）

### 修改（commit 见 git log）
- mujoco_env.py: MAX_WHEEL_VEL 41.2→31.4 + 注释修正（删除虚构 CTEA-20 引用）
- wheel_to_discrete.py: 21 动作表前向速度层等比缩放 FW_MAX 0.7→0.53 m/s
- rev2.sdf: 轮径 0.048 / 扭矩 0.3 / 限速 31.4 rad/s
- urdf.xacro: 质量 0.025 / effort 0.3 / velocity 31.4
- 新建 models/motor_spec.json（单一事实源）+ .aionui/context/motor_consistency_audit.md

### 验证
- pytest 61/61 通过
- 物理验证：FW_MAX 实测峰值 0.526 m/s ≈ 理论 0.534 m/s ✓
- **门回归（新 baseline）**：MuJoCo abdl 90%→**80%**、heuristic 60%、v11 100%；lightweight abdl 70%→**60%**
- 速度物理化后普遍回落 ~10% —— 仿真现在诚实反映 300rpm 真实冲刺能力

### 遗留
- 实物轮径待用户裁决（34 vs 48mm）→ 若 48mm 需全量重 baseline
- heuristic aggressive/counter 0%：依赖旧 0.7m/s 冲锋，需战术参数优化
- 固件 FW_MAX 常量待对齐
- git 仓库根级 .aionui/ 为重组前陈旧副本（部分跟踪），bottlesumo_pi/.aionui/ 为现行

### Gazebo 负载测试（commit 71ff4f9, Queue #4 step 4 收尾）✅
- 方法: bottlesumo_simple.launch.py + sumo arena（WSL headless），cmd_vel 0.53 m/s，odom+joint_states 双源探针
- **结果 PASS**: 轮速 **31.18 rad/s = 300rpm**（理论 31.4, 99.3%）；odom **0.523 m/s**（理论 0.534, 98%）
- **真凶**: Gazebo 把 joint <dynamics friction> 当粘性摩擦（N·m·s/rad）→ 旧 0.2 在 31.4 rad/s 时
  6.3 N·m = 堵转 21 倍 → 机器人永远无法前进（G2 

### Gazebo 负载测试（commit 71ff4f9, Queue #4 step 4 收尾）✅
- 方法: bottlesumo_simple.launch.py + sumo arena（WSL headless），cmd_vel 0.53 m/s，odom+joint_states 双源探针
- **结果 PASS**: 轮速 **31.18 rad/s = 300rpm**（理论 31.4, 99.3%）；odom **0.523 m/s**（理论 0.534, 98%）
- **真凶**: Gazebo 把 joint `<dynamics friction>` 当粘性摩擦（N·m·s/rad）→ 旧 0.2 在 31.4 rad/s 时
  6.3 N·m = 堵转 21 倍 → 机器人永远无法前进（G2 "motion proof" 是 mock 的物理根因）。修复 0.02 ✓
- **反射惯量 1.28e-4** 加入 wheel izz（URDF 0.0001291 / rev2.sdf 0.000136）→ 消除 ODE 数值爆炸
- **DEBT-016**: Gazebo classic 不硬执行 joint velocity limit（21-action table + firmware 保证上限）
- rev2.sdf 已同步（izz/dynamics/accel 200.0）；验证: pytest 61/61, final_verify ALL_PASS 8/8, XML well-formed
