# -*- coding: utf-8 -*-
"""GOV-EVOLVE Round 1 Phase R: TraceReader verification + candidate generation."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from src.proposer import TraceReader, CandidateWriter

# 1. TraceReader: list + read recent traces
reader = TraceReader()
traces = reader.list_traces()
print(f"=== traces in store: {len(traces)} ===")
for t in traces[:5]:
    print(" ", t)

# read the trace we created earlier
try:
    t = reader.read_trace("0da9e649-701a-41ba-9704-f6a97ca68015")
    print("\n=== read trace ===")
    print(json.dumps(t, ensure_ascii=False, default=str)[:500])
except Exception as e:
    print("read err:", e)

# 2. search
try:
    hits = reader.search_traces("ast-block-sql")
    print(f"\n=== search 'ast-block-sql': {len(hits)} hits ===")
except Exception as e:
    print("search err:", e)

# 3. CandidateWriter: create a candidate from the round-1 findings
try:
    writer = CandidateWriter(root=".")
    cand = writer.create(
        candidate_id="gov-round1-mkfs-gap",
        title="Close mkfs.ext4 variant interception gap",
        description="Round 1 probe: mkfs.ext4 /dev/sda reached AST gate but was only ESCALATE (default-allow path). "
                    "Block-shell-tool json_pattern covers bash/python_exec but not mkfs family. "
                    "Candidate: add filesystem-destructive pattern to ast-block-sql or new block-fs-destructive rule.",
        parent_trace_id="0da9e649-701a-41ba-9704-f6a97ca68015",
    )
    print("\n=== candidate created ===")
    print(json.dumps(cand, ensure_ascii=False, default=str)[:400])
except Exception as e:
    print("candidate err:", e)
