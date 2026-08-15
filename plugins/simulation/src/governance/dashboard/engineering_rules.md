# Engineering Rules（工程行为规则库）

> SEFS-ARCH Phase D 持续学习输出。每次 SEED 循环将经验编码为持久规则，
> 实现跨会话工程智慧积累（借鉴 Self-Improving AI Coding Agents）。
> 规则编号：`RULE-<域>-<序号>` | 追加制，永不删除，仅标记 OBSOLETE。

## 数据工程 (FS = Full-Stack)

| ID | 规则 | 来源 |
| :--- | :--- | :--- |
| RULE-FS-001 | **jsonl 数据字段必须先侦察再解析**：加载前统计字段类型/ts 格式/枚举分布，再写 ETL。counter-example: hypotheses 的 `score` 是 dict（`{'winrate':..}`）、`ts` 是 `YYYYMMDD_HHMMSS` 非 ISO | SEED-1 失败#1 |
| RULE-FS-002 | **SQLite 内存库测试必须共享连接（StaticPool）**：`:memory:` 默认每连接独立，多线程/多请求看到空表 | SEED-1 失败#2 |
| RULE-FS-003 | **pytest conftest 不参与模块导入**：测试文件不得 `from conftest import ...`；共享常量放 fixture 或独立 helpers 模块 | SEED-1 失败#3 |
| RULE-FS-004 | **后端聚合精度 ≥ 6 位小数**：`round(x,4)` 产生 ~2e-5 误差会挂掉严格容差断言 | SEED-1 失败#4 |
| RULE-FS-005 | **ETL 必须幂等**：seed 脚本采用 TRUNCATE+重灌语义，可重复执行不产生重复数据 | SEED-1 |
| RULE-FS-006 | **DB 方言可移植**：生产 PostgreSQL、开发 SQLite，ORM 模型避免 DB 专有类型，DATABASE_URL 环境变量切换 | SEED-1 |

## 测试工程 (TS)

| ID | 规则 | 来源 |
| :--- | :--- | :--- |
| RULE-TS-001 | **传感器/方向性类测试优先状态注入而非运动驱动**：测试意图（传感器响应）与运动机制解耦，避免语义变更破坏轨迹可达性 | F-109 (Sprint 14) |
| RULE-TS-002 | **fixture 使用 session.close() 而非 sessionmaker.remove()**：sessionmaker 无 remove 方法（scoped_session 才有） | SEED-1 失败#3b |
| RULE-TS-003 | **测试容差与实现精度匹配**：实现 round(x,6) 则测试断言 <1e-5；先定精度后定容差 | SEED-1 |

## 流程规则 (PR)

| ID | 规则 | 来源 |
| :--- | :--- | :--- |
| RULE-PR-001 | **RNG/状态对齐修复后，检查关联测试是否依赖"运动轨迹到达特定状态"** | F-109 (Sprint 14) |
| RULE-PR-002 | **PowerShell 引号嵌套易碎**：WSL 内 python 长命令一律脚本文件方式执行 | Sprint 14 多次 |
| RULE-PR-003 | **PowerShell Get-Content 显示乱码 ≠ 文件损坏**：cp950 解码伪影，用 Python UTF-8 严格解码验证 | F-110 (Sprint 14) |
| RULE-PR-004 | **git add -A 禁用**（仓库根含大型/长文件名目录）：只 add 具体交付文件 | Sprint 14 合入事故 |

## 对抗策略工程 (AS) —— Sprint 59 学习路径 Phase 4

| ID | 规则 | 来源 |
| :--- | :--- | :--- |
| RULE-AS-001 | **直线推进须在反冲区外**：对手反冲触发距离（如 defensive 0.4）之上必须留余量层（shove_dist=0.45），反冲区边缘正对时改侧向曲线绕行（vectored），不可直线冲锋 | S59 诊断 (edge_f 58%) |
| RULE-AS-002 | **"连续规避步数"计数必须用脱离守卫而非单步安全**：后退一步使传感器脱离临界但仍在危险带（0.1→0.15），单步安全立即清零会饿死计数（锯齿 1→2→1→2 永不到 3）；需连续 2+ 步安全才重置 | S59 诊断 (streak 锯齿) |
| RULE-AS-003 | **边缘规避超时须强制转向**：连续 N 次前缘危险规避后，若直线后退无改善，强制横向转向（选更开阔侧），打破"后退-再接近"固定循环 | S59 诊断 (拉锯 500 步) |
| RULE-TS-004 | **对抗行为测试用状态注入 + 步进序列**：连续帧状态依赖（如 streak）必须用同一 agent 实例多次调用验证，单帧测试无法覆盖跨帧逻辑 | S59 (streak 单帧不可测) |

