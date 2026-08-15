#!/usr/bin/env python3
# S34 P1 验证: 12 规则基线下重跑 D5 再校准, 确认三强规则置信度稳定复现
import json
import subprocess
import sys

OUT = r"_tmp/s34_recal_out"

cmd = [
    sys.executable, "governance/meta_harness/distill_loop.py",
    "--recalibrate", "--out", OUT,
]
p = subprocess.run(cmd, capture_output=True, text=True, cwd=r"/mnt/c/Users/ivy/AppData/Roaming/AionUi/aionui/conversations/2026/07/27/aionrs-temp-48324704/bottlesumo_pi")
print("=== stderr ===")
print(p.stderr[:2000] if p.stderr else "(none)")
print("=== exit ===", p.returncode)

# run() 返回 summary; 完整规则在 rules_file (distill_rules_<ts>.json)
try:
    d = json.loads(p.stdout)
except Exception as e:
    print("JSON parse failed:", e)
    print(p.stdout[:2000])
    sys.exit(1)

rules_path = d.get("rules_file")
print("=== rules_file:", rules_path)
if not rules_path:
    print("no rules_file in summary:", json.dumps(d, ensure_ascii=False)[:1000])
    sys.exit(1)

with open(rules_path, "r", encoding="utf-8") as f:
    rules = json.load(f)

# 重排后的规则列表位于顶层 d1_desensitization / d2_perturbation_prior
d1 = rules.get("d1_desensitization") or []
d2 = rules.get("d2_perturbation_prior") or []
print("=== d1 top5 (recalibrated) ===")
for r in d1[:5]:
    print(" ", r.get("id"), round(r.get("confidence", 0), 3), "| q=", r.get("quality", "?"))
print("=== d2 top5 (recalibrated) ===")
for r in d2[:5]:
    print(" ", r.get("id"), round(r.get("confidence", 0), 3), "| q=", r.get("quality", "?"))

# 断言三强规则存在且置信度与 S33 一致 (0.48 / 0.30 / 0.26)
expect = {"topo_B": 0.48, "mapping_001": 0.30, "topo_A": 0.26}
combined = {r.get("id"): r for r in d1 + d2}
ok = True
for vid, conf in expect.items():
    r = next((rr for k, rr in combined.items() if vid in k), None)
    if r is None:
        print(f"MISSING: {vid}")
        ok = False
    else:
        c = round(r.get("confidence", 0), 2)
        flag = "OK" if abs(c - conf) < 0.02 else "MISMATCH"
        if flag != "OK":
            ok = False
        print(f"{vid} ({r.get('id')}): conf={c} (expect {conf}) -> {flag}")
print("=== SUMMARY:", "PASS - 三强规则稳定复现" if ok else "FAIL - 置信度漂移")
sys.exit(0 if ok else 1)
