# 边界声明 (HONEST-BOUNDARY v1.0) — tag=S56

> 生成: 2026-08-10 (20260810_195605) | 机制: B.O.U.N.D. Phase B+O (自动注入)

## 数据边界
- 数据来源: NCLT 27-session MSAN 传感器融合数据集
- 版本: 2026-07 镜像 (gps_rtk.csv + ms25.csv + ms25_euler.csv)
- 覆盖: 27/27 sessions
- 缺失 session: 无
- 已知缺口: ["仅姿态真值 (ms25_euler), 无独立位置真值 — 位置评估依赖 fix>=3 RTK 作参考", "RTK fix=2 退化段坐标冻结/陈旧 (系统性偏置, 占行 6.5-17.9%)", "gps_rtk.csv 时间戳乱序 (需排序; 早期脚本曾受影响)"]

## 模型边界
- 模型: DeepSeek v4-pro (治理主模型) + Ollama Qwen2.5-Coder-7B/1.5B (本地蒸馏)
- 知识截止: 2025-05 (DeepSeek), 本地模型随训练集
- 能力范围: 传感器融合 EKF 治理/自进化/元能力框架; 不覆盖实时嵌入式部署验证
- 已知局限: ["无独立位置真值导致评估依赖 RTK 参考 (数据边界联动)", "置信度量化依赖 hypotheses.jsonl conf 字段 (部分覆盖)"]

## 工具边界
- 可用: AionUi MCP + WSL 工具链 (python3/bash/git)
- 记录: mcp_usage_report.jsonl 存在
- 局限性: ["WSL 下 PowerShell 引号破坏内联 python -c (用脚本文件规避)", "背景进程随 WSL 会话退出被终止 (需前台分块运行)", "27-session 全量回测单线程 ~30min"]

## 认知边界
- 置信度机制: hypotheses.jsonl conf + meta_decisions.jsonl 决策记录
- 不确定来源: ["数据不足: 位置真值缺失 / fix=2 退化段", "模型局限: 知识截止/未覆盖最新传感器", "工具不可用: Renode 实时仿真未启用"]
- 近期实证: S56: 02-23 pos RMSE 443.85->36.96m (置信度: 高, 三源验证: metrics+debug trace+fused pose)
