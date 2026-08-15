# -*- coding: utf-8 -*-
"""Correct the candidate - mkfs IS blocked (no gap). Rewrite candidate description honestly."""
import sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, ".")
from src.proposer import CandidateWriter

writer = CandidateWriter(root=".")
cand = writer.create(
    name="gov-r1-verify-mkfs-path",
    parent_trace_id="0da9e649-701a-41ba-9704-f6a97ca68015",
    mutation_note=(
        "Round1 verification (honest correction): mkfs.ext4 /dev/sdb1 IS DENIED by ast-block-bash "
        "(destructive-filesystem-tool, sexp=command_name word). No interception gap. "
        "The earlier 'mkfs gap' hypothesis was WRONG - HTTP probe used tools-declaration format "
        "which routes to block-shell-tool json_pattern, while benchmark uses script field "
        "routing to AST gate. Both paths intercept correctly. "
        "Round1 finding: 6/6 verdict correctness (3 DENY + 3 ALLOW), 0 false positives. "
        "TraceReader+ CandidateWriter pipeline verified working."
    ),
)
print("candidate:", json.dumps(cand, ensure_ascii=False, default=str)[:300])