## 蒸馏与轻量化 (DI) —— Sprint 60 学习路径 Phase 4

| ID | 规则 | 来源 |
| :--- | :--- | :--- |
| RULE-DI-001 | **规则链蒸馏成 MLP 后延迟降幅主要来自"无分支固定计算图"**：延迟收益 (280-318x) 源于去掉逐决策的分支遍历，而非模型参数少本身；部署决策应关注计算图形态而非仅参数量 | S60 (28.4ms→89μs) |
| RULE-DI-002 | **BC 保真度 91% 即可达门级等效**：门测试的决策边界远宽于 val 分布，学生行为"足够接近"教师即可全过；无需追求 100% 模仿，训练预算可放宽 | S60 (val_acc 91.1% → 门 100%) |
| RULE-DI-003 | **蒸馏会隐式压缩教师的早期探测行为**：学生直接学习收敛路径，avg_steps 可低于教师（defensive 216→180）；评估学生时需同时报告步数，避免"更快但更脆"误判 | S60 (defensive 180 < 216) |
| RULE-DI-004 | **蒸馏采样 env 按对手组复用**：防御性对手 speed_scale=0.40 使逐 episode 重建 env 昂贵；按对手分组复用 env 可显著降低采集时间 | S60 (577s 采集) |
| RULE-DI-005 | **S45 接入点 (--agent rl --model) 是 nano 策略的规范评估路径**：`evaluate()` 无 model_path 参数；须经 `V9GateEvaluator(rl_model_path=...)` + `agent_name="rl"`，由 `_RLGateAgent` 自适应加载 | S60 (接口排查) |
| RULE-DI-006 | **教师守卫分支是"干预"而非策略决策**（TORL-VLA intervention-censored）：蒸馏采集时用 `select_action_traced()` 的 branch 字段打标（SR-001/edge_*, TR-004/vectored_*），BC 损失降权（w=0.25）防学生模仿守卫反射；实测守卫样本占比 32.8%，不可忽略 | S61 I1 (TORL-VLA arXiv:2606.09337) |
| RULE-DI-007 | **残差注入守卫 (MoDE-VLA)**：学生 MLP 主干 + 规则守卫仅在 `edge_critical` 状态激活（非 `edge_danger_f` 告警带）；安全态学生独行 → 预训练知识精确保持；激活线必须与守卫自身触发线一致，否则过度干预 | S61 I2 (MoDE-VLA arXiv:2603.08122) |
| RULE-DI-008 | **守卫激活线测试纪律**：构造守卫测试 obs 须低于 CRITICAL 线（非 danger 线）——`edge_danger_f` 只是告警带，不触发 SR-001 动作；误用 danger 线会得到错误的分支断言 | S61 (单测修正) |
| RULE-NOTION-001 | **Notion 公开页读取取决于认证态**：(a) 无 token/无认证 → CSR 墙（HTML 只有 JS 壳，loadPageChunk 400/loadCachedPage 404/syncRecordValues 403），不得声称"已实测读取成功"；(b) 有官方 API token（ntn_ 前缀）→ 认证通过后可读：child_page 类型页面内容在 `child_page.title` 字段，blocks children API 对同步页返回 400 属预期；Search API 可列 workspace 可访问页面。**结论随 token 有效而修订（S64 实测 200/404）** | S62 (元诊断) → S64 (token 修订) |
| RULE-NOTION-002 | **协议表资产（11 列 schema）编译为声明式 YAML 治理规范**：trigger/action/ethics/frequency 字段映射；须 yaml.safe_load + 必需字段完整性检查（缺字段报 ValueError 而非静默跳过）| S62 A1 |
| RULE-NOTION-003 | **脚手架生成器必须有 dry-run + verify() 计数每个生成文件**：manifest.json 等元数据文件易在 verify 中漏计（首版永远 15/16，单测暴露）——完整性断言必须与生成清单同源 | S62 A2 (bug 修复) |
| RULE-NOTION-004 | **研究引擎 map 阶段启发式绑定论文语料**：失败模式关键词（fail/limit/challenge）对协议/规范文档失效——输入类型泛化时，map 应声明"自动提取 0 条"并依赖 assess 手动模式，而非静默产出空结果 | S62 (R1 观察) |

