# -*- coding: utf-8 -*-
"""
plugin_manager.py — 插件加载器/生命周期/依赖解析 (PLUGINIFY v1.0)
=================================================================
    [发现] -> [加载] -> [启用] -> [运行] -> [禁用] -> [卸载]
      |         |          |
      v         v          v
   扫描目录   on_load    on_enable

依赖解析: 按 manifest.dependencies 拓扑排序, 依赖先加载先启用。
隔离运行: 进程内模式 (异常隔离) + 子进程模式 (sync 守护等长驻服务)。
热插拔:   enable/disable 运行时生效, 无需重启引擎。

红线:
  1. 未验证依赖关系不得加载插件
  2. 未隔离环境不得运行插件
  3. 未测试热插拔不得发布版本
"""
import importlib.util
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .event_bus import EventBus
from .plugin_base import Plugin


class PluginState:
    DISCOVERED = "discovered"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    UNLOADED = "unloaded"
    ERROR = "error"


@dataclass
class PluginRecord:
    """一个已发现插件的完整记录。"""
    plugin_id: str
    name: str = "?"
    version: str = "?"
    description: str = ""
    author: str = ""
    license: str = ""
    main: str = "plugin.py"
    dependencies: Dict[str, str] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    hooks: List[str] = field(default_factory=list)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    source: str = "local"
    verified: bool = False
    state: str = PluginState.DISCOVERED
    path: str = ""
    error: Optional[str] = None


