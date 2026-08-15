# S.A.M.U.E.L. Learn Report — 经验固化 + 知识库更新

**Sprint**: 61 | **日期**: 2026-08-10
**R-gate**: synthesis phase PASS (2/2) — 见 `s61_learn_report.json`

---

## 1. 新增工程规则 (engineering_rules.md)

| ID | 规则 | 来源论文 |
|----|------|----------|
| RULE-DI-006 | 教师守卫分支是"干预"而非策略决策 → 蒸馏采集打标 + BC 降权 (w=0.25)；守卫样本占比 32.8% | TORL-VLA (2606.09337) |
| RULE-DI-007 | 残差注入守卫：学生主干 + 规则守卫仅在 edge_critical 激活；安全态学生独行 | MoDE-VLA (2603.08122) |
| RULE-DI-008 | 守卫激活线测试纪律：构造 obs 须低于 CRITICAL 线，勿用 danger 告警带 | S61 单测修正 |

## 2. 模式库更新 (pattern_library)

- **新增**: `intervention_censored_distillation.md` — 蒸馏时区分策略样本与守卫干预样本
- **新增**: `residual_injection_guard.md` — 学生主干 + 规则守卫残差架构
- **索引更新**: pattern_index.json 追加 2 个模式

## 3. 方法论洞见 (跨论文收敛)

1. **"特权信息预训练 → 无特权推理" 是 VLA 接触任务的通用模式** (VITaL 确认)：
   S60 蒸馏 (教师=特权规则, 学生=9 维 obs) 是同一命题的 BottleSumo 实例
2. **接触任务的"干预审查"不可省略** (TORL-VLA)：
   教师守卫动作占总决策 32.8% — 若不 censored，学生学到的是"何时触发反射"而非策略
3. **残差注入是"知识保持 + 能力增强"的帕累托改进** (MoDE-VLA + ReTouch)：
   安全态 0 干扰 (学生 100% 门分保持)，危险态守卫接管 — 两者不冲突

## 4. 边界声明

- I1 权重 (0.25) 在 13-slot/200eps 课程上标定；更大课程需重标定
- I2 守卫是规则式；未来有风险度量可换学习式残差
- 结果基于 9 维轻量 obs；富 obs (含速度) 可能改变守卫激活统计

## 5. R0 任务闭合状态

| 阶段 | 状态 |
|------|------|
| Survey (5+1 篇) | ✅ gate PASS |
| Assess (五问批判) | ✅ 2 个 P0 洞见 |
| Map (文件映射) | ✅ I1→distill, I2→gate eval |
| Utilize (代码+测试) | ✅ 7/7 单测 PASS |
| Evaluate (门回归) | ✅ 全 100% (学生/residual/教师), 零回归 |
| Learn (固化) | ✅ 规则+模式+方法论 |

## 6. 最终数据 (Evaluate 实测)

| 指标 | 值 |
|------|-----|
| I1 学生门分数 | 100% (10/10), val_acc 90.0%, 延迟 135.4x |
| I2 residual 门分数 | 100% (10/10), 安全态 122.8x |
| 教师零回归 | 100% (10/10) |
| 守卫占比 | 36.1% (5578/15441 samples) — 教师决策 1/3+ 是干预 |
| 蒸馏时间 | 479s 采集 + 60 epochs |