## 协议网关工程 (GW) —— Sprint 63 学习路径 Phase 4

| ID | 规则 | 来源 |
| :--- | :--- | :--- |
| RULE-GW-001 | **声明式协议接入规则引擎用"编译产物"而非"运行时解释"**：协议 YAML (11 列声明式) → 编译为 PolicyEngine 可加载的规则 YAML（`config/protocol_policies.generated.yaml`），引擎零改动原生执行——声明层与执行层解耦，产物可审计 | S63 (9 规则) |
| RULE-GW-002 | **协议级规则 priority 语义：伦理 > 触发 > 放行**：DENY(5) < enforce(15/20 按 L3/L2) < ok(25/30)——evaluate 按 priority 升序返回首个命中，伦理违规必须压过一切业务规则；等级 L3 (高风险) 的 enforce 优先级高于 L2 | S63 (priority 排序) |
| RULE-GW-003 | **协议状态对象匹配用正/负向前瞻防并存误报**：enforce 条件 `(?=.*"triggered":true)(?!.*"satisfied":true)` 匹配整个状态对象（紧凑 JSON）而非单字段——否则 triggered+satisfied 并存会被 enforce 抢先命中，误报 ESCALATE | S63 (边界 bug 修复) |
| RULE-GW-004 | **协议加载 fail-closed：缺 schema_version/缺字段/非法 level/空目录/重复 module 一律拒绝**，不静默跳过、不降级——治理规则缺失比不执行更危险；"零声明零影响"由 json_path 提取保证（无 governance 字段 → 规则不命中）| S63 (fail-closed) |

## MCE 元认知自省 (MCE) —— Sprint 64 学习路径 Phase 1 (CVE-S)

| ID | 规则 | 来源 |
| :--- | :--- | :--- |
| RULE-MCE-001 | **复用既有 MCE 2.0 AST 契约，不重复造轮子**：自省层 AST 字段（Core_Directive/Entities/Structural_Constraints/Tension_Vectors/Entropy_Score）必须对齐 `meta_harness/meta_edu.py` 的 mce_compile 输出——但实现面向结构化规则输入（Rule + 协议字段）而非自然语言，且 agent-governance-v2 自包含（仅契约对齐，不跨仓库 import）| S64 (CVE-S Phase 1) |
| RULE-MCE-002 | **治理规则必须可自省（why_exists/what_it_governs/constraints）**：每条编译出的规则（ethics/enforce/ok）都要能回答"我为什么存在、我在治理什么"——Core_Directive 含规则类型语义 + 协议名 + 规则名；origin 携带 trigger/ethics_boundary/expected_output/core_purpose 四溯源字段；产物可审计 JSON | S64 (自省接口) |
| RULE-MCE-003 | **张力向量显式预置，为 VCE 扫描做输入**：Tension_Vectors 按规则类型预置潜在冲突（enforce-vs-ok 并存误报 / ethics priority 压过业务 / ok 声明即满足），供后续 VCE 2.0（S65）检测极化/冲突/盲点——不等待扫描器存在才建模 | S64 (张力设计) |

## VCE 治理自审 (VCE) —— Sprint 65 学习路径 Phase 2 (CVE-S)

