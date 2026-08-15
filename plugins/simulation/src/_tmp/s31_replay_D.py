#!/usr/bin/env python3
"""S31 T2 复核: 重放 topo_D diff, 确认 apply 产物精确性.

疑点: topo_D 结果中 92 次裸 'abdl:' 键 + FLANK-LEFT 84->133 反增,
      需确认是 '规则真空'(收窄留下 (10,15] 与 [-15,-10) 无规则覆盖, 真实负结果)
      还是 apply 破坏 (str.replace 污染其他规则).
"""
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
RULES = os.path.join(REPO, "governance", "meta_language", "simulation_rules.abdl")

src = open(RULES, encoding="utf-8").read()

# 1. 锚点精确性: < -10 与 > 10 各出现几次 (含 BETWEEN 里的 -10, 10 要排除)
print("=== 锚点计数 (原文件) ===")
for pat in ["sensor(opponent_angle) < -10", "sensor(opponent_angle) > 10",
            "sensor(opponent_angle) < -15", "sensor(opponent_angle) > 15",
            "BETWEEN(sensor(opponent_angle), -10, 10)"]:
    print(f"  {pat!r}: {src.count(pat)} 次")

# 2. 重放 D 的 diff
d1 = src.replace("sensor(opponent_angle) < -10", "sensor(opponent_angle) < -15")
d1 = d1.replace("sensor(opponent_angle) > 10", "sensor(opponent_angle) > 15")

print("\n=== 重放后关键行 ===")
for i, line in enumerate(d1.splitlines(), 1):
    if any(k in line for k in ["FLANK", "CLOSE-PUSH", "CAUTIOUS-EDGE", "Pursue"]):
        print(f"  L{i}: {line.strip()[:110]}")

# 3. 检查是否残留 < -10 或 > 10 (BETWEEN 除外)
print("\n=== 残留检查 ===")
print(f"  '< -10' 残留: {d1.count('sensor(opponent_angle) < -10')} (应为 0)")
print(f"  '> 10' 残留: {d1.count('sensor(opponent_angle) > 10')} (应为 0)")
print(f"  'BETWEEN(..., -10, 10)' 保留: {d1.count('BETWEEN(sensor(opponent_angle), -10, 10)')} (应=1)")
print(f"  '< -15': {d1.count('sensor(opponent_angle) < -15')} (应=1)")
print(f"  '> 15': {d1.count('sensor(opponent_angle) > 15')} (应=1)")

# 4. 语义检查: 收窄后的覆盖真空
#    原: FLANK-RIGHT < -10, CLOSE-PUSH [-10,10], FLANK-LEFT > 10  (全覆盖)
#    新: FLANK-RIGHT < -15, CLOSE-PUSH [-10,10], FLANK-LEFT > 15  ((-15,-10)∪(10,15) 真空)
print("\n=== 覆盖真空分析 ===")
print("  原规则角度覆盖: (-inf,-10) FR / [-10,10] CP / (10,+inf) FL  -> 全覆盖")
print("  新规则角度覆盖: (-inf,-15) FR / [-10,10] CP / (15,+inf) FL")
print("  真空区间: (-15,-10) 与 (10,15) — 若 ABDL 无 fallback, 触发裸分支或默认动作")
