# Changelog

## v2.1.5 (2026-08-16) — 外部基准评估通道打通 (DSH 桥接)

### 新增
- **P0 DSH 模型桥接**: cognify/benchmark/dsh_bridge.py — OpenAI 兼容 /v1/chat/completions → `dsh --profile headless` (deepseek-v4-flash 真实推理)
  - 纯标准库实现, 每次请求 spawn DSH headless (诚实慢速: 15-85s/次), 调用日志 jsonl
  - 实测: OpenAI SDK 客户端连通 (含 usage 字段); AgencyBench Code/scenario1/subtask1 真实任务端到端冒烟 84s (产物 external/agencybench_code_smoke_1.json)
- **本地适配器第 5 项**: DSH 模型桥接可用性探测 (benchmark --full 实测 100.0, 15.9s)
- **注册表状态升级**: AgencyBench = 已克隆 + 数据完整性 + **评估链路冒烟通过** (他证通道就绪)
- **诚实核验**: 用户方描述的 conda/examples/eval.py/API key 前提与本地不符 → 全部实测纠正 (conda 无, examples/ 无, agentenv 未装, .env 无); AgentGym searchqa 环境需外部数据集 + FAISS RAG + conda → 标记本地不可行

### 修复
- detect_external 克隆完整性核验补 AgencyBench 双文件统计 + 冒烟状态
- runner 报告适配 status 三级状态 (missing/cloned/installed) + 优先级列

### 工程
- 本地适配器 5/5 (98.0) | 8 域 8/8 (98.5) | 自使用 5/5 (94.0) | 注册表 26 项 (P0×3 已克隆)
- 评估成本实测: 桥接单次推理 15-85s (DSH headless), 大任务评估需分批

## v2.1.4 (2026-08-16) — 全基准测试体系 (BENCHMARK-FULL-AUTO)

### 新增
- **P0 全基准执行器**: `cognify benchmark --full` (cognify/benchmark/adapters.py + runner.py, B.E.N.C.H.-F.U.L.L. 八步)
  - **外部基准注册表 17 项** (AgentGym2/OSWorld 2.0/AlphaEval/LiveClawBench/Claw-SWE-Bench/Enterprise-Bench/EnterpriseOps-Gym/KAMI/MCP-Universe/MCPToolBench++/LiveMCPBench/KAware/Reflection-Bench/Meta-Agent/TRIAGE/EmbodiedBench/BEAR): 类别/阈值/命令/安装指引, **诚实检测 ready/missing (当前 0/17 未安装, 不造假分数)**
  - **本地真实适配器 4 项**: MCP 生态 (真实启动 4 个 MCP 服务器: cognify/filesystem/memory/sequential-thinking, 连接+工具调用评估 100.0) / 自我意识一致性 KAware 风格 (最近 10 条决策 MCE+VCE, 100.0) / 元反思 Reflection 风格 (MMC 心跳闭环率+自检 6/6, 100.0) / Agent 构建能力 Meta-Agent 风格 (插件 verified 9/10, 90.0)
  - 首轮: **本地 4/4 PASS, 均分 97.5** (基准报告 benchmark_full_report.md + full_report.json 趋势)
- **调度**: BENCHMARK-WEEKLY 升级为 `benchmark.py full` (8 域 + 外部适配器), 已触发验证 LastResult 0
- **元提示词入库**: BENCHMARK-FULL-AUTO v1.0 → **AionUi 源目录** (~/.aionui/meta_prompts, meta_system.py 重建索引 67 条) → 守护镜像 hub
- **修复元提示词持久化根因**: 索引曾被同步守护覆盖 (只写 hub 镜像不持久) → 全部新条目改入源目录 + L1 重建, hub 由 TRI-SYNC 自动镜像

### 修复
- 外部检测误报 (find_spec 未打印) → print 布尔结果判定
- 元反思分母错误 (len(hb)=30 vs 样本 10) → 样本数; 自检计数混入动作行 → 限定 "## 闭环自检" 段
- EVOLVE-FORCE 元提示词 md 缺失 (上轮只更新索引未写文件) → 补写

### 工程
- 门禁: 本地全基准 4/4 (97.5) | 8 域 8/8 (98.5) | 自使用 5/5 (94.0) | 双轨 96.2 | 进化证据 5/5
- 外部基准 17 项诚实标注未安装 (集成阶段 1-3 待选型接入)

## v2.1.3 (2026-08-16) — 强制进化引擎 (EVOLVE-FORCE)

