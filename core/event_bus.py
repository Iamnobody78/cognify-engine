# -*- coding: utf-8 -*-
"""
event_bus.py — 插件间事件总线 (PLUGINIFY v1.0)
===============================================
解耦通信: 插件不互相 import, 只通过事件类型收发消息。

    bus.subscribe("cognify.heartbeat", cb)   # 订阅 (返回 token)
    bus.publish("cognify.heartbeat", {...})  # 发布 (同步回调)

红线: 未注册事件监听的情况下禁止插件间直接通信。
"""
import itertools
import threading
from typing import Any, Callable, Dict, List, Tuple


class EventBus:
    """进程内同步事件总线。"""

    def __init__(self) -> None:
        self._subs: Dict[str, List[Tuple[int, Callable[[Any], None]]]] = {}
        self._lock = threading.Lock()
        self._counter = itertools.count(1)
        self._history: List[Dict[str, Any]] = []

    def subscribe(self, event_type: str, callback: Callable[[Any], None]) -> int:
        """订阅事件, 返回可退订的 token。"""
        if not callable(callback):
            raise TypeError("callback must be callable")
        with self._lock:
            token = next(self._counter)
            self._subs.setdefault(event_type, []).append((token, callback))
            return token

    def unsubscribe(self, token: int) -> bool:
        """按 token 退订。幂等。"""
        with self._lock:
            for event_type, subs in self._subs.items():
                for i, (t, _cb) in enumerate(subs):
                    if t == token:
                        subs.pop(i)
                        if not subs:
                            del self._subs[event_type]
                        return True
        return False

    def publish(self, event_type: str, data: Any = None) -> int:
        """发布事件, 同步调用所有订阅者。返回投递数。

        单个订阅者异常被捕获记录, 不影响其他订阅者 (隔离红线)。
        """
        with self._lock:
            subs = list(self._subs.get(event_type, []))
        delivered = 0
        for _token, cb in subs:
            try:
                cb(data)
                delivered += 1
            except Exception as exc:  # noqa: BLE001 - 隔离单个订阅者故障
                self._history.append({"event": event_type, "error": str(exc)})
        self._history.append({"event": event_type, "delivered": delivered})
        self._history = self._history[-200:]  # 环形日志
        return delivered

    def history(self) -> List[Dict[str, Any]]:
        """最近事件日志 (观测/审计用)。"""
        return list(self._history)

    def subscriptions(self) -> Dict[str, int]:
        """当前订阅统计。"""
        return {k: len(v) for k, v in self._subs.items()}
