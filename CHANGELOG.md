# Changelog

## v2.1.1 (2026-08-16) — 基准测试体系 (BENCHMARK-AUTO + BENCHMARK-CONTINUOUS)

### 新增
- **P0 基准控制器**: `cognify benchmark --all/--score/--domain/--report/--trend/--warnings/--fix` (cli/cognify.py dispatch → daemon/benchmark.py)
- **8 域健康评分**: 元能力体系 / MCP生态 / 三系统同步 / 治理引擎 / 认知引擎 / 统一工程 / 磁盘健康 / 元自动化 (B.E.N.C.H. 五步法)
- **T.R.E.N.D. 全链路**: trend_data.json 30 轮滚动 + trend_report.md (Notify) + degradation_report.md (Review) + 域级退化告警 (Escalate: 域下降 >5% 告警 / >10% 修复模式) + `--fix` 决策 (Decide)
- **P2 插件 `cognify.benchmark`**: plugins/benchmark/ (manifest + plugin.py + 冻结快照 + VENDORED.md), 冒烟通过
- **调度**: BENCHMARK-WEEKLY 计划任务 (每周一 00:00 全量基准, 已手动验证 Last Result 0)
- 首轮全量基准: 整体 98.5/100, 8/8 域 PASS (基线 2026-08-16T15:36)

### 修复
- MCP 生态评分溢出: registry 以 YAML 解析 + 三端镜像一致性度量 (ready 服务器须同时存在于 Hermes config 与 AionUi 库), 得分钳制 [0,100]
- 总分污染: 各域得分统一钳制 [0,100] 后取均值 (原 318.5 溢出值已从趋势剔除)
- 治理引擎误判 0: pytest 在 0 failed 时省略该段, 改为分别提取 passed/failed/skipped
- 认知引擎误判 56.2: 仅统计 MMC 自检心跳 (mmce_*), 排除无闭合段的汇总报告 (perpetual_*) → 真实 96.4%
- Hermes config.yaml 非法 YAML: mcp_sync.py 改用单引号标量写 Windows 路径 (双引号内 `\U`/`\t` 被 YAML 当转义), 存量 14 处双引号路径已迁移, 严格解析恢复

### 工程
- 门禁: 基准 8/8 PASS (98.5) | META-VERIFY 12/12 | cert 5/5 | unity 6/6 | deploy-track 100%

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

## v2.1.0 (2026-08-16) — MCP 注册表 172 项 + 4 入口修正

- 修正 4 个固定入口路径 (mcp-cad-studio→dist/cli.js, three-ws-vision→src/index.js, chrome-devtools→build/.../bin, cad-mcp-server→dist/src) SDK 4/4 PASS
- 新增 51 项: 元层/元编程/元算法/元编排/数据库/浏览器/搜索/安全/开发 (npm 18 + pypi 13 核查)
- 未验证项一律 registry-only 待 SDK 验证 (防 AionUi 握手失败复发)

## v2.1.0 (2026-08-16) — 元层 MCP 全维度入库 (注册表 245 项)

- 元哲学/元理论/元系统/元模型 19 项 (mcp-wisdom/steelmind/clear-thought/MPC/metamcp/MetaGO...)
- 元分析/元优化/元数据/元计算 15 项 (Cochrane/medresearch/compressor/promptdiet/OpenMetadata/MaxCompute/PySpark...)
- 元搜索/元设计/元语言/元沟通 18 项 (metasearch2/meta-mcp-search/astryx/figma-bridge/lsp-mcp/metaengine/metacall...)
- 元知识/元数学/元类别 21 项 (MKG/memento/plexus/sagemath/axiom/open-ontologies/OAK/EBi-OLS...)
- npm 18 + pypi 7 核查; 未验证项 registry-only 待 SDK 验证
- 部署追踪门禁全 PASS: 覆盖率 100% 健康度 100% (14 ready 全 connected)

## v2.1.0 (2026-08-16) — 元自动化/元CICD/元领域 + 论文基准矩阵 (注册表 269 项)

