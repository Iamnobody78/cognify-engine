# 冻结快照声明 — VENDORED (cognify.self_validate)
================================================
来源 (产品模块, 单一事实来源):
  cognify-engine/cognify/self_validate/engine.py   (轨 B: 自使用验证引擎)
  cognify-engine/cognify/self_validate/schema.sql  (结果持久化)
  cognify-engine/cognify/iterate/fusion.py         (轨 C: 双轨融合分析)
  cognify-engine/cognify/iterate/report.py         (轨 D: 每日迭代报告 + 冲刺模式)
  ~/.aionui-tri-sync/daemon/self_validate.py       (调度壳: SELF-VALIDATE-MINUTE)
  ~/.aionui-tri-sync/daemon/iterate.py             (调度壳: DAILY-FUSION)

本插件为仓库自包含入口, 直接调用仓库内产品引擎;
活调度运行于规范安装 (每分钟自使用验证 / 每日 08:00 融合报告)。
数据写者唯一: self_validate.db / self_validation_result.json / daily_iteration_report.md

5 场景 (真实调用, 不造假):
  认知引擎自用 (MCE/VCE/CEE) / 治理引擎自用 (协议网关) / 元记忆自用 (学习账本) /
  MCP工具自用 (cognify MCP 服务器 cognify_meta) / 元能力自评 (30 维 status)
门禁: 场景连续 3 次失败 → 修复模式 | 双轨差异 >10 → 深度审查 | 连续 3 天无改进 → 冲刺模式

锁定期: 2026-08-16 (cognify-engine v2.1.1 SELF-VALIDATE-ITERATE)
