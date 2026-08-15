# MCP 使用数据分析报告 (A4)

> **生成时间**: 2026-08-07T20:06:42
> **数据源**: `mcp_usage_report.jsonl` (50 条记录)
> **时间范围**: 2026-08-07T18:28:10.894 ~ 2026-08-07T19:52:40.835
> **触发**: PM 裁决 2 — 记录数 ≥50 自动生成

## 1. 总览

| 指标 | 值 |
| :--- | :--- |
| 总调用数 | 50 |
| 成功 | 49 (98.0%) |
| 失败 | 1 (2.0%) |
| 服务器数 | 3 |
| 工具数 | 7 |

## 2. 服务器使用分布

| 服务器 | 调用数 | 占比 |
| :--- | :--- | :--- |
| meta_cognition_server | 23 | 46.0% |
| environment_bootstrap_server | 14 | 28.0% |
| semantic_retrieval_server | 13 | 26.0% |

## 3. 工具调用频率 (Top)

| 工具 | 调用数 | 占比 |
| :--- | :--- | :--- |
| semantic_search | 12 | 24.0% |
| environment_snapshot | 12 | 24.0% |
| hypothesis_stats | 11 | 22.0% |
| meta_config_status | 11 | 22.0% |
| check_write_scope | 2 | 4.0% |
| reasoning_chain_query | 1 | 2.0% |
| nonexistent_tool | 1 | 2.0% |

## 4. 延迟分析 (按工具)

| 工具 | 次数 | min(ms) | p50(ms) | avg(ms) | max(ms) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| semantic_search | 12 | 2568.1 | 9438.7 | 8025.0 | 11763.9 |
| environment_snapshot | 12 | 343.1 | 472.0 | 1503.8 | 5350.0 |
| hypothesis_stats | 11 | 4.8 | 26.0 | 327.9 | 3395.5 |
| meta_config_status | 11 | 5.2 | 31.8 | 30.6 | 69.3 |
| check_write_scope | 2 | 2.9 | 3.9 | 3.9 | 4.8 |
| reasoning_chain_query | 1 | 7.2 | 7.2 | 7.2 | 7.2 |
| nonexistent_tool | 1 | 4.1 | 4.1 | 4.1 | 4.1 |

## 5. 错误明细

| 时间 | 服务器 | 工具 | 错误 |
| :--- | :--- | :--- | :--- |
| 2026-08-07T18:28:19.537 | semantic_retrieval_server | nonexistent_tool | `Unknown tool: nonexistent_tool` |

## 6. 洞察与优化建议

- **最高频工具**: `semantic_search` (12 次, 24.0%) — MCP 上下文构建的核心依赖, 建议优先优化其延迟
- **延迟瓶颈**: `semantic_search` (avg 8025.0ms, max 11763.9ms) — 若为 bge-m3 嵌入类调用, 可考虑缓存或批量嵌入
- **失败率 2.0%**: 1 次失败, 主要为预期错误 (参数校验/工具不存在), 无持续性故障
- **服务器负载**: `meta_cognition_server` 调用最密集 (23 次) — 三服务器负载基本均衡

*免责声明: 假设数据质量待修正 (F-110, 排期 Sprint 14), 工具统计不受影响。*
