"""BottleSumo 高级组合规性检查器 (BS-DEPLOY-PREP A5)。

依据: 2026 CTEA 賽規 (高級組) — constraints_spec.json
用途: 赛前检查 (非硬件, 纯配置校验); 红线 #1: 未通过合规检查禁止参赛。

检查项 (对齐赛规):
  G1 尺寸紧凑: 直径≤30cm, 高度≤30cm
  G2 尺寸延展: 直径≤35cm, 高度≤35cm
  G3 重量: ≤1kg
  G4 控制器: ≤2 個
  G5 电机: ≤3 個 (任何種類)
  G6 传感器: 无视觉系统限制 (高级组不限, 须对人无害)
  G7 电池电压: ≤14V
  G8 违禁部件: 无固定裝置(吸盤/真空泵)/黏性車輪/鋒利刀口
  G9 地面间隙: 除移動結構/支撐物外 ≥2mm
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class RobotSpec:
    """待检机器人配置 (真机就绪后填入实际值)。"""
    name: str = "bottlesumo-2026"
    diameter_cm: float = 25.0       # 比赛状态直径
    height_cm: float = 25.0         # 比赛状态高度
    extended_diameter_cm: float = 32.0   # 延展后直径
    extended_height_cm: float = 30.0     # 延展后高度
    weight_kg: float = 0.75         # 总重 (LiDAR 60g 已计入)
    controllers: int = 1            # 主控数量
    motors: int = 3                 # 电机数量 (24GP-2430 x3)
    has_camera: bool = False        # 高级组不限, 此处如实声明
    battery_v: float = 7.4          # 2S LiPo
    has_suction: bool = False       # 吸盤/真空泵
    has_sticky_wheels: bool = False # 黏性車輪
    has_blades: bool = False        # 鋒利刀口
    ground_clearance_mm: float = 5.0


@dataclass
class CheckResult:
    passed: bool
    items: List[Dict] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"[{'PASS' if self.passed else 'FAIL'}] 合规性检查"]
        for it in self.items:
            mark = "✅" if it["ok"] else "❌"
            lines.append(f"  {mark} {it['id']}: {it['detail']}")
        return "\n".join(lines)


class ComplianceChecker:
    """赛前合规性检查 — 纯配置校验, 无硬件操作。"""

    def check(self, spec: RobotSpec) -> CheckResult:
        items: List[Dict] = []
        ok_all = True

        def _add(ok: bool, cid: str, detail: str):
            nonlocal ok_all
            ok_all = ok_all and ok
            items.append({"ok": ok, "id": cid, "detail": detail})

        # G1 紧凑尺寸
        _add(spec.diameter_cm <= 30, "G1a", f"直径 {spec.diameter_cm}cm ≤ 30cm")
        _add(spec.height_cm <= 30, "G1b", f"高度 {spec.height_cm}cm ≤ 30cm")
        # G2 延展尺寸
        _add(spec.extended_diameter_cm <= 35, "G2a",
             f"延展直径 {spec.extended_diameter_cm}cm ≤ 35cm")
        _add(spec.extended_height_cm <= 35, "G2b",
             f"延展高度 {spec.extended_height_cm}cm ≤ 35cm")
        # G3 重量
        _add(spec.weight_kg <= 1.0, "G3", f"重量 {spec.weight_kg}kg ≤ 1kg")
        # G4 控制器
        _add(spec.controllers <= 2, "G4", f"控制器 {spec.controllers} ≤ 2")
        # G5 电机
        _add(spec.motors <= 3, "G5", f"电机 {spec.motors} ≤ 3")
        # G6 传感器 (高级组不限; 如实声明视觉)
        _add(True, "G6", f"传感器不限 (高级组); camera={'有' if spec.has_camera else '无'}")
        # G7 电池
        _add(spec.battery_v <= 14, "G7", f"电池 {spec.battery_v}V ≤ 14V")
        # G8 违禁部件
        _add(not spec.has_suction, "G8a", "无吸盤/真空泵" if not spec.has_suction else "❌ 含吸盤")
        _add(not spec.has_sticky_wheels, "G8b", "无黏性車輪" if not spec.has_sticky_wheels else "❌ 含黏性輪")
        _add(not spec.has_blades, "G8c", "无鋒利刀口" if not spec.has_blades else "❌ 含刀口")
        # G9 地面间隙
        _add(spec.ground_clearance_mm >= 2, "G9",
             f"地面间隙 {spec.ground_clearance_mm}mm ≥ 2mm")

        return CheckResult(passed=ok_all, items=items)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    result = ComplianceChecker().check(RobotSpec())
    print(result.render())
    print("门禁 G4:", "PASS" if result.passed else "FAIL")
