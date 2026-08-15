# 🧠 Cognify Engine — 演示控制台

> 2026-08-15T15:26:07 | 认知操作产品 (MMCE 驱动)

## 七大资产

| 资产 | 状态 | 入口 |
|:--|:--|:--|
| 治理引擎 | 🟢 | cognify cert (AST 93/93, 1052/1053) |
| 仿真平台 | 🟢 | bottlesumo_pi Renode HIL |
| 三方同步 | 🟢 | sync_daemon 30s + 看门狗 |
| 元能力体系 | 🟢 | meta_capabilities (22/22) |
| 债务系统 | 🟢 | debt_engine (10 已解决) |
| 认知操作系统 | 🟢 | cve_s + mmc_agent (6/6 心跳) |
| 元提示词库 | 🟢 | meta_system (45 条) |

## 运行演示

```bash
python cognify-engine/cli/cognify.py status   # 产品状态
python cognify-engine/cli/cognify.py cert    # 四认证项
python cognify-engine/cli/cognify.py heartbeat  # MVE 心跳
```

## 服务端口

- DSH Web UI :3080 | Rerun :9090 | AFFiNE :3001 | Dashboard :8010 (按需)