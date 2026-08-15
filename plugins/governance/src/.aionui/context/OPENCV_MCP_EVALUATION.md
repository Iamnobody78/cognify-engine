# 🔍 OpenCV MCP 独立评估报告（Evaluation Chain · 2026-08-05）

> 评估人：agent-governance-v2 自主决策代理（Autonomous Decision Agent）
> 触发：用户指示启动 OpenCV MCP 独立评估链（2026-08-05）
> 上游参考：memory `project-future-capability-backlog.md` #8（visionpower 替代路径）
> 结论预览：**不采纳社区包入治理栈；维护"自建 audit-only 轻量 MCP"方案待触发；BottleSumo 机器人侧可另用社区包**

---

## 1. 事实核查表（证据优先，不依赖简报声称）

| 简报声称 | 核查结果 | 证据 |
|---|---|---|
| "`opencv-mcp-server` 是真实可用、社区维护的替代方案" | ⚠️ **部分成立**：包真实存在，但"社区维护"言过其实 | PyPI: **0.1.2**（仅 3 个版本）；GitHub: **112 stars / 21 forks / 最后推送 2025-09-11（距今 11 个月）** / MIT / 3 open issues |
| "OpenCV 5.0（2026-06 发布）重大升级" | ✅ **已验证（2026-08-05 联网实证）**：GitHub opencv/opencv latest release = **5.0.0（2026-06-06）**；PyPI opencv-python 最新 = **5.0.0.93**（headless/contrib 同步 5.0.0.93）。简报声称属实 | |
| ~~"该包锁定 4.12 线拿不到 5.0"~~ | ⚠️ **修正（2026-08-05）**：`opencv-contrib-python>=4.12.0.88` 是**下界**不是锁定 — 今天全新安装解析到 **5.0.0.93**（能拿到 5.0）。但该包最后测试于 2025-09（当时仅 4.12），**5.0 兼容性无人验证**（休眠项目 = 无人修破坏性变更）→ 采纳风险从"拿不到 5.0"变为"拿得到但可能跑不起来" | PyPI opencv-contrib-python releases = [4.x…, 5.0.0.93]；项目最后推送 2025-09-11 |
| 安装轻量、适合边缘 | ❌ **不轻量** | requires_dist: `mcp>=1.13.1` + `numpy>2.2.6` + **`opencv-contrib-python>=4.12.0.88`**（contrib 全家桶，~90MB+ 轮子） |
| 与 Sidecar 架构契合 | ✅ 成立 | 本工作区 `.aionui/mcp/` 已有 **5 个自建 Python MCP stdio 服务器**先例（fetch/memory/filesystem/research/team_coordinator），运行时 Python 3.12 现成 |
| visionpower 是空头注册 | ✅ 已核实（上轮） | 平台级 `servers.json` 中 status=unavailable，备注指向自建替代路径 |
| 本地可跑 | ✅ 成立 | 系统 Python 3.11.15（≥3.11 满足）；`.venv-research` 已含 mcp + numpy 2.2.6 + PIL；无 cv2（任一路线都需装） |

## 2. 方案对比

| 维度 | A. 采纳 opencv-mcp-server | B. 自建轻量 MCP（audit-only） | C. 暂缓（当前建议） |
|---|---|---|---|
| 工具面 | 通用全家桶：相机/视频/人脸/跟踪（**治理视角 = 攻击面大**，含 camera 控制 + 文件读写） | 仅治理所需：load_image / analyze（无相机、无视频、无写盘） | — |
| 依赖 | opencv-contrib（~90MB, 下界>=4.12.0.88 → 解析到 5.0.0.93 但**兼容性未验证**）+ mcp + numpy | **opencv-python-headless 5.0.0.93**（纯 5.0, 无 GUI 依赖, 比 contrib 小）或先 numpy+PIL 零新增（.venv-research 已有） | 零 |
| 维护 | ⚠️ 11 个月未推送，0.1.x | 自持（本环境已有 5 个自建先例） | — |
| 与治理哲学 | 违背最小权限 | ✅ 契合（least privilege） | — |
| 成本 | ~30 分钟接入 | 1-2 天（含测试） | 0 |
| 适配场景 | ✅ **BottleSumo 机器人侧**（相机/跟踪/人脸正需要） | ✅ 治理侧（输入审核/输出验证） | 当前无调用方（见 §3） |

## 3. 关键架构事实：**治理侧当前没有图像入口**

agent-governance-v2 的 intercept/chat 路径处理的是**文本 JSON**（chat messages），无任何图片摄取路径。这意味着：

- "输入侧图像审核"目前**没有数据源**——构建视觉 MCP 将产生"无调用方的工具"
- 真正的调用方是 BottleSumo（机器人项目），与本仓库问题域不同（上轮用户已明确区分"视觉治理 vs 代码治理"）

## 4. 决策矩阵（触发条件驱动）

| 触发条件 | 行动 |
|---|---|
| 治理流量出现多模态输入（图片消息进入 intercept 路径） | 启动 **方案 B**：自建 audit-only MCP（load_image + 违规检测 + 图表验证），接入语义审计链（复用 judge 8765 + CoT） |
| BottleSumo 视觉立项 | 机器人侧采用**方案 A**（社区包全家桶正合适）或直连 OpenCV，与本仓库无关 |
| 两者皆未触发（**当前**） | 方案 C：保持 backlog，不引入任何新依赖 |

## 5. 采纳建议（待用户裁决）

**推荐：方案 C（暂缓）+ 方案 B 预案入册**。理由：
1. 治理侧无图像入口 → B 现在建设无调用方（违背"最小成本优先"决策规则）
2. 方案 A 的 dormancy（11 个月）+ contrib 重量级依赖 + 通用工具攻击面，**不值得为无调用方的能力引入治理栈**
3. 本环境自建 MCP 范式成熟（5 先例），触发时 1-2 天可交付，风险可控

**若用户现在就要视觉能力**（例如为 BottleSumo 预研），替代动作：在 `.venv-research` 装 `opencv-mcp-server` 做冒烟验证（30 分钟），但不入 agent-governance-v2 依赖。

## 6. 附：环境事实速查

- Python: 系统 3.11.15 / 平台 MCP 运行时 3.12（`C:/Users/ivy/AppData/Local/Programs/Python/Python312`）
- `.venv-research`: mcp ✓ numpy 2.2.6 ✓ PIL ✓（自建路线零新增起步）
- 测试 venv `.venv-b1`: 无 cv2（**不装**——治理栈保持轻）
- 平台 servers.json: visionpower=unavailable（备注已指向本评估）
