# Sprint 18–26 跨领域证据矩阵 — 归档

> **Sprint**：18–26（动态锚点 + M2 多信号融合 + 扰动阶梯实证的跨领域证据链）
> **分支**：`feature/sprint26_pass_threshold`（基座 main@sprint25-closed）
> **日期**：2026-08-08
> **依据**：PM Sprint 25 签收裁决 —— "sprint 18-26 的详细跨领域证据矩阵" 归档请求
> **状态**：COMPLETE（Sprint 26 A1 阶梯实证收口）

---

## 〇、证据矩阵总览（理论锚定 → 工程实现 → 实证闭环）

| 跨领域维度 | Sprint 18–19（种子库） | Sprint 20–22（动态化） | Sprint 23–24（M2 评估） | Sprint 25–26（阶梯实证） |
| :--- | :--- | :--- | :--- | :--- |
| **种子生成** | 静态锚点，S19 候选应用后锚点失效（死锚点） | 动态锚点 `anchor="regex"` 雏形（FP-MC-017 复发） | 动态 expected 计数（S19 教训固化） | 3 死锚点根治 + 双路径校准（_gen 无 bump / _seed_variants 有 bump） |
| **评估器** | winrate 单信号 | 四态判定（PASSED/REGRESSION/SUSPICIOUS/INCONCLUSIVE） | M2 多信号融合（steps_eff + layer_signal），Q 三档细化 | 三态共存实证（S25）+ Q 阶梯斜率标定（S26） |
| **治理门** | V9 门阈值 60% 胜率 | 探索饱和门 P2-V4 | RULES CLOSED 外部治理 | V9 门暂缓（D），负样本库建立 |
| **失败模式库** | FP-MC-014/015（评估器） | FP-MC-017（锚点失效 3 次复发） | FP-MC-020（abs 阈值误用归一化参数） | FP-NEG-001（动量 1.20 过冲负样本） |

## 一、核心论文锚定（跨领域理论支撑）

| 论文/框架 | 领域 | Sprint 落点 |
| :--- | :--- | :--- |
| **Meta-Harness**（Stanford IRIS, arXiv:2603.28052） | 迭代搜索 + 帕累托前沿 | 全局框架：候选→验证→失败分析→前沿更新（S18–S26 全周期） |
| **AIProbe: Differential Testing for Autonomous Agents**（AAAI 2025） | 黑盒差分测试 | S17 评估器差分框架 → S24 M2 多信号对照（baseline/diff 双跑） |
| **DT4LM Differential Testing** | 动态阈值策略 | S24 M2 三档 Q 阈值（±0.15/±0.02）的动态化参照 |
| **AutoTestForge**（ACM TOSEM 2025） | 多维交叉验证 | M2 layer_signal（branch_hist/动作熵/平均奖励）多信号设计参照 |
| **RL 课程学习/自蒸馏** | 程序化 RL 课程生成 | P2 蒸馏管道设计（S20）→ B 方向（M2 判定纳入蒸馏）Sprint 26 解锁 |
| **FSCL-ARCH / MAA-ARCH** | 元认知架构 | outer_loop 融入（S15 立项）→ 种子层信号枯竭修复（S25） |

## 二、工程实现证据链（Sprint 18→26 演进）

| Sprint | 交付 | 文件 | 关键证据 |
| :--- | :--- | :--- | :--- |
| 18–19 | 种子库 + 差分评估 | `evaluator_diff_test.py`、`variants.py` | 四态判定；S19 死锚点首现 |
| 20–22 | P2 蒸馏设计 | `s20_p2_distill_evidence_20260808.md` | 蒸馏管道设计文档 |
| 23 | D2 重校准 | variants.py 阈值语义修正 | FP-MC-020 根因修正（abs 阈值误用于归一化参数） |
| 24 | M2 多信号融合 | `evaluator_v9.py --layer`、`test_m2_fused_signals.py`（17 用例） | Q=0.5×steps_eff+0.5×layer_signal；SUSPICIOUS 同构打破；rules 排除 |
| 25 | 动态锚点根治 | `variants.py _SEED_PARAMS`、`outer_loop.py` | 3 死锚点动态正则化；physics 1→3 种子；REGRESSION 首现（动量 1.20）；三态共存 |
| 26 | 扰动阶梯实证 | `variants.py`（_gen 变体 C + seed_1）、`failure_analysis.md` | **-5°→-8°→-10° 阶梯 Q=0.02/0.03/0.04，斜率 0.005 Q/度**；FP-NEG-001 入库；路径澄清（_gen 无 bump） |

## 三、实证闭环数据（Sprint 25–26 核心量测）

| 量测 | S25（-5°, 40→35） | S26 P0（-8°, 40→32） | S26 兜底（-10°, 40→30） |
| :--- | :--- | :--- | :--- |
| Q | 0.02 | 0.03 | 0.04 |
| steps_eff | +0.037 | +0.051 | +0.056 |
| 动作熵 Δ | +0.010 | +0.013 | +0.015 |
| 判定 | SUSPICIOUS | SUSPICIOUS | SUSPICIOUS（P2-V4 饱和门停止） |

**结论**：mapping 角度阈值轴扰动-响应斜率 ≈ 0.005 Q/度（线性饱和），非幅度不足而是**锚点行为影响力饱和**。
**跨领域启示**：① 评估器 M2 能精确感知 0.01 级 Q 差异（SUSPICIOUS 档可解析）；② 种子层信号质量决定搜索效率上限（死锚点 vs 动态锚点差 3 倍产出）；③ 失败模式库需负样本（REGRESSION 与 PASSED 同权入库）。

## 四、关联归档（索引）

| 文档 | 路径 |
| :--- | :--- |
| 帕累托前沿 | `governance/meta_harness/pareto_frontier.md`（Sprint 26 阶梯记录） |
| 失败分析 | `governance/meta_harness/failure_analysis.md`（FP-NEG-001 负样本） |
| 路线图 | `docs/architecture/ROADMAP_v2.md`（11.21 Sprint 26） |
| 蒸馏设计 | `docs/engineering/s20_p2_distill_design_20260808.md` |
| 差分证据 | `docs/engineering/s17_evaluator_diff_test_evidence_20260808.md` |
