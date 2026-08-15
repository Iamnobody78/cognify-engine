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
