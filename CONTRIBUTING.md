# 贡献指南 (CONTRIBUTING)

欢迎贡献 Cognify Engine！本指南帮助外部开发者理解、使用并贡献。

## 快速开始

```bash
git clone https://github.com/Iamnobody78/cognify-engine.git
cd cognify-engine
python -m pip install -e .          # 本地安装
python cli/cognify.py status        # 验证运行
python cli/cognify.py cert          # 认证检查
python cli/cognify.py test --plugin core   # 核心测试
```

## 提交规范 (Conventional Commits)

- `feat(scope): 描述` — 新功能
- `fix(scope): 描述` — 缺陷修复
- `docs(scope): 描述` — 文档
- `chore(scope): 描述` — 工程杂项
- `refactor(scope): 描述` — 重构 (不改变行为)

示例: `feat(governance): 新增 LLM 语义验证器插槽`

## 测试要求

- 所有新代码必须附带测试 (plugins/governance 全量 1038+ 测试为基准)
- 提交前必须通过:
  - `python cli/cognify.py test --plugin core` (核心单测)
  - `python cli/cognify.py cert` (认证 5 项)
  - `python cli/cognify.py verify --unified` (三仓库融合)
- 回归套件: `cognify test --plugin governance` (需 venv python)

## 分支与 PR 流程

1. 从 `develop` 切出 `feature/plugin-*` 分支
2. 提交符合 Conventional Commits
3. 开 PR 到 `develop`, 通过 8 道 GATE 检查:
   - [ ] 代码格式 (与现有风格一致)
   - [ ] 单元测试通过
   - [ ] 认证检查通过
   - [ ] 无 secrets 泄露
   - [ ] 文档已更新
   - [ ] CHANGELOG 已更新
   - [ ] 无破坏性变更 (或已声明)
   - [ ] 自测证据附上

## CLA 签署

提交 PR 即视为同意 MIT 许可条款下贡献代码。
如有公司雇佣关系, 请确认雇主授权。

## 维护者流程

- Issue 响应 SLA: 48 小时内回复
- PR 评审: 7 天内
- 标签: `good-first-issue` / `help-wanted` / `bug` / `enhancement`

## 插件开发

见 [docs/plugin_development.md](docs/plugin_development.md) — 生命周期钩子/依赖声明/事件总线/红线。
