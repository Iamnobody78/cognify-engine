# -*- coding: utf-8 -*-
"""
DEBT-021 缓解 (2026-08-15): uv python 3.11.15 在 Windows Proactor 事件循环 +
线程路径下原生 AV (0xC0000005, asyncio/windows_events + linecache)。
本 conftest 将测试会话强制为 SelectorEventLoop 策略, 绕开崩溃路径。
纯测试基建, 不影响引擎语义。若需回退: 删除本文件。
"""
import asyncio
import sys

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
