"""S60: verify research engine modules import cleanly (standalone paths)."""
import sys

sys.path.insert(0, "governance/research")
from paper_retriever import fetch_arxiv, save
from research_gate import evaluate_artifact, CRITERIA
from research_orchestrator import phase_survey, phase_map, OUTPUTS
import os

print("imports OK")
print("gate phases:", sorted(CRITERIA.keys()))
print("outputs dir:", OUTPUTS, "exists:", os.path.isdir(OUTPUTS))

# quick offline gate check on existing artifact
p = os.path.join(OUTPUTS, "research_papers_list.json")
if os.path.exists(p):
    rep = evaluate_artifact("papers", p)
    print(f"existing papers artifact: passed={rep['passed']} ({rep['n_pass']}/{rep['n_total']})")
else:
    print("papers artifact not found — run paper_retriever first")
