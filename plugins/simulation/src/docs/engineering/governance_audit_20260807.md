# 治理审计归档 — 跨项目文件污染修复

- **审计日期**: 2026-08-07
- **审计者**: BottleSumo 治理智能体 (Meta-Harness 双环)
- **关联提交**: 5303f90
- **状态**: ✅ 已修复并归档

## 1. 污染根因

**`outer_loop.py` 的 `PARETO_FILE` / `FAILURE_FILE` 指向工作区根**（`REPO_ROOT/../pareto_frontier.md`），而非引擎所在目录。工作区根同时被多个项目共享（AST Guard 调度器项目先写入同一路径），导致：

- `pareto_frontier.md`：1-31 行为 AST Guard 内容（2026-08-03），34 行起为 BottleSumo P1 的 TASK-005d 表（ROUND 1-11 全记录被附加其下）
- `failure_analysis.md`：1-52 行为 AST Guard 内容，54 行起为 P1 的 BottleSumo 段（F-100~F-106 + 轮次记录）
- 污染自 P1 起始提交 2181108 即存在——P1 引擎从一开始就在被污染的混合文件上写入

**为什么功能未受影响**: `variants.py` 的解析器按 marker（`text.find("BottleSumo TASK-005d")`）定位段落，AST Guard 头部对解析无影响。但文件归属混乱，一旦 AST Guard 项目更新其头部或 P1 更新尾部，两个项目互相覆盖对方数据。

## 2. 修复方案（数据零丢失）

| 步骤 | 操作 |
| :--- | :--- |
| 1 | P1 专属段提取：`pareto_frontier.md` 的 `# TASK-005d Pareto` 起（11292 chars）→ `governance/meta_harness/pareto_frontier.md` |
| 2 | P1 专属段提取：`failure_analysis.md` 的 `# BottleSumo TASK-005d` 起（24052 chars）→ `governance/meta_harness/failure_analysis.md` |
| 3 | 三处定位逻辑重定向（meta_harness 优先） |
| 4 | 工作区根两文件还原为 AST Guard 纯内容 + 迁移说明（不删他人数据） |

**定位逻辑修改清单**:

| 文件 | 修改点 |
| :--- | :--- |
| `outer_loop.py` | `PARETO_FILE` / `FAILURE_FILE` → `os.path.join(META_HARNESS_DIR, ...)` |
| `variants.py` | `_find_file()` 搜索基数: `(META_HARNESS_DIR, REPO_ROOT, REPO_ROOT/../..)` |
| `code_agent_proposer.py` | `_find_ws()` 搜索基数: `(META_HARNESS_DIR, WORKSPACE_ROOT, REPO_ROOT)` |

**验证结果**: `load_pareto` → current_best 1.0 (PASS), last_row mh_physics_008（血缘 2e33751）; `load_failure_analysis` → 7 条缺陷全解析; 三处定位全部命中新文件。ROUND 1-11 全记录 + 潜伏注册表 + 附注零丢失。

## 3. 预防措施（SRS 协议新增项）

1. **文件归属检查**（SRS 强制项）: 血缘文件（pareto_frontier / failure_analysis / harness_candidates）的 `PARETO_FILE` 类路径常量**必须指向引擎所在目录**（`META_HARNESS_DIR`），禁止指向工作区根。
2. **写入前归属验证**: 引擎写入血缘文件前，校验文件头部 marker 属于本项目（如 `# TASK-005d Pareto`），不匹配则拒绝写入并报警。
3. **定期审计**: 每个 Sprint 结束时检查工作区根文件是否存在跨项目混合（头部 marker 与尾部内容项目归属不一致）。
4. **`.gitignore` / 命名隔离**: 不同项目的工作区产物应使用独立子目录（如 `bottlesumo_pi/governance/meta_harness/`），避免根目录共享。

## 4. 经验沉淀

- **教训**: 路径常量是最隐蔽的耦合点——"指向工作区根"看似灵活，实则为跨项目污染敞开大门。P1 引擎的 `PARETO_FILE` 从第一天就指向了错误归属。
- **正面验证**: 解析器按 marker 定位的设计（`text.find`）意外提供了容错性——即使文件被混合，数据仍可解析。这验证了"按语义标记定位而非按位置解析"的健壮性。
- **后续**: 建议在 SRS 协议中固化第 3 节四项预防措施，并纳入新会话启动序列自检。
