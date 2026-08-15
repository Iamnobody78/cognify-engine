"""S62 R1 unit tests: A1 protocol compiler + A2 memory scaffold.

Run: python3 governance/tests/test_s62_notion_r1.py
"""
import json
import os
import shutil
import sys
import tempfile

# repo root = tests/../../.. (governance/tests -> governance -> bottlesumo_pi)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO_ROOT)
from governance.protocols.protocol_compiler import (compile_protocols,
                                                    verify_yaml,
                                                    REQUIRED_FIELDS,
                                                    demo_records)
from governance.memory_scaffold import scaffold, verify, SCAFFOLD, ROOT_FILES


# ── A1: protocol compiler ──────────────────────────────────────────────────
def test_compiler_requires_all_11_fields():
    bad = [{"module": "x"}]  # missing 11 fields
    try:
        compile_protocols(bad, "/tmp/never")
        return False, "should have raised ValueError"
    except ValueError as e:
        assert "missing required fields" in str(e)
        return True, ""

def test_compiler_writes_valid_yaml():
    with tempfile.TemporaryDirectory() as td:
        out = compile_protocols(demo_records(), td)
        assert len(out) == 3
        for p in out.values():
            assert os.path.isfile(p)
            assert verify_yaml(p), f"{p} failed verify"
        return True, f"3 protocols verified"

def test_compiler_yaml_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        out = compile_protocols(demo_records(), td)
        fpath = list(out.values())[0]
        import yaml
        with open(fpath, encoding="utf-8") as f:
            doc = yaml.safe_load(f)
        proto = doc["protocol"]
        for k in REQUIRED_FIELDS:
            assert k in proto, f"missing {k}"
        return True, "yaml roundtrip OK"


# ── A2: memory scaffold ────────────────────────────────────────────────────
def test_scaffold_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "aionui")
        scaffold(target, dry_run=True)
        assert not os.path.exists(target), "dry-run must not write"
        return True, "dry-run clean"

def test_scaffold_full_generation_and_verify():
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "aionui")
        scaffold(target, dry_run=False)
        rep = verify(target)
        assert rep["complete"], f"verify incomplete: {rep}"
        return True, f"dirs {rep['dirs_ok']}/{rep['dirs_total']} files {rep['files_ok']}/{rep['files_total']} manifest={rep['manifest_valid']}"

def test_scaffold_manifest_valid_json():
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "aionui")
        scaffold(target, dry_run=False)
        with open(os.path.join(target, "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        assert m["file_count"] == sum(len(v) for v in SCAFFOLD.values()) + len(ROOT_FILES)
        return True, f"manifest file_count={m['file_count']}"


def test_scaffold_has_expected_dirs():
    with tempfile.TemporaryDirectory() as td:
        target = os.path.join(td, "aionui")
        scaffold(target, dry_run=False)
        for d in SCAFFOLD:
            assert os.path.isdir(os.path.join(target, d)), f"missing dir {d}"
        return True, f"all {len(SCAFFOLD)} dirs present"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    npass = 0
    fails = []
    for name, fn in tests:
        try:
            ok, msg = fn()
            if ok:
                print(f"  [PASS] {name}: {msg}")
                npass += 1
            else:
                fails.append((name, msg))
        except Exception as e:
            fails.append((name, f"{type(e).__name__}: {e}"))
    for name, err in fails:
        print(f"  [FAIL] {name}: {err}")
    print(f"\n{len(tests)} tests, {npass} passed")
    sys.exit(0 if npass == len(tests) else 1)
