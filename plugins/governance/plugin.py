# -*- coding: utf-8 -*-
"""
Governance Engine 插件 (cognify.governance)
===========================================
内容: agent-governance-v2 全仓库快照 (src/ 子树, git 历史保留)。
职责: 协议网关 / VCE 扫描 / 声明验证 / 治理回归测试。
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from pathlib import Path
from typing import Any, Dict

from core.plugin_base import Plugin as BasePlugin

HERE = Path(__file__).resolve().parent
REPO = HERE / "src"  # agv2 仓库根


class Plugin(BasePlugin):
    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._gateway = None

    @property
    def manifest(self) -> Dict[str, Any]:
        return {
            "id": "cognify.governance", "name": "Governance Engine",
            "version": "0.1.0",
            "capabilities": ["governance", "vce", "verification", "audit"],
        }

    def on_load(self, config: Dict[str, Any]) -> None:
        gateway = REPO / "src" / "protocol_gateway.py"
        if not gateway.exists():
            raise FileNotFoundError(f"协议网关缺失: {gateway}")
        self._gateway = gateway

    def on_enable(self) -> None:
        if self.bus:
            self.bus.publish("governance.ready", {"id": "cognify.governance",
                                                  "gateway": str(self._gateway)})
        # 网关冒烟: 导入即验证
        sys.path.insert(0, str(REPO))
        try:
            from src.protocol_gateway import ProtocolGateway  # noqa: F401
            self._smoke = True
        except Exception as exc:  # noqa: BLE001
            self._smoke = False
            raise RuntimeError(f"网关导入失败: {exc}")

    def on_disable(self) -> None:
        self._smoke = False

    def on_unload(self) -> None:
        self._gateway = None

    def run_regression(self) -> Dict[str, Any]:
        """治理回归: 运行 src/tests (需 pytest + pytest-asyncio)。"""
        import subprocess
        py = self.config.get("python") or r"C:\Users\ivy\AppData\Local\Programs\Python\Python312\python.exe"
        r = subprocess.run([py, "-m", "pytest", "-q", "--no-header", "tests"],
                           cwd=str(REPO), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=1800)
        return {"returncode": r.returncode, "tail": (r.stdout or r.stderr or "")[-400:]}
