# -*- coding: utf-8 -*-
"""
plugin_base.py — Plugin 抽象基类 (PLUGINIFY v1.0)
==================================================
所有插件的统一生命周期契约:
    [发现] -> [加载 on_load] -> [启用 on_enable] -> [运行]
                                      |                    |
                                   [禁用 on_disable]       |
                                      |                    v
                                   [卸载 on_unload]   [更新 -> 版本升级]

红线:
  1. 未实现 Plugin 基类不得声称"已插件化"
  2. on_load 未通过不得进入 on_enable
  3. on_disable 必须可重复调用 (幂等)
"""
from abc import ABC, abstractmethod
from typing import Any, Dict


class Plugin(ABC):
    """所有插件的基类 — 实现四个生命周期钩子 + manifest 属性。"""

    #: 生命周期状态: discovered -> loaded -> enabled -> disabled -> unloaded
    state = "discovered"

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.bus = None  # 由 PluginManager 注入 EventBus

    @abstractmethod
    def on_load(self, config: Dict[str, Any]) -> None:
        """插件加载时调用 — 初始化资源、验证环境。失败抛异常即加载失败。"""

    @abstractmethod
    def on_enable(self) -> None:
        """插件启用时调用 — 启动服务、注册路由/事件订阅。幂等。"""

    @abstractmethod
    def on_disable(self) -> None:
        """插件禁用时调用 — 停止服务、清理资源。幂等、可重复。"""

    @abstractmethod
    def on_unload(self) -> None:
        """插件卸载时调用 — 释放所有资源。幂等、可重复。"""

    @property
    @abstractmethod
    def manifest(self) -> Dict[str, Any]:
        """返回插件的 manifest 信息 (id/name/version/capabilities...)。"""

    # ---- 便利方法 ----
    def info(self) -> Dict[str, Any]:
        m = dict(self.manifest)
        m["state"] = self.state
        return m

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        m = self.manifest
        return f"<Plugin {m.get('id', '?')} v{m.get('version', '?')} [{self.state}]>"
