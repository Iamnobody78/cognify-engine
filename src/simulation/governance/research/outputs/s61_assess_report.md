# S.A.M.U.E.L. Assess Report — R0: VLA 模型在接触密集型任务中的失败模式

**Sprint**: 61 | **分支**: `feature/s61_research_r0` | **日期**: 2026-08-10
**输入**: `governance/research/outputs/research_papers_list.json`（6 篇，含 PM 预期的 5 篇 + ReTouch）

---

## 1. 论文清单与五问批判

### P1. TORL-VLA: Tactile Guided Online RL for Contact-Rich Manipulation (arXiv:2606.09337)
- **问题**: VLA 离线策略在接触条件漂移时无法在线适应 → 接触力不当、低效重试
- **方法**: 触觉力/力矩感知 VLA 预测参考动作 + 轻量在线 RL 模块精化；intervention-censored critic
- **关键洞见**: **intervention-censored critic**——防止"干预后成功"被错误归因给干预前的策略动作（credit assignment 陷阱）
- **局限**: 依赖触觉传感器硬件；在线 RL 需要真实交互预算
- **BottleSumo 迁移**: 教师 heuristic 的守卫分支（edge_f_turn/2 步安全）本质是"干预"——蒸馏时若不加区分，学生会把守卫行为当策略行为学（模仿噪声）。→ **干预标记蒸馏**

### P2. T-Rex: Tactile-Reactive Dexterous Manipulation (arXiv:2606.17055)
- **问题**: VLA 普遍忽略触觉模态或限于静态编码器；高频触觉信号利用率低
- **方法**: 100h 触觉数据集 + variable-rate Mixture-of-Transformers + 时序触觉 VQ-VAE
- **关键洞见**: 高频接触信号需要**专门的时序编码器**，且用"基础运动原语"优先采集
- **局限**: 数据集规模要求高（100h）；MoT 架构重
- **BottleSumo 迁移**: 弱（架构过重）；仅"原语优先课程"思想可借鉴——我们的 13-slot 课程已隐含

### P3. Representation-Aligned Tactile Grounding (arXiv:2607.14609)
- **问题**: 触觉预测监督应施加在 VLA 表示的哪一层？(representation-alignment 问题)
- **方法**: linear probe 发现未来触觉状态最可从**中间 action-expert 特征**预测；LTP 轻量潜在触觉预测器
- **关键洞见**: **监督施加位置决定学习效率**——中间表示比末层更易预测动作后果
- **局限**: 需要触觉未来状态标签
- **BottleSumo 迁移**: 中等——蒸馏时加 aux loss（中间层预测"推开成功"）可对齐中间表示与接触后果，但收益验证成本高

### P4. VITaL Pretraining (arXiv:2403.11898)
- **问题**: 如何把触觉信息纳入模仿学习平台？
- **方法**: visuo-tactile 预训练，然后推理时**非触觉 agent 也受益**（USB 插拔 20%→85%）
- **关键洞见**: **特权信息预训练提升无特权推理性能**——这与教师蒸馏完全同构！教师（特权：完整状态+规则）预训练学生（无特权：仅 9 维 obs）
- **局限**: 预训练数据质量决定上限
- **BottleSumo 迁移**: **强**——S60 已验证（学生 100%）；VITaL 进一步提示**多任务/多教师预训练**可能更强

### P5. ReTouch: Online-Refined Tactile Prediction (arXiv:2608.01824)
- **问题**: 触觉预测如何在线精化以适配快速变化的物理交互？
- **方法**: Tactile-Patch Encoder 保留指元身份 + 高频动作模块联合预测未来触觉态与动作块，执行时反馈闭环精化
- **关键洞见**: **执行时闭环精化**（closed-loop refinement）提升对接触变化的鲁棒性
- **局限**: 需要高频触觉反馈回路
- **BottleSumo 迁移**: 中——学生推理时检测危险状态（edge_danger_f 带）→ 触发轻量守卫覆盖 = 闭环校正

### P6. MoDE-VLA: RL-Augmented Teleoperation + Mixture-of-Dexterous-Experts (arXiv:2603.08122)
- **问题**: 灵巧接触任务的高保真数据采集 + 多技能学习 + 多模态融合瓶颈
- **方法**: IMCopilot（RL 原子技能，双角色：共享自主助手 + VLA 低层原语）+ MoDE-VLA（residual injection 集成力/触觉模态）
- **关键洞见**: **残差注入机制**——接触感知精化不损害预训练主干知识（residual injection preserves pretrained knowledge）
- **局限**: 技能库设计人工依赖
- **BottleSumo 迁移**: **强**——学生 MLP 为预训练主干，S59 守卫（edge_f_turn/2 步安全）作为"原子技能"以残差方式注入，危险态才激活 → 鲁棒性提升而不损害学习

---

## 2. 可迁移洞见优先级矩阵

| ID | 洞见 | 来源 | 迁移成本 | 预期收益 | 优先级 |
|----|------|------|----------|----------|--------|
| **I1** | 干预标记蒸馏 (intervention-censored) | P1 TORL-VLA | 低（采集时打标） | 中（去模仿噪声，蒸馏保真度↑） | **P0** |
| **I2** | 残差注入安全守卫 (residual injection) | P6 MoDE-VLA + P5 ReTouch | 低（评估时叠加） | 高（学生鲁棒性↑，不损害学习） | **P0** |
| **I3** | 特权预训练同构确认 | P4 VITaL | 零（已由 S60 验证） | 高（方法论确认） | P1 |
| I4 | 中间表示 aux loss 接地 | P3 | 高（需新标签+训练改造） | 中 | P2 |
| I5 | 原语优先课程 | P2 T-Rex | 中（课程改造） | 低（13-slot 已隐含） | P3 |

## 3. 结论

R0 的 6 篇论文收敛出 **2 个 P0 可执行洞见**：
- **I1（干预标记蒸馏）**：直接修补 S60 蒸馏的盲区——教师守卫干预样本与策略样本混训
- **I2（残差注入守卫）**：学生 MLP 保持轻量，危险态由 S59 守卫残差接管——架构级鲁棒性

两者均低迁移成本、可单元测试、可门回归验证。进入 Map 阶段。
