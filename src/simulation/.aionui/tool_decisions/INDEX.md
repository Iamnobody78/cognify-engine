# 工具决策索引 — INDEX.md

> 所有发现/评估/适配/更新的决策状态汇总。更新日期：2026-08-05

| 工具 | 类别 | 状态 | 决策 | 报告 |
|------|------|------|------|------|
| **MuJoCo 3.11.0** | 物理引擎 | 🟢 **已集成**（2026-08-05：gym 21 动作 + V9 门第二后端 + RViz 桥 + 14 单测） | 训练级物理引擎；v11 策略转移 100%，heuristic 60%，abdl 40% | [mujoco_evaluation.md](../tool_evaluations/mujoco_evaluation.md) |
| **Gazebo 11.10.2** | 物理引擎 | 🟢 **已跑通**（2026-08-05，DEBT-013 关闭，原名 DEBT-008） | 演示孪生：模型加载 + 边缘传感器 + cmd_vel 控制 + odom + joint_state + TF 全链路验证通过 | — |
| ShowUI 0.5B / Vocaela-2 | GUI VLM | 🟡 暂缓 | 演示层 ROI 低；先决条件：装 Ollama | [gui_vlm_evaluation.md](../tool_evaluations/gui_vlm_evaluation.md) |
| CogAgent / UI-TARS / GUI-Actor 等 ≥3B | GUI VLM | 🔴 否决 | 内存 5.8G 硬约束不可行 | 同上 |
| Isaac Sim / Genesis / Newton | 物理仿真 | 🔴 否决 | 无 NVIDIA GPU | [2026-08-05_discovery.md](../tool_discovery/2026-08-05_discovery.md) |
| Webots | 物理仿真 | 🟡 不推荐 | 内存紧张，Gazebo 已覆盖 | 同上 |
| pybullet | 物理引擎 | 🟡 备选 | MuJoCo 更优，不引入 | 同上 |
| PhysBench / FysicsEval / PAC Bench | 物理推理基准 | 📋 仅引用 | 评测集，不部署 | 同上 |
| **RViz 数值桥接（G1）** | "眼睛" | ✅ 已实现 | 当前阶段的机器眼 | [2026-08-05_gui_startup.md](../sessions/2026-08-05_gui_startup.md) |

## 执行队列（按优先级）
1. [x] **G2 Gazebo 数字孪生** ✅（2026-08-05，DEBT-013 关闭，原名 DEBT-008）：URDF 轮轴 Z→Y + publish_odom + joint_state 插件 + caster 触地 + spawn z=0；headless 验证：模型加载、edge 传感器话题 ×4 + tof_scan、cmd_vel→差速→位移 10.7cm、odom 消息 + TF 全链路
2. [x] **MuJoCo 集成** ✅（2026-08-05 完成）：gym 包装（21 动作）→ V9 门第二后端（`--backend mujoco`）→ RViz 桥（`--backend mujoco`）→ 14 单测
3. [ ] Ollama 安装（如未来要跑小 VLM 的前提；记忆校正：系统提示声称存在，实测不存在）
4. [ ] aggressive 反制策略（环境级挑战，留待 MuJoCo 训练阶段）

## 记忆校正记录
- ⚠️ 系统提示称"Ollama Qwen2.5-Coder-7B/1.5B 本地模型"——2026-08-05 实测 WSL 与 Windows 均未安装 ollama。标记为环境事实待修正。
- ℹ️ G2 前置修正：`bottlesumo_gym_env.py` docstring 称依赖 `bottlesumo_simple.launch.py (v5)`，实测该 launch 存在于 `bottlesumo_description/launch/`（此前误判为缺失）。
