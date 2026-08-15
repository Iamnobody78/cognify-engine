# BottleSumo 旗舰版 — 架构设计（顶层视图）

> **快照**: v11.11-IndustrialGrade + 治理闭环 S63→S69 · 2026-08-10
> **详细**: 9 层物理架构权威描述见 [architecture_overview.md](architecture_overview.md)；
> 治理引擎（agent-governance-v2）架构见其仓库 [ARCHITECTURE.md](https://github.com/Iamnobody78/agent-governance-v2/blob/main/ARCHITECTURE.md)。

---

## 1. 双系统架构

```
┌────────────────────────────────────────────────────────────────────┐
│           GOVERNANCE CENTER DASHBOARD (S67-S69 产品化)              │
│                                                                    │
│  Frontend (React/Vite :5173)  ──proxy──▶  Backend (FastAPI :8010) │
│   仪表盘 · 策略管理 · 审计 · VCE · 策略编辑器      │               │
│                                               ▼                   │
│                                   GovernanceEngine 门面            │
│                                   (同进程 import agent-governance) │
│                                    ┌───────────────┐               │
│                                    │ ProtocolGateway│◀── audit_sink│
│                                    └───────────────┘               │
└────────────────────────────────────────────────────────────────────┘
                              │ (治理请求 / 裁决记录)
┌─────────────────────────────▼──────────────────────────────────────┐
│           BOTTLE SUMO 旗舰主体 (9层架构)                            │
│  Layer 0: 工作流宪法 (Understand→Design→Execute→Verify→Record)     │
│  Layer 1: Agent 治理层 (.aionui/ 元认知/技能/热力学)                │
│  Layer 2-8: 物理栈 (PCB/CAD → 驱动 → 传感 → 控制 → 决策 → 感知 → AI)│
│  Layer 9: 软件研发 (需求→设计→实现→测试→文档)                      │
│  Layer 10: 14层工具链 (PlatformIO/KiCad/Renode/Gazebo/PyTorch...)  │
└────────────────────────────────────────────────────────────────────┘
```

---

## 2. 旗舰主体（bottlesumo_pi/ 9 层）

| 层 | 职责 | 关键路径 |
|---|---|---|
| L0 工作流宪法 | Universal Protocol + Quality Gates | `governance/` |
| L1 Agent 治理 | 元认知 / 技能 / 热力学 / 债务 | `.aionui/` |
| L2 物理层 | PCB (KiCad) / CAD (FreeCAD) | `hardware/` |
| L3 驱动层 | PWM/舵机驱动 | `firmware/` |
| L4 传感层 | I2C/SPI 传感器 | `firmware/` |
| L5 控制层 | FreeRTOS 实时控制 | `firmware/` |
| L6 决策层 | DQN 强化学习 | `rl/`, `training/` |
| L7 感知层 | CV 视觉 | `vision/`, `models/` |
| L8 AI 平台 | 模型推理/蒸馏 | `models/`, `bottlesumo_pi/config.py` |
| L9 软件研发 | 质量门控 ruff→mypy→pytest→60% | `core/`, `tests/` |
| L10 工具链 | 14 层工具链（仿真验证） | `simulation/` |

---

## 3. Dashboard 后端（dashboard/backend）

| 模块 | 职责 |
|---|---|
| `main.py` | FastAPI 应用装配（CORS、路由注册） |
| `models.py` | SQLAlchemy 4 表（决策/审计/协议/健康） |
| `database.py` | SQLite 连接 + 会话管理 |
| `seed.py` | Demo 种子数据 |
| `governance_engine.py` | ⭐ GovernanceEngine 门面：协议加载/校验/部署（`.bak` 回滚）、快照、规则编译 |
| `routers/governance.py` | REST 端点（仪表盘/审计/策略/编辑器） |

**端点一览**（S68-S69，前缀 `/api/governance`）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 引擎健康检查 |
| POST | `/api/governance/evaluate` | 治理裁决（evaluate_verified） |
| POST | `/api/governance/audit/ingest` | 审计事件批量写入（预留） |
| GET | `/api/governance/policies` | 协议列表 |
| GET | `/api/governance/policies/{protocol}` | 协议详情 |
| GET | `/api/governance/policies/{protocol}/source` | YAML 源（编辑器加载，404 缺失） |
| POST | `/api/governance/policies/validate` | 零副作用校验（200+valid:false 语义层错误；名称非法 400） |
| POST | `/api/governance/policies/deploy` | 部署（校验失败 422；写入+重建网关+`.bak` 回滚） |
| GET | `/api/governance/vce/scan` | VCE 扫描结果 |

---

## 4. 关键设计决策

| 决策 | 理由 |
|---|---|
| Dashboard 同进程 import 治理引擎 | 避免跨进程序列化损失；`GOV_AGENTS_V2_PATH` 可覆盖路径 |
| audit_sink 回调 fail-open | 审计失败不阻塞裁决（可用性优先） |
| 协议 YAML 声明式（11-col-v1） | 12 必填字段 schema fail-closed；规则由编译器生成 |
| 部署带 .bak 回滚 | 热更新失败不损坏运行中网关 |
| 测试隔离（临时协议目录） | 编辑器 deploy 测试绝不污染真实 config |
| CI 只跑轻量冒烟（主仓库）+ dashboard 全量 | 140GB 资产不适合 CI；轻量验证 + 产物化闭环 |

---

## 5. 演进路线（Sprint 图）

```
S63 可编译 ─▶ S64 可自省 ─▶ S65 可自审 ─▶ S66 可验证 ─▶ S67 规格
                                                          │
                S68 Dashboard MVP (四视图 + audit_sink) ◀──┘
                          │
                S69 策略编辑器 + 开源资产 + CI/CD  ◀── 当前
                          │
                S70+ RBAC / 合规导出 / VCE 定时扫描 / CODEOWNERS
```
