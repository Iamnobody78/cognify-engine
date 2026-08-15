#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TRI-SYNC PATHS — 路径中心化模块 (2026-08-15 解耦化)
===================================================
单一事实来源: 读 daemon/sync_config.yaml 的 sources 段, 暴露 WS/TRI/HOME 常量。
各脚本不再各自硬编码绝对路径 — 迁移样板: meta_cognition.py。
用法: from trisync_paths import WS, TRI, HOME
"""
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

TRI = Path(r"C:\Users\ivy\.aionui-tri-sync")
HOME = Path.home()

_config_path = TRI / "daemon" / "sync_config.yaml"
WS = None
if yaml and _config_path.exists():
    try:
        cfg = yaml.safe_load(_config_path.read_text(encoding="utf-8"))
        ws_path = cfg.get("sync", {}).get("workspace")
        if ws_path:
            WS = Path(ws_path)
    except Exception:
        WS = None
if WS is None:
    WS = Path(r"C:\Users\ivy\AppData\Roaming\AionUi\aionui\conversations\2026\07\27\aionrs-temp-48324704")


def main():
    print(f"TRI = {TRI}")
    print(f"WS  = {WS} (来自 sync_config.yaml)")
    print(f"HOME= {HOME}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
