# 可视化强制约束（Visualization Mandate）

> 状态: **最高优先级硬约束**（用户 2026-08-05 明确声明"已写入记忆"，经核查此前未落盘——
> 本次正式创建。诚实边界记录: 见本文件底部"落盘历史"）
> 位置: `.aionui/context/visualization_mandate.md`（治理元数据现行区）
> 关联: `.aionui/context/motor_consistency_audit.md`（模型=实物一致）、`bottlesumo_pi/.aionui/sessions/`

## 1. 约束正文（硬性）

**所有训练 / 调试 / 评估必须具备 3D 可视化（Gazebo 或 MuJoCo + RViz）。禁止纯数值 / 无头训练。**

1. **P0 — 训练可视化**: 任何强化学习 / 规则引擎训练会话，必须能实时或事后回放 3D 场景。
   允许 `render_mode` 关闭以提速，但**必须**配套 G3 决策层 overlay（marker 可视化）或
   轨迹回放工具，训练产物必须可目视审查。
2. **P1 — 调试可视化**: 策略 / 规则 / 传感器调试一律先目视确认行为语义，再做数值断言。
3. **P2 — 评估可视化**: V9 门等自动化评估，报告必须附代表性 episode 的可视化截图/回放
   链接（`_screenshots/` 或 `simulation/logs/`）。
4. **双后端并行**: Gazebo（Rev2, rev2.sdf + sumo_arena.world）与 MuJoCo（34mm Rev1 几何）
   同时维护，任一后端变更需在另一后端做一致性抽检。

## 2. 落地清单（2026-08-05 状态）

| 项目 | 状态 | 证据 |
|------|------|------|
| G1 RViz 决策 overlay | ✅ | `simulation/bottlesumo_vis_bridge.py` pub_debug |
| G2 Gazebo（rev2.sdf + world） | ✅ | 队列 #1, DEBT-013 关闭 |
| G3 决策层 marker（abdl/heuristic 分支标签） | ✅ | commit 528d636 |
| MuJoCo 训练可视化回放 | ✅ 部分 | render + trajectory JSON |
| V9 门评估截图存档 | ⚠️ 部分 | `_screenshots/` 存在，代表性回放待补齐 |

## 3. 违反即回退原则

任何"仅打印数字就跑训练/评估"的流程 = 违反硬约束，立即回退并补可视化。

---

### 落盘历史（诚实边界）
- 2026-08-05 用户声明"已写入记忆"；经 Glob/检索核查，磁盘上不存在该文件。
- 2026-08-05（晚）本文件正式创建于 `.aionui/context/`，作为约束的**唯一事实来源**，
  并同步登记至持久记忆（project 类型）。
