# Web UI MVP 设计规格 — Governance Center Dashboard

- 版本: v1.0 (S67 交付, T1 设计)
- 日期: 2026-08-10
- 分支: `feature/productization_dashboard`
- 关联: agent-governance-v2 S63-S66 能力闭环 (可编译→自省→自审→可验证)
- 产品化路线: 从"技术闭环"跨越到"产品可用"的第一步

## 1. 背景与目标

S63-S66 在 agent-governance-v2 完成了治理能力闭环:

| Sprint | 能力 | 产物 |
|--------|------|------|
| S63 | 治理可编译 | protocol YAML → 9 条可执行规则 |
| S64 | 治理可自省 | MCE AST introspection (规则回答"为什么存在") |
| S65 | 治理可自审 | VCE 2.0 扫描 (极化/冲突/盲点) |
| S66 | 治理可验证 | 验证通道 (谎报声明 → ESCALATE 降级) |

**问题**: 这些能力全部沉淀在 Python 库 + JSON 产物中, 无用户界面。治理团队/审计员
无法直观查看: 哪些 agent 在治理之下? 策略如何组织? 哪些裁决被升级? 治理健康度如何?
VCE 扫描发现了什么?

**目标 (S67 MVP)**: 在既有 dashboard 栈 (FastAPI + React/Vite, `governance/dashboard/`)
上新增 **治理中心 (Governance Center)** 四大视图:

1. **代理清单** (Agent Registry) — 治理下的 agent 全景
2. **策略管理** (Policy Management) — 协议/规则可视化
3. **审计查看** (Audit View) — 裁决 + 验证结果可审计追溯
4. **VCE 扫描可视化** (VCE Visualization) — 治理健康度自审结果

## 2. 现状侦察

### 2.1 既有 dashboard (复用基础)

```
governance/dashboard/
├── backend/            FastAPI (port 8010) + SQLite
│   ├── app/main.py     入口, 已挂 health/usage/hypotheses 三路由
│   ├── app/routers/    health.py / usage.py / hypotheses.py
│   ├── app/models.py   SQLAlchemy 模型
│   ├── app/database.py init_db()
│   ├── app/schemas.py  Pydantic
│   ├── seed.py         Demo 数据
│   └── Dockerfile / requirements.txt
└── frontend/           React + Vite
    ├── src/App.jsx     单页聚合 (健康卡片/延迟表/假设面板/时间线)
    ├── src/api.js      fetch 封装
    └── src/components/ HealthCards / LatencyTable / HypothesisPanel / UsageTimeline
```

**结论**: 复用 FastAPI+SQLite+React 技术栈与部署 (Docker/nginx), 新增
`governance` 路由 + `治理中心` 前端页签; 既有"运行监控"视图保留为另一页签。

### 2.2 agent-governance-v2 可消费产物 (数据源)

| 产物 | 路径 | 内容 |
|------|------|------|
| 协议源 | `config/protocols/*.yaml` | 3 模块 (feynman_test/entropy_denoise/logic_chain_check) |
| 编译规则 | `config/protocol_policies.generated.yaml` | 9 条规则 (ethics/enforce/ok × 3) |
| MCE 自省 | `config/mce_introspection.generated.json` | 规则 why-exists/约束/溯源 |
| VCE 扫描 | `config/vce_scan_report.json` | 极化指数/冲突/盲点/Verification_Channel |
| 验证通道 | `config/verification_channel.generated.json` | 通道状态 + 样本裁决 |
| 核心库 | `src/{protocol_gateway,policy,mce_introspection,vce_scanner,verification}.py` | 可编程调用 |

## 3. 架构设计

