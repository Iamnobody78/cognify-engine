# 最终执行操作手册 — 社区就绪激活

生成时间：2026-08-03 · 对应协议：最终综合执行协议 + Wiki 文档体系 + 仓库健康度诊断

## ✅ 自动执行部分（已完成）

| # | 任务 | 状态 |
|---|------|------|
| 1 | Dependabot 配置（.github/dependabot.yml） | ✅ 已提交 v1.24.0 |
| 2 | CodeQL 工作流（.github/workflows/codeql.yml） | ✅ 已提交 v1.24.0 |
| 3 | README 社区徽章 + Wiki 链接（AC7） | ✅ 已提交 fc5f583 |
| 4 | 全量回归 574 passed（AC8 ≥488） | ✅ |
| 5 | 提交 + 快照 v1.25.0 + tag | ✅ v1.24.0/v1.25.0 已推送 |
| 6 | Wiki 10 页资产（docs/wiki/） | ✅ 已提交 92b40b9 |
| 7 | GitHub 远程同步 | ✅ 0 ahead/behind |
| 8 | **Wiki 10 页推送到 wiki 仓库（AC3-4）** | ✅ wiki master 5179d53（用户初始化后自动推送） |
| 9 | **3 个 Good First Issues（AC5）** | ✅ #6 Docker / #7 性能基准 / #8 OpenAPI（含标签） |
| 10 | **Welcome Discussion（AC6）** | ✅ Discussions #9（已启用 has_discussions=true） |
| 11 | **破坏性 dependabot PR 关闭（#1/#2）** | ✅ tree-sitter 0.26.0/1.10.2 升级被锁定，ignore 规则已加 |
| 12 | **CI 全绿（gates-1-8）** | ✅ AUDIT-0047/0048: GATE 1/2a/3/6/6a/6b 修复 + 扫描器精度 |

## 🔲 人工操作（需浏览器，仅剩安全面板 3 项）

### 步骤 1：启用私有漏洞报告（P0）

1. Settings → Security → **Code security and analysis**
2. **Private vulnerability reporting** → 点击 **Enable**

### 步骤 2：启用 Dependabot 警报（P1）

1. Settings → Security → **Code security and analysis**
2. **Dependabot alerts** → 点击 **Enable**
3. （Dependabot 配置 .github/dependabot.yml 已推送，Enable 后自动生效 weekly 更新）

### 步骤 3：启用 CodeQL 扫描（P2）

1. Settings → Security → **Code security and analysis**
2. **Code scanning** → 点击 **Set up** → 选 **CodeQL analysis**
3. 选 **Default** 配置 → **Enable**
4. （.github/workflows/codeql.yml 已推送，Enable 后每周一 03:00 UTC 自动扫描）

### 步骤 4：创建 3 个 Good First Issues（P0）✅ 已完成 → #6/#7/#8（2026-08-03 自动执行）

> 以下内容仅供核对。若需手动重发，路径：Issues → **New issue** → 逐个粘贴以下内容，标签选 `good first issue` + `help wanted`（无标签则先建标签）

---

**Issue 1 标题**：`[GOOD-FIRST] 添加 Docker 部署支持`

```markdown
## 任务描述
为 agent-governance-v2 添加 Docker 支持，创建 Dockerfile 和 docker-compose.yml。

## 预期产出
- Dockerfile：基于 Python 3.10-slim，安装依赖并启动网关
- docker-compose.yml：包含网关服务和可选数据库服务
- 更新 README.md 添加 Docker 部署章节
- 运行 pytest tests/ -q 验证通过

## 技术栈
- Docker
- Python 3.10+
- aiohttp

## 相关文件
- src/main.py（已有）
- requirements.txt（已有）
- docs/wiki/Deployment.md（已有框架，补全 Docker 章节）

## 难度
🟢 新手友好

## 预计耗时
2-3 小时
```

---

**Issue 2 标题**：`[GOOD-FIRST] 性能基准测试（P14）`

