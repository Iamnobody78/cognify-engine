# -*- coding: utf-8 -*-
"""
cognify._cli — 入口 shim: 委托仓库内 cli/cognify.py (保持单一事实来源)。

本地部署模式: 仓库完整克隆, 入口指向仓库内 CLI。
PyPI 模式: 仓库随 wheel 分发 (后续将 cli/ 纳入 package-data 后同路径生效)。
"""
import runpy
import sys
from pathlib import Path


def main() -> int:
    cli = Path(__file__).resolve().parent.parent / "cli" / "cognify.py"
    if not cli.exists():
        print(f"[cognify] 未找到 CLI: {cli}")
        return 1
    sys.argv[0] = str(cli)
    runpy.run_path(str(cli), run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main())
