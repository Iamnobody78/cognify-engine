# 冻结快照声明 — VENDORED (cognify.evolve)
============================================
来源 (产品模块, 单一事实来源):
  cognify-engine/cognify/evolve/engine.py   (E.V.O.L.V.E. 六步引擎)
  ~/.aionui-tri-sync/daemon/evolve.py       (调度壳: EVOLVE-DAILY 每日 23:30)

本插件为仓库自包含入口, 直接调用仓库内产品引擎;
活调度运行于规范安装。数据写者唯一: evolve/ 目录 (审计 jsonl 只追加)。

强制门禁 (无证据 = 没进化):
  G1 每日证据: 5 检查项 ≥3 满足 (commit/测试≥98%/性能不倒退/文档/新功能)
  G2 每周闭环: 发现→设计→实现→验证→部署
  G3/G4 双轨不倒退: 基准 + 自使用 ≥ 上周
  G5 可追溯: 每项证据含 commit hash + 验证报告
红线: 无证据声称进化 / 伪造数据 (最高红线) / 验证下降跳过回滚 — 全部禁止。

锁定期: 2026-08-16 (cognify-engine v2.1.2 EVOLVE-FORCE)
