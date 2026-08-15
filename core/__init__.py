# -*- coding: utf-8 -*-
"""
cognify.core — 插件平台核心 (PLUGINIFY v1.0)
=============================================
- plugin_base:      Plugin 抽象基类 (生命周期钩子契约)
- event_bus:        插件间解耦通信 (订阅/发布)
- plugin_manager:   发现/加载/依赖解析/生命周期/隔离运行
"""
from .plugin_base import Plugin
from .event_bus import EventBus
from .plugin_manager import PluginManager, PluginState

__all__ = ["Plugin", "EventBus", "PluginManager", "PluginState"]
__version__ = "2.0.0"
