# Sprint 61 规格 — 研究引擎 R0 闭环：将 VLA 论文洞察转化为代码变更

**状态**: CLOSED | **分支**: `feature/s61_research_r0` | **日期**: 2026-08-10
**PM 指令**: "研究引擎 R0 闭环：将 VLA 论文洞察转化为代码变更" — P0

---

## 1. 目标

基于研究引擎检索的 VLA 论文（R0 实际 6 篇），完成 S.A.M.U.E.L. 五步：
Assess → Map → Utilize → Evaluate → Learn，把论文洞察落地为可验证的代码变更。

## 2. 验收标准

| 标准 | 目标 |
|------|------|
| S.A.M.U.E.L. 全链路 | 6 phase 可执行且过 R-gate |
| 论文 → 代码桥接 | ≥ 2 个 P0 洞见落地为代码 + 单测 |
| 门回归 | 学生/residual ≥ 90%，教师 100% 零回归 |
| 延迟 | residual 安全态 ≥ 10x |
| 知识固化 | 规则 + 模式 + trace |

## 3. 范围（现状审计 + 增量）

- **现状**: research_orchestrator 的 assess/utilize/evaluate/learn 为占位接口
- **增量**: 补全 4 接口 + 全链路 gate + 2 个代码变更（I1/I2）+ 7 单测 + 6 报告

## 4. 交付物

见 s61_gate_report.md §5
