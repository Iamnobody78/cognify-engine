# -*- coding: utf-8 -*-
"""GOV-EVOLVE Round 1: create candidate with correct API + inspect candidates dir."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from src.proposer import TraceReader, CandidateWriter

writer = CandidateWriter(root=".")
cand = writer.create(
    name="close-mkfs-ext4-gap",
    parent_trace_id="0da9e649-701a-41ba-9704-f6a97ca68015",
    mutation_note="Round1 probe: mkfs.ext4 reached AST gate as default-allow. Add fs-destructive rule.",
)
print("candidate:", json.dumps(cand, ensure_ascii=False, default=str)[:300])

# check candidates dir
import os
cands_dir = os.path.join("candidates")
if os.path.isdir(cands_dir):
    print("\n=== candidates dir ===")
    for d in os.listdir(cands_dir)[:10]:
        print(" ", d)
        # check src content
        src = os.path.join(cands_dir, d, "src")
        if os.path.isdir(src):
            for f in os.listdir(src)[:5]:
                print(f"    src/{f}")
