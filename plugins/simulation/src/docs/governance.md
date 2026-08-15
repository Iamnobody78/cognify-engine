# 治理

BottleSumo 由 [agent-governance-v2](https://github.com/Iamnobody78/agent-governance-v2)
治理引擎驱动（同进程门面集成）。

## 三层护栏

1. **可验证**：裸 `satisfied=true` 声明 → `ESCALATE`（S66 谎报缓解）
2. **可审计**：每次裁决 audit_sink 回调（fail-open）
3. **可自审**：VCE 扫描器检测规则冲突/盲点/极化（S65）

## Dashboard

- 仪表盘 / 策略管理 / 审计查看 / VCE 可视化 / 策略编辑器
- 运行：后端 `uvicorn main:app --port 8010`（`dashboard/backend/`），前端 `npm run dev`（`dashboard/frontend/`）
