# Queue #5 Manifest — 战术补偿 + 数据管道 (feature/queue5_tactical_distill)

> 状态: INFRASTRUCTURE GO / TRAINING HOLD（2026-08-05 PM 签署）
> 分支: feature/queue5_tactical_distill（自 audit_queue4_closed 切出, 已并入 3d8871b 本能接收框架）
> 验收会: 48h 后（对照 Rerun 截图 + step_response.json 上升沿曲线）

## 双轨结构

```
TASK-005a  step_response 标定      ──GO──┐
TASK-005b  状态空间数据收集器        ──GO──┼──→ TASK-005d 调参(HOLD, 依赖 a)
TASK-005c  Rerun 3D 可视化看板      ──GO──┘         │
                                                   ↓
                                    Option C MuJoCo 蒸馏 (FROZEN, 依赖 a+b+d)
```

## 任务清单

| ID | 内容 | 依赖 | 状态 | 交付物 |
|----|------|------|------|--------|
| 005a | Gazebo step_response 标定 (cmd_vel 0→0.53 m/s 阶跃, 10 次重复) | 无 | **GO** | `simulation/calibration/step_response_<ts>.json` (rise_time_90% / settling_time) |
| 005b | 状态空间数据收集器 (距离 0.1~1.0m × 角度 -π~π, heuristic 滚动) | 无 | **GO** | `data/raw_episodes/episode_xxx.parquet` (obs/action/reward/done) |
| 005c | Rerun 3D 实时可视化 (速度箭头 + 5s 时序曲线 + episode 计数) | 无 | **GO** | Rerun 截图 (127.0.0.1:9876) + `config/visualizer.yaml` |
| 005d | heuristic aggressive/counter 增益重调 (仅 kp_gain_multiplier / feedforward_boost) | 005a | **HOLD** | 修改后 `heuristic_config.yaml` + 收敛曲线验证 |
| Option C | MuJoCo BC/DAgger 蒸馏 (Teacher=调参后 heuristic, 50k~100k 转移) | a+b+d | **FROZEN** | 学生策略 + 双后端验证 |

## PM 强约束（执行边界）

1. **TASK-005d 必须基于实测标定**：禁止拍脑袋改 yaml；唯一依据 = step_response json。
2. **修改范围锁死**：仅 `heuristic_config.yaml` 的 aggressive/counter 段落
   （kp_gain_multiplier / feedforward_boost）；**严禁**碰 control_pipeline.py 核心逻辑
   与 lightweight/v11 门回归基线阈值。
3. **TASK-005d 验收（硬性）**：
   - CLOSE-PUSH (<0.3m) Gazebo 实测成功率 0% → **≥60%**
   - NORMAL (>0.5m) 无过冲振荡：角速度超调 < 15%
4. **Option C 解冻条件（双前置）**：
   - 条件 A: TASK-005d 完成, CLOSE-PUSH ≥ 60%（最优人类先验已找到）
   - 条件 B: ME 维度检查 data/raw_episodes 的 action 分布覆盖高扭矩/急转向区域
   （避免全匀速巡航 → 蒸馏平庸策略）

## 环境

- Python 3.10.12 (WSL), rerun-sdk 0.35.0 可用 (pip index 确认)
- Gazebo classic (humble) + bottlesumo_simple.launch.py, 34mm 轮物理化模型
- 回退方案 (rerun-sdk 装不上时): matplotlib 实时绘图 + rviz2 纯 3D 分开看

## 48h 交付物

1. `simulation/calibration/step_response_<ts>.json`（上升沿曲线数据）
2. `data_collector.py` dry-run 日志（闭环写盘证明, 不要求跑满数据量）
3. **Rerun 截图**（机器人跑起来 + 速度箭头可见）
