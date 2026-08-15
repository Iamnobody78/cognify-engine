# 架构

## 统一迭代流程 (单仓库闭环)

| 分支 | 用途 | 来源 |
|------|------|------|
| main | 稳定发布版 | 经过认证和测试 |
| develop | 集成开发分支 | 所有 PR 合并目标 |
| feature/plugin-* | 插件级功能开发 | 从 develop 切出 |
| hotfix/plugin-* | 插件级紧急修复 | 从 main 切出 |
| release/v* | 版本发布准备 | 从 develop 切出 |

## 插件平台 (PLUGINIFY v1.0)

```
cognify-engine/
├── core/           # plugin_manager + event_bus + plugin_base
├── plugins/        # 7 个独立插件 (governance/simulation/cognitive/sync/meta/debt/dashboard)
├── plugin_registry.json
└── cli/cognify.py  # 统一入口
```

## 三方同步 (TRI-SYNC)

AionUi (backup) ↔ Hermes (governance) ↔ DSH (engine) 通过
`~/.aionui-tri-sync/hub` 统一枢纽实时同步 (30s 守护 + 5min 看门狗)。

## 永续迭代 (PERPETUAL-ITERATE)

30 分钟心跳闭环: 感知 → 决策 (L1/L2/L3) → 执行 → 学习 → 交付。
心跳报告: `~/.dsh/heartbeat/latest.md`。

## 跨系统学习 (CROSS-LEARN-SYNC)

L.E.A.R.N. 五步法, 统一学习账本: `~/.aionui-tri-sync/learning/`。

## 产品化路线图 (PRODUCT-ROADMAP)

P0 认知服务 API ✅ → P1 文档站/治理网关 ✅ → P2 PyPI (待 token) → P3 插件注册表。
