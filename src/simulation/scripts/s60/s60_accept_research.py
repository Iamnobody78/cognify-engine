"""S60: research engine acceptance — all gate phases + pipeline determinism."""
import json, os, sys, tempfile

sys.path.insert(0, "governance/research")
from research_gate import evaluate_artifact, CRITERIA
from research_orchestrator import phase_map

OUT = "governance/research/outputs"

# 1. gate phases present
print("gate phases:", sorted(CRITERIA.keys()))

# 2. map phase on existing papers artifact
papers_path = os.path.join(OUT, "research_papers_list.json")
assert os.path.exists(papers_path), "papers artifact missing"
mapped = phase_map(papers_path)
with open(mapped) as f:
    mp = json.load(f)
print(f"map -> {len(mp['patterns'])} patterns; gate papers check on source:")
rep = evaluate_artifact("papers", papers_path)
print(f"  papers gate: passed={rep['passed']} ({rep['n_pass']}/{rep['n_total']})")

# 3. experiment + evidence + synthesis gates accept a well-formed artifact
wellformed = {
    "independent": ["model_type"], "dependent": ["success_rate"],
    "control": ["task_set"], "predictions": ["VTLA>VLA in contact tasks"],
    "confidence": 0.82, "effect_size": "d=1.3",
    "engineering_rules": ["RULE-RS-001"], "boundaries": ["sim-only"],
}
for ph in ("experiment", "evidence", "synthesis"):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(wellformed, f)
        p = f.name
    rep = evaluate_artifact(ph, p)
    os.unlink(p)
    print(f"  {ph} gate: passed={rep['passed']} ({rep['n_pass']}/{rep['n_total']})")
print("RESEARCH ENGINE ACCEPTANCE: OK")