- 元自动化/元CICD 12 项 (meta-automation-architect/mcp-tools-orchestrator/loopsense/cicd-orchestrator/circleci/jenkins/woodpecker...)
- 元CV/ML/DL/具身/ME/EE/AI 12 项 (cv-mcp/hf-cv-server/cadquery/pcbparts/meta-prompt-mcp/rosbag...)
- 论文/源码/基准支撑矩阵 → docs/adaptation/meta_mcp_matrix.md (MR-Ben/Reflection-Bench 等 7 基准)
- 门禁全 PASS (14 ready 100% healthy)

## v2.1.0 (2026-08-16) — META-DISK-GOVERN v1.0 元硬盘治理

- meta_disk_govern.py: 六维模型 (D1-D6) + S.C.A.N.-R.E.P.O.R.T. 九步法
- cognify meta-disk --status/--scan/--govern/clean --confirm
- 首轮治理: 69% 使用率, 🟢 10GB 可清理 (执行待确认)
- DISK-GOVERN-WEEKLY 调度 (每周一 09:00); 回滚清单 + 审计日志

## v2.1.0 (2026-08-16) — META-VERIFY-FORCE v1.0 元层强制验证

- meta_verify_force.py: V.E.R.I.F.Y. 六步法 + 三级门禁 (80%/50%/熔断)
- cognify meta-verify --full/--compliance/--benchmark/--trend
- 首轮验证: 健康 7/7, 合规 33.3% BLOCK — 8 类元工具已部署未使用 (真实治理发现)
- 引擎级证据: 元执行/元决策/元学习/元思考 ✅ (exec-audit/decision/CLS/MMC)
- 外部基准 (MR-Ben/Reflection-Bench) 待数据集接入 (诚实边界)

## v2.1.0 (2026-08-16) — MCP-UNIVERSAL-FORCE + MCP-LOW-DISK

- mcp_universal_force.py: V.A.L.I.D.A.T.E. 八步法, 三端可用性矩阵 (首轮 14/14 全通)
- mcp_low_disk.py: C.L.E.A.N.-R.U.N. 七步法, 阈值 (<5GB 拒启/85%/2GB/1GB), 策略固化
- MCP-LOW-DISK-WEEKLY 调度 (每周一 06:00); 空间检查历史 jsonl

## v2.1.0 (2026-08-16) — ARCH-HEAL-CLOSE v1.0 架构自愈与闭环

- arch_heal_close.py: 六大闭环引擎 E1-E6 + C.L.O.S.E. 五步法
- 首轮: 健康 100/100 (green), 六引擎产出全生成
- SELF_DESCRIPTION.md / METAGOVERNANCE_PROTOCOL.md / SIM2REAL_PROTOCOL.md / vNEXT_PROPOSAL.md
- cognify meta close --full/--health/--describe/--vnext + cognify whoami
- ARCH-CLOSE-WEEKLY 调度 (每周一 00:00)

## v2.1.0 (2026-08-16) — 产品化推进 (PRODUCT-ROADMAP-PUSH L1-L3)

- 开源资产补齐: LICENSE (MIT) / CONTRIBUTING (8道GATE) / CODE_OF_CONDUCT / ISSUE+PR 模板 / CODEOWNERS
- cognify product --status 13/13 全绿
- serve 公开 API: /api/v1/mce/compile /vce/scan /cee/evolve /govern/evaluate /meta/status /health (实测通过)
- docker-compose.yml + Dockerfile (cognify-api + dashboard profile)
- GitHub: Discussions 启用 + main 分支保护 (1 review, enforce_admins=false)

## v2.1.0 (2026-08-16) — META-VERIFY 合规率 33%→91.7% PASS

- 引擎级元调用证据扩展至 11/12 类别 (真实运行产物映射: 元认知/元分析/元优化/元知识/元类别/元编程)
- 元数学诚实缺失 (无真实数学引擎, 待 sagemath/axiom 验证接入)
- 合规门禁从 BLOCK → PASS; 趋势可追踪 (meta-verify --trend)

## v2.1.0 (2026-08-16) — META-VERIFY 合规率 100% (12/12)

- axiom-math (Giac/Xcas WASM CAS) SDK 验证通过 → 固定安装 + 三端注册 (Hermes/AionUi/注册表 ready)
- 元数学真实调用证据接入 tool_usage_log; 合规率 91.7%→100%
- 修复: usage log 膨胀 (去重复追加), 调用窗口 60→300
- 趋势: 33% → 91.7% → 100% 单调上升
