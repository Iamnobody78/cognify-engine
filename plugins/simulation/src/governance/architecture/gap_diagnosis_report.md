# ARCH-COMPLETE 缺口诊断报告 (gap_diagnosis_report.md)

> 诊断时间: 2026-08-10 | 代理: ARCH-COMPLETE v1.0 | 目标仓库: bottlesumo_pi (main=aecaa1b)
> 方法: 代码/配置实测 + 文档交叉核对（非仅凭印象）
> 输入: README.md / ARCHITECTURE.md / CHANGELOG.md / CONTRIBUTING.md / SECURITY.md / ROADMAP_v2.md / dashboard/backend 全源码 / frontend package.json / .github/workflows / requirements.txt / mkdocs.yml

---

## 0. 已确认的现状（正面基线，避免重复补全）

| 领域 | 现状 | 证据 |
|------|------|------|
| CI/CD | ✅ 6 workflows + dependabot.yml（ci/e2e/docs/release/codeql/stale） | .github/workflows/ |
| 开源资产 | ✅ README/ARCHITECTURE/CONTRIBUTING/LICENSE/SECURITY/CHANGELOG/MAINTAINERS/CoC + mkdocs | 根级 9 件 |
| 策略编辑器 | ✅ 3 端点 + tab6 + 28/28 测试 + E2E 9/9 | dashboard/backend |
| 治理引擎集成 | ✅ 同进程导入（低延迟，但见 GAP-3.1 耦合风险） | governance_engine.py |
| 审计链 | ✅ audit_sink → SQLite（见 GAP-1.2 扩展性） | models.py / database.py |
| 健康检查 | ✅ GET /api/health（见 GAP-6.2 语义不足） | main.py |

---

## 1. L1 可观测性

| 缺口 ID | 缺口 | 实测现状 | 等级 |
|---------|------|----------|------|
| GAP-1.1 | **无统一指标端点**：无法与 Prometheus 集成，无系统级监控/告警 | requirements.txt 无 prometheus-client；main.py 无 /metrics；无指标采集代码 | **P0** |
| GAP-1.2 | **审计日志存储单一**：仅 SQLite 写入，无 ELK/Loki 集成方案；无轮转/归档/清理策略 | models.py 仅 SQLite ORM 表；无日志管道抽象 | P1 |
| GAP-1.3 | **无分布式追踪**：跨旗舰主体/治理中枢请求无 Jaeger/Zipkin 埋点 | 无 OpenTelemetry 依赖与 instrumentation | P2 |

## 2. L2 数据存储

| 缺口 ID | 缺口 | 实测现状 | 等级 |
|---------|------|----------|------|
| GAP-2.1 | **默认库扩展性受限**：SQLite 硬编码，无 PostgreSQL 切换指导 | database.py: `sqlite:///{db_path}`（GOV_DASH_DB 仅覆盖路径非 URL——切 PG 需改代码）| **P0** |
| GAP-2.2 | **140GB 仿真资产无版本化/分发方案** | 无 DVC 配置；无资产 manifest/清单 | P1 |
| GAP-2.3 | **RL 中间状态/模型文件管理未明确**：无中断恢复/实验对比方案 | 无 MLflow/W&B 集成；rl/ 目录无 checkpoint 策略文档 | P1 |

## 3. L3 安全合规

| 缺口 ID | 缺口 | 实测现状 | 等级 |
|---------|------|----------|------|
| GAP-3.1 | **无认证/RBAC**：Dashboard API 与管理界面无用户认证与角色控制 | main.py 无 auth 依赖/中间件；frontend 无登录态 | **P0**（PM 路线图 P1，因"无任何访问控制"我上调——见 §6 裁决说明）|
| GAP-3.2 | **敏感信息管理缺失**：SECURITY.md 未涉及配置文件/API 密钥管理（Vault/env 规范） | SECURITY.md 已存在但无 secrets 章节 | P1 |
| GAP-3.3 | **组件间 TLS 未提及** | 架构文档无传输加密策略 | P2 |

## 4. L4 测试质量

| 缺口 ID | 缺口 | 实测现状 | 等级 |
|---------|------|----------|------|
| GAP-4.1 | **无性能基准测试**：CONTRIBUTING 强调功能测试但无性能基线（P99 决策延迟/审计吞吐）| requirements 无 pytest-benchmark；无 perf/ 目录 | P1 |
| GAP-4.2 | **UI 自动化缺失**：Playwright 计划未实现 | frontend package.json 无测试脚本；无 playwright.config | P1 |
| GAP-4.3 | **140GB 资产测试策略未定义**：CI 仅轻量冒烟，大资产验证策略缺失 | ci.yml 无资产冒烟采样任务 | P1 |

## 5. L5 部署运维

