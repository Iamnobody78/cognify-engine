# Contributing to BottleSumo 旗舰版

> **先读本文件**。本仓库执行 **8-GATE 治理流程**——这是与 agent-governance-v2 治理引擎
> 同步的"治理自身"自举闭环。所有贡献（含 AI Agent 贡献）一律走 GATE。

---

## 1. 仓库定位（贡献前必读）

- **两层内容**：① BottleSumo 旗舰主体（9 层物理架构，140GB 仿真资产在 WSL 侧，git 只存代码与轻量资产）；② Governance Center Dashboard（FastAPI + React）。
- **治理中枢**：Dashboard 是治理引擎的产品化门面；对治理引擎的修改在 [agent-governance-v2](https://github.com/Iamnobody78/agent-governance-v2) 仓库。
- **红线**：Dashboard 部署策略必须走引擎的校验/回滚通道；禁止绕过。

## 2. 8-GATE 流程

| GATE | 名称 | 动作 | 验收 |
|---|---|---|---|
| 1 | 方案 | 输出方案 + 验收标准（AC1-AC6） | 经维护者裁决（实质变更）；bugfix 可直推 |
| 2 | 合同 | 在测试中锁定行为（先写失败测试） | 新测试失败且原因明确 |
| 3 | 单元+集成 | `python -m pytest tests/ -m smoke -q`（主仓库）+ `cd dashboard/backend && python -m pytest tests -q` | 主仓库冒烟全绿；Dashboard **28/28 PASS**（2026-08-10 基线） |
| 4 | 契约 | 既有测试是契约，不得违反 | 违反 = 重写，须在 PR 说明 |
| 5 | 批判 | 自审：`governance/dashboard/engineering_rules.md` 合规 | RULE 表逐条对照 |
| 6 | 自审 | VCE 视角：变更是否引入规则冲突/盲点 | 扫描无新增冲突（或已注明） |
| 7 | 审计 | `.aionui/audit_log.md` 追加 AUDIT-NNNN | 永久记录，不删改 |
| 8 | 文档 | 架构级变更同提交更新 `ARCHITECTURE.md` + `CHANGELOG.md` | 「文档与代码同提交」 |

## 3. 本地开发

```bash
# Dashboard 后端
cd dashboard/backend
pip install -r requirements.txt
python -m pytest tests -q          # 28/28 PASS

# Dashboard 前端
cd dashboard/frontend
npm install
npm run build                       # vite build (39 modules)

# 主仓库轻量冒烟
cd <repo-root>
python -m pytest tests/ -m smoke -q
```

> ⚠️ **CWD 铁律**：pytest 必须在仓库根或对应子目录运行。在会话根目录运行会导致 config
> 相对路径解析失败 → 假失败/假通过（S66 已记录教训）。

## 4. 新增协议（Governance 贡献）

协议是 11-col-v1 声明式 YAML（12 必填字段），位于治理引擎仓库 `config/protocols/`：

```yaml
schema_version: 11-col-v1
protocol:
  module: my_protocol
  category: ...
  level: 1
  core_purpose: ...        # 一句话目的
  metacognitive_q: ...     # 自省问题
  collab_directive: ...    # 协作指令
  trigger: ...             # 触发条件
  ethics_boundary: ...     # 伦理边界（编译为 DENY 规则）
  source: ...              # 来源（可追溯）
  frequency: always
  strategy: ...
  expected_output: ...     # 必填！缺此字段 schema 校验失败
```

**部署通道**：Dashboard `POST /api/governance/policies/deploy`（校验→写入→重建网关→快照，带 `.bak` 回滚）。
**禁止**：绕过部署通道直接改 `config/protocols/` 生产协议。

## 5. 提交规范

```
S<sprint> <track>: <一句话摘要>

- 变更明细（bullet）
- 验收证据（测试数/构建结果）
```

示例：`S69 Track1: 策略编辑器完整实现 — 后端 validate/deploy/source 端点 + 前端编辑器标签页`

## 6. PR 检查单

- [ ] GATE 1-8 逐条通过（见 §2）
- [ ] 测试结果已粘贴（主仓库冒烟 + Dashboard 28/28）
- [ ] `git diff --check` 无空白错误
- [ ] 若为架构变更：`ARCHITECTURE.md` + `CHANGELOG.md` 同提交
- [ ] 无 140GB 仿真资产误提交（`.gitignore` 核对）

## 7. 行为准则

见 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)（Contributor Covenant 2.1）。
