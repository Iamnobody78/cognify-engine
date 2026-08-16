#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
paths.py — A4 路径中立化共享解析 (三期)
========================================
优先级: 环境变量 → 本机 legacy 路径 (兼容现有部署) → ~/.cognify (中立默认)。
新机器无 legacy 时: TRI 指向 ~/.cognify, 未初始化时引擎输出指引而非崩溃。
"""
import os
import sys
from pathlib import Path

LEGACY_TRI = Path.home() / ".aionui-tri-sync"
LEGACY_PROD = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704\cognify-engine")
NEUTRAL_TRI = Path.home() / ".cognify"
NEUTRAL_PROD = Path.home() / ".cognify/cognify-engine"


def resolve_tri() -> Path:
    env = os.environ.get("COGNIFY_TRI")
    if env:
        return Path(env)
    if LEGACY_TRI.exists():
        return LEGACY_TRI
    return NEUTRAL_TRI


def resolve_prod() -> Path:
    env = os.environ.get("COGNIFY_PROD")
    if env:
        return Path(env)
    if LEGACY_PROD.exists():
        return LEGACY_PROD
    # 退化: 从本文件位置推导仓库根
    here = Path(__file__).resolve()
    if (here.parent.parent / "cli" / "cognify.py").exists():
        return here.parent.parent
    return NEUTRAL_PROD


def resolve_py() -> str:
    env = os.environ.get("COGNIFY_PY")
    if env:
        return env
    return sys.executable


TRI = resolve_tri()
PROD = resolve_prod()
PY = resolve_py()
