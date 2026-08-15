# agent-governance-v2

**一个可迁移的 Agent 治理范式 —— 用 Agent 治理 Agent，让治理框架治理自身。**

![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-574%20passed-green)
![GATE 8](https://img.shields.io/badge/GATE%208-5%2F5%20PASS-green)
![Snapshot](https://img.shields.io/badge/snapshot-v1.25.0-blue)

## 快速导航

- 🚀 [Getting Started](Getting-Started) — 5 分钟上手
- 🏛️ [Architecture](Architecture) — 五层架构详解
- 📚 [API Reference](API-Reference) — 治理端点文档
- 🛠️ [Deployment](Deployment) — 生产部署指南
- 🧭 [Roadmap](Roadmap) — 项目演进路线图
- 🤝 [Governance](Governance) — 治理流程与元能力
- 📝 [Contributing](Contributing) — 如何贡献
- ❓ [FAQ](FAQ) — 常见问题
- 📦 [Releases](Releases) — 版本历史

## 一句话定位

当 AI Agent 越来越强大、越来越自主时，谁来确保它们的行为是安全的、可审计的、与人类意图对齐的？

`agent-governance` 解决了这个问题：**它是一个 Sidecar 治理网关，为任何 Agent 提供"元认知、自演进、安全边界"三大能力，且 Agent 代码零修改。**

## 核心原则

1. **诚实**：每个宣称都有代码证据（Critic-Docs D2 守护版本声明一致性）
2. **可审计**：所有决策记录在 SQLite，可追溯（Trace 因果链 + HMAC 防伪造）
3. **零侵入**：Sidecar 模式，Agent 代码零修改
4. **自举**：用治理框架治理自身（Meta-Binding：本项目由 agent-governance 自举生成并签名绑定）
5. **fail-closed**：任何检查缺失/损坏 → 拒绝服务，绝不静默放行（AST 前门 + 超时熔断）

## 治理口号

> 让 Agent 治理 Agent，让治理框架治理自身。
