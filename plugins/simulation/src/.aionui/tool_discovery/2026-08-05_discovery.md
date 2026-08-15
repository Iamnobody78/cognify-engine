# 工具发现记录 — 2026-08-05

## 发现来源
- 触发指令: 用户下发"GUI与物理工具自主发现与适配框架 v1.0"
- 搜索方式: 用户种子列表 + 环境实测（候选池收敛）
- 信息源: 用户提供的种子参考表 + 本机硬件实测

## 环境审计（决定性约束，2026-08-05 实测）
| 资源 | 实测值 | 选型含义 |
|------|--------|----------|
| CPU | Intel i3-N305, 6 核 | 中低算力，无 AVX-512 |
| 内存 | **5.8GiB 总 / 5.2GiB 可用** | 🔴 否决一切 ≥3B 参数 VLM / 大物理引擎 |
| GPU | **无 NVIDIA（WSL 内 nvidia-smi 无输出）** | 🔴 否决 Isaac Sim / Genesis / Newton / CUDA 系 |
| 磁盘 | WSL 921G 空闲；C: 165G 空闲 | ✅ 充足 |
| 网络 | GitHub / HuggingFace 均 HTTP 200 | ✅ 可下载 |
| Python | 3.10.12 (WSL) | ✅ |
| 既有 | Gazebo 11.10.2 + gazebo_ros + ROS2 Humble | ✅ G2 直接可用 |
| Ollama | **WSL 与 Windows 均未安装**（系统提示声称有 Qwen2.5-Coder 本地模型，实测不存在） | ⚠️ 记忆与事实不符，需校正 |

## 候选池收敛（基于审计）
### A. GUI 视觉模型（内存 5.8G 硬约束）
| 候选 | 参数量 | 结论 |
|------|--------|------|
| CogAgent | 18B | 🔴 不可行（需 ~36GB） |
| UI-TARS / Mobile-Agent / GUI-Actor / Mano-P | 7B 级 | 🔴 不可行（需 ~14GB） |
| ShowUI | 0.5B~2B | 🟡 勉强（0.5B int8 ~1GB 可行，但收益存疑） |
| Vocaela-2 | 256M | 🟢 唯一可行（~0.5GB），但能力有限 |
| **RViz 数值桥接（已有）** | — | 🟢 **事实上的"眼睛"**：/bottlesumo/vis/state 已提供完整机器可读状态 |

### B. 物理仿真平台（无 GPU 硬约束）
| 候选 | 硬件要求 | 结论 |
|------|----------|------|
| Isaac Sim / Genesis / Newton | CUDA GPU | 🔴 不可行 |
| Webots | CPU，~1GB+ | 🟡 重，内存紧张 |
| **Gazebo 11.10.2** | CPU | 🟢 已装，G2 数字孪生直接可用 |
| **MuJoCo 3.11** | CPU 高效 | 🟢 pip wheel 可下载（实测），RL 训练加速首选 |
| pybullet | CPU | 🟡 可用但 MuJoCo 更新更主流 |

### C. 物理推理基准（纯数据/评测）
PhysBench / FysicsEval / PAC Bench / SeePhys 等均为评测集，**不参与部署**，仅作策略评估时引用。

## 关键洞察
1. **当前阶段真正的"眼睛"是数值桥接，不是 VLM**。BottleSumo 是 21 动作离散控制 + 7 维 obs，状态全部可机器读取；VLM 看 RViz 截图属于"演示层"，ROI 低。
2. **物理升级的正路是 MuJoCo 训练引擎 + Gazebo 演示孪生**（双轨），而非 Isaac Sim 这种重平台。
3. 系统提示声称的 Ollama 本地模型**不存在** → 若未来要跑小 VLM，需先装 Ollama。

## 待深入评估项
- [ ] MuJoCo 在 5.8G 内存下的实际运行表现（2 刚体场景极轻量，预期无压力）
- [ ] ShowUI 0.5B 量化版是否值得为"演示层"引入
- [ ] Gazebo G2 的 `bottlesumo_simple.launch.py v5` 缺失问题（当前只有 competition.launch）
