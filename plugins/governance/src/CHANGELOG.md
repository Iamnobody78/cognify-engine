# Changelog

本仓库采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格，按治理 Sprint 组织。
版本格式：`v<major>.<minor>.<patch>`，每 Sprint 递增 minor（S63 起）。

## [Unreleased]

## [v2.0.0] — 2026-08-10 · Sprint 69（治理闭环 S63→S69）

### Added
- **治理闭环四阶段**（CVE-S 全链）：
  - S63 可编译：`11-col-v1` 声明式协议 YAML → 编译器生成规则（`protocol_gateway.compile_protocol_rules`）
  - S64 可自省：`mce_introspection.py` MCE 2.0 AST（规则 why-exists / governs / origin）
  - S65 可自审：`vce_scanner.py` VCE 2.0（极化指数 / RuleConflicts / BlindSpots）
  - S66 可验证：`verification.py` 声明验证通道（裸 `satisfied` → `ESCALATE` c=0.6）
- **产品化**（S67-S69）：
  - Governance Dashboard 规格（docs/productization/dashboard_spec.md）
  - `audit_sink` 回调（fail-open，每次裁决可审计）
  - 策略编辑器 API：`GET /policies/{protocol}/source`、`POST /policies/validate`（零副作用）、`POST /policies/deploy`（校验+写入+重建网关+`.bak` 回滚）
  - 路径遍历防护 `_safe_protocol_name`（`[a-z_][a-z0-9_]*`）
- **开源治理资产**（PM P0 清单）：CONTRIBUTING.md（8-GATE）、CODE_OF_CONDUCT.md、SECURITY.md、MAINTAINERS.md、CHANGELOG.md、LICENSE（MIT）、ARCHITECTURE.md、`.github/ISSUE_TEMPLATE/`（YAML 表单）、`.github/PULL_REQUEST_TEMPLATE.md`、examples/

### Changed
- 协议加载改为**schema 校验 fail-closed**（12 必填字段，缺 `expected_output` 等 → load 失败）
- README 定位明确：**AI 代理治理层——安全护栏，不是构建框架**

### Fixed
- S66 谎报漏洞：`satisfied=true` 裸声明不再直通（→ ESCALATE c=0.6）
- S69 测试隔离：deploy 测试使用临时协议目录，不再污染真实 `config/protocols/`

### Security
- 安全相关：`SECURITY.md` 定义漏洞报告路径；修复建议遵循 fail-closed 原则

## [v1.25.0] — 2026-08-03 · 历史基线（五层架构 L1-L5 完整）

### Added
- **L1 基础设施**：`storage.py` SQLite WAL + 批量写入 + 降级缓冲 + Trace CTE；`ha/`（FileLock + Lease + FailoverCoordinator）；`certification/`（ED25519 签名/验证）
- **L2 核心网关**：`auth.py` TenantAuth（API key → tenant_id，401/403 门）；`policy.py` JsonPathIndex 前缀索引；`revoke.py` 撤销注册表
- **L3 治理大脑**：五级判定（ALLOW / ALLOW_WITH_WARNING / ESCALATE / DENY / SUSPEND）；`context_hmac.py` HMAC 信任门（canonical 字段序 + ±300s 防重放）
- **L4 Critic Agent**：GATE 8 五批判者（audit/security/arch/test/docs）并行裁决
- **L5 Meta-Harness**：策略建议生成 + 沙箱隔离（pending_rules/）

### Fixed
- 多阶段 relay_state 语义修正（"全完成仍 IN_PROGRESS" 误报，AUDIT-0038 教训）

---

## 版本历史索引

| 版本 | 阶段 | 日期 |
|---|---|---|
| v1.x | 五层架构 L1-L5 演进（P0-P9） | ~2026-07 → 08-03 |
| v2.0.0 | 治理闭环 CVE-S + 产品化 | 2026-08-10 |

## 如何贡献

新增条目遵循 [CONTRIBUTING.md](CONTRIBUTING.md) 8-GATE 流程。Changelog 必须随代码变更**同一提交**更新（「文档与代码同提交」铁律）。
