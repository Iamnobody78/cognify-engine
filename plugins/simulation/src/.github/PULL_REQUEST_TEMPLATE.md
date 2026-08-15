# Pull Request — BottleSumo 旗舰版

> **先读 [CONTRIBUTING.md](../CONTRIBUTING.md)** —— 8-GATE 流程，PR 是 Gate 5 入口。

## 类型

- [ ] 🐛 Bugfix
- [ ] ✨ Feature（Dashboard / 策略 / 旗舰能力）
- [ ] 📚 文档 / 治理资产
- [ ] 🔧 重构 / CI
- [ ] ⚠️ 架构级（需同步更新 ARCHITECTURE.md）

## 关联 Issue

- Closes #

## 变更摘要

## 验收清单（8-GATE）

- [ ] Gate 1-2：已裁决方案；新行为有测试合同
- [ ] Gate 3：Dashboard `pytest dashboard/backend/tests -q` 28/28 + 主仓库冒烟全绿
- [ ] Gate 4：未违反既有测试契约
- [ ] Gate 5-6：工程规则合规；VCE 无新增冲突
- [ ] Gate 7：audit_log.md 追加 AUDIT-NNNN
- [ ] Gate 8：架构级变更同提交更新 ARCHITECTURE.md + CHANGELOG.md
- [ ] 无 140GB 仿真资产误提交（.gitignore 核对）

## 测试结果

```
（粘贴 pytest/vite build 输出尾部）
```

## 特别声明（涉安全）

- [ ] 本 PR 涉及安全相关变更，已按 SECURITY.md 处理
- [ ] 本 PR 不含谎报：声明均为真实可验证结果
