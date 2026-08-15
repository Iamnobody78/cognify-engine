# Maintainers

## 当前维护者

| 角色 | ID | 职责 |
|---|---|---|
| **项目负责人 / 最终裁决者** | Iamnobody78 | 战略方向、Sprint 签收、发布决策 |
| **旗舰主体维护者** | BottleSumo 旗舰 Agent | bottlesumo_pi/ 9 层架构、仿真、训练 |
| **Dashboard 维护者** | Dashboard Agent | governance_engine 门面、API、前端、策略编辑器 |
| **治理引擎维护者** | agent-governance-v2 | 协议网关/验证通道/MCE/VCE（独立仓库） |

## 治理流程

1. **裁决门**：实质性变更先方案 + 验收标准，经维护者裁决后启动；bugfix 可直推。
2. **8-GATE**：所有贡献走 [CONTRIBUTING.md](CONTRIBUTING.md) 的 8 道门。
3. **审计链**：Phase 完成追加 `.aionui/audit_log.md` AUDIT-NNNN。
4. **契约优先**：既有测试是契约；违反 = 重写，须 PR 说明。
5. **文档与代码同提交**：架构级变更同提交更新 ARCHITECTURE.md + CHANGELOG.md。

## 权限矩阵

| 操作 | 贡献者 | 维护者 |
|---|---|---|
| 开 Issue / PR | ✅ | ✅ |
| 合并 PR | ❌ | ✅ |
| 部署生产协议 | ❌ | ✅（经 Dashboard 通道，带 .bak 回滚） |
| 发 Release | ❌ | ✅ |
| 修改治理铁律 | 提 PR | ✅ 终审 |

## 晋升 / 离职

- 连续 3 个 Sprint 通过 GATE 8 的贡献者可申请加入。
- 连续 2 个 Sprint 无响应的维护者自动降级为荣誉维护者。

## 安全

安全漏洞**不要**开公开 issue——见 [SECURITY.md](SECURITY.md)。
