# 磁盘扫描报告 (BS-DEPLOY-PREP B1 / SRS Phase S)

> 日期: 2026-08-11 | 执行: Hermes Leader (BS-DEPLOY-PREP v1.0)

## 总览

| 磁盘 | 总量 | 已用 | 可用 | 健康度 |
|------|------|------|------|--------|
| Windows C: | ~475.7GB | 324.5GB | **151.2GB** | 🟡 Yellow 阈值边缘 (>130GB 警告) |
| WSL /dev/sdd | 1007GB | 37GB | **919GB** | ✅ 优秀 (4% used) |

⚠️ Windows C: 剩余 151.2GB — 处于安全阈值 Yellow(>130GB) 边缘, 未达 Red(>135GB),
建议本次清理后回归安全区间。

## 🟢 可安全删除 (缓存/临时, 无项目数据)

| 路径 | 大小 | 类型 | 删除方式 |
|------|------|------|----------|
| Windows `%LOCALAPPDATA%\pip\cache` | 0.27GB | pip 缓存 | `pip cache purge` |
| Windows `%LOCALAPPDATA%\npm-cache` | 0.53GB | npm 缓存 | `npm cache clean --force` |
| Windows `%LOCALAPPDATA%\Temp` | 1.17GB | 系统临时 | `Remove-Item -Recurse` (跳过占用) |
| Windows `~/.cache` | 0.38GB | 用户缓存 | `Remove-Item -Recurse` |
| WSL `/var/cache/apt` | 1.60GB | apt 缓存 | `apt-get clean` |
| WSL pip cache (~/.cache/pip) | 1.74GB | pip 缓存 | `pip cache purge` |
| **合计** | **≈5.69GB** | | |

## 🟡 待确认 (不自动删除)

| 路径 | 大小 | 理由 |
|------|------|------|
| `bottlesumo_pi/dashboard/frontend/node_modules` | 42M | 项目构建依赖, 删除需 `npm ci` 重建 — 保留 |
| `bottlesumo_pi/governance/dashboard/frontend/node_modules` | 52M | 同上 |
| Hermes venv (`%LOCALAPPDATA%\hermes\hermes-agent\venv`) | 1.11GB | 运行依赖, 不可删 |

## 🔴 需人工确认 (跳过)

- 项目文件 (`bottlesumo_pi/`, `agent-governance-v2/`) — 红线 #3 禁止删除
- 系统文件 — 不触碰

## 回滚策略 (红线 #4)

| 清理项 | 回滚方式 |
|--------|----------|
| pip cache (Win/WSL) | 自动重建 (下次 pip install 重新下载) |
| npm cache | 自动重建 |
| apt cache | `apt-get update` 后按需重下载 |
| Temp / .cache | 均为可再生缓存, 无回滚需求 |
| node_modules | **未删除** (🟡 保留), 无需回滚 |

**结论: 所有 🟢 清理项均为可再生缓存, 无数据丢失风险; 🟡/🔴 未触碰。**
