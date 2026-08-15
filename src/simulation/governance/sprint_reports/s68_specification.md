# Sprint 68 Specification — 治理中心 Dashboard Phase 1 MVP（产品化落地）

## 1. 目标

**将 S63-S66 治理能力闭环（可编译→自省→自审→可验证）转化为可运行、可交互的 Web 产品。**

S67 设计规格 `docs/productization/dashboard_spec.md` 经 PM 签收；本 Sprint 按 Phase 1 范围编码实现。

## 2. 范围（PM 确认）

| 模块 | 内容 | 优先级 |
|------|------|--------|
| 后端治理路由 | FastAPI 10 端点（代理清单/策略管理/审计/VCE） | P0 |
| 引擎门面 | 同进程 import agent-governance-v2，复用现有引擎 | P0 |
| 审计事件回调 | 裁决时自动写入 `audit_events` 表 | P0 |
| 前端四视图 | 代理清单 / 策略管理 / 审计查看 / VCE 可视化 | P0 |
| seed demo 数据 | 预置 3 条示例策略 + 5 条审计事件 | P1 |

## 3. 交付物

**agent-governance-v2**（引擎层，`4333f9d` 已推送）：
- `ProtocolGateway` 新增 `audit_sink` 回调钩子（每次 evaluate_verified 触发，fail-open）
- 4 新单测（触发/无事件/默认 None/故障隔离），治理套件 87/87

**bottlesumo_pi/dashboard/**（产品层，本 Sprint 主体）：
```
dashboard/
├── backend/
│   ├── main.py                  FastAPI 入口 (:8010, CORS, 引擎注入)
│   ├── governance_engine.py     GovernanceEngine 门面 (同进程集成 + 审计入库)
│   ├── models.py                agents / audit_events / vce_scans / policy_snapshots
│   ├── database.py              SQLite 引擎/会话
│   ├── routers/governance.py    10 端点 + ingest 预留
│   ├── seed.py                  demo: 3 agents + 5 审计 + 2 VCE + 9 规则快照
│   ├── tests/test_governance_api.py  19 测试
│   └── requirements.txt
├── frontend/
│   ├── src/App.jsx              页签导航 (5 视图)
│   ├── src/pages/               Agents / Policies / Audit / Vce / EvaluateTool
│   ├── src/services/api.js      governanceApi 客户端
│   └── src/styles.css           治理中心主题
├── db/                          SQLite (gitignore)
└── migrations/                  预留
```

## 4. 关键设计

### 4.1 引擎门面（RULE-DASH-002）
- `GovernanceEngine` 同进程构建 `ProtocolGateway(validator=BaselineDeclarationValidator(), audit_sink=_on_audit)`
- agent-governance-v2 通过相对路径 sys.path 引入（`GOV_AGENTS_V2_PATH` 可覆盖）
- 审计 agent_id 用 `contextvars` 传递（FastAPI 线程池安全）

### 4.2 审计链（RULE-DASH-001）
- 引擎层：`audit_sink` 回调（fail-open，不阻塞裁决）
- 门面层：`_on_audit` 写入 audit_events（含 verification 全字段 + raw_body）
- UI 层：ESCALATE + baseline 验证失败 → "⚠ 声明未通过验证"高亮

### 4.3 谎报降级 demo（GATE G4）
- `/api/governance/evaluate` 接受 agent_id + body
- 裸 `{"satisfied": true}` → 无锚点 → verified=False(c=0.6) → action 降级 ESCALATE

### 4.4 VCE 拐点（GATE G3）
- seed 写入 2 次扫描：S65 基线（盲点 3, 无通道）→ S66（盲点 0, 通道启用）
- VCE 视图趋势表展示 3→0 拐点

## 5. 验收判据（GATE）

| # | 判据 | 结果 |
|---|------|------|
| G1 | 四视图 API 契约完整且与引擎实时联通 | ✅ 19/19 后端测试 |
| G2 | 审计事件自动入库（evaluate → AuditEvent） | ✅ test_evaluate_writes_audit |
| G3 | VCE 可视化含 S65→S66 盲点 3→0 拐点 | ✅ vce/history 2 条 |
| G4 | 实时裁决工具复现谎报降级 demo | ✅ E2E 验证 ESCALATE/False/0.6 |
| G5 | 前端构建零错误 | ✅ vite build 37 modules |
| G6 | E2E 全链路（浏览器→vite→FastAPI→引擎→DB） | ✅ 代理链路 3 agents + 200 |

## 6. 非目标（Honest Scope）

- 无策略在线编辑器（S69）
- 无 WebSocket 实时推送（轮询刷新）
- 无 RBAC/多租户（S70+）
- 无 LLM 语义验证器接入（P1 遗留）
- 既有 governance/dashboard 运行监控视图未纳入（独立演进）

## 7. 遗留

| 优先级 | 项 |
|--------|----|
| P1 | S69: 策略编辑器 + 合规导出 + VCE 定时扫描 |
| P1 | LLM 语义验证器插槽（误报率观察后评估） |
| P2 | S70+: RBAC/多租户/告警/合规报告模板 |
| P2 | CEE 推演器（验证通道稳定 1 个完整 Sprint 后启动） |
