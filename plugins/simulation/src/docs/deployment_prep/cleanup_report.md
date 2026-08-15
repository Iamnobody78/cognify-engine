# 磁盘治理固化 (BS-DEPLOY-PREP B4 / SRS Phase N)

> 日期: 2026-08-11 | 执行: Hermes Leader

## 清理结果 (G6 门禁验证)

| 清理项 | 计划 | 实际 | 状态 |
|--------|------|------|------|
| Win pip cache | 0.27GB | ~0.3GB | ✅ (purge 确认) |
| Win npm cache | 0.53GB | ~0.5GB | ✅ (clean --force) |
| Win Temp | 1.17GB | **0.53GB 释放** (残留 0.67GB 占用中) | ✅ 部分 |
| Win ~/.cache | 0.38GB | 0.38GB | ✅ |
| WSL pip cache | 1.74GB | **1.74GB (655 文件)** | ✅ |
| WSL apt cache | 1.60GB | ⚠️ 需 sudo, 未执行 | 🟡 待人工 |
| **合计** | **5.69GB 计划** | **≈3.5GB 确认释放** | G6 ⚠️ 部分达标 |

### G6 门禁判定
- 释放 ≥5GB 计划: ⚠️ 实际确认 ≈3.5GB (apt 1.6GB 需 sudo 未计入)
- **替代达标**: "或达到可接受水平" — WSL 可用 **921GB** (4% used), 磁盘压力极低; Win C: 152.9GB free
- **结论: G6 视为 PASS (资源充足, 无紧迫清理需求); apt cache 待 PM 授权 sudo 后补清**

## 固化规则 (engineering_rules.md 增量)

1. **R-DISK-001**: 每月执行一次 SRS 扫描 (npm/pip/apt 缓存); 目标: Win C: free > 130GB
2. **R-DISK-002**: 任何 >1GB 的构建产物 (node_modules/venv/模型) 必须登记于 `.directory_structure.yaml`
3. **R-DISK-003**: 删除操作红线 — 仅允许 🟢 缓存类; 🟡/🔴 必须 PM 确认; 删除前必须有回滚说明
4. **R-DISK-004**: Hermes venv (1.11GB) 为运行依赖, 禁止清理; node_modules (94MB 合计) 保留

## 已回滚风险
- 所有已删项均为可再生缓存 → 无回滚需求 (pip/npm/apt 缓存自动重建)
- 🟡 node_modules / Hermes venv / 🟡 apt cache: **未删除**, 零风险

## 未决事项
- [ ] apt cache 1.6GB: 需 `sudo apt-get clean` (等待 PM 授权提权)
- [ ] Windows C: 152.9GB free — 处于 Yellow 阈值 (130GB) 上方, 建议下月 SRS 复查
