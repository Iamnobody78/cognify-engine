# -*- coding: utf-8 -*-
"""
cognify._cli — 入口 shim: 委托仓库内 cli/cognify.py (保持单一事实来源)。

本地部署模式: 仓库完整克隆, 入口指向仓库内 CLI。
PyPI 模式: 当前 wheel 不含 cli/ (P2 打包修复中) — 提供诚实降级提示。
"""
import runpy
import sys
from pathlib import Path


def main() -> int:
    cli = Path(__file__).resolve().parent.parent / "cli" / "cognify.py"
    if not cli.exists():
        print("[cognify] PyPI 安装模式: 完整 CLI 尚未打包 (v2.3.0 修复中)。")
        print("[cognify] 完整功能请从源码运行: git clone https://github.com/Iamnobody78/cognify-engine")
        return 1
    sys.argv[0] = str(cli)
    runpy.run_path(str(cli), run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