```
┌─────────────────────────── 浏览器 ───────────────────────────┐
│  Governance Center Dashboard (React/Vite, 新增治理中心页签)      │
│  ┌────────────┬────────────┬────────────┬──────────────────┐  │
│  │ 代理清单     │ 策略管理     │ 审计查看     │ VCE 扫描可视化     │  │
│  └────────────┴────────────┴────────────┴──────────────────┘  │
└─────────────────────────────┬─────────────────────────────────┘
                              │ REST /api/governance/*
┌─────────────────────────────▼─────────────────────────────────┐
│  governance-api (FastAPI, 复用既有 dashboard backend)           │
│  ├─ routers/governance.py   ← 新增: 四视图数据 + 实时裁决           │
│  ├─ models.py               ← 新增: agents / audit_events /       │
│  │                              vce_scans / policy_snapshots     │
│  └─ deps.governance_engine  ← agent-governance-v2 引擎门面         │
└───────────────┬───────────────────────────┬─────────────────────┘
                │ 直接 import (同进程)          │ 启动时加载 JSON 产物
┌───────────────▼──────────────┐  ┌──────────▼────────────────────┐
│ agent-governance-v2 (核心库)  │  │ config/*.generated.json       │
│ ProtocolGateway / PolicyEngine│  │ mce / vce / verification      │
└──────────────────────────────┘  └───────────────────────────────┘
```

### 3.1 引擎接入方式 (裁决: 库内嵌, 产物快照)

| 选项 | 说明 | 裁决 |
|------|------|------|
| A: 子进程 CLI | 每次请求 spawn python -m ... | 慢, 不选 |
| B: 同进程 import | `pip install -e ../agent-governance-v2`, FastAPI 进程内直接调用 | ✅ 快, 热更新 |
| C: 独立治理微服务 | 单独部署 governance-api | 过度设计 (MVP), 预留演进 |

**B 为 MVP 方案**: 依赖注入 `GovernanceEngine` 门面, 启动时构建
`ProtocolGateway(validator=BaselineDeclarationValidator())`; 审计事件写入 SQLite。

### 3.2 数据模型 (SQLite 新增表)

```python
# governance 表 (SQLAlchemy)
class Agent(db.Model):            # 代理清单
    id: str PK                    # agent_id
    name: str
    role: str                     # 执行器/审查器/规划器...
    status: str                   # active/idle/suspended
    last_seen: datetime
    sessions: int                 # 会话数
    escalations: int              # 触发升级次数 (enforce/降级)
    verified_ok: int              # 声明验证通过数
    verified_fail: int            # 声明验证失败数 (谎报嫌疑)

class AuditEvent(db.Model):       # 审计查看
    id: int PK autoincr
    ts: datetime
    agent_id: str
    path: str
    method: str
    matched_rule: str             # 命中规则名
    action: str                   # 最终动作 (含降级后 ESCALATE)
    channel: str                  # 验证器名称
    verification: JSON            # VerificationResult.to_dict() 全字段
    raw_body: JSON                # 请求体 (声明)

class VceScan(db.Model):          # VCE 扫描历史
    id: int PK autoincr
    ts: datetime
    report: JSON                  # vce_scan_report.json 全量快照
    polarization: float           # 极化指数 (索引列)
    conflict_count: int
    blindspot_count: int
    channel_enabled: bool

class PolicySnapshot(db.Model):   # 策略管理
    id: int PK autoincr
    ts: datetime
    protocol: str
    rule_type: str                # ethics/enforce/ok
    rule_name: str
    priority: int
    action: str
    json_path: str
    json_pattern: str
    origin: str                   # 溯源
```

## 4. 四大视图规格

### 4.1 代理清单 (Agent Registry)

**价值**: 回答"治理之下有哪些 agent, 各自治理姿态如何"

- 表格: name / role / status / 会话数 / 升级次数 / 验证通过 / **验证失败 (谎报嫌疑)**
- 行级操作: 查看该 agent 的审计流 (跳转审计视图, 按 agent_id 过滤)
- 状态徽章: `active`(绿) / `idle`(灰) / `suspended`(红)
- 顶部 KPI: 治理中 agent 总数 / 活跃数 / 本周升级数
- 数据源: `agents` 表 + `audit_events` 聚合
- API: `GET /api/governance/agents` → `[{id,name,role,status,last_seen,sessions,escalations,verified_ok,verified_fail}]`
- API: `GET /api/governance/agents/{id}/audit?limit=50` → 过滤审计流

### 4.2 策略管理 (Policy Management)

**价值**: 让非开发者看懂治理策略结构 — 回答"协议如何被治理"