class PluginManager:
    """插件生命周期管理器。"""

    def __init__(self, root: Path | str, registry: Path | str | None = None) -> None:
        self.root = Path(root)
        self.registry_path = Path(registry) if registry else self.root / "plugin_registry.json"
        self.bus = EventBus()
        self._records: Dict[str, PluginRecord] = {}
        self._instances: Dict[str, Plugin] = {}
        self._module_cache: Dict[str, Any] = {}

    # ---------- 发现 ----------
    def discover(self) -> List[PluginRecord]:
        """扫描 plugins/*/manifest.json, 重建记录。"""
        self._records = {}
        for mf in sorted(self.root.glob("plugins/*/manifest.json")):
            try:
                data = json.loads(mf.read_text(encoding="utf-8"))
                rec = PluginRecord(
                    plugin_id=data.get("id", mf.parent.name),
                    name=data.get("name", mf.parent.name),
                    version=data.get("version", "0.0.0"),
                    description=data.get("description", ""),
                    author=data.get("author", ""),
                    license=data.get("license", ""),
                    main=data.get("main", "plugin.py"),
                    dependencies=dict(data.get("dependencies", {})),
                    capabilities=list(data.get("capabilities", [])),
                    hooks=list(data.get("hooks", [])),
                    config_schema=dict(data.get("config_schema", {})),
                    source=data.get("source", "local"),
                    verified=bool(data.get("verified", False)),
                    path=str(mf.parent),
                )
                self._records[rec.plugin_id] = rec
            except Exception as exc:  # noqa: BLE001
                self._records[mf.parent.name] = PluginRecord(
                    plugin_id=mf.parent.name, name=mf.parent.name,
                    version="?", state=PluginState.ERROR, error=f"manifest 解析失败: {exc}",
                    path=str(mf.parent))
        return list(self._records.values())

    # ---------- 依赖解析 (拓扑排序) ----------
    def resolve_order(self) -> List[str]:
        """按依赖拓扑序返回插件 id 列表 (依赖在前)。循环依赖抛错。"""
        order: List[str] = []
        visited: Dict[str, int] = {}  # 0=visiting 1=done

        def visit(pid: str, chain: List[str]) -> None:
            if visited.get(pid) == 1:
                return
            if visited.get(pid) == 0:
                raise ValueError(f"依赖循环: {' -> '.join(chain + [pid])}")
            visited[pid] = 0
            rec = self._records.get(pid)
            if rec is None:
                raise ValueError(f"依赖缺失: {pid} (被 {chain[-1] if chain else '?'} 引用)")
            for dep in rec.dependencies:
                if dep == "cognify.core":
                    continue  # 核心平台, 非插件
                visit(dep, chain + [pid])
            visited[pid] = 1
            order.append(pid)

        for pid in self._records:
            visit(pid, [])
        return order

    # ---------- 加载 ----------
    def load(self, plugin_id: str, config: Dict[str, Any] | None = None) -> Plugin:
        """加载插件: 导入 plugin.py -> 实例化 -> on_load。"""
        rec = self._records.get(plugin_id)
        if rec is None:
            raise KeyError(f"未发现插件: {plugin_id}")
        if rec.state in (PluginState.LOADED, PluginState.ENABLED):
            return self._instances[plugin_id]
        # 依赖前置检查 (红线 1)
        for dep in rec.dependencies:
            if dep != "cognify.core" and self._records.get(dep, PluginRecord("", "", "")).state not in (
                    PluginState.LOADED, PluginState.ENABLED):
                raise RuntimeError(f"依赖未就绪: {plugin_id} -> {dep} (先加载依赖)")
        main_path = Path(rec.path) / rec.main
        if not main_path.exists():
            raise FileNotFoundError(f"插件入口缺失: {main_path}")
        module_name = f"cognify_plugin_{plugin_id.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, main_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"无法解析插件入口: {main_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        self._module_cache[plugin_id] = module
        cls = getattr(module, "Plugin", None)
        if cls is None or not (isinstance(cls, type) and issubclass(cls, Plugin)):
            raise TypeError(f"{plugin_id}: plugin.py 必须导出 Plugin 基类子类 (红线 1)")
        instance = cls(config or {})
        instance.bus = self.bus
        try:
            instance.on_load(config or {})
        except Exception as exc:  # noqa: BLE001
            rec.state = PluginState.ERROR
            rec.error = f"on_load 失败: {exc}"
            raise
        instance.state = PluginState.LOADED
        rec.state = PluginState.LOADED
        rec.error = None
        self._instances[plugin_id] = instance
        self.bus.publish("plugin.loaded", {"id": plugin_id, "version": rec.version})
        return instance

    # ---------- 启用/禁用 (热插拔) ----------
    def enable(self, plugin_id: str) -> Plugin:
        """启用插件 (幂等)。依赖须先启用。"""
        rec = self._records.get(plugin_id)
        if rec is None:
            raise KeyError(f"未发现插件: {plugin_id}")
        if rec.state == PluginState.ENABLED:
            return self._instances[plugin_id]
        if rec.state not in (PluginState.LOADED, PluginState.DISABLED):
            raise RuntimeError(f"{plugin_id} 当前状态 {rec.state}, 不可启用")
        for dep in rec.dependencies:
            if dep != "cognify.core" and self._records.get(dep).state != PluginState.ENABLED:
                raise RuntimeError(f"依赖未启用: {plugin_id} -> {dep}")
        inst = self._instances[plugin_id]
        inst.on_enable()  # 失败则由调用方处理, 状态保持
        inst.state = PluginState.ENABLED
        rec.state = PluginState.ENABLED
        self.bus.publish("plugin.enabled", {"id": plugin_id})
        return inst

    def disable(self, plugin_id: str) -> Plugin:
        """禁用插件 (幂等热插拔)。依赖该插件的其他插件须先禁用。"""
        rec = self._records.get(plugin_id)
        if rec is None:
            raise KeyError(f"未发现插件: {plugin_id}")
        if rec.state == PluginState.DISABLED:
            return self._instances[plugin_id]
        if rec.state != PluginState.ENABLED:
            raise RuntimeError(f"{plugin_id} 当前状态 {rec.state}, 不可禁用")
        for other in self._records.values():
            if plugin_id in other.dependencies and other.state == PluginState.ENABLED:
                raise RuntimeError(f"存在依赖方未禁用: {other.plugin_id} -> {plugin_id}")
        inst = self._instances[plugin_id]
        inst.on_disable()
        inst.state = PluginState.DISABLED
        rec.state = PluginState.DISABLED
        self.bus.publish("plugin.disabled", {"id": plugin_id})
        return inst

    def unload(self, plugin_id: str) -> None:
        """卸载插件 (须先禁用)。"""
        rec = self._records.get(plugin_id)
        if rec is None:
            raise KeyError(f"未发现插件: {plugin_id}")
        if rec.state == PluginState.ENABLED:
            self.disable(plugin_id)
        inst = self._instances.pop(plugin_id, None)
        if inst is not None:
            inst.on_unload()
            inst.state = PluginState.UNLOADED
        rec.state = PluginState.UNLOADED
        self.bus.publish("plugin.unloaded", {"id": plugin_id})

    # ---------- 全生命周期冒烟 (热插拔验证, 红线 3) ----------
    def lifecycle_smoke(self, configs: Dict[str, Dict[str, Any]] | None = None) -> Dict[str, Any]:
        """按依赖序 加载全部 -> 启用全部 -> 禁用再启用 (热插拔) -> 卸载全部。"""
        configs = configs or {}
        order = self.resolve_order()
        report = {"order": order, "steps": [], "ok": True}
        for pid in order:
            self.load(pid, configs.get(pid))
            self.enable(pid)
            report["steps"].append(f"enable {pid}")
        for pid in reversed(order):  # 热插拔: 全部禁用再全部启用
            self.disable(pid)
            report["steps"].append(f"disable {pid}")
        for pid in order:
            self.enable(pid)
            report["steps"].append(f"re-enable {pid} (热插拔)")
        for pid in reversed(order):
            self.unload(pid)
            report["steps"].append(f"unload {pid}")
        report["ok"] = all(r.state == PluginState.UNLOADED for r in self._records.values())
        return report

    # ---------- 注册表 ----------
    def save_registry(self) -> Path:
        """写全局插件注册表 plugin_registry.json。"""
        entries = []
        for rec in self._records.values():
            entries.append({
                "id": rec.plugin_id, "name": rec.name, "version": rec.version,
                "description": rec.description, "author": rec.author, "license": rec.license,
                "source": rec.source, "verified": rec.verified, "status": rec.state,
                "capabilities": rec.capabilities, "hooks": rec.hooks,
                "dependencies": rec.dependencies, "path": rec.path,
            })
        payload = {"generated": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
                   "count": len(entries), "plugins": entries}
        self.registry_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
        return self.registry_path

    # ---------- 查询 ----------
    def records(self) -> List[PluginRecord]:
        return list(self._records.values())

    def get(self, plugin_id: str) -> Optional[PluginRecord]:
        return self._records.get(plugin_id)

    def instance(self, plugin_id: str) -> Optional[Plugin]:
        return self._instances.get(plugin_id)
