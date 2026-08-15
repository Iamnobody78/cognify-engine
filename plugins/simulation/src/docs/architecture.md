# 架构

见仓库根 [ARCHITECTURE.md](https://github.com/Iamnobody78/bottlesumo-pi/blob/main/ARCHITECTURE.md)。

## 快速摘要

- **双系统**：Governance Center Dashboard（FastAPI + React）+ BottleSumo 旗舰主体（9 层物理架构）
- **治理闭环**：S63 可编译 → S64 可自省 → S65 可自审 → S66 可验证 → S67-S69 产品化
- **协议模型**：11-col-v1 声明式 YAML（12 必填字段，schema fail-closed）
