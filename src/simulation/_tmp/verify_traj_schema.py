import json
from pathlib import Path

root = Path("models/mujoco_aggressive_trajectories")
files = sorted(root.glob("ep_*.json"))
print(f"{len(files)} trajectory files written")
if files:
    d = json.loads(files[0].read_text())
    print("keys:", list(d.keys()))
    print("steps:", d["steps"], "won:", d["won"], "reason:", d["reason"])
    print("first frame:", d["trajectory"][0])
    # sanity: all obs length 7, actions ints
    assert all(len(fr["obs"]) == 7 for fr in d["trajectory"]), "obs len != 7"
    assert all(isinstance(fr["action"], int) for fr in d["trajectory"])
    print("schema OK (obs=7, actions int)")