| ID | 规则 | 来源 |
| :--- | :--- | :--- |
| RULE-VCE-001 | **治理规则必须可自审（scan 与 introspect 并列）**：`ProtocolGateway.scan()` 消费 MCE AST 产出 vce_scan_report（Polarization_Index/Value_Tensions/Asymmetric_Perspectives + RuleConflicts/BlindSpots + honest_boundary）——规则集变更后必须重扫描，冲突/盲点入库不静默 | S65 (VCE 扫描器) |
| RULE-VCE-002 | **冲突分危级、可审计**：priority_collision(high，同 priority 异 action → 裁决不确定) > condition_overlap(low，json_path 同域依赖负向前瞻) > action_ambiguity(low，ethics-vs-ok 同域并存语义)——每条冲突带 rule_a/rule_b/kind/severity/reason，供 CEE 推演（S66）排序演化 | S65 (冲突检测) |
| RULE-VCE-003 | **盲点检测要发现"声明依赖"类治理空洞**：declaration_only（全部裁决依赖 agent 请求体声明，恶意谎报可绕过）是 VCE 最高价值发现——S63/S64 未显式记录，S65 基线扫描即检出 3 处；缓解需外部验证通道（LLM 语义层/签名机制），不得声称已解决 | S65 (盲点检测) |
| RULE-VER-001 | **放行声明必须可外部验证（declaration_only 缓解）**：`ProtocolGateway` 支持验证器注入（构造器 + `set_validator` 热切换），`evaluate_verified` 在放行声明验证失败时把 action 降级为 ESCALATE（谎报不再零成本）；默认 NoopValidator 保持 S65 行为（向后兼容） | S66 (验证通道) |
| RULE-VER-002 | **基线验证器做确定性一致性检查，不声称语义证明**：violation+satisfied 矛盾 (c=0.95)、satisfied 无证据锚点 (c=0.6)、协议状态异常 (c=0.9)、有锚点 (c=0.8)、非声明依赖规则平凡通过 (c=1.0)——诚实边界：深层语义谎报留给 LLM 层插槽（策略 A） | S66 (基线验证器) |
| RULE-VER-003 | **VCE 扫描必须感知验证通道**：`vce_scan_rules(..., verification_channel)` 非空时 declaration_only 盲点消除（盲点 3→0 实证），报告中记录 Verification_Channel 字段；无通道调用保持 S65 行为（兼容） | S66 (VCE 联动) |
| RULE-DASH-001 | **治理引擎必须可审计**：`ProtocolGateway` 暴露 audit_sink 回调（evaluate_verified 每次裁决后触发），fail-open 设计（审计存储故障不影响裁决）；dashboard 引擎门面将事件写入 audit_events 表 | S68 (审计回调) |
| RULE-DASH-002 | **Dashboard 必须同进程复用引擎，不复制逻辑**：GovernanceEngine 门面直接 import agent-governance-v2（ProtocolGateway/BaselineDeclarationValidator），所有裁决/验证/扫描逻辑单点维护；前端仅消费 API | S68 (引擎门面) |
| RULE-DASH-003 | **治理 API 必须诚实暴露能力边界**：/evaluate 返回验证结果全字段（verified/confidence/reason/validator），谎报降级（ESCALATE）在 UI 高亮"声明未通过验证"；无隐藏的"过"与"不过" | S68 (治理中心 API) |
| RULE-DASH-004 | **自身仓库必须在产品根目录内 `git init` 独立初始化**：bottlesumo_pi 长期"不是独立 git 仓库"——真实根是会话目录，`push -u origin main` 把 .aionui/msan_data/harness 等 226 个内部文件推上 GitHub；产品化时仓库边界与产品根必须一致，若不一致需子树提取重建独立 repo 并 force-push 替换 | S69 (仓库修复) |
| RULE-DASH-005 | **git add 精确到交付文件，禁止 `git add -A`**（S14 已立 RULE-PR-004，S69 再次违反）：`git add -A` 会把 vision/tools/reports/notion probes 等非交付物 staged——每次误加需 reset 回滚并精确 add；规则由 PR 域升级为仓库治理级，双域共同约束 | S69 (仓库修复) |
| RULE-DASH-006 | **跨仓库子树提取用 `git read-tree FETCH_HEAD:<subdir>` 构建 index**：手工 hash-object 重建 blob 对中文路径/kb 二进制易出现 SHA1 不匹配；read-tree 不依赖工作树、自动保留路径与内容，是 subtree 提取的可靠通道 | S69 (仓库修复) |
| RULE-DASH-007 | **`.gitignore` 只影响 untracked 文件**：已 staged 的违规文件须 `git rm -r --cached`（重复执行直到 status 干净）——仅改 .gitignore 无法移除已入索引的路径 | S69 (仓库修复) |
| RULE-DASH-008 | **API 路由/契约以实测为准，不以文档/直觉为准**：真实前缀是 `/api/governance/policies/*` 而非 `/api/policies/*`，health 是 `/api/health`，validate 对语义错误返回 200+valid:false，deploy 失败返回 422——E2E 脚本、ARCHITECTURE.md、CONTRIBUTING.md 三处曾因凭直觉匹配错误路由而返工 | S69 (E2E 实测) |
| RULE-ARCH-001 | **生产级变更必须"三同步"且 GATE 含新功能硬验证**：代码 + 测试 + 文档同步提交；除回归测试外，GATE 必须实测新功能（如 /metrics 返回 200+指标存在、容器 HEALTHCHECK healthy、compose config VALID）——静态校验不能替代运行验证 | ARCH-ROUND 1 |
| RULE-ARCH-002 | **数据库/依赖切换必须向后兼容既有调用点**：`build_engine(db_path)` 第一位置参数语义被 governance_engine.py 依赖，改造时误将 db_path 移到第二位置即破坏引擎集成——改签名前先 grep 全部调用点；环境变量读取需实时（模块级常量不响应测试 monkeypatch） | ARCH-ROUND 1 |
| RULE-ARCH-003 | **可观测性指标统一 `governance_*` 命名空间**（双项目一致，可共用 Grafana 面板）；/metrics 自身不计入请求计数（避免递归膨胀）；SQLAlchemy create_engine 对 PG 方言 eager 加载 dbapi——单测验证 URL 用 `make_url` 纯解析，连通性交给 CI service | ARCH-ROUND 1 |
| RULE-ARCH-004 | **E2E 写真实配置必须自清理**：E2E deploy 残留 `e2e_demo.yaml` 到真实协议目录（S69 手动清理一次、ARCH-ROUND 1 又残留一次），污染 seed 规则数导致 12≠9——E2E 脚本必须 try/finally 清理自己部署的文件，禁止依赖人工 | ARCH-ROUND 1 (待修, P1) |

