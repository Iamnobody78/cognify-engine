# Contributing

贡献指南（与 `CONTRIBUTING.md` 互补）。

## 开发流程

1. **Fork** 仓库并克隆
2. 创建特性分支：`git checkout -b feat/xxx`
3. 编码 + 测试：`pytest tests/ -q`（全量必须通过）
4. 运行 Critic：`python -m src.critic.runner`（GATE 8 必须 PASS）
5. 提交（遵循规范 Commit Message + 签名）
6. 推送并创建 PR

## 提交规范

```
[AUDIT-00XX] 摘要（冒号后动词开头，如 修复/新增/重构）
```

示例：`[AUDIT-0046] 新增: Tree-sitter AST 硬阻断引擎 (v1.25.0)`

## PR 检查清单

- [ ] `pytest tests/ -q` 通过（≥574 passed）
- [ ] `python -m src.critic.runner --all` 通过（GATE 8 5/5）
- [ ] 新功能附带测试用例
- [ ] 文档同步更新（README / docs / Wiki）
- [ ] 版本链更新（如涉及：快照 + ci.yml GATE 7）
- [ ] 提交已签名（ED25519，如可用）

## Good First Issues

以下 Issue 对新手友好，欢迎认领：

1. **[GOOD-FIRST] 添加 Docker 部署支持**（Dockerfile + compose + README 章节）
2. **[GOOD-FIRST] 性能基准测试（P14）**（locust/pytest-benchmark + benchmarks/ 目录）
3. **[GOOD-FIRST] OpenAPI/Swagger 文档（P16）**（docs/openapi.yaml 覆盖全端点）

## 代码风格

- Python 3.10+，类型标注
- Ruff lint 零错误（15 类规则）
- 测试用 unittest 风格（含裸 assert 满足 Critic-Test T1）
- 不引入新正则到 AST 引擎（S-expression 查询在 `queries/*.scm`）

## 行为守则

所有贡献者必须遵守 [CODE_OF_CONDUCT](https://github.com/Iamnobody78/agent-governance-v2/blob/main/CODE_OF_CONDUCT.md)。

## 安全报告

发现漏洞请**不要**创建公开 Issue，按 [SECURITY.md](https://github.com/Iamnobody78/agent-governance-v2/blob/main/SECURITY.md) 私下报告（24h 响应承诺）。
