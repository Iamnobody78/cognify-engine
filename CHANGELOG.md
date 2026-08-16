# Changelog

## v2.1.0 (2026-08-15) — 产品化路线图 (PRODUCT-ROADMAP)

### 新增
- **P0 认知服务 API**: `cognify serve` — FastAPI 服务, 端点 `/mce` `/vce` `/cee` `/health` (cli/serve.py)
- **P1 治理网关**: `/governance/evaluate` 五层裁决端点 (复用 protocol_gateway.evaluate_verified)
- **P1 文档站点**: mkdocs 站点部署 GitHub Pages (https://iamnobody78.github.io/cognify-engine)
- **P2 PyPI 就绪**: pyproject.toml + `cognify` 包 (__init__/__main__/_cli) + console script, 本地 `pip install -e .` 验证通过
- **P3 插件注册表**: 自托管 `plugin_registry_remote.json` + `cognify plugin search/install`
- **CROSS-LEARN-SYNC v1.0**: 跨系统元学习引擎 (L.E.A.R.N. 五步法, learning/ 账本, 一致性红线 ≥90%)

### 修复
- 元哲学探针 (BOUNDARY.md 迁移 governance/boundary/) → 25/25 恢复

### 工程
- 债务 13/21 | 认证 CERTIFIED 5/5 | 永续心跳 #1-#5 | CLS-ROUND 1-2

## v2.0.0 (2026-08-15) — PLUGINIFY 插件平台

- core/plugin_manager + event_bus + plugin_base
- 7 插件 (governance/simulation/cognitive/sync/meta/debt/dashboard)
- cognify plugin list/info/enable/disable/verify + pluginify --all
- 统一迭代流程: verify --unified / sync --upstream / redirect / test --plugin
- 公开仓库 + develop 分支 + 原仓库 CI 收编

## v1.0.0 (2026-08-15) — 认知操作产品

- 七资产统一入口 (status/heartbeat/cert/package/observe/demo/docs)
- subtree 历史合入 (governance/simulation)
- 认证 CERTIFIED 4/4

## v2.1.0 (2026-08-15) — 三方 MCP 统一接入

- UNIFIED MCP REGISTRY: config/mcp_registry.yaml (52 项, ready/pending-* 分类)
- daemon/mcp_sync.py: 一处配置三处同步 (Hermes config.yaml +8 / AionUi mcp_servers 表 +9 / DSH 参考)
- 接入: filesystem/git/github/fetch/memory/sequential-thinking/sqlite/playwright/chrome-devtools/cognify
- AionUi DeepSeek Harness (DSH ACP) 修复: 桥接文件恢复 + Python312 稳定运行时

## v2.1.0 (2026-08-15) — 元执行监督 (M26-M30) + 版本自主管理 (M31-M35) + ME/EE MCP

- META-EXECUTOR: meta_executor.py E.X.E.C.U.T.E. 七步法, 元能力 25→30 维 (30/30 active)
- cognify meta-exec --status/--audit/--bootstrap/run
- VERSION-AUTO-UPDATE: cognify version --check/--upstream/--history/--sync + update --auto (备份+回滚)
- ME/EE MCP 接入: loki-cad-mcp / mcp-cad-studio / cad-mcp-server (ready 13) 三系统同步
- 注册表 77 项 (ME 15 / EE 9 / pending-* 分类)

## v2.1.0 (2026-08-15) — MCP-DEPLOY-TRACK + MCP 握手修复

- MCP-DEPLOY-TRACK v1.0: mcp_deploy_track.py (D1-D5 五维模型 + T.R.A.C.K. 五步法 + 四门禁)
- cognify mcp track --full/--status/--history/--compliance
- 清单: ~/.cognify/mcp_registry/deployment_manifest.yaml (13 条)
- MCP 握手修复: 路径斜杠规范化 (Node CreateProcess) + npx 缓存预热
- 部署追踪诚实门禁: 7/13 healthy → WARN (待 AionUi 重测后转 PASS)

## v2.1.0 (2026-08-15) — MCP 握手根因修复 (SDK 双模帧)

- 根因1: 新版 MCP SDK (2025-11-25+) stdio 用换行分隔 JSON, 服务器只认 Content-Length → 握手超时
- 修复: cognify_mcp_server.py 双模帧 (自动检测, 兼容新旧客户端)
- 根因2: @modelcontextprotocol/server-git/fetch/sqlite 官方 npm 未发布 (404) → 注册表降级 registry-only + 三系统清理
- SDK 同款客户端验证: cognify 291ms / sequential-thinking / memory (9 tools) / mcp-cad-studio (13 tools) 全 PASS
- 三方统一清单: mcp-registry/ 分发至 Hermes/DSH/AionUi 三域

## v2.1.0 (2026-08-16) — AI/ML/DL + 具身/CV MCP 接入 (~120 项注册表)

- AI/ML/DL 23 项: three-ws-vision/image-recognition/llm-vision/visionsearch (npx 验证) +
  tabicl/automl/mlflow/neo/ultimate (uvx pypi 验证) + zerofit/predicatalot (docker)
- 具身/CV 30 项: 精确分类 (pending-hardware 5 / pending-app 14 / registry-only 8 / pending-key 3)
- pypi/npm 核查: 12 存在 / 5 缺失 (ml-lab/datascience/tabpfn/mujoco 包名待确认, 如实 registry-only)

## v2.1.0 (2026-08-16) — MCP 固定入口化 (13/13 服务器)

- 根因: npx 每次解析开销 10-18s 超 AionUi 握手窗口 (8-10s)
- 方案: 固定安装 13 个 ready 服务器到 ~/.aionui-tri-sync/mcp-server/, node 直连
- SDK 同款客户端实测: 13/13 PASS, 平均 1.6s (0.7-3.5s)
- 修复: llm-vision 需 mcp 子命令 (7 tools); visionsearch npx 路径 bug → 固定入口直连 (8 tools)
- neo-mcp uvx 崩溃 (.fsutil 导入失败) → 移除/降级; loki-cad-mcp 误降级修正
- AionUi + Hermes 13 行全部切换固定入口; 注册表 14 ready
