#!/usr/bin/env python3
"""检查 D5 输出顶层结构."""
import json

d = json.load(open("governance/meta_harness/experience/distill_rules_20260808_192309.json"))
print("d1 top-level type:", type(d["d1_desensitization"]).__name__)
if isinstance(d["d1_desensitization"], dict):
    print("d1 keys:", list(d["d1_desensitization"].keys())[:8])
elif isinstance(d["d1_desensitization"], list):
    print("d1 len:", len(d["d1_desensitization"]))
    print("first elem type:", type(d["d1_desensitization"][0]).__name__)
    if isinstance(d["d1_desensitization"][0], dict):
        print("first keys:", list(d["d1_desensitization"][0].keys()))
print()
print("d2 top-level type:", type(d["d2_perturbation_prior"]).__name__)
if isinstance(d["d2_perturbation_prior"], dict):
    print("d2 keys:", list(d["d2_perturbation_prior"].keys())[:8])
elif isinstance(d["d2_perturbation_prior"], list):
    print("d2 len:", len(d["d2_perturbation_prior"]))
    print("first elem type:", type(d["d2_perturbation_prior"][0]).__name__)
    if isinstance(d["d2_perturbation_prior"][0], dict):
        print("first keys:", list(d["d2_perturbation_prior"][0].keys()))
