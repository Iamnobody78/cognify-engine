# PERMANENT-ANCHOR v1.0 学术与工程支撑矩阵

> 来源：用户提供（2026-08-13）。用途：永久锚定系统（防止代理遗忘关键知识）的学术/工程/基准三重支撑。
> 对应 A1-A5 五层锚定机制与 A.N.C.H.O.R. 六步法。

---

## 一、核心论文

| 论文 | 核心贡献 | 对应锚定机制 |
|:---|:---|:---|
| Persistent Memory in AI Agents: A Survey of Long-Term Retention Mechanisms (2025) | 系统调研 AI 代理长期记忆保留机制；识别"遗忘"主因（上下文窗口限制、记忆压缩损失、跨会话状态不共享）；提出"锚定框架"作为解决方案 | 整体（A1-A5） |
| The Forgetting Problem in Continual Learning for LLM Agents (2025) | 揭示 LLM 代理连续学习中的灾难性遗忘问题；提出"经验回放 + 锚定样本"混合策略 | A1（静态锚点样本） |
| Checkpointing and Rollback in Autonomous Agents (2025) | 讨论通过检查点机制防止代理状态漂移；提供"恢复点锚定"具体算法 | Phase C（定期校验）+ Phase R（恢复） |

## 二、源码库

| 源码库 | 核心能力 | 与锚定协议的对应 |
|:---|:---|:---|
| agent-checkpoint | 代理状态快照与恢复 | Phase R（恢复机制） |
| immutable-config | 不可变配置加载 | Phase A（静态锚点） |
| guardian-hooks | 运行时钩子拦截 | Phase H（变更阻断） |
| memory-verifier | 记忆完整性校验 | Phase C（定期校验） |

## 三、基准与数据集

| 基准 | 用途 | 对应锚定机制 |
|:---|:---|:---|
| LongMemEval | 评估代理长期记忆保留能力 | A1-A5 整体效果 |
| ForgettingBench | 测量代理在连续会话中的遗忘率 | Phase C（定期校验） |

## 四、总结

PERMANENT-ANCHOR 协议通过 **静态锚点文件（A1）+ 强制启动加载（A2）+ 定期校验（A3）+ 变更阻断（A4）+ 跨会话一致性检查（A5）+ 自动恢复（R）** 六层机制，确保代理永远不会忘记关键知识。它不依赖代理的"自觉"，而是通过工程手段强制锁住核心协议、边界和红线。学术上对应"锚定框架"（Persistent Memory Survey）、"经验回放+锚定样本"（Forgetting Problem）、"检查点回滚"（Checkpointing）三大方向；工程上有 4 个开源库可直接参考；评估上有 LongMemEval / ForgettingBench 两个专门基准。
