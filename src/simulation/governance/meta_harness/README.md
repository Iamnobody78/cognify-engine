# meta_harness 目录结构规范 (v1.0)

> 本目录是 Meta-Harness 双环架构的执行体。**根目录只放核心框架文件，禁止平铺调试/日志/报告工件。**
> 违反者 = 目录污染恶习 (RULE-MC-015)。

## 目录结构

```
meta_harness/
├── (根目录)            核心引擎 + 文档 + 状态 (39 文件, 强耦合, 勿拆)
│   ├── *.py           核心引擎 (bootstrap_loop / meta_bootstrap / self_evolve /
│   │                  permanent_anchor / uncertainty_source / variants /
│   │                  outer_loop / code_agent_proposer / cell_learner /
│   │                  distill_loop / meta_architect / meta_edu / meta_kb /
│   │                  meta_monitor / meta_config / semantic_retriever / ...)
│   ├── *.md           文档与规则 (meta_engineering_rules / ROADMAP /
│   │                  domain_spec / failure_analysis / pareto_frontier / ...)
│   └── meta_*.jsonl   状态 (meta_decisions / meta_capability_scorecard / ...)
│
├── mcp_servers/       MCP 服务器 (meta_cognition / semantic_retrieval / ...)
├── tests/             测试
├── variants/          变体生成输出 (与 variants.py 对应)
├── candidates/        候选方案
├── experience/        经验库
├── self_reports/      自评估报告
├── architecture_export/ 架构导出
│
├── scripts/           调试/诊断/探针脚本 (*.ps1 / *.sh / 一次性 *.py)
├── logs/              日志 (*.log / *.err / *.xml)
├── reports/           Sprint 执行报告 (sprint*.md)
├── test_artifacts/    测试工件 (s17*.json 等)
└── _tmp/ _cache/ __pycache__/ .pytest_cache/  临时/缓存 (git-ignored)
```

## 核心引擎清单 (根目录, 强耦合)

| 引擎 | 职责 | 关键依赖 |
|:--|:--|:--|
| bootstrap_loop.py | 数据驱动自举闭环 (scan→select→allocate→formalize) | meta_engineering_rules.md, meta_capability_scorecard.md, ROADMAP.md, meta_decisions.jsonl |
| meta_bootstrap.py | S.E.L.F. 演进引擎 (assess→evolve) | import bootstrap_loop |
| self_evolve.py | D1-D7 自我评估 + S.E.L.F. 循环 | self_evolve_state.json |
| permanent_anchor.py | A.N.C.H.O.R. 永久锚定 + SHA-256 | governance/anchors/ |
| uncertainty_source.py | 三通道不确定性来源识别 (RULE-MC-014) | uncertainty_annotations.jsonl |
| variants.py | 变体生成器 (harness 层) | simulation/*.py (firmware 仓库) |
| outer_loop.py | 外环编排 (apply→evaluate→pareto) | variants.py |
| code_agent_proposer.py | LLM 变体提议器 | variants.py |

## 规则 (RULE-MC-015)

1. **根目录只放核心引擎/文档/状态**，绝不投放一次性调试脚本、日志、报告、测试工件。
2. 新脚本 → `scripts/`；新日志 → `logs/`；sprint 报告 → `reports/`；测试工件 → `test_artifacts/`。
3. 每次任务完成后执行 **META-THINK 元思考**（T.H.I.N.K. 五步），Phase N 检查是否污染了目录。
4. 临时脚本用完即删，不留 `_xxx_tmp.py` / `_verify_tmp.py` 残留。
