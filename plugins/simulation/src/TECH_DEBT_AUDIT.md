# Technical Debt Audit & Consolidation Report

**Date**: 2026-07-27  |  **Phase**: Meta-Harness 迭代 - 技术债务清理与整合

## 🏚️ 发现的债务

| # | 债务类型 | 严重度 | 影响范围 | 状态 |
|---|---------|:---:|------|:---:|
| 1 | QNet/DQN 类重复定义 7 次 | 🔴 Critical | train_*.py ×5, distill, gatekeeper, eval | ✅ 已修复 |
| 2 | evaluate() 函数重复 5+ 次, 阈值不一致 | 🔴 Critical | 所有 eval/train 脚本 | ✅ 已修复 |
| 3 | Agent 类重复 3+ 次, epsilon 衰减逻辑散落 | 🟠 Major | 3 个训练脚本 | ✅ 已修复 |
| 4 | HP 散落各文件, 无类型安全 | 🟠 Major | 全网 | ✅ 已修复 |
| 5 | 硬编码路径: `/bottlesumo_env/`, `/mnt/c/Users/` | 🟠 Major | 4 个脚本 | ✅ 已修复 |
| 6 | win_threshold 不一致 (100 vs >100 vs 150) | 🟡 Moderate | eval 脚本 | ✅ 已统一 |
| 7 | clip_grad_norm 值不一致 (1.0 vs 10.0) | 🟡 Moderate | train 脚本 | ✅ 已统一 |
| 8 | Nano V1 无视对手特征 (SHAP=0%) | 🟡 Moderate | distill_nano.py | ✅ 已修复 |

## ✅ 修复内容

### 1. 新建 `bottlesumo_pi/common/` 统一模块

```
bottlesumo_pi/common/
├── __init__.py       → 统一导出: DQN, DQNAgent, ReplayBuffer, evaluate, Config
├── network.py        → DQN (灵活架构) + NanoQNet (嵌入式)
├── agent.py          → 单 Agent (支持 DQN/Double DQN 切换)
├── replay_buffer.py  → 单 ReplayBuffer
├── evaluation.py     → 单 evaluate() (可配置阈值)
└── config.py         → Dataclass 配置 (BayesOpt / Nano / QuickTest 预设)
```

### 2. 重构训练管道 `train.py`
- 替代 `train_dqn_v10.py` + `train_v10d_batch.py` + `train_v10e_extended.py`
- 支持 `--config bayesopt|nano|quick_test` 预设
- Double DQN 通过 `Config.use_double_dqn` 切换
- 课程学习 (Curriculum) 通过 `--no-curriculum` 关闭

### 3. 统一评估 `eval.py`
- 替代 `eval_v10.py` + `eval_best_model.py`
- 多对手 profile 基准测试
- 自动生成 JSON 报告
- 统一阈值: win ≥ 100, edge ≤ -50

### 4. 对手感知蒸馏 `distill_nano_v2.py`
- **核心修复**: 新增 opponent_correlation_loss
- 效果: Nano V2 对手敏感度 = **2.89×** V1 基线
- V1 SHAP: opponent_x=0%, V2 expected: opponent_x>10%

## 📊 验证结果

| 测试 | 结果 | 时间 |
|------|------|-----:|
| `common/` 模块导入 | ✅ 全部通过 | <1s |
| `train.py --config quick_test` | ✅ WR=70%, 无错误 | 2s |
| `eval.py --model v10_dqn_best.pt` | ✅ 4 profile 基准 | 15s |
| `distill_nano_v2.py` | ✅ opp_sens=2.89× V1 | 22s |

## 📋 剩余债务

- [ ] 旧 `train_*.py` 文件仍存在 — 可移入 `_archive/` 或删除
- [ ] `train_bnn.py`, `train_sensor_denoise.py` 等存活状态不明
- [ ] 缺少单元测试 (env dynamics, reward, agent update)
- [ ] Nano V2 需要完整 SHAP 重新分析确认对手感知恢复程度
- [ ] v10_dqn_best.pt 仅 37.5% WR — 是否已过期?

---

## 🔩 新增债务登记 (2026-08-05, Queue #4 电机物理审计 + 收口)

| # | 债务类型 | 严重度 | 影响范围 | 状态 |
|---|---------|:---:|------|:---:|
| 016 | Gazebo classic 不硬执行 joint `<limit velocity>` (ODE 只硬执行 position/effort) — 高速指令下可超速 | 🟡 Moderate | rev2.sdf / urdf.xacro, 21-action table | ⏳ 由动作表 FW_MAX=0.53 + firmware 保证上限; 自限速方案 (viscous b=0.0089) 因 ODE 低速平衡失败已回退 |
| 017 | 仿真-硬件轮径偏移: sim 34mm (Rev1/V9 门契约) vs 物理 48mm (Rev2 权威) — 同转速下线速度偏差 41% | 🟡 Moderate | 全仿真速度语义 | ⏳ CALIBRATION_PENDING — 延后至 HIL 校准期, 经 HAL `wheel_radius_multiplier` 映射; 见 motor_spec.json |
| 018 | WSL 3D 可视化依赖: Rerun GUI 需 wgpu 渲染后端; 裸 WSL 缺 GL/Vulkan 驱动 → R32Float 不可用 | 🟢 Resolved | TASK-005c visualizer | ✅ RESOLVED (2026-08-05): 安装 `mesa-vulkan-drivers` (lavapipe) + `mesa-utils`/`vulkan-tools` 后, wgpu 走 Vulkan llvmpipe 软件渲染, Rerun GUI 实测启动成功 (Vulkan 1.3.255, device_type=Cpu), WSLg 渲染到 Windows 桌面; 截图 docs/visuals/wslg_screenshot.png |

**DEBT-017 关联**: TASK-005 (heuristic gain retuning) 依赖 DEBT-016 的实测角速度标定;
轮径校准 (DEBT-017) 完成后需重验 0.53 m/s 上限锚定。