| 缺口 ID | 缺口 | 实测现状 | 等级 |
|---------|------|----------|------|
| GAP-5.1 | **无容器化**：仅本地开发运行，无 Dockerfile/docker-compose/K8s | 根级 Glob `*ocker*` → 无匹配；无 deployment/ 目录 | **P0** |
| GAP-5.2 | **发布/回滚策略未定义**（系统级，非策略级） | release.yml 仅 tag→sdist；无回滚文档 | P1 |
| GAP-5.3 | **备份/恢复计划缺失**：SQLite + 140GB 资产无备份策略 | 无 backup 文档/脚本 | P2 |
| GAP-5.4 | **健康检查探针语义不足**：/api/health 无 liveness/readiness 区分；无自动重启策略 | main.py 单端点 | P2 |

## 6. L6 社区生态

| 缺口 ID | 缺口 | 实测现状 | 等级 |
|---------|------|----------|------|
| GAP-6.1 | **架构层路线图缺失**：ROADMAP_v2.md 是视觉/RL 工程路线图（Sprint 7-28），非生产化路线图 | 需新建 ROADMAP_PRODUCTION.md（或并入 ARCHITECTURE）| **P0**（规划先行，其余 P0 补全的编排依据）|
| GAP-6.2 | **API 版本管理策略缺失**：/api/governance/* 无 v1 前缀 | routers/governance.py 无版本前缀 | P1 |
| GAP-6.3 | **端到端教程缺失**：无"仿真启动 → 治理裁决 → Dashboard 观察"教程 | docs/ 无 tutorial | P1 |
| GAP-6.4 | **API 文档示例/错误码不足**：Swagger 自动生成但无请求/响应示例与错误码表 | 无 docs/api/ 手写参考 | P1 |
| GAP-6.5 | **扩展点未文档化**：无自定义治理规则/策略类型/可视化插件接口说明 | 无 plugins/ 目录与文档 | P2 |
| GAP-6.6 | **SemVer 策略/兼容矩阵未定义** | CHANGELOG 有版本记录无策略声明 | P2 |
| GAP-6.7 | **C4 架构图缺失**：仅文本/表格 | docs 无 mermaid/图 | P2 |
| GAP-6.8 | **ESCALATE 后处理路径未文档化**：升级后由谁介入（人工/高级复审/自动）未定义 | 架构文档无 escalation flow | P1 |
| GAP-6.9 | **策略治理流程（治理的治理）可流程化**：策略提出→评审→测试→部署→变更 | 部分存在（11-col-v1 + deploy gate），缺策略生命周期状态机文档 | P2 |
| GAP-6.10 | **GitHub 生态项**：issues/discussions enablement、branch protection、CODEOWNERS 生效 | 需 GitHub UI/API 操作（PM 已授权 token）| P1 |

---

## 7. 汇总统计

| 等级 | 数量 | 清单 |
|------|------|------|
| **P0** | 4 | GAP-1.1 可观测性指标 / GAP-2.1 PostgreSQL / GAP-5.1 容器化 / GAP-6.1 生产路线图 |
| **P1** | 11 | 1.2 审计日志管道 / 2.2 资产版本化 / 2.3 实验管理 / 3.1 RBAC / 3.2 密钥管理 / 4.1 性能基准 / 4.2 Playwright / 4.3 资产测试策略 / 5.2 发布回滚 / 6.2 API 版本 / 6.3 教程 / 6.4 API 文档 / 6.8 ESCALATE 路径 / 6.10 GitHub 生态 |
| **P2** | 8 | 1.3 追踪 / 3.3 TLS / 5.3 备份 / 5.4 探针 / 6.5 扩展点 / 6.6 SemVer / 6.7 C4 图 / 6.9 策略生命周期 |

## 8. 裁决说明（透明披露）

- GAP-3.1 (RBAC) 按 PM 路线图列为 P1，但本诊断上调为 **P0**：Dashboard 当前**零访问控制**，任何拿到端口的人可部署/回滚治理策略——这是可被利用的攻击面。裁决：本周期 P0 按 PM 清单执行（PG/可观测/容器化/路线图），RBAC 列为 P1 首项，不占用 P0 名额但排在 P1 最前。
- 引擎侧（agent-governance-v2）不在本周期范围；ARCH-COMPLETE 聚焦 bottlesumo_pi 产品化，引擎解耦属 v3.0（GAP 3.x 文档化即可）。
- 治理引擎耦合（同进程 import）已识别为 v3.0 解耦候选，本周期仅文档化约束（GATE：任何引擎变更必须过 dashboard 28/28 + E2E 9/9）。

## 9. 证据文件

- dashboard/backend/database.py（SQLite 硬编码 URL）
- dashboard/backend/requirements.txt（缺 prometheus-client/structlog/pytest-benchmark）
- dashboard/frontend/package.json（缺 Playwright/vitest）
- 根级 `*ocker*` Glob 无匹配（无容器化）
- docs/architecture/ROADMAP_v2.md（内容为视觉/RL 工程路线图）
