# Sprint 37 证据文档 — 观测升级 (9 维) + 轮转课程 + 门回归 (2026-08-08)

> 分支: `feature/s37_obs_upgrade` (基于 main 7c831e2 = S36 合入 + tag sprint36-closed)
> PM 裁决: P0 = 观测升级 (opp_vx/vy + 朝向 → 9-10 维) | P1 = 轮转课程 (并行) | T3 门 ≥60% (12/20)
> 验收: T1 训练脚本可运行/DQN 输入维度匹配 | T2 每档案 episode 占比 ≥15% | T3 门分数 ≥60% + 双端回归全绿

---

## 0. 结论速览

| 任务 | 状态 | 关键数字 |
| :--- | :--- | :--- |
| T1 观测升级 (7→9 维) | ✅ 完成 | obs 追加 opp 速度 (机器人相对系), DQN 9→32→21 对齐 |
| T2 轮转课程 (13 槽加权) | ✅ 完成 | 每门档案 2/13 = 15.4% ≥ 15% 验收 |
| T3 门回归 | ✅ **通过 (BC 轨道)** | **chase-BC 门胜率 77.5% (31/40) ≥ 60%** |
| T3 门回归 (DQN 微调轨道) | ⚠️ 失败 (FP-RL-005) | 4 模型一致 40.0% — DQN 微调摧毁追击技能 |
| 双端回归 | ✅ 全绿 | **220 passed + 1 skipped + 0 失败** |

**核心交付**: 观测升级 (lightweight_env 9 维 + Config.state_dim=9)、13 槽加权轮转课程、
**第二代教师桥 rl/chase_teacher_bc.py (全知追敌教师 BC)**、门 RL 代理 `--model` 覆盖、
**FP-RL-003 证伪链 + FP-RL-005 新失败模式 + defensive 物理不可胜证明**。

---

## 1. T1 — 观测空间扩展 (7→9 维)

### 1.1 实现

```
观测 (机器人相对系, 追加 2 维):
[edge_f, edge_b, edge_l, edge_r, opp_dist, opp_angle_rel, robot_speed,
 opp_v_forward, opp_v_right]        ← 新增: 对手速度投影 (归一化 /0.6, 裁剪 ±1)
```

- `lightweight_env.py` `_get_obs_for`: 在**观测者坐标系**投影对手速度 (前向/右向分量)
  — 旋转等变归纳偏置, 优于全局 vx/vy (策略无需隐式解耦自身朝向)
- 帧判断: 显式 `other_vel` 参数传递 (机器人帧=对手速度, 对手帧=机器人速度), 避免浮点比较
- 零侵入: 追加在索引 7,8 — 门策略 (obs[0..5])、ABDL 教师 (obs[0..6])、奖励 (obs[0..6]) 全部不受影响
- `common/config.py` `state_dim: int = 9` (DQNAgent 全链自动传播)
- 验收: 训练脚本运行 ✅ (1000ep/5000ep/2000ep 三次), DQN 输入 9 维对齐 ✅

### 1.2 观测充分性判定 (关键前置)

**obs[5] = opp_angle_rel 即"机器人指向对手的角差"** — 与全知追敌启发式所用信息
(atans2 相对方位) 等价。9 维观测信息**绝对充分**, 这是后续判别实验的逻辑基础。

---

## 2. T2 — 轮转课程 (13 槽加权, FP-RL-002 升级)

```
CURRICULUM_POOL (13 槽):
[random, aggressive, defensive, circler, counter] ×2   ← 门行为套件
+ [moderate, passive, stationary]                       ← 速度阶梯
```

- 每门档案 2/13 = **15.4% ≥ 15% 验收** ✅ (S36 的 8 槽 12.5% 不满足 PM 验收, 已加权)
- 轮转无遗忘 (FP-RL-002 修复保持)、预算均匀无稀释
- 训练日志验证: 13 槽轮转 → 每档案占比精确 15.4% (ep % 13)

---

## 3. T3 — 门回归 (20/40 对局)

### 3.1 结果全景

| 策略 | random | aggr | def | circ | counter | **总** |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| ABDL 规则基线 (历史) | — | — | — | — | — | **10%** |
| 9 维 DQN (1000ep) | 0/4 | 4/4 | 0/4 | 0/4 | 4/4 | **40%** |
| 9 维 DQN (5000ep) | 0/4 | 4/4 | 0/4 | 0/4 | 4/4 | **40%** |
| chase-BC 预热 + DQN (2000ep) | 0/4 | 4/4 | 0/4 | 0/4 | 4/4 | **40%** |
| **chase-BC (未微调, 20 对局)** | **3/4** | 4/4 | 0/4 | **4/4** | 4/4 | **75%** ✅ |
| **chase-BC (未微调, 40 对局)** | **7/8** | 8/8 | 0/8 | **8/8** | 8/8 | **77.5%** ✅ |

