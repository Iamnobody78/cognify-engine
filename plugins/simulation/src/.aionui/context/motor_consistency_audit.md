# 电机一致性审计报告 (Motor Consistency Audit)

> 日期: 2026-08-05 | 状态: 进行中（参数统一已提交，实物测量待用户）
> 触发: 队列 #4 前置验证 —— "模型=实物一致原则"（物理规律验证 + 模型可追溯至 Datasheet）
> 审计人: 治理智能体（ME/SIM 角色）

## 1. 审计结论（TL;DR）

**电机型号: N20 微型金属减速电机，6V，输出空载转速 300 rpm（减速比约 1:40 级）**

证据: `models/cad/design_spec.json`（权威设计文档 v2.0）+ WSL 侧部署配置
`src/bottlesumo_description/config/controller.yaml` 两处**独立**引用 300rpm，数学自洽
（300rpm × π × 0.034m = 0.534 m/s ✓）。

其余互相矛盾的参数均找到来源与判定，详见 §3-§4。

## 2. 四处互不矛盾的矛盾模型（审计前状态）

| # | 文件 | 电机 | 轮径 | 最大轮速 | 轮扭矩 | 判定 |
|---|------|------|------|----------|--------|------|
| 1 | `models/cad/design_spec.json` v2.0 (2026-07-27) | N20 6V **300rpm** | **48mm** | — | — | ✅ **权威** |
| 2 | `simulation/gazebo/bottlesumo_rev2.sdf` (2026-07-29, 生成) | N20 **298:1 gearbox** + 48CPR | collision 48mm, diff_drive **43mm** | joint limit 6.28 rad/s (60rpm) | diff_drive **0.015 N·m**, effort 10 | ❌ 内部自相矛盾 + 与权威冲突 |
| 3 | `simulation/gazebo/bottlesumo_description/bottlesumo.urdf.xacro` (Rev1) | N20（质量 30g） | **34mm** | 10 rad/s (95rpm) | effort 0.5, max_wheel_torque **1.0** | ❌ 轮速/扭矩偏离 4~66 倍 |
| 4 | `simulation/mujoco_env.py` | — | **34mm** (r=0.017) | **41.2 rad/s** (393rpm) | — | ❌ 轮速 +31% |
| 5 | WSL `src/.../controller.yaml` (部署侧) | N20 6V **300rpm** | **34mm** | max 0.8 m/s | **~0.3 N·m** 堵转 | ⚠️ 电机✅ 轮径=Rev1 |
| 6 | `simulation/tcs_validator.py` | — | **20mm** (r=0.02) | — | MAX_MOTOR_TORQUE **0.015 N·m** | ❌ 第三处轮径 + 扭矩过小 |
| 7 | `architecture_overview.md` L429 | N20 **200rpm ×4** + DRV8833 | — | — | — | ❌ 旧 Rev1 大底盘架构遗留 |

## 3. 物理裁决推理

### 3.1 电机转速: 300rpm 胜出（298:1 是编码器规格混入）
- `rev2.sdf` 声称 "48 CPR × N20 298:1 gearbox ≈ 14,304 ticks/rev" —— 这是 Pololu 系
  N20 **298:1 减速版**（输出仅 ~30-40rpm @6V）的编码器计数规格，被生成器误抄进模型。
- 物理矛盾: 若减速比 298:1，输出 30-40rpm × 轮径 0.043m = **0.09 m/s**，无法胜任相扑
  竞技（同文件内还自写 "48mm dia" 轮，但 diff_drive 用 43mm）。
- `design_spec.json`（权威）+ `controller.yaml`（部署）双源独立支持 **300rpm 输出**。
- `architecture_overview.md` 的 200rpm×4/DRV8833/250×250mm 为旧架构描述，与 Rev2
  （180×220mm, N20×2, TB6612FNG）不兼容 → 归档引用，不改模型。

### 3.2 轮径三处冲突: 48mm(权威) vs 43mm(SDF内部) vs 34mm(实现) vs 20mm(tcs)
- `design_spec.json` 权威: **48mm** (Rev2 设计)。
- 34mm 出现在 urdf.xacro / mujoco_env.py / controller.yaml —— 三者一致的 Rev1 仿真几何。
- mujoco_env.py 注释 "matches CTEA-20: wheel radius 0.017m, separation 0.13m" 引用的
  **CTEA-20 文档在仓库内不存在**（虚构引用，诚实边界记录）→ 注释已改为引用 design_spec。
