# GUI 可视化启动会话 —— 2026-08-05 (Phase G / G1)

## 目标
在 RViz 中显示 `bottlesumo_gym` 的机器人状态（数字世界、仿真优先、无真实硬件）。

## 成果（G1 完成 ✅）

### 桥接节点 `simulation/bottlesumo_vis_bridge.py`
- 单一来源：直接复用 `V9RuleAgent(abdl)` + `LightweightBottleSumoEnv`（不复制逻辑）
- 发布 12.5Hz（env TIMESTEP 0.08s）：
  - `/bottlesumo/vis/markers`（visualization_msgs/MarkerArray）：土俵环（半透明白）、机器人（红柱+黄朝向箭头）、对手（蓝柱）、轨迹（黄线，120 点）
  - `/bottlesumo/vis/state`（std_msgs/String）：agent/opponent/episode/step/reward/score/done 决策透明度
- 支持 `--agent abdl|heuristic`、`--opponent random|aggressive|defensive|circler|counter`、`--seed`

### RViz 配置 `simulation/rviz/bottlesumo_gym.rviz`
- Fixed Frame: `dohyo`，Grid 0.1m，MarkerArray 显示

## 验证证据（三证据协议）
1. 代码：桥接 + rviz 配置（commit 2a124fb）
2. 实测：rviz2 启动成功（WSLg，OpenGL 4.5）；8 秒内 96 条 MarkerArray / 480 markers；ABDL 13 规则加载；机器人实时运动
3. 记录：本文件 + verifier 输出

## 关键坑与修复
1. **rclpy `Rate.sleep()` 无 executor 时无限阻塞**（Humble 已知行为）→ 用 `time.sleep(0.08)`
2. **numpy 标量 → ROS 消息**：`ColorRGBA`/`Quaternion`/`Point` 需要 Python float → `float()` 包裹
3. **WSLg GUI**：`LIBGL_ALWAYS_SOFTWARE=1` 兜底 GL；rviz2 通过 WSLg 显示 OK

## 观测：counter 对局僵持
step 26-101 机器人位置几乎不动（0.15,0.21 附近）—— 与 counter 互顶。与 gate 实验 counter 1/2 吻合：abdl 能顶住但推进不足。留待策略迭代。

## 运行命令（WSL）
```bash
source /opt/ros/humble/setup.bash
export PYTHONPATH=/mnt/c/.../aionrs-temp-48324704:$PYTHONPATH
python3 bottlesumo_pi/simulation/bottlesumo_vis_bridge.py --opponent counter --agent abdl
rviz2 -d bottlesumo_pi/simulation/rviz/bottlesumo_gym.rviz
```

## 下一步
- G2: Gazebo 数字孪生（`bottlesumo_gym_env.py` 依赖 `bottlesumo_simple.launch.py v5`，当前只有 competition.launch —— 需新建 launch + world）
- 用户新指令：工具自主发现框架（GUI VLM + 物理仿真平台调研）→ 启动 Discovery Protocol
