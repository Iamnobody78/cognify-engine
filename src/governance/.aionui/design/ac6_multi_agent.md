# AC6 — 多 Agent 治理（src/multi_agent/ 目录预留）

- **状态**: 🧭 PRINCIPLE（架构预留，非当前焦点）
- **来源**: 外部治理资源整合任务 3/AC6（"创建 src/multi_agent/ 目录，包含至少 1 个多 agent 治理模板"）
- **保留决定**: 2026-08-04 修正版判定 — 作为多 Agent 场景的架构预留，不消耗迭代资源；模板实现前先评估真实需求

## 现状（2026-08-04 源码核查）

**已有相关资产**:
- `.aionui/tools/agent_registry.yaml`（Agent 注册表：能力边界/状态/会话 — 外环机制已在用）
- `src/task_scheduler.py`（任务调度）与 `src/bootstrap/scheduler.py`（P12 确定性调度器：感知→诊断→修复→部署, 人类在环）
- `src/agent_tools/`（self_heal / self_trace / self_critic — L4/L5 自举三件套）
- 治理拦截层天然单入口（见 AC4）— 多 Agent 进入同一网关时**共享同一评估边界**，无需每个 Agent 独立治理

## 为什么当前不建目录（YAGNI 论证）
1. 网关是单入口架构：任意数量的外部 Agent（langchain/autogen 零侵入接入已演示, P9）都走同一 /v1/intercept 评估点 — **多 Agent 治理 = 治理多 Agent 的流量**，而非为每个 Agent 建子治理
2. `src/multi_agent/` 若只放"模板"（如 groupchat 编排示例），其治理语义已被 examples/（P9 三生态零侵入）覆盖
3. 真实缺口若出现，形态是"编排层治理"（跨 Agent 的依赖图/资源仲裁），而非"每个 Agent 一个治理器"

## 架构预留（不实现, 记录方向）
```
若出现真实多 Agent 编排需求:
  src/multi_agent/
    registry.py   # 复用/升级 .aionui/tools/agent_registry.yaml（能力边界+沙箱策略）
    router.py     # 任务拆解→子任务→移交指令（外环路由仲裁）
    deps.py       # 依赖图（Agent 间数据/工具依赖, 防死锁/资源竞争）
    sandbox.yaml  # 声明式隔离（"Codex 只能写 projects/firmware/" 类策略）
  接入: 全部流量仍过 AC4 单入口; registry 提供身份→租户映射（P6 tenant 复用）
```

## 触发条件
1. 真实出现 ≥2 个外部 Agent 编排同一任务的场景（当前 examples/ 均为单 Agent 零侵入）
2. 或：编排层资源竞争/依赖冲突成为实际问题

## 边界
- "模板"本身不是价值：若只为满足 AC6 字面要求而建目录，属于仪式性代码 — 拒绝
- 与 AC4 联动：多入口出现之日 = AC4 升级为运行时注册表之时
