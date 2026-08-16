# vNext 设计提案 (ARCH-HEAL-CLOSE E5)

> 2026-08-16T15:05:26 | 生成机制: 每月 1 日 / 手动触发

## 技术债务现状

- 债务: 13/21 已解决 | 趋势: 持续下降
- 未偿重点: DEBT-016 (dashboard 桩) / DEBT-021 (tree-sitter Python312)

## vNext 方向 (候选)

- P0: dashboard 插件实装 (DEBT-016 偿债)
- P1: 元工具真实调用接入 (META-VERIFY-FORCE 合规率 33%→80%+)
- P1: 外部基准接入 (MR-Ben/Reflection-Bench 数据集)
- P2: 分层记忆 (工作/情景/语义 + 向量检索)

## 迁移计划

- 每项: 目标 → 设计原则 → 模块变更 → 验证 → 回滚