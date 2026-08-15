#!/usr/bin/env python3
"""S34 P0: 从 simulation_rules.abdl 物理删除 CAUTIOUS-EDGE 规则块 (注释化->删除)."""
import sys

p = "bottlesumo_pi/governance/meta_language/simulation_rules.abdl"
with open(p, "rb") as f:
    data = f.read()
# 推断行尾符: 优先 CRLF (Windows 工作区), 否则 LF
nl = "\r\n" if b"\r\n" in data else "\n"
text = data.decode("utf-8")

old_block = (
    '  - id: "SIM-HEUR-CAUTIOUS-EDGE"' + nl +
    '    level: 3' + nl +
    '    condition: "BETWEEN(sensor(edge_proximity), 0.55, 0.78)"' + nl +
    "    action: \"EXECUTE(PolicyCautiousEdge) AND LOG('cautious_edge')\"" + nl +
    '    priority: 250' + nl +
    '    description: "When moderate edge risk, reduce speed and widen turns"' + nl +
    '    context: "edge_awareness"' + nl +
    '    source: "simulation_rules.abdl > L3 Heuristic"'
)

cnt = text.count(old_block)
assert cnt == 1, f"CAUTIOUS-EDGE block count={cnt} (expected 1)"
text = text.replace(old_block, "")
while nl + nl + nl in text:
    text = text.replace(nl + nl + nl, nl + nl)
with open(p, "wb") as f:
    f.write(text.encode("utf-8"))
print(f"removed CAUTIOUS-EDGE block (count={cnt})")
print(f"CAUTIOUS occurrences now: {text.count('CAUTIOUS')}")
print(f"SIM-HEUR- rule ids now: {text.count('- id: \"SIM-HEUR-')}")
print(f"total rule ids: {text.count('  - id:')}")
