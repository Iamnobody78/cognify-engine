# 事实核查报告 — 远程仓库实况 vs 外部调查结论

> 时间: 2026-08-11 | 依据: GitHub API git/trees/recursive + compare + issues 实测
> 背景: 外部调查声称 bottlesumo-pi"旗舰主体几乎不存在"、dashboard 为空、文档缺失。本报告用远程实况逐条核验。

## 一、远程仓库实测基线（GitHub API，非本地缓存）

### bottlesumo-pi (main 分支, 830 blobs)

| 顶层目录 | 文件数 | 实测内容 |
|----------|--------|----------|
| `core/` | 25 | environment/execution/hil/memory/meta_language/meta_philosophy/observability/output/reality_bridge/self_evolution_closed_loop.py |
| `simulation/` | 129 | 仿真资产与桥接层（非 22KB 胶水——129 文件） |
| `firmware/` | 12 | stm32_mcu: Makefile + ld/stm32f103c8tx.ld + stm32f407vgtx.ld + src/aux_f103.c + dqn_weights.c/h 等 |
| `dashboard/` | 29 | backend 13 文件（main.py/database.py/governance_engine.py/metrics.py/seed.py/routers/governance.py/e2e/ + tests×3）+ frontend 16 文件（App.jsx/6 页面/api.js/vite.config） |
| `models/` | 48 | 模型层 |
| `hardware/` | 21 | 硬件层 |
| `governance/` | 284 | 治理文档与架构（含 gap_diagnosis/completion/verification 报告） |
| `docs/` | 116 | 架构/部署/观测文档 |
| `scripts/` | 13 | 工具脚本 |
| `tests/` | 10 | 测试 |
| `.aionui/` | 40 | 元数据 |
| 根文档 | 19 | **ARCHITECTURE.md / architecture_overview.md / CONTRIBUTING.md / SECURITY.md / MAINTAINERS.md / CODE_OF_CONDUCT.md / CHANGELOG.md / TECH_DEBT_AUDIT.md / LICENSE 全部存在** |

### agent-governance-v2 (main 分支, 335 blobs)

| 目录 | 文件数 | 实测内容 |
|------|--------|----------|
| `src/` | 63 | ast_guard/protocol_gateway/mce_introspection/vce_scanner/verification/agent_tools(self_critic/self_heal/self_trace)/bootstrap/certification/codegen/critic/ha/meta_harness/pareto/proposer/trace 等 12+ 子模块 |
| `tests/` | 79 | 完整测试套件（含 conftest.py） |
| 根文档 | — | README/dockerignore/env.example 等 |

**Issues 实测**: agent-governance-v2 有 **3 个 OPEN GOOD-FIRST issue**（#6/#7/#8, help wanted + good first issue 标签）。bottlesumo-pi issues = 0（仓库重建后未迁移，真实缺口）。

## 二、逐条核验外部调查结论

| # | 外部调查声称 | 实测 | 判定 |
|---|--------------|------|------|
| 1 | bottlesumo_pi/ 目录 404，旗舰主体缺失 | 无 `bottlesumo_pi/` 顶层包（代码按 core/simulation/firmware 顶层分布），**核心代码 830 文件全量存在** | ❌ 误判（结构认知偏差） |
| 2 | firmware/stm32_mcu/ 为空目录 | **12 文件**（Makefile/ld/src 齐全） | ❌ 错误 |
| 3 | dashboard/backend/ 为空目录 | **13 文件**（含 routers、e2e、tests×3） | ❌ 错误 |
| 4 | dashboard/frontend/ 为空目录 | **16 文件**（App.jsx + 6 页面 + api.js） | ❌ 错误 |
| 5 | CONTRIBUTING.md / ARCHITECTURE.md / architecture_overview.md 不存在 | **全部存在**（根目录 19 文档） | ❌ 错误 |
| 6 | agent_tools 为空目录 | **4 文件**（self_critic/self_heal/self_trace/__init__） | ❌ 错误 |
| 7 | 两个仓库 Issues 均为 0 | 引擎 **3 个 OPEN GOOD-FIRST issue**；bottlesumo-pi 确实 0 | ⚠️ 部分正确 |
| 8 | 测试目录不可见 | dashboard/backend/tests/ + 顶层 tests/ 均在远程 | ❌ 错误 |
| 9 | simulation/ 仅 22KB 胶水 | **129 文件** | ❌ 错误 |
| 10 | 所有 PR 死锁 | #17/#13 确实 BLOCKED (REVIEW_REQUIRED) | ✅ 正确 |

**可能误判来源**: 外部调查引用了"页面提示需登录"，疑似基于未登录的 GitHub 网页快照或第三方缓存（非 API 全量树），导致大目录被渲染为空/缺失。

## 三、真实存在的缺口（外部调查命中项，须诚实承认）

| 缺口 | 严重度 | 处置 |
|------|--------|------|
| 140GB 仿真资产存放方式未在 README 说明（资产在本机 /bottlesumo_env/，GitHub 无法验证） | 🔴 高 | README 增加"资产策略"章节：声明本机资产 + 外部存储计划 |
| fail-open 设计警示不足（README 未充分警示审计失效时放行风险） | 🟡 中 | README 增加 fail-open 安全警示 + 默认建议 |
| BaselineDeclarationValidator 为 Noop 基线（LLM/签名验证为未来项） | 🟡 中 | README 明确"当前验证能力 = 语法级 + 规则级，语义级为路线图项" |
| bottlesumo-pi issues = 0（重建后未迁移追踪） | 🟡 中 | 迁移引擎 3 个 GOOD-FIRST 模板 + 新建架构债务 issue |
| 合并死锁未解决（#17/#13 卡 REVIEW_REQUIRED） | 🔴 高 | 待 PM 裁决：bot 账号 / override / 独立 review 账号 |
| CI 只覆盖单元+E2E，140GB 资产仿真未入 CI | 🟡 中 | 路线图项（资产先落地外部存储后接 CI 冒烟） |

## 四、结论

1. **外部调查的"旗舰空心化"指控不成立**——远程 main 分支 830 文件全量存在，核心代码/文档/固件/仿真均非空。
2. **真实缺口集中在"资产可见性"与"协作流程"**：140GB 资产无法远程验证、fail-open 警示不足、验证器为 Noop 基线、issues 未迁移、合并死锁——这些须逐一处置。
3. **最高优先级不变**：解除合并死锁（#17 RBAC + #13 AUDIT），使 ARCH-ROUND 2 进入 main。
