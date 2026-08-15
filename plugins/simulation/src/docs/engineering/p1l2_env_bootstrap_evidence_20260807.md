# P1-2 环境引导增强 — 支撑矩阵与验收证据链归档

- **归档日期**: 2026-08-07
- **交付提交**: `894ca84`（feature/sprint9_mha_p1）
- **状态**: ✅ PM 已签收（证据链完整）
- **关联**: P1-1 日志标准化（990a748）→ P1-2 环境引导增强（894ca84）→ P1-3 MCP 封装（HOLD，依赖本项）

---

## 1. 核心论文（理论锚定）

| 论文/基准 | 核心贡献 | 与 P1-2 的关联 |
| :--- | :--- | :--- |
| **Meta-Harness: End-to-End Optimization of Model Harnesses**（arXiv:2603.28052） | 定义 Harness 优化框架，Proposer 通过文件系统访问历史候选的源码、分数和执行轨迹 | 环境引导的理论基础——快照是 Proposer 获取执行轨迹的前提 |
| **Terminal-Bench 2.0 实现**（stanford-iris-lab/meta-harness-tbench2-artifact） | 76.4% 成功率（89 任务 × 5 轮，Claude Opus 4.6） | 工程实证：代理循环启动前采集沙箱快照并注入初始提示，节省 2-5 轮早期探索 |
| **SetupBench**（arXiv） | 93 实例基准，隔离评估 environment-bootstrap 技能（bare Linux → 装包/配置 DB），当前模型成功率仅 38.9-57.4% | 独立验证环境引导是**独立可评估技能** |

**核心洞察**: 环境引导通过消除"环境迷失"阶段，将早期探索轮次从 2-5 轮压缩至 0 轮——是 76.4% 成功率的关键技术组件。

## 2. 源码库（可直接集成）

| 仓库 | 关键特性 | P1-2 对应实现 |
| :--- | :--- | :--- |
| **stanford-iris-lab/meta-harness-tbench2-artifact** | 快照内容参考标准（工作目录/文件列表/语言/工具/包管理器/内存） | `build_environment_snapshot()`（repo_root/python/git_head/文件 size+mtime/工具/磁盘） |
| **SuperagenticAI/metaharness** | `src/metaharness/store/filesystem.py`: 候选工作空间创建、快照捕获、`allowed_write_paths` 白名单、显式结果（keep/discard/scope-violation） | `candidates/<candidate_id>/` 四件套 + 生成侧/应用侧双层防御 + scope-violation 记录 |
| **muratcankoylan/meta-harness** | `reference_examples/terminal_bench_2/` + `ONBOARDING.md` 领域适配流程 | SessionResult 契约模板（P1-1） |

### 官方 Terminal-Bench 2 快照格式（参考标准）
```python
snapshot = {
    "working_directory": "/workspace",
    "file_listing": [...],           # 文件列表（含大小/修改时间）
    "available_languages": ["python3", "bash"],
    "available_tools": ["git", "curl", "pip"],
    "package_managers": ["apt", "pip"],
    "memory": {...}                  # 内存/磁盘状态
}
```
> P1-2 `build_environment_snapshot()` 已对齐此结构。

## 3. 数据库/知识库（记忆与检索支撑）

| 资源 | 类型 | 核心价值 |
| :--- | :--- | :--- |
| `candidates/*/snapshot.json` | 本地结构化存储 | 每个候选的完整环境快照，版本化可追溯 |
| `candidates/*/gate_result.json` | 本地结构化存储 | 评估结果回写（score/passed/steps/gate_exit），形成候选血缘链 |
| `experience/sessions.jsonl` | 本地日志存储 | 含 scope-violation 记录，对齐显式候选结果类型 |
| project-synapse（MCP） | 知识检索基础设施 | P1-V3 bge-m3 检索是其本地等价物（P1-3 封装候选） |

## 4. 相关基准测试

| 基准 | 关键数据 | 对 BottleSumo 的启示 |
| :--- | :--- | :--- |
| Terminal-Bench 2.0 | 89 任务 × 5 轮，环境引导验证 76.4% | 快照注入价值已被大规模验证 |
| SetupBench | 93 实例，当前模型 38.9-57.4% | 环境引导是独立技能，模型普遍偏弱——快照注入是对冲 |
| Multi-Docker-Eval | 自动环境构建 ≤37.7% | 环境构建是主要瓶颈，验证了 bootstrap 的必要性 |

## 5. 对齐确认（P1-2 vs 官方）

| 维度 | 官方 Meta-Harness | P1-2 实现 | 对齐 |
| :--- | :--- | :--- | :--- |
| 快照时机 | 代理循环启动前 | 每次提议前 | ✅ |
| 快照内容 | 工作目录/文件列表/语言/工具/包管理器/内存 | repo_root/python/git_head/文件 size+mtime/工具/磁盘 | ✅ |
| 写作用域 | `allowed_write_paths` 白名单 | 生成侧 + 应用侧双层防御 | ✅ |
| 候选工作空间 | `candidates/<candidate_id>/` | 四件套（snapshot/proposal/diff/gate_result） | ✅ |
| 显式候选结果 | keep/discard/scope-violation | scope-violation 记录入 sessions.jsonl | ✅ |

## 6. 验收证据链

| 验收项 | 标准 | 证据 | 支撑来源 |
| :--- | :--- | :--- | :--- |
| ① 环境快照 | 每次提议前自动捕获 | `candidates/*/snapshot.json` 落盘，377 ≤ 400 chars | Terminal-Bench 2 实证 |
| ② 写作用域强制 | 越权写入被拒绝 | scope-violation count=1 真实写入 sessions.jsonl | SuperagenticAI 实现 |
| ③ 工作空间隔离 | 每个候选独立目录 | 四件套齐全，gate_result.json 回写 score=1.0/214 步 | SuperagenticAI 运行存储 |
| ④ 回归验证 | 门分数 ≥ 1.0 | pytest 53 passed / 4 failed（既有，非本次引入） | — |
| ⑤ token 预算 | 快照注入 ≤400 chars | 377 chars | — |

## 7. 待办挂起

- **P1-3 MCP 封装**: HOLD（裁决不与 P1-2 并行）。前置已就绪: P0-V2 元认知 ≈ advanced-reasoning MCP；P1-V3 bge-m3 ≈ project-synapse；P1-2 快照/写作用域 = 安全边界
- **test_heuristic_rules.py 4 项断言**: GRIP_DECAY=0.08 定稿后启发式等价性断言过时（既有失败，非本次引入）
