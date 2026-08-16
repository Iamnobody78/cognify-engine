# 闭环运行时消费口径 (2.3/三期 B3)

## EXPECTED 8 配对依据 (consumption.py)

| # | producer | consumer | 依据 |
|---|---|---|---|
| 1 | learning/ledger | meta_call | 调用链元记忆步骤真实检索账本 |
| 2 | meta-call/certification_report | evolve | EVOLVE-FORCE 双轨验证读取认证 |
| 3 | meta/status | generate-status | 状态报告读取元能力计数 |
| 4 | debt/debt_inventory | generate-status | 状态报告读取债务 |
| 5 | meta/status | meta_smoke | 冒烟读取元能力状态 (待埋点) |
| 6 | meta-call/certification_report | meta_smoke | 元验证冒烟读取认证 (已埋点) |
| 7 | benchmark/trend_data | generate-status | 状态报告读取基准趋势 |
| 8 | learning/ledger | meta_smoke | 元记忆冒烟检索账本 (已埋点) |

## 口径

- 运行时消费率 = 今日实际消费配对 / 期望配对 (静态映射仅作 fallback 对照)
- 缺失对列表诚实呈现 (如 evolve 当日未运行 → 该对缺失)
- 修订史: 2026-08-16 首版 (8 对)
