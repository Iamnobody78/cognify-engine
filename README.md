# Cognify Engine

**认知操作产品 (插件平台 v2.0)**: 融合元模型控制工程 (MMCE)、价值控制工程 (VCE)、
认知演化工程 (CEE) 的 AI 代理治理与认知操作系统。

## 核心能力 (插件即模块)

- **governance** — 治理即代码: 协议网关 + VCE 扫描 + 声明验证 (agent-governance-v2)
- **cognitive** — 认知即服务: MCE 编译 / VCE 扫描 / CEE 推演 (cve_s.py)
- **sync** — 同步即默认: AionUi/Hermes/DSH 三方实时同步 (tri-sync)
- **meta** — 元能力即基础设施: 25 维元能力体系默认开启 (meta_capabilities)
- **debt** — 债务即资产: 自动发现/分类/偿还 (debt_miner + debt_engine)
- **simulation** — 仿真平台: Renode HIL, firmware-in-the-loop (bottlesumo-pi)
- **dashboard** — 治理仪表板 (DEBT-016 待偿, 诚实桩)

## 快速开始

```bash
python cli/cognify.py status
python cli/cognify.py cert
python cli/cognify.py plugin list
python cli/cognify.py pluginify --all
```

## 插件开发

见 docs/plugin_development.md (生命周期钩子/依赖声明/事件总线/红线)

## 认证状态

- 25 维元能力: 25/25 active | 闭环率 ≥90% | 治理回归 1052/1053
- 插件平台: 7 插件 + 生命周期冒烟 (PLUGINIFY v1.0 PASS)
- 详见 certificate.json

## 文档

- STATUS.md (运行状态) / manifest.json (资产清单) / demo/DEMO.md (演示)