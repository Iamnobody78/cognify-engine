# 插件开发

见 [plugin_development.md](plugin_development.md) — 生命周期钩子 / 依赖声明 /
事件总线 / 红线。

## 插件三要素

1. **manifest.json** — id/name/version/dependencies/capabilities/hooks
2. **plugin.py** — 导出 `Plugin` 基类子类, 实现 on_load/on_enable/on_disable/on_unload
3. **src/** — 插件代码 (冻结快照须附 VENDORED.md)

## 命令

```bash
cognify plugin list                     # 列出所有插件
cognify plugin info governance          # 插件详情
cognify plugin enable simulation        # 热启用
cognify plugin disable simulation       # 热禁用 (幂等)
cognify plugin verify                   # 依赖拓扑 + 生命周期冒烟
cognify plugin search                   # 远程注册表搜索 (P3)
cognify plugin install <name>           # 从注册表安装 (P3)
```
