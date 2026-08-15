# 🧠 Cognify Engine — 演示控制台

> 2026-08-15T16:11:52 | 认知操作产品 (插件平台 PLUGINIFY v1.0)

## 七大插件

| 插件 | 状态 | 入口 |
|:--|:--|:--|
| governance 治理引擎 | 🟢 | cognify plugin enable governance (AST 守卫, 1052/1053) |
| simulation 仿真平台 | 🟢 | cognify plugin enable simulation (bottlesumo_pi Renode HIL) |
| sync 三方同步 | 🟢 | cognify plugin enable sync (30s 守护 + 看门狗) |
| meta 元能力体系 | 🟢 | cognify plugin enable meta (25/25 维) |
| debt 债务系统 | 🟢 | cognify plugin enable debt (10 已解决) |
| cognitive 认知操作系统 | 🟢 | cognify plugin enable cognitive (6/6 心跳) |
| dashboard 治理仪表板 | 🟡 桩 | DEBT-016 待偿 (诚实桩, 不伪称服务) |

## 运行演示

```bash
python cognify-engine/cli/cognify.py status          # 产品状态
python cognify-engine/cli/cognify.py cert           # 认证 (含插件平台检查)
python cognify-engine/cli/cognify.py plugin list    # 7 插件清单
python cognify-engine/cli/cognify.py pluginify --all # P.L.U.G.I.N. 六步法
python cognify-engine/cli/cognify.py heartbeat      # MVE 心跳
```

## 服务端口

- DSH Web UI :3080 | Rerun :9090 | AFFiNE :3001 | Dashboard :8010 (按需, DEBT-016)