# AC4 — 不可绕过的执行边界（Enforcement Boundary）

- **状态**: 🧭 PRINCIPLE（架构原则，不急于实现，作为长期方向保留）
- **来源**: 外部治理资源整合任务 3/AC4（"不可绕过的执行边界"）；概念对照: Execution Governance for Agentic AI（arXiv:2512.04408）
- **保留决定**: 2026-08-04 修正版判定 — 概念层保留为架构原则

## 原则表述

**所有 Agent 工具调用必须且只能经过唯一的评估 choke point；任何新增入口（新 API 端点/新协议/直连通道）若绕过该点，视为架构违规。**

## 现状盘点（2026-08-04 源码核查）

| 防线 | 位置 | 状态 |
|------|------|------|
| 策略裁决（YAML 规则含 json_path/tool_args） | `src/policy.py` PolicyEngine | ✅ 拦截路径主判 |
| AST 硬阻断（tree-sitter 三语言） | `src/ast_guard.py`（main.py 前门注入, fail-closed） | ✅ Priority 0 前门 |
| 租户认证 | `src/auth.py`（401/403 双头注入） | ✅ 入口层 |
| 语义 LLM-Judge 旁路 | `src/semantic_hook.py`（判定后升级, 只升不降, fail-soft） | ✅ 旁路（不阻断, 撤销 trace） |
| 治理头 HMAC | `src/context_hmac.py`（防伪造链根隔离） | ✅ 信任门 |
| 审计存储 | `src/storage.py`（决策记录, 含 trace 因果） | ✅ 落盘 |

**已识别缺口（评估用, 非当前实现项）**:
1. 拦截层集中在 `src/main.py` 的 chat_completions_handler / proxy 路径 — 若未来新增直连 LLM 通道（如流式直通绕过 create_task 分派点）需同步挂载评估点
2. ASTGuard 仅覆盖 Python/Bash/SQL 三类载荷 — 新语言（JS/PowerShell）未覆盖时该通道存在语义盲区（有 json_path/tool_args 兜底, 但非 AST 级）
3. bootstrap/deployer 白名单机制与策略层无交叉校验（deployer 只管 git 提交白名单）

## 保留理由
- 当前唯一入口架构下"不可绕过"已近似成立（单 handler + fail-closed 注入）；原则只需固化, 不需新增代码
- 强制实现（如入口注册表/通道审计）在无第二入口前是过度设计（YAGNI）

## 触发条件
1. 新增第二类入口（非 /v1/chat 直通通道、多协议网关）
2. 多 Agent 外部编排（AC6）引入旁路通道时
3. 合规要求"所有入口统一评估"的证明文档

## 边界
- "不可绕过"= 架构不变量（文档/审查标准），非运行时自证明；若需运行时证明 → 升级为 AC3 式设计（入口注册表 + 未注册入口 fail-closed）
