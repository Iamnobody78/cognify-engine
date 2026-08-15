# .aionui 记忆库

本项目使用 .aionui/ 目录持久化跨会话上下文。

## 目录

- `tools/`: 已安装工具清单
- `config/`: Agent 配置与偏好
- `context/`: 项目状态与决策记录
- `sessions/`: 会话索引与摘要
- `templates/`: 可复用模板

## 新会话恢复

读取 `context/current_state.md` + `context/decision_log.md` 恢复上下文。
