# Maintainers

本仓库由以下维护者负责。维护者的裁决是仓库的最终治理门（8-GATE 之外的第九道门）。

## 当前维护者

| 角色 | 姓名 / ID | 职责 |
|---|---|---|
| **项目负责人 / 最终裁决者** | Iamnobody78 | 战略方向、Sprint 签收、GATE 8 结果终审、发布决策 |
| **治理引擎维护者** | AI Governance Agent（agent-governance-v2） | `src/` 核心模块、协议编译器、验证通道、CI/CD |
| **Dashboard 维护者** | Dashboard Agent（bottlesumo-pi） | Governance Dashboard 后端/前端、策略编辑器、e2e |

## 治理流程

本仓库是"治理引擎治理自身"的自举演示。维护者遵循：

1. **裁决门**：实质性变更（新模块/新 Phase/架构调整）先输出方案 + 验收标准，经维护者裁决后启动；纯 bugfix 可直推。
2. **审计链**：每次 Phase 完成后向 `.aionui/audit_log.md` 追加 `AUDIT-NNNN`，永久不删改。
3. **快照**：`.aionui/context/TRIPLE_LOOP_SNAPSHOT.md` 版本号递增，任何会话 30 秒恢复。
4. **契约优先**：既有测试文件是契约；违反既有契约 = 重写。
5. **文档与代码同提交**：架构级变更必须同一提交更新 [ARCHITECTURE.md](ARCHITECTURE.md) 与 [CHANGELOG.md](CHANGELOG.md)。

## 权限矩阵

| 操作 | 贡献者 | 维护者 |
|---|---|---|
| 开 Issue / PR | ✅ | ✅ |
| 合并 PR | ❌ | ✅（或经过 8-GATE + 裁决） |
| 修改 `config/protocols/`（生产协议） | ❌ | ✅（经 Dashboard 部署通道，带 .bak 回滚） |
| 发 Release / Tag | ❌ | ✅ |
| 修改治理铁律（CONTRIBUTING/ARCHITECTURE 维护条款） | 提出 PR | ✅ 终审 |

## 晋升通道

- 连续 3 个 Sprint 通过 GATE 8 且贡献被合并的贡献者，可申请加入 MAINTAINERS。
- 晋升需项目负责人裁决 + 现有维护者多数同意。

## 离职 / 失效

- 维护者连续 2 个 Sprint 无响应，自动降级为"荣誉维护者"（无合并权）。
- 仓库始终保留"治理规则治理维护者自身"的逃生舱：任何维护者的变更同样走 8-GATE。

## 联系方式

- Issues / Discussions：本仓库 GitHub 页面
- 安全漏洞：**不要**开公开 issue，见 [SECURITY.md](SECURITY.md)
