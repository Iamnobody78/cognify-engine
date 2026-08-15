# Roadmap

项目演进路线图。

## 已完成（v1.0.0 - v1.25.0）

| 里程碑 | 版本 | 内容 |
|--------|------|------|
| 核心网关 | v0.4.0+ | Sidecar 代理 + YAML 策略引擎 + SQLite 审计 |
| Trace 因果链 | v0.5.0 | 决策追踪 + CTE 递归 |
| Context Hook HMAC | v0.6.0 | 治理头防伪造（±300s 防重放） |
| P1-P14 主线 | v1.x | 14 个主线 Phase（认证/超时熔断/语义hook/归档/性能/认证授权...） |
| 五层架构闭环 | v1.13.0 基线 | L1-L5 完整 |
| Meta-Harness | v1.20.0 | 策略建议 + 帕累托前沿 + 元编程声明 |
| P12 Bootstrap | v1.21.0 | 确定性调度器 + codegen 漂移检测 |
| 批判与审计 | v1.22.0 | 14 层 meta-layer 审计 + 28 调度器执行器 |
| P13 认证授权 | v1.23.0 | ED25519 双身份绑定 + 租户隔离 |
| 社区标准合规 | v1.24.0 | CODE_OF_CONDUCT/SECURITY/模板/Dependabot/CodeQL |
| **AST 硬阻断** | **v1.25.0** | **Tree-sitter 零正则前门（Priority 0）** |

## 进行中（v1.26.0 - v1.30.0）

- 🔄 PostgreSQL 支持（替换/并存 SQLite）
- 🔄 性能基准测试套件（P14，Good First Issue #2）
- 🔄 Grafana Dashboard
- 🔄 OpenAPI/Swagger 文档（P16，Good First Issue #3）
- 🔄 Docker 镜像发布（Good First Issue #1）

## 计划中（v2.0.0+）

- ⏳ Kubernetes Operator
- ⏳ 可视化策略编辑器
- ⏳ 智能策略建议（ML-based）
- ⏳ 多 Agent 编排治理（Meta-Scheduler 网格）

## 治理原则

- 每个版本必须有：全量测试全绿 + GATE 8 PASS + 快照 + 审计日志
- 每项能力必须有代码证据（诚实原则）
- 版本链：README ↔ 快照 ↔ main.py ↔ ci.yml GATE 7 四端一致
