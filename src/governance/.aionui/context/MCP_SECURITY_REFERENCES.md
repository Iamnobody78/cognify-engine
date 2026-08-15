# 📚 MCP 安全与视觉生态参考库（Verified Reference Registry · 2026-08-05）

> 来源：联网实证核查（PyPI/GitHub/arXiv/IETF API 直查，全部条目可复核）
> 用途：agent-governance-v2 的治理研究参考；评估报告 `OPENCV_MCP_EVALUATION.md` 的外部依据
> 状态：**每条均为 2026-08-05 实测，非二手转述**

## 1. 学术论文（arXiv，全部实测存在）

| 论文 | 与本项目关联 |
|---|---|
| **Model Context Protocol for Vision Systems: Audit, Security, and Protocol Extensions** | 简报声称的"91 个视觉 MCP 服务器审计"来源（78.0% schema-format misalignments / 24.6% coordinate-convention errors）——**视觉 MCP 治理最直接参考** |
| **Registry Descriptions Go Stale Unevenly: An 89-Day Measurement of MCP Registry Drift**（2026-08-02） | **直接佐证本项目发现**：visionpower / opencv-mcp-server 的"注册存在但维护停滞"是系统性现象，非个例 |
| **Exposed by Design: A Dynamic Security Assessment of Internet-Facing MCP Servers at Scale**（2026-07-31） | 暴露面风险实证——与治理网关"最小权限"哲学互证 |
| **MCP-DPT: A Defense-Placement Taxonomy and Coverage Analysis for MCP Security** | 防御布点分类法——可映射到六层治理架构 |
| **MCPShield: Security Cognition Layer for Adaptive Trust Calibration in MCP Agents** | 自适应信任校准——与本项目 judge 裁决思想同源 |
| **SMCP: Secure Model Context Protocol** | 协议层安全扩展 |
| **ChainWatch: Kill Chain-Aligned Sequential Detection for Multi-Step Attacks in MCP-Based AI Agents**（2026-07-20） | 多步攻击检测——CoT 轨迹审计的学术对应 |

## 2. 标准与协议

| 标准 | 状态 | 说明 |
|---|---|---|
| **IETF AIGA Protocol**（AI Governance and Accountability Protocol） | ✅ `draft-aylward-aiga-2`（datatracker 实测） | 治理自主 AI Agent 的实用框架——与"自主决策代理协议"同主题 |

## 3. 视觉 MCP 生态实测（2026-08-05，GitHub API）

| 项目 | stars | 最后推送 | 判定 |
|---|---|---|---|
| OGAM（agent 框架, 非纯视觉） | 2,870 | 2026-08-05 | 类别顶部但非视觉 MCP 专用 |
| **SurfSense**（NotebookLM 替代, REST+MCP） | **15,753** | 2026-08-04 | 简报未强调的活跃大项目 |
| **browser-use** | **107,917** | 2026-08-05 | 简报称 21K+ 严重低估; Rust 核心方向属实 |
| VisionCraft-MCP-Server | 123 | 2025-09-19 | 停滞 |
| **opencv-mcp-server** | 112 | 2025-09-11 | 类别中游（112★ 非垫底） |
| Visual-Enhancement-mcp | 71 | 2026-06-21 | 简报 4 候选中最实在的一个 |
| huashu-doubao-search | 87 | 2026-07-25 | 存在（GitHub-only, 非 PyPI） |
| SearchClaw（RUC-NLPIR） | 108 | 2026-06-16 | 存在（GitHub-only） |
| vision-foundation-mcp | **0** | 2026-07-31 | 零星新仓 |
| deepseek-vision-mcp（lmtttt） | **7** | 2026-05-27 | 无牵引 |
| open-vision-mcp | — | — | **无独立项目**（搜索命中均为无关仓库） |
| wigolo | — | — | 存在（v0.2.1, 仅 2 releases, 极早期） |

**生态结论（对简报的修正）**：简报称视觉 MCP 有"更活跃、更专业的替代方案"——**实测不成立**。4 个具名候选：1 个 0★、1 个 7★、1 个不存在独立项目、仅 Visual-Enhancement-mcp（71★）属实。"丰富生态"实为**稀疏低牵引赛道**（全类别 top ~3K★ 且非专用）。→ **强化评估报告"暂缓 + 自建"结论**：社区无可依赖的成熟视觉 MCP，自建 audit-only 方案（openCV 5.0.0.93 headless）仍是唯一务实路径。

## 4. 对 agent-governance-v2 的启示

1. **MCP 注册漂移是系统性现象**（89 天测量论文）——治理网关对第三方 MCP 的依赖需默认"信任但验证"：接入前实测、运行期健康检查、定期复核（本项目已用 `/v1/health` 实证）
2. **Schema/坐标错误率高达 78%/24.6%**——若未来接入视觉 MCP，坐标约定（bounding box 等）必须作为审计字段校验点
3. **IETF AIGA + MCPShield/MCP-DPT** 提供治理设计语言——六层治理架构可映射其防御布点分类法
4. **联网能力**：本代理已有 urllib（API 直查）+ 内置浏览器工具（页面浏览）双通道；SearchClaw/SurfSense/wigolo 等工具链**不引入治理栈**（.venv-b1 保持零新增），如用户需要可入 `.venv-research` 冒烟验证