```markdown
## 任务描述
为 agent-governance-v2 创建性能基准测试套件，测量网关在不同负载下的表现。

## 预期产出
- benchmarks/ 目录，含测试脚本（locust 或 pytest-benchmark）
- 文档说明当前性能基线（/v1/bench/intercept 路由已存在）
- 测试结果记录到 .aionui/performance/

## 技术栈
- Python 3.10+
- locust 或 pytest-benchmark
- aiohttp

## 相关文件
- src/main.py（/v1/bench/intercept 路由，P14 已实现）
- requirements.txt

## 难度
🟡 中等

## 预计耗时
3-4 小时
```

---

**Issue 3 标题**：`[GOOD-FIRST] OpenAPI/Swagger 文档（P16）`

```markdown
## 任务描述
为 agent-governance-v2 的 API 端点生成 OpenAPI/Swagger 文档。

## 预期产出
- docs/openapi.yaml 或 docs/swagger.json <!-- 状态: 任务模板 — OpenAPI 文档尚未生成,文件不存在;阶段 D 待交付 (AUDIT-0058 D1) -->
- 覆盖所有端点：/v1/intercept、/v1/health、/v1/decisions、/v1/trace/{id}、/v1/chat/completions、/v1/bench/intercept
- 包含请求/响应 schema（五级判定：ALLOW/ALLOW_WITH_WARNING/ESCALATE/DENY/SUSPEND）

## 技术栈
- OpenAPI 3.0
- Python 3.10+

## 相关文件
- src/main.py（端点实现）
- docs/wiki/API-Reference.md（已有端点文档框架）

## 难度
🟡 中等

## 预计耗时
2-3 小时
```

---

### 步骤 5：创建 Welcome Discussion（P0）✅ 已完成 → Discussions #9（2026-08-03 自动执行）

> 以下内容仅供核对。若需手动重发，路径：仓库页面 → **Discussions** → **New discussion** → 类别选 **General**，标题：

`👋 欢迎来到 agent-governance-v2！`

```markdown
## 这个项目是什么？

**agent-governance** 是一个让任何 Agent 都具备元认知、自演进、安全边界三大能力的开源框架。

我们相信：**一个能治理自身的治理框架，才值得被信任。**

## 当前状态

- ✅ 574 测试通过
- ✅ GATE 1-8 全绿
- ✅ 五层架构完整
- ✅ 14 个主线 Phase 完成（P1-P14）
- ✅ Tree-sitter AST 硬阻断引擎（v1.25.0）
- ✅ 社区标准合规（CODE_OF_CONDUCT、SECURITY、模板）

## 你可以做什么？

1. 🐛 发现 Bug？创建 Issue
2. 💡 有新想法？发起 Discussion
3. 🔧 想贡献？挑选 Good First Issue
4. 📖 阅读 Wiki 了解架构
5. 🏗️ 尝试部署，告诉我们你的体验

## 讨论话题

- 💬 **使用体验**：部署和使用过程中遇到什么问题？
- 🚀 **功能建议**：你希望添加什么功能？
- 🧠 **元治理**：关于"用 AI 治理 AI"这个方向，你怎么看？
- 🔧 **贡献指导**：需要什么帮助才能开始贡献？

期待你的参与！ 🎉
```

---

## 验收核对表

| AC | 验收项 | 完成条件 |
|----|--------|----------|
| AC1 | Dependabot 配置 | ✅ 已推送 |
| AC2 | CodeQL 工作流 | ✅ 已推送（Settings Enable 后生效） |
| AC3-4 | Wiki 首页 + ≥4 页 | ✅ 10 页已推送（wiki master 5179d53） |
| AC5 | 3 个 Good First Issues | ✅ #6/#7/#8（good first issue + help wanted 标签） |
| AC6 | Welcome Discussion | ✅ Discussions #9（General 类别） |
| AC7 | README Wiki 链接 | ✅ 已推送 |
| AC8 | 全量测试 ≥488 | ✅ 574 passed |
| AC9 | 快照 v1.25.0 tag | ✅ 已推送 |
| AC10 | GitHub 远程同步 | ✅ 0 ahead/behind |
| — | CI gates-1-8 全绿 | ✅ AUDIT-0047/0048 |
