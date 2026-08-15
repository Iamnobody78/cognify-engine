# 元能力改进实施 (META-CHANGE IMPLEMENTATION)

> 生成: 2026-08-13 (20260813_164001)

## 改动内容
1. **规则固化**: RULE-MC-014 | 传感器退化段不是失锁: 码/浮点解 (fix=2) 携带冻结/陈旧坐标, 按退化段处理 (软位置更新 + 协方差增长), 而非纯 DR 保持; 检测特征 = 连续相同坐标 + fix 降级 (NCLT 实证: 02-23 154s -> +10km)
2. **可复用能力载体**: nclt_fusion_ekf.py S56 参数块 (F2_USE/F2_SIGMA/F2_STALE_RATE/
   F2_MIN_GAP/F2_VCLAMP) + kind=4 soft 更新分支 — 偏差检测/补偿模式已在 NCLT 域落地,
   规则抽取后可供其他传感器融合域迁移 (知识迁移形式化第一步)。
3. **检测逻辑 (可操作规则候选)**:
   - 特征: fix 降级至 <3 且连续相同坐标 (frozen/stale) 时长 > F2_MIN_GAP
   - 响应: 软位置更新 (sigma 15m) + P 增长 (0.5 m/s per sqrt(s)) + 速度抗饱和 (20 m/s)
