# 三系统自适配总览 (SELF-ADAPT v1.0 + UNIFY-ENGINE v1.0)

## 适配状态

| 系统 | 通道 | 状态 | 测试 |
|------|------|------|------|
| AionUi | Cognify Engine 助手 + cognify 技能 | ✅ 已注册 (重启生效) | PASS |
| Hermes | cognify MCP 服务器 (5 工具) | ✅ 已注册 | PASS (握手+tools) |
| DSH | cognify profile | ✅ 已创建 | PASS (结构+CLI) |

## 统一状态 (书同文车同轨)

| 维度 | 位置 | 状态 |
|------|------|------|
| 数据格式 | `~/.aionui-tri-sync/schemas/unified.schema.json` | ✅ |
| 配置 | `~/.aionui-tri-sync/config/unified.yaml` | ✅ |
| 版本 | `~/.aionui-tri-sync/VERSION` = 2.1.0 | ✅ |
| 状态 | `~/.aionui-tri-sync/state/unified.json` | ✅ |
| 入口 | `cognify` (6 统一子命令) | ✅ |
| 日志 | JSONL (decision/timeline) | ✅ |

## 调用路径

```
AionUi 对话 → Cognify Engine 助手 → cognify CLI → 治理/认知/同步/元能力/债务
Hermes 对话 → cognify_* MCP 工具 → cognify CLI
DSH 会话  → cognify profile → cognify CLI
外部系统  → cognify serve REST (:8080 /mce /vce /cee /governance/evaluate)
```

## 红线合规

- 未测试不声称完成: 三通道均测试 PASS (Hermes 握手 / AionUi 行验证 / DSH 结构+CLI)
- 文档已生成: docs/adaptation/ (aionui/hermes/dsh/overview)
- 未改核心代码: 全部为适配层 (MCP 服务器/技能/profile/注册), 零源码修改
- 适配日志: ~/.aionui-tri-sync/adaptation/
