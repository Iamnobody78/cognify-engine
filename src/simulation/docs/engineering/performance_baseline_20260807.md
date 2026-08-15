# 性能基线归档 — Meta-Harness 提议器时延 (2026-08-07)

- **归档者**: BottleSumo 治理智能体 (P2-V4 开发前性能参照)
- **关联**: PM 裁决 1 (2026-08-07) — 批准 P1-V3 时延增量现状, 不强制压缩
- **运行环境**: Windows + WSL 评估, Ollama qwen2.5:7b (CPU 推理 ~1.7 token/s), bge-m3:latest (1024 维)

## 1. 基线数据

| 阶段 | prompt_tokens | completion_tokens | duration_s | 备注 |
| :--- | :--- | :--- | :--- | :--- |
| P0 基线 (无检索, MHA_MULTIROUND_1) | 2828 | 156-170 | 335-341 | 3 轮全 PASS |
| P1-V3 (bge-m3, MHA_P1V3_1) | 3109 | 158-250 | 132-401 | ROUND 1 有效 (360s), ROUND 2/3 无效 (探索副作用) |
| P1-V3 修复后 (MHA_P1V3_2) | 3137 | 135-250 | 371-434 | 3/3 PASS (均值 ~392s) |

**关键指标**:
- LLM 推理时延增量: +31~93s (均值 +54s, 相对 P0 基线 335-341s)
- 检索时延: 3.7-10.5s/轮 (≤30s 预算达标)
- prompt 增量: 2828 → 3137 (+309 tokens = retrieved_experience 注入), 预填充 +10-15s
- 异常值: ROUND 3 (MHA_P1V3_2) 的 434s — completion=250 达到 max_tokens 截断

## 2. 时延构成分析

```
LLM 总时延 = 预填充 (prompt 处理, 与 tokens 数线性) + 生成 (completion × ~1.7s/token)
- P0:     预填充 ~45s + 生成 ~290s = ~340s
- P1-V3:  预填充 ~55s (prompt +309) + 生成 ~330s (completion 更大) = ~390s
```

## 3. 压缩方案 (P2-V4 时延 > 500s/轮 时启用)

| 措施 | 预期收益 | 风险 |
| :--- | :--- | :--- |
| max_tokens 250→230 | 生成 -40s (最坏截断场景) | 候选 JSON 截断风险低 (正常 completion 135-170) |
| format_experience max_chars 400→300 | prompt -100 tokens, 预填充 -4s | 检索注入信息量略降 |
| 组合预期 | 均值增量降至 +30-40s | 低 |

## 4. P2-V4 触发阈值

- **触发**: 单轮总时延 > 500s (含重试)
- **动作**: 执行压缩方案 (第 3 节)
- **监控**: sessions.jsonl 的 duration_s 字段 (每轮自动记录)

## 5. 结论

CPU 推理场景下 +54s 增量是语义检索的合理代价 — 换来候选生成精准度 (有效率 100%,
避免探索 abdl 规则文件) 与上下文质量。时延优化列为 P2-V4 验收前可选增强项。