- 协议卡片 ×3: feynman_test / entropy_denoise / logic_chain_check
- 每卡片内按规则类型分三栏: ethics(DENY) / enforce(ESCALATE) / ok(ALLOW_WITH_WARNING)
- 规则条目: 规则名 / priority / action / json_path / json_pattern (等宽字体)
- **冲突高亮**: 读取最近一次 VCE 扫描的 `RuleConflicts`, 关联规则名 → 红色角标 + 冲突描述 tooltip
- "为什么存在"入口: 点规则 → 展开 MCE 自省 (why_exists / what_it_governs / origin)
- 数据源: `policy_snapshots` (编译时快照) + `mce_introspection.generated.json` (缓存) + `vce_scan_report.json`
- API: `GET /api/governance/policies` → 按模块聚合的规则树 (含 MCE 摘要)
- API: `GET /api/governance/policies/{protocol}` → 单模块详情

### 4.3 审计查看 (Audit View)

**价值**: 可追溯 — 回答"谁在何时声明了什么, 治理如何裁决, 是否可信"

- 过滤: 时间范围 / 规则 / 动作 / 验证器通道 / agent
- 表格: ts / agent / path / matched_rule / action / channel / verified
- 行展开: VerificationResult 全字段 (claim / confidence / reason / validator) + raw_body JSON 视图
- **降级标记**: action=ESCALATE 且原规则为 ok (验证失败降级) → 高亮"⚠ 声明未通过验证"
- 数据源: `audit_events` 表 (引擎每次 `evaluate_verified` 自动写入)
- API: `GET /api/governance/audit?limit=100&rule=&action=&agent=&channel=`
- API: `GET /api/governance/audit/{id}` → 单条全量 (含 raw_body)

### 4.4 VCE 扫描可视化 (VCE Visualization)

**价值**: 治理健康度自审 — 回答"治理规则本身是否健康"

- **极化仪表**: Polarization_Index 0-1 环形仪表 (当前 0.383, 黄区)
- **冲突列表**: RuleConflicts 卡片 (priority_collision / condition_overlap / action_ambiguity, severity 徽章)
- **盲点时间线**: 历次扫描 blindspot_count 折线 (S65: 3 → S66: 0, 验证通道落地拐点)
- **验证通道状态**: Verification_Channel 卡片 (enabled / validator / mitigates)
- **Honest Boundary**: does_not_detect 声明 (诚实边界可审计)
- 触发按钮: "立即重扫" → `POST /api/governance/vce/scan` (同步执行 scan() 并入库)
- 数据源: `vce_scans` 表
- API: `GET /api/governance/vce/latest` → 最近一次全量报告
- API: `GET /api/governance/vce/history?limit=20` → 历次极化/盲点趋势
- API: `POST /api/governance/vce/scan` → 触发重扫入库

### 4.5 附加: 实时裁决试炼 (Live Evaluate, 开发者工具)

- 表单: agent_id / path / method / body (JSON textarea)
- 提交 → `POST /api/governance/evaluate` → 返回 `evaluate_verified` 全量结果
- 用途: 演示谎报缓解 (裸 `{"satisfied": true}` → ESCALATE), 验证通道 demo

## 5. API 契约汇总

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/governance/agents` | 代理清单 |
| GET | `/api/governance/agents/{id}/audit` | 单代理审计流 |
| GET | `/api/governance/policies` | 策略树 (含 MCE 摘要) |
| GET | `/api/governance/policies/{protocol}` | 单协议详情 |
| GET | `/api/governance/audit` | 审计流 (多条件过滤) |
| GET | `/api/governance/audit/{id}` | 审计单条全量 |
| GET | `/api/governance/vce/latest` | 最近 VCE 报告 |
| GET | `/api/governance/vce/history` | VCE 趋势 |
| POST | `/api/governance/vce/scan` | 触发重扫 |
| POST | `/api/governance/evaluate` | 实时裁决 (dev tool) |
| POST | `/api/governance/audit/ingest` | 外部系统批量写入审计事件 (预留) |

**安全**: MVP 全部只读 + 本地回环绑定; 写操作仅 `vce/scan` 与 `evaluate` (受控)。
生产化时加 RBAC + API key (见 Phase 3)。

## 6. 前端导航改造

```
App.jsx 改造: 顶部页签导航
├─ 运行监控 (既有: HealthCards / LatencyTable / HypothesisPanel / UsageTimeline)
└─ 治理中心 (新增)
   ├─ AgentsView.jsx        代理清单
   ├─ PoliciesView.jsx      策略管理
   ├─ AuditView.jsx         审计查看
   ├─ VceView.jsx           VCE 扫描可视化
   └─ EvaluateTool.jsx      实时裁决试炼 (开发者工具)