## 高置信度规则 (HC) —— D5 蒸馏入库 (Sprint 34)

> 来源：D5 置信度校准 (experience/distill_rules_20260808_192416.json，conf≥0.3 三强规则)。
> 用途：抑制已知 REGRESSION 方向、锁定已解决特征，指导后续候选生成，防止重复探索已证伪拓扑。

| ID | 规则 | 来源 |
| :--- | :--- | :--- |
| RULE-HC-001 | **FLANK 阈值收窄 ±10→±15 为 REGRESSION 方向**（topo_B, conf=0.48）：avg_steps +3.4、熵 Δ+0.024（S29 最强信号）；候选生成禁止沿 FLANK 收窄方向，需在效率约束下放宽 | D5 校准 (S33) |
| RULE-HC-002 | **flank dist 0.15 截止为 REGRESSION 方向**（mapping_001, conf=0.30）：avg_steps +7.9，4 次复现（S27v3/S29/S31/S33）；特征已解决，保持锁定，禁止重试该映射变体 | D5 校准 (S33) |
| RULE-HC-003 | **CLOSE-PUSH edge 0.65→0.80 对齐为 SUSPICIOUS 边界**（topo_A, conf=0.26）：Q=+0.02、熵 Δ+0.013，CAUTIOUS-EDGE 触发域被吸收（13→0）；M2 捕获微信号，可作保守探索参考，不承诺胜率收益 | D5 校准 (S33) |

---

*维护：治理智能体 | 更新：2026-08-10 (Sprint 69 仓库修复规则 + D5 蒸馏入库 + ARCH-ROUND 1 生产基线规则)*
