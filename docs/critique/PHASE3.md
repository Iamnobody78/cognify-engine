# 三期元批判报告 (2026-08-16) — 二期整改核验 + 三期执行记录

> 来源: 外部指导 Agent 基于代码与运行态实测 (不以汇报为准)。本文件为外部 witness 存档, 供复核。

## 二期核验总账 (实测)

| 二期声称 | 实测判定 |
|---|---|
| C1 快照同步 30 维 | ✅ 真 |
| C2 门禁统一 ≥7 | ✅ 真 (提交时) |
| C3 元执行 U1-U6 | ✅ 真 |
| C7 可移植 16 文件 | ⚠️ 半途 (51 文件仍含 ivy 路径, 见 N4) |
| 2.1 冒烟 6/6 | ✅ 真 (evidence.jsonl 18 条) |
| 2.2 grade=smoke | ⚠️ 瞬态 (被 generate-status 覆盖, 见 N1) |
| 2.3 闭环运行时化 | ✅ 真 |
| 2.4 mcp-stats | ✅ 真 |
| 2.5 selftest 负向用例 | ✅ 真 (二期最佳) |
| 2.7 规则版本化 | ✅ 真 |
| 0.1 维度事实源 | ❌ 名不副实 (capabilities.yaml 不存在) |
| 0.2 证书-文档联动 | ❌ 失效 (双写者, 见 N1) |
| 0.4 版本统一 | ❌ 名不副实 (死代码 2.1.9) |
| 1.2 输出隔离 | ⚠️ 半途 (仅 observe) |
| 1.3 CI 门禁 | ✅ 真 |
| 1.4 打包 | ✅ 真 |
| 1.5 卫生 | ⚠️ 半途 (心跳自动提交仍在) |

## 三期批判 N1-N7

- **N1 (最高) 双写者架构**: cert() 写完整证书, generate-status 用简化格式覆盖 → grade/overall 证据被销毁, 红线稳态不可达
- **N2 治理回归检查退回存在性**: 固定日期证据文件 + 正则不匹配仍 pass
- **N3 版本硬编码死代码**: meta_dev.py `if False else "2.1.9"`; cert 硬编码 2.2.3
- **N4 可移植性 = 可覆盖非可移植**: 默认值仍为本机路径 (51 文件含 ivy)
- **N5 本机冒烟必挂**: cp950 UnicodeEncodeError (缺 PYTHONIOENCODING 规范)
- **N6 心跳自动提交污染 main**
- **N7 PyPI 口径**: 完整打包未发布

## 三期执行记录 (Agent 元执行)

| ID | 任务 | 状态 |
|---|---|---|
| A1 | 单一写者: generate-status 禁写 certificate.json (只读渲染 STATUS 认证行) | ✅ 已执行 |
| A2 | cert 第 3 项内容化: glob 最新证据 + 正则不匹配/failed → false | ✅ 已执行 |
| A3 | 版本单一源: 死代码移除, meta_dev 版本读 pyproject | ✅ 已执行 |
| A5 | 冒烟环境规范: plugin.py reconfigure + ci.yml PYTHONIOENCODING | ✅ 已执行 |
| B4 | selftest 挂 CI | ⏳ 待执行 |
| C2 | 本报告入库 (本文件) | ✅ 已执行 |
| C3 | 红线补录 (双写者禁令/无认证不宣称) | ✅ 已执行 |
| A4 | 默认路径中立化 (~/.cognify) | ⏳ 批次 A 剩余 |
| A6 | capabilities.yaml 维度事实源 | ⏳ 批次 A 剩余 |
| B1-B3 | STATUS 写 ~/.cognify / 心跳提交独立 / consumption 文档化 | ⏳ 批次 B |
| C1 | PyPI 口径 README | ⏳ 批次 C |

## 结论 (指导者)

二期约 10/16 真实、3/16 半途、3/16 名不副实。最大问题是多写者冲突 (N1) — 已修复 (A1)。
