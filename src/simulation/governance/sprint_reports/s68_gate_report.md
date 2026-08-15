# Sprint 68 Gate Report — 治理中心 Dashboard Phase 1 MVP

- **日期**: 2026-08-10
- **分支**: `feature/productization_dashboard`（S67 签收后延续）
- **PM 指令**: "Phase 1 编码实现，产出可运行的 MVP 仪表板原型"
- **关联**: S67 设计规格 `docs/productization/dashboard_spec.md`（已签收）

---

## 1. 交付摘要

| 层 | 资产 | 验证 |
|----|------|------|
| 引擎 | agent-governance-v2 `ProtocolGateway.audit_sink`（`4333f9d` 已推送）| 87/87 治理测试 |
| 后端 | `bottlesumo_pi/dashboard/backend/` — 门面/模型/10 路由/seed/测试 | 19/19 测试 |
| 前端 | `bottlesumo_pi/dashboard/frontend/` — 5 视图页签 + governanceApi | vite build ✅ |
| E2E | 全链路（vite 代理 5173→FastAPI 8010→引擎→SQLite）| 3 agents + index 200 + 谎报 demo ✅ |

## 2. 门禁判定

| 门 | 判据 | 结果 |
|----|------|------|
| G1 | 四视图 API 契约完整且与引擎实时联通 | ✅ |
| G2 | 审计事件自动入库 | ✅ |
| G3 | VCE 可视化含盲点 3→0 拐点 | ✅ |
| G4 | 实时裁决工具复现谎报降级 demo | ✅ |
| G5 | 前端构建零错误 | ✅ |
| G6 | E2E 全链路 | ✅ |

**GATE 判定：✅ PASS（6/6）**

## 3. 关键实证

### 3.1 谎报降级 demo（E2E 复现）
```
POST /api/governance/evaluate
{"agent_id":"agent-solver-b","body":{"governance":{"protocols":{"feynman_test":{"satisfied":true}}}}}
→ rule=protocol-feynman_test-ok, action=ESCALATE, verified=False, confidence=0.6
→ 审计入库: agent-solver-b escalation+1, verified_fail+1
```
裸声明从 S65 的 ALLOW（绕过成功）到 S68 的 **ESCALATE + 审计留痕**——产品层完整复现 S66 缓解。

### 3.2 审计链（RULE-DASH-001）
```
evaluate_verified → audit_sink(event) → _on_audit → audit_events 表
agent-solver-b 聚合: escalations=2, verified_fail=2 (feynman+logic 裸声明)
```

### 3.3 VCE 拐点（GATE G3）
```
vce_scans: #1 S65 基线 (blindspot=3, channel=off) → #2 S66 (blindspot=0, channel=on)
趋势表: 3→0 拐点可视化 ✅
```

### 3.4 重要发现（S68 实测）
**带 violation 的请求体在完整网关流中先命中 ethics 规则（DENY）**，ok 规则不会触发
——矛盾检查只在 ok 规则直接评估时可达（纵深防御价值）。正常流下矛盾体直接被拒，
比降级更安全。此发现已体现在 seed 数据设计（violation 样本走 DENY 路径）。

## 4. 技术债与遗留

| 项 | 说明 |
|----|------|
| 3 个历史测试失败 | test_revoke.py aiohttp `@unittest_run_loop` 弃用（S66 前已存在，与 S68 无关）|
| db/governance.db | 本地 seed 产物，gitignore 排除 |
| 引擎路径 | 相对 sys.path 引入 agent-governance-v2，生产化建议 pip 安装（S70+）|

## 5. 工程规则

- RULE-DASH-001: 治理引擎必须可审计（audit_sink fail-open）
- RULE-DASH-002: Dashboard 同进程复用引擎，不复制逻辑
- RULE-DASH-003: 治理 API 诚实暴露能力边界

## 6. 下一步

| 项 | 优先级 |
|----|--------|
| S69: 策略编辑器 + 合规导出 + VCE 定时扫描 | P1 |
| LLM 语义验证器插槽 | P1 |
| RBAC/多租户/告警 | P2 |
| CEE 推演器 | P2 |