- ⚠️ **待用户裁决**: 仿真/训练侧保持 34mm（不推翻 V9 门 21 动作契约与已训练策略），
  物理权威 48mm。切换开关见 `models/motor_spec.json`。若实物确为 48mm，需全量
  重新 baseline V9 门（轮径直接驱动速度上限）。

### 3.3 最大轮速: 41.2 → 31.4 rad/s（=300rpm）
- 物理: 300rpm = 300/60 × 2π = **31.4 rad/s**。
- MuJoCo 41.2 rad/s ≈ 393rpm 无物理来源（注释 "matches FW_MAX" 为循环引用）。
- 34mm 轮下: 31.4 × 0.017 = **0.53 m/s**（与 controller.yaml "300RPM → 0.53 m/s" 一致）。

### 3.4 轮扭矩: 统一 0.3 N·m（堵转）
- `controller.yaml`: "N20 减速电机扭矩: ~0.3 N·m (堵转)"（部署侧实测预估）。
- `rev2.sdf` 0.015 N·m 与 `tcs_validator.py` MAX_MOTOR_TORQUE 0.015 同源过小
  （0.015 N·m / 0.017m = 0.88N 单轮推力，连自重加速都困难）。
- `urdf.xacro` 1.0 N·m 过大（1.0 / 0.017 = 59N 单轮推力，不物理）。
- 0.3 N·m / 0.017m ≈ **17.6N 单轮推力**，符合 0.607kg 级相扑机器人推挤需求。

### 3.5 电机质量: 0.030 → 0.025 kg
- `design_spec.json` 权威: motor_each 0.025kg。urdf.xacro 0.030 无来源。

## 4. 已实施修改（本审计提交）

| 文件 | 修改 |
|------|------|
| `simulation/mujoco_env.py` | `MAX_WHEEL_VEL` 41.2 → **31.4** rad/s（300rpm），注释改引 design_spec.json |
| `tests/test_mujoco_env.py` | 硬编码 41.2 断言 → 引用 `MAX_WHEEL_VEL` 常量 |
| `simulation/wheel_to_discrete.py` | 21 动作表前向速度层等比缩放至物理极限: FW_MAX (0.7,0)→**(0.53,0)** m/s；CREEP 0.08 / SLOW 0.15 / MED 0.27 / FAST 0.38 / 组合动作同步缩放（角速度层不动） |
| `simulation/gazebo/bottlesumo_rev2.sdf` | diff_drive: wheel_diameter 0.043→**0.048**, wheel_radius 0.0215→**0.024**, max_wheel_torque 0.015→**0.3**; joint limit velocity 6.28→**31.4**, effort 10→**0.3**（×2）; 头部注释 298:1 → 300rpm |
| `simulation/gazebo/bottlesumo_description/bottlesumo.urdf.xacro` | mass_motor 0.030→**0.025**; joint limit effort 0.5→**0.3**, velocity 10.0→**31.4**（×2）; diff_drive max_wheel_torque 1.0→**0.3** |
| `models/motor_spec.json` | 新建: 机器可读单一事实源（本表 §5） |

## 5. 统一后的电机规格（单一事实源 → models/motor_spec.json）

```json
{
  "motor": {
    "type": "N20_micro_gearmotor",
    "voltage_v": 6.0,
    "no_load_output_rpm": 300,
    "max_wheel_vel_rad_s": 31.4,
    "stall_torque_nm": 0.3,
    "mass_kg": 0.025,
    "count": 2,
    "driver": "TB6612FNG",
    "source": "models/cad/design_spec.json + WSL controller.yaml"
  },
  "wheel": {
    "diameter_mm_authoritative": 48,
    "diameter_mm_sim_rev1": 34,
    "conflict": "PENDING_USER_ADJUDICATION"
  }
}
```

## 6. 诚实边界声明

- **无实物测量**: 本次审计基于项目内文档交叉验证 + 行业通用 N20 300rpm 类规格推理；
  堵转扭矩 0.3 N·m 来自部署侧 controller.yaml（未见实测记录）。如需 Datasheet 级确认，
  需用户提供实物电机型号/采购链接或测量数据。
- **CTEA-20 引用不实**: mujoco_env.py 原注释引用的 CTEA-20 文档不存在于仓库。
- **仿真轮径未切换**: 34mm（Rev1 仿真几何）保持不变，避免破坏 V9 门契约；48mm（Rev2
  权威）切换需用户裁决 + 全量重新 baseline。