### 3.2 判别实验链 (Meta-Harness 内环, FP-RL-003 证伪)

**实验 1 — 全知追敌基线 (内部状态, 无观测限制)**: random 10/10, circler 9/10,
**defensive 0/10**, aggressive 10/10, counter 10/10
→ 追击型对手物理可胜 (除 defensive); 若 RL 学不会, 是学习问题而非物理

**实验 2 — 反直觉策略变体 (诱敌反击/侧翼闪避)**: defensive 在三种策略下全 0/10
→ defensive 是**对称速度/推力参数下的结构性不可胜** (0.53 vs 0.53 对冲僵持 +
  edge_f<0.3 边缘撤退回中循环逃逸) — 超出 RL 范畴, 需物理参数审计或门档案复核

**实验 3 — 9 维 DQN 1000ep/5000ep**: 门结果逐策略完全相同 (40%), 训练量 5 倍零改善
→ 排除"训练量不足"假设

**实验 4 — chase-BC 预热 + 2000ep 微调**: 依旧 40%, 逐策略一致
→ **FP-RL-005: DQN 微调灾难性覆盖** — 微调把 BC 注入的追击技能覆盖为"对冲型"
  折中策略 (混合对手 replay + epsilon 探索破坏数十步时序一致的追击轨迹)

**实验 5 — chase-BC 纯权重直接打门: 77.5% (31/40) PASS**
→ 9 维观测 + 行为克隆**足以过门**; 证明观测充分 (FP-RL-003 证伪) 且追击技能可学,
  瓶颈在 DQN 微调环节而非表征/物理

### 3.3 FP-RL-005 因果分析 (S38 课题)

- 症状: BC 权重门 77.5%, 经任何 DQN 微调后恒 40%
- 机制: 追击需数十步"持续转向+前进"的时序一致行为; DQN 回放缓冲混合 8 种对手,
  epsilon-greedy 打断成功轨迹, Q 学习收敛到"对冲型"折中 (对主动冲撞的 aggressive/
  counter 有效, 对非接触型 random/circler 无效)
- 修复候选 (S38): (a) 微调阶段低 epsilon + 仅梯度保护 BC 技能 (正则/冻结前层),
  (b) 分策略 Q 集成 (per-profile critics), (c) DAgger 在线纠正而非离线 BC,
  (d) 直接部署 BC 策略 + 后续离线学习提升

---

## 4. 验收核对

- T1 ✅: 训练脚本运行, DQN 输入维度匹配 (9→32→21)
- T2 ✅: 每门档案 episode 占比 15.4% ≥ 15%
- T3 ✅ (BC 轨道): 门分数 **77.5% ≥ 60%** (12/20 口径超达标)
- 双端回归 ✅: **220 passed + 1 skipped + 0 失败**
- **技术债 (如实上报)**: DQN 微调轨道仍 40% (FP-RL-005), defensive 物理不可胜 (0/8)

## 5. 工程资产清单

| 资产 | 路径 | 说明 |
| :--- | :--- | :--- |
| 观测升级 | `simulation/lightweight_env.py` (+ 首次 git 跟踪) | 7→9 维, 对手速度投影 |
| 状态维度 | `common/config.py` (+ 首次 git 跟踪) | state_dim 7→9 |
| 第二代教师桥 | `rl/chase_teacher_bc.py` (新) | 全知追敌教师 → BC (96.1% 复现率) |
| 轮转课程 | `simulation/training/train.py` | 13 槽加权 (15.4%/档案) |
| 契约测试更新 | `tests/test_env_factory.py`, `tests/test_mujoco_env.py` | 9 维 + 前后端 prefix 契约 |
| 模型 | `models/chase_teacher_bc_s37.pt` (门 77.5%), `v10_dqn_s37_9d*` (40%), `abdl_teacher_bc_s37.pt` | 全部保留作证据 |
| 证据文档 | `docs/engineering/s37_obs_upgrade_evidence_20260808.md` | 本文件 |

## 6. 运维记录

- **仓库卫生发现**: `common/config.py` 与 `simulation/lightweight_env.py` 此前**未被
  git 跟踪** (S30 时代历史未跟踪文件) — 本次提交首次纳入, 防止 S37 核心改动丢失
- `Config("quick_test")` 是错误用法 (dataclass 位置参数赋给 state_dim) —
  正确: `Config.quick_test()` 工厂方法 (RULE-PR-002 家族新条目)
- pytest anyio 插件冲突 → `-p no:anyio` 依旧
- 完整回归 (governance+tests) 需分块运行 (governance 124s), 整批易超时
