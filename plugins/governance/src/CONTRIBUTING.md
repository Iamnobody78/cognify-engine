# Contributing — agent-governance-v2

> 本仓库既是**产品**（非侵入式 Agent 治理网关），也是**治理流程的运行演示**——
> 每一次变更都走审计链 + 快照 + 裁决门。欢迎人类与 AI Agent 贡献。

## 1. 环境准备

```bash
# Python 3.10+（CI 用 ubuntu-latest / 3.11）
python -m venv .venv-b2
.venv-b2/Scripts/pip install -r requirements.txt
.venv-b2/Scripts/pip install pytest pytest-asyncio pytest-timeout  # test extras

# 可选（真实 SDK 路径，跑 examples/ 的 SDK 分支）
.venv-b1/Scripts/pip install langchain langchain-openai          # LangChain demo
.venv-b2/Scripts/pip install autogen-agentchat aiohttp           # AutoGen demo
```

Windows 下两个 venv 的分工：`.venv-b1` = LangChain SDK；`.venv-b2` = 核心+测试+AutoGen SDK。

## 2. 测试与门禁（GATE 1-8）

```bash
# GATE 1  语法/导入     python -m compileall src tests examples
# GATE 2  策略一致性     python examples/policy_probe.py        # exit 0 = 一致
# GATE 3  单元+集成      python -m pytest tests -q              # 基线 ≥1042 passed（2026-08-10 实测；S63-S66 CVE-S 套件已含）
# GATE 4  B1/B2 契约    python -m pytest tests/test_integration_langchain.py tests/test_integration_autogen.py -q
# GATE 5  认证层自检     python -m src.certification.sign --file <f> && python -m src.certification.verify --file <f>
# GATE 6  示例 E2E       powershell -File examples/run_examples.ps1   # PASS=3 FAIL=0
# GATE 7  架构审计       见 docs/architecture.md 的治理工作文件清单（audit_log / snapshot / debt_registry 一致）
# GATE 8  批判者团队     python -m src.critic.runner            # exit 0 = 通过（多数放行）
```

提交前必须：GATE 1-3 + GATE 8 通过；改 examples/ 或契约测试时加跑 GATE 4/6。

## 3. Agent 治理流程（本仓库的贡献协议）

本仓库是"治理引擎治理自身"的自举演示。**任何变更**（无论人类还是 AI Agent 提交）遵循：

1. **裁决门**：实质性变更（新模块/新 Phase/架构调整）先输出方案 + 验收标准（AC1-AC6），经维护者裁决后启动；纯 bugfix 可直推。
2. **审计链**：每次 Phase 完成后向 `.aionui/audit_log.md` 追加 `AUDIT-NNNN`（PR / 标题 / 变更文件 / 关键修复 / 全量回归数 / GATE 8 结果 / 版本），永久不删改。
3. **快照**：`.aionui/context/TRIPLE_LOOP_SNAPSHOT.md` 版本号递增（vX.Y.Z），记录最近审计 + 最近事件 + 提交链。30 秒恢复：任何会话从快照即可续跑。
4. **提交规范**：`<Phase>: <一句话>（<关键事实>）`；Phase 关闭提交附 `AUDIT-NNNN · 快照 vX.Y.Z · GATE 8 · NNN tests`。
5. **契约优先**：仓库既有测试文件是**契约**（如 `tests/test_integration_langchain.py::TestZeroTouchClaim` 用 AST 证明"零侵入"）。新实现必须先读契约再动手——违反既有契约 = 重写（教训见 AUDIT-0038）。
6. **可迁移性证明**：新增外部生态接入示例时必须可运行、输出含可验证治理证据（DENY/ESCALATE + trace_id）、外部依赖用 try/except 优雅降级。

## 4. 代码风格

- Python 3.10+，类型标注用于公共 API；内部工具函数可省略。
- 测试命名 `test_<模块>_<行为>`；契约测试放 `tests/test_integration_*.py`。
- 不引入新的全局可变状态；网关核心保持无外部服务依赖（SQLite 文件即数据库）。
- 新增依赖必须同步更新 `pyproject.toml` + `requirements.txt`。

## 5. 提交流程

```bash
git checkout -b fix/<描述>        # 或 feat/<phase>
# ... 实现 + 测试（GATE 1-3/8 通过）...
git add -A
git commit -m "<Phase>: <摘要>"    # 见 §3.4 规范
git push origin <branch>          # 开 PR → 维护者裁决 → merge
```

## 6. 问题报告

- 安全/治理绕过：**不要开公开 issue**，直接提交审计日志或联系维护者（本仓库以"暗雷区"方式记录并修复）。
- 普通 bug/增强：开 issue 并附最小复现 + 相关测试名。
