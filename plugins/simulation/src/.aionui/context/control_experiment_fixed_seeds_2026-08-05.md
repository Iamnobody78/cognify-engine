# 对照实验记录 —— 固定种子三智能体控制实验（2026-08-05，最终版）

## 实验设计（测量完整性第三阶段）

- **种子修复**：`hash(opponent_name)` 受 PYTHONHASHSEED 盐化 → 每次进程运行对手出生点不同（abdl 漂移 40%↔60%）。改为 hashlib 确定性种子（`_stable_seed`）。
- **固定种子集**：同一组种子跑全部 agent，公平 A/B，结果可复现。
- **环境**：lightweight_env（real，非 mock），21 动作门环境，DOHYO_RADIUS=0.40m。
- **每 agent 10 episodes**：random×2, aggressive×2, defensive×2, circler×2, counter×2。

## 最终结果（固定种子，abdl 规则工程后）

| agent | total | random | aggressive | defensive | circler | counter | 门(≥60%) |
|-------|-------|--------|------------|-----------|---------|---------|----------|
| **abdl** | **70% (7/10)** | 2/2 | 0/2 | 2/2 | 2/2 | 1/2 | ✅ pass (margin 2) |
| v11 | 70% (7/10) | 1/2 | 0/2 | 2/2 | 2/2 | 2/2 | ✅ (模板) |
| heuristic | 30% (3/10) | 0/2 | 0/2 | 2/2 | 1/2 | 0/2 | ❌ |

abdl 已与 v11 模板持平（70%），且 aggressive 从"被推出界"(137/292步) 变为"500 步僵持"——不再坠落，但 aggressive 也无伤（平局判负）。

## 因果推理链（abdl 20% → 70% 的关键修复，按序）

1. **测量完整性链**（658f76b）：真实环境接线 + 边缘传感器线性化 + win 检测 + ABDL 真实 API 接线 + mock 警告。20% → 真实基线。
2. **确定性种子**（db9c897）：hash→hashlib，A/B 可复现，消除 40%↔60% 漂移。
3. **pursue 方向 bug**（db9c897）：`angle>0` 注释"对手在右"，环境语义是正值=左侧 → 追猎转向完全反向。counter 0/2→1/2。
4. **FLANK 条件反转**（db9c897）：FLANK-RIGHT 条件写 `angle>30`（实为左翼）→ 转向对齐反了。修复。
5. **冲撞窗口过宽**（db9c897）：dist<0.3 就 FW_MAX（= counter 触发距离，迎面对撞）。收紧 0.22m/±12°（v11 模板：0.18m 严格对齐）。
6. **abdl_engine stdout 污染**（db9c897）：诊断打印改 stderr，`--json` stdout 保持机器可读。
7. **确定性方向感知边缘保护**（e2056f0）：
   - `_edge_retreat` 原为 random.choice([REV_SLOW, TURN_L, TURN_R, **CREEP_FWD**]) → 25% 概率边缘向前爬行坠落（circler ep 14 步坠亡）。改为：前缘危险→REV_SLOW；否则转向清障更大一侧。
   - `_edge_recovery` 随机转向 → 始终 REV_SLOW（对齐 v11 edge<0.12→backwards）。
   - `_pursue_opponent` dist>0.6 左翼分支返回 FW_RIGHT_FAST（方向错）→ FW_LEFT_FAST。
   - 效果：circler 1/2→2/2；aggressive 不再被推出界；总体 60%→70%。

## 剩余弱点：aggressive 0/2（所有 agent 共享）

- aggressive 策略：dist<0.3 → spin 面对 + hard forward 持续推压。
- abdl 现在可 500 步僵持（不坠落），v11 在 292 步被推出界。
- 门评估允许放弃此维度（其他 4 种策略全胜即可 80%）。aggressive 反制 = 环境级挑战，留待全链路管线阶段。

## 决策记录

- **V9 门正式通过**：abdl 70% (7/10)，mode=real，margin 2 场（对种子方差稳健）。
- gate report 双处同步：`.aionui/meta_governance/gate/v9_gate_report.json`（canonical）+ `bottlesumo_pi/.aionui/`（镜像）。
- 提交：658f76b（测量链）、db9c897（种子+方向）、e2056f0（边缘保护）。
- 下一阶段：GUI 可视化（Gazebo/RViz 并行）→ 全链路数字机器人管线。
