# Pull Request

> **先读 [CONTRIBUTING.md](CONTRIBUTING.md)** —— 本仓库执行 8-GATE 流程，PR 是 Gate 5 的入口。

## 类型

- [ ] 🐛 Bugfix
- [ ] ✨ Feature（新协议 / 新验证通道 / 新自省能力 / Dashboard 功能）
- [ ] 📚 文档 / 治理资产
- [ ] 🔧 重构 / 基础设施（CI、依赖）
- [ ] ⚠️ 架构级变更（需同时更新 ARCHITECTURE.md）

## 关联 Issue

- Closes #（issue 编号）

## 变更摘要

（1-3 句：改了什么、为什么）

## 验收清单（8-GATE 对照）

- [ ] **Gate 1-2 方案/合同**：实现了已裁决的方案；新行为有对应测试契约（AC1-AC6 或测试名）
- [ ] **Gate 3 测试**：新增/修改测试已写入 `tests/`；本地 `pytest tests/ -q` 全绿
- [ ] **Gate 4 契约**：未违反既有测试契约（既有测试文件是契约；违反 = 重写，需在 PR 说明）
- [ ] **Gate 5-6 批判/自审**：`critic/` 或 VCE 扫描结果无新增冲突/盲点
- [ ] **Gate 7 审计**：涉及 Phase 流程的变更在 `.aionui/audit_log.md` 追加 AUDIT-NNNN
- [ ] **Gate 8 文档**：架构级变更同提交更新 `ARCHITECTURE.md` + `CHANGELOG.md`
- [ ] **铁律**：文档与代码同提交；快照 `.aionui/context/TRIPLE_LOOP_SNAPSHOT.md` 版本递增

## 测试结果

```
（粘贴 pytest 输出尾部：passed / failed 数）
```

## 自测 / 截图

（可选：e2e 截图、VCE 扫描输出、Dashboard 验证）

---

## 特别声明（涉安全 / 治理绕过时必填）

- [ ] 本 PR 涉及安全相关变更（验证通道、判定降级、审计），已按 [SECURITY.md](SECURITY.md) 处理
- [ ] 本 PR 不含**谎报**：声明均为真实可验证结果