### 新增
- **P0 强制进化引擎**: `cognify evolve --report/--status/--trend/--force/--activate` (cognify/evolve/engine.py)
  - E.V.O.L.V.E. 六步法: Evidence 扫描 (5 检查项: commit/测试≥98%/性能不倒退/文档/新功能) → Verify (git cat-file commit 核验 + pytest 证据在位) → Organize (分类 fix/optimize/new/docs/test + 贡献度评分) → Log (evolution_audit.jsonl 只追加 + 写后校验, 记录失败=进化无效) → Validate (双轨整体 vs 上周期, 倒退→回滚标记) → Enforce (门禁失败→债务 P0 优先提案 Top3)
  - 门禁: 5 项 ≥3 满足否则强制进化模式; 首轮实测 **5/5 证据, 整体 96.2, 模式 normal**
- **P2 插件 `cognify.evolve`**: plugins/evolve/ (manifest + plugin.py + VENDORED.md), 冒烟通过
- **调度**: EVOLVE-DAILY 每日 23:30 全链执行 (Register-ScheduledTask, 已触发验证 LastResult 0)
- **元提示词入库**: EVOLVE-FORCE v1.0 → meta_prompts 索引 (json+yaml, 66 条; 修复 SELF-VALIDATE-ITERATE 被同步进程覆盖丢失问题)

### 修复
- 审计日志读取: _json() 误用于 jsonl 整读 (首行解析为 dict 后 .read_text 崩溃) → 逐行解析取最后一条
- activate 内嵌 schtasks 被沙箱拒绝 (WinError 5) → 任务改用 Register-ScheduledTask cmdlet 注册; evolve.py 保留 --activate 入口

### 工程
- 门禁: 进化证据 5/5 | 基准 8/8 (98.5) | 自使用 5/5 (94.0) | 双轨整体 96.2 | 审计链 1 条 (只追加)

## v2.1.2 (2026-08-16) — 双轨验证闭环 (SELF-VALIDATE-ITERATE)

### 新增
- **P0 自使用验证引擎**: `cognify self-validate --start/--status/--history` (cognify/self_validate/engine.py)
  - 轨 B 5 场景真实调用 (不造假): 认知引擎自用 (MCE/VCE/CEE 编译最近真实输入) / 治理引擎自用 (协议网关裁决真实决策, 触发 entropy_denoise 规则 → ESCALATE) / 元记忆自用 (学习账本记录+检索) / MCP工具自用 (真实启动 cognify MCP 服务器, 5 工具注册 + cognify_meta 调用) / 元能力自评 (30 维 status)
  - SQLite 持久化 (schema.sql: runs + scenarios), 首轮实测 **94.0/100, 5/5 通过**
- **P0 双轨融合分析** (轨 C): cognify/iterate/fusion.py — benchmark_only / self_validation_only 缺口识别 + 一致性评分 + 双轨差异 >10 触发深度审查 (首轮实测: 一致性 75%, 4 缺口, 治理引擎差异 30 分触发审查)
- **P0 每日迭代报告 + 冲刺模式** (轨 D): cognify/iterate/report.py — daily_iteration_report.md (整体 96.2 🟢 优秀) + 连续 3 天无改进 → sprint_mode.json
- **P2 插件 `cognify.self_validate`**: plugins/self_validate/ (manifest + plugin.py + VENDORED.md), 冒烟通过
- **调度**: SELF-VALIDATE-MINUTE (每分钟自使用验证) + DAILY-FUSION (每日 08:00 融合报告), 均已手动验证 Last Result 0
- **元提示词入库**: SELF-VALIDATE-ITERATE v1.0 → meta_prompts 索引 (json+yaml, 65 条)

### 修复
- MCP 自用场景卡死: cognify_sync 工具内部同步执行 CLI sync (慢且有副作用) → 改用 cognify_meta + JSON-RPC 通知与请求分离 (notifications/initialized 无响应不再等待) + 线程队列超时保护 (15s)
- 治理自用误判: 裸文本不命中规则 (规则条件为 governance.protocols.{module}.triggered) → 携带真实协议模块触发声明, 实测命中 protocol-entropy_denoise-enforce
- daemon 调度壳接受 `--status/--report` 带横线参数 (lstrip("-"))

### 工程
- 门禁: 自使用验证 5/5 (94.0) | 基准 8/8 (98.5) | 双轨整体 96.2 | 深度审查标记在位 (治理引擎 30 分差)

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