```

- `api.js` 新增 `governanceApi` 模块 (10 个端点封装)
- 组件风格对齐既有 (CSS 类复用, 卡片/表格/徽章统一)

## 7. 企业合规映射 (NIST AI RMF / EU AI Act)

| 视图/能力 | NIST AI RMF | EU AI Act | 落地 |
|-----------|-------------|-----------|------|
| 代理清单 | Map (上下文/资产) | Art.12 记录保存 | agent 身份与角色可审计 |
| 策略管理 | Govern (治理框架) | Art.9 风险管理 | 规则结构可读可审查 |
| 审计查看 | Measure/Manage (度量+处置) | Art.12 日志追溯 | 每次裁决全字段留痕 |
| VCE 可视化 | Measure (指标) | Art.14 人工监督 | 自审健康度可汇报 |
| 验证通道 | Manage (缓解) | Art.14 人工监督 | 声明降级 = 人工/升级复核触发 |

**MVP 即具备审计链**: 每次 `evaluate_verified` 产生 AuditEvent (agent/rule/action/verification 全字段),
满足基础合规审计要求; 导出 CSV/JSON 在 Phase 2 提供。

## 8. 分阶段路线

| 阶段 | 范围 | 验收 |
|------|------|------|
| **Phase 1 (MVP, S67-68)** | 四视图 + 实时裁决 + 审计入库 | 本规格四视图全可用, 与 agent-governance-v2 实时联通 |
| Phase 2 (S69) | 策略编辑器 (协议 YAML 编辑→重编译→diff)、合规导出、VCE 定时扫描 (cron) | 治理变更闭环 + 报表 |
| Phase 3 (S70+) | RBAC/SSO、多租户、审计 webhook 通知、告警 (升级频率异常)、企业合规报告模板 | 企业级就绪 |

## 9. 非目标 (Honest Scope)

- MVP **不含**策略在线编辑器 (Phase 2); 策略修改走协议 YAML + 重编译
- MVP **不含**实时 WebSocket 推送 (审计流用轮询刷新, 5s 间隔)
- MVP **不含**RBAC/多租户 (Phase 3)
- MVP **不含**LLM 语义验证器接入 (P1 遗留, 与 Web UI 正交)
- 既有运行监控视图原样保留, 不做重构

## 10. 工程落地步骤 (S67 后续)

```
1. agent-governance-v2 增加 audit 事件回调钩子 (evaluate_verified → on_audit)
2. dashboard backend: deps/governance_engine.py 门面 + models.py 新表 + routers/governance.py
3. dashboard backend: pip 依赖 agent-governance-v2 (本地路径或 git)
4. frontend: 页签导航 + 四视图组件 + governanceApi
5. seed.py: 生成 demo agents + 审计事件 + 历次 VCE 扫描 (含 S65→S66 拐点)
6. 测试: backend pytest (治理路由) + frontend 构建冒烟
7. 部署: 复用既有 Docker (backend+frontend), 端口 8010/5173
```

## 11. 验收判据 (GATE)

| # | 判据 |
|---|------|
| G1 | 四视图 API 契约完整 (10 端点 + 数据模型) 且与引擎实时联通 |
| G2 | 审计事件自动入库 (evaluate_verified 每次调用 → AuditEvent) |
| G3 | VCE 可视化含 S65→S66 盲点 3→0 拐点时间线 (真实历史数据) |
| G4 | 实时裁决工具复现谎报降级 demo (裸 satisfied → ESCALATE) |
| G5 | 既有运行监控视图零回归 (页签改造不破坏) |
| G6 | 合规映射表落地 (NIST/EU 字段入 spec 与审计 schema) |

---

*本规格为 S67 设计交付; 实现启动需 PM 确认 Phase 1 范围后进入 S68 编码。*
