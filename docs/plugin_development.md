# 插件开发指南 — cognify-engine (PLUGINIFY v1.0)
================================================

cognify-engine 不再是单体, 而是**插件平台**。治理、仿真、认知、同步、
元能力、债务、仪表板 — 每一个都是可选插件, 按需组合。

## 目录结构

```
cognify-engine/
├── core/
│   ├── plugin_base.py      # Plugin 抽象基类 (生命周期钩子契约)
│   ├── event_bus.py        # 插件间事件总线 (解耦通信)
│   └── plugin_manager.py   # 发现/依赖解析/生命周期/隔离
├── plugins/
│   ├── governance/         # 治理引擎 (agent-governance-v2)
│   ├── simulation/         # 仿真平台 (bottlesumo-pi)
│   ├── cognitive/          # 认知引擎 (CVE-S/MMCE)
│   ├── sync/               # 三方同步 (tri-sync)
│   ├── meta/               # 25 维元能力
│   ├── debt/               # 债务系统
│   └── dashboard/          # 治理仪表板 (DEBT-016 待偿, 诚实桩)
├── plugin_registry.json    # 全局插件注册表 (可查询)
└── cli/cognify.py          # CLI 入口 (插件感知)
```

## 插件三要素

1. **manifest.json** — 声明 id/name/version/dependencies/capabilities/hooks/config_schema
2. **plugin.py** — 导出 `Plugin` 基类子类, 实现四个生命周期钩子
3. **src/** — 插件代码 (冻结快照须附 VENDORED.md 声明来源)

## 生命周期钩子

| 钩子 | 时机 | 失败语义 |
|------|------|----------|
| `on_load(config)` | 发现后加载 | 抛异常 = 加载失败, 不得进入 enable |
| `on_enable()` | 启用 | 抛异常 = 启用失败, 状态保持 |
| `on_disable()` | 禁用 | 必须幂等可重复 |
| `on_unload()` | 卸载 | 必须幂等可重复 |

## 依赖声明与拓扑

```json
"dependencies": { "cognify.core": ">=1.0.0 <3.0.0", "cognify.cognitive": ">=1.0.0" }
```

依赖先加载先启用; 循环依赖抛错; 依赖未启用时直接 enable 被拒绝。

## 插件间通信 (事件总线)

插件不得互相 import — 通过 EventBus 解耦:

```python
self.bus.subscribe("governance.ready", self._on_gov_ready)   # 启用时订阅
self.bus.publish("sync.ready", {"id": "cognify.sync"})        # 就绪广播
```

单个订阅者异常被隔离, 不影响其他订阅者。

## 命令

```bash
cognify plugin list                     # 列出所有插件
cognify plugin info governance          # 插件详情
cognify plugin enable simulation        # 热启用
cognify plugin disable simulation       # 热禁用 (幂等)
cognify plugin verify                   # 依赖拓扑 + 生命周期冒烟
cognify pluginify --all                 # P.L.U.G.I.N. 六步法验证
```

## 新插件模板

```python
# plugins/myplugin/plugin.py
from core.plugin_base import Plugin as BasePlugin

class Plugin(BasePlugin):
    @property
    def manifest(self):
        return {"id": "cognify.myplugin", "name": "...", "version": "1.0.0",
                "capabilities": ["..."]}

    def on_load(self, config): ...      # 验证环境/资源
    def on_enable(self): ...            # 启动服务/订阅事件
    def on_disable(self): ...           # 停止服务 (幂等)
    def on_unload(self): ...            # 释放资源 (幂等)
```

## 红线

1. 未完成 Plugin 基类实现不得声称"已插件化"
2. 未验证依赖关系不得加载插件
3. 未隔离环境不得运行插件 (事件总线异常隔离 + 长驻服务子进程化)
4. 未注册事件监听不得插件间通信
5. 未测试热插拔不得发布版本 (`cognify plugin verify` 为必过门禁)
