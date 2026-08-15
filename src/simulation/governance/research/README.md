# RES-AGENT 研究引擎 — 使用说明

**状态**: v0.1 可执行闭环（2026-08-10 落地）
**目的**: 将研究能力从元提示词层面落地为可验证的执行引擎，闭合
"设计-执行断裂"（FS-GOVERN 事件暴露的根因）。

## 模块

| 模块 | 功能 | 状态 |
|------|------|------|
| `paper_retriever.py` | arXiv 实时检索（R0.1 文献）| ✅ 实测通过 |
| `research_gate.py` | 产出门禁（R-gate，与 v9_gate 同构）| ✅ 实测通过 |
| `research_orchestrator.py` | S.A.M.U.E.L. 可执行主循环 | ✅ 实测通过（survey→map）|
| `experimental_design.py` | 实验设计器 | 📋 规划（R0.3）|
| `evidence_evaluator.py` | 证据评估（置信度/效应量）| 📋 规划（R0.4）|
| `knowledge_synthesizer.py` | 知识合成（→工程规则）| 📋 规划（R0.5）|

## 快速开始

```bash
# 1. 文献检索 + 门验证
python3 governance/research/paper_retriever.py \
  --query "VLA tactile manipulation" --max 5

# 2. 产出门禁验证
python3 governance/research/research_gate.py \
  --artifact governance/research/outputs/research_papers_list.json --phase papers

# 3. 完整流水线（survey→map）
python3 governance/research/research_orchestrator.py \
  --task "VLA tactile manipulation contact rich failures" --max 6
```

## R-gate 判据（与 v9_gate 同构的验证层）

| phase | 判据 |
|-------|------|
| papers | ≥3 篇；含元数据；每篇含 id+title |
| patterns | ≥2 模式；每模式含 pattern+evidence |
| experiment | 含自变量/因变量/控制变量；含可证伪预测 |
| evidence | 含置信度；含效应量 |
| synthesis | 含 ≥1 工程规则；含适用边界 |

**设计原则**: 每个产出必须过对应判据才能进入下一 phase 或固化知识库。
这直接防止"产出了但未验证"的断裂（FS-GOVERN 教训）。

## 输出目录

```
governance/research/outputs/
├── research_papers_list.json   # R0.1 文献
├── research_patterns.json      # R0.2 模式
├── critical_notes/             # 五问批判笔记
└── experiment_design.md        # R0.3 (规划)
```

## 边界声明（诚实）

- 当前实现覆盖 S.A.M.U.E.L. 的 S(urvey)/M(ap) + 门验证；A(ssess)/U(tilize)/
  E(valuate)/L(earn) 由 agent 在 orchestrator 循环外执行（深度阅读与知识合成
  依赖 agent 推理，已留接口）。
- 模式提取为最小启发式（摘要关键词），深度模式提取需 agent 参与。
- R0 任务（VLA 失败模式研究）是首个验证案例，结果见 outputs/。