## 7. 后续动作

- [ ] 用户确认实物电机型号/轮径 → 更新 motor_spec.json → 全量重新 baseline V9 门
- [x] Gazebo 负载测试（rev2.sdf, 300rpm 模型）—— 见会话日志附段
- [x] MuJoCo 门回归（MAX_WHEEL_VEL 变化后的 baseline 快照）
- [ ] 与固件 FW_MAX 对齐（firmware 侧常量待核对）

## 8. 门回归快照（2026-08-05, 模型物理化后）

物理验证: FW_MAX 实测峰值 0.526 m/s ≈ 理论 0.534 m/s（300rpm × 0.017m）✓

| Backend | Agent | 旧 baseline | 新 baseline | 备注 |
|---------|-------|-------------|-------------|------|
| MuJoCo | abdl | 90% | **80%** (8/10) | PASS; circler/counter 各 50% |
| MuJoCo | heuristic | 60% | **60%** (6/10) | 压线; aggressive/counter 0% — 依赖旧 0.7m/s 冲锋 |
| MuJoCo | v11 | 100% | **100%** (10/10) | 全策略 100%，不变量 |
| lightweight | abdl | 70% | **60%** (6/10) | 压线; aggressive 0% |

速度上限物理化（0.7→0.53 m/s）后各 agent 普遍回落 10% 左右，符合预期——仿真现在
"诚实" 反映 300rpm N20 的真实冲刺能力。下一步优化杠杆: 针对 circler/counter/aggressive
的战术参数（CLOSE-PUSH 触发距离、转向增益），或动作表新增高角速度快转档。

## 9. Gazebo 负载测试结果（2026-08-05, step 4 完成）

### 9.1 结果: PASS ✅

| 指标 | 理论值 | 实测值 | 偏差 |
|------|--------|--------|------|
| 轮速（PHASE1, cmd=0.53 m/s） | 31.4 rad/s (300rpm) | **31.18 rad/s** | 99.3% |
| 前进速度（odom） | 0.534 m/s | **0.523 m/s** | 98% |
| 控制环稳定性 | — | 稳定（无数值爆炸） | ✓ |

### 9.2 真凶修复: 关节摩擦 0.2 → 0.02

- Gazebo classic 把 `<dynamics friction>` 解释为**粘性摩擦**系数（N·m·s/rad）。
- 旧值 0.2 → 31.4 rad/s 时阻力扭矩 6.3 N·m = 电机堵转上限 0.3 N·m 的 **21 倍**
  → 机器人永远无法前进（这就是 G2 时代 Gazebo "motion proof" 是 mock 的物理根因）。
- 修复后 `damping=0.001, friction=0.02` → 实测 31.18 rad/s = 300rpm ✓
  （此前所谓 "G2 motion proof" 从未真正通过物理测试。）

### 9.3 反射惯量稳定控制环

- N20 gearmotor 反射惯量: J_rotor ~1e-7 × gear_ratio² 40² × η 0.8 = **1.28e-4 kg·m²**
- 主导 wheel link 自身惯量 ~1.2e-6 约 100 倍 → 消除 ODE 数值爆炸（此前 1.7e47 rad/s）。
- 已同步到 `bottlesumo.urdf.xacro`（izz=0.0001291）与 `bottlesumo_rev2.sdf`（izz=0.000136,
  48mm 轮径下 8e-6 + 1.28e-4），max_wheel_acceleration 2.0→200.0 对齐。

### 9.4 DEBT-016: Gazebo classic 不硬执行 joint velocity limit

- Gazebo classic ODE 只硬执行 position/effort 限制；`<limit velocity>` 仅作为 PID 目标参考。
- 高速指令（PHASE2 cmd=0.80 m/s）下 ODE 可超速——由 21-action table（FW_MAX=0.53）+
  firmware 保证速度上限。自限速方案（viscous b=0.0089）因 ODE 在 torque≈stall-ε 时
  进入低速平衡（5.79 rad/s）而失败，已回退到 damping=0.001。

### 9.5 证据

- 探针: `_tmp/motor_load_final.sh` / `final_probe`（odom + joint_states 双源）
- 生成 URDF 校验: `_tmp/final_verify.sh` → ALL_PASS 8/8（torque 0.3 / vel 31.4 /
  damping 0.001 / friction 0.02 / izz 0.0001291 / accel 200.0）
- rev2.sdf XML 校验: `_tmp/validate_sdf_xml.py` → well-formed
