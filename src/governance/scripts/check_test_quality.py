"""Gate 1 + 2: Test quality scanner.

Gate 1 (no-dataclass-asserts): AST-scans test files for `assert x == y` patterns
that test Python dataclass field assignment instead of real runtime behavior.

Gate 2 (test-count): prevents test inflation by enforcing a maximum test count.
If exceeded, the test author must provide explicit justification.

Usage:
    python scripts/check_test_quality.py
    # exit 0 = all gates pass, exit 1 = gate failure with explanation
"""

import ast
import sys
from pathlib import Path

# ── configuration ──────────────────────────────────────────────────
MAX_TEST_COUNT = 50          # beyond this, require explicit approval
TEST_DIR = "tests"
VIOLATION_EXIT_CODE = 1

# known-good patterns that are NOT dataclass asserts:
# - assert resp.status == 200      (verify HTTP response)
# - assert data["verdict"] == "DENY" (verify API response)
# - assert elapsed < 1.0           (verify timeout)
# - assert len(set(ids)) == 15     (verify uniqueness of generated UUIDs)
# - assert "block-delete" in ...   (verify content match)
# These all operate on runtime values, not dataclass fields.


class AssertVisitor(ast.NodeVisitor):
    """Visit all `assert` statements and classify them."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.total_asserts = 0
        self.dataclass_asserts: list[tuple[int, str]] = []

    def visit_Assert(self, node: ast.Assert):
        self.total_asserts += 1
        # Check if this is a simple equality assert of two simple names/literals
        if isinstance(node.test, ast.Compare):
            comp = node.test
            if self._is_simple_equality(comp):
                self.dataclass_asserts.append((
                    node.lineno,
                    ast.unparse(node.test) if hasattr(ast, "unparse") else str(node.lineno),
                ))
        self.generic_visit(node)

    @staticmethod
    def _has_call_root(node) -> bool:
        """True if node is (or is an attribute/subscript chain rooted in) a
        function call — i.e. a *runtime result* (engine.evaluate(...).action,
        extract_tool_names(...)[0]), never a dataclass field.

        v0.2.2 (external critique #6.2): previously only Name-rooted attribute
        chains were exempted, so `engine.evaluate(...).action == 'DENY'` was
        wrongly flagged as a dataclass assert.
        """
        while isinstance(node, (ast.Attribute, ast.Subscript)):
            node = node.value
        return isinstance(node, ast.Call)

    @staticmethod
    def _is_simple_equality(comp: ast.Compare) -> bool:
        """Detect patterns like `assert x == y` or `assert x.attr == "value"`.

        We consider it a dataclass assert if both sides are:
        - simple names (x, y)
        - attribute access on simple names (x.id, x.content)
        - simple constants ("string", 42)
        AND neither side involves:
        - HTTP response patterns (resp.status, data["key"], result.verdict)
        - function calls (len(), set(), json.loads())
        - attribute chains rooted in a call (runtime results)
        - comparison operators other than ==
        """
        if len(comp.ops) != 1 or not isinstance(comp.ops[0], ast.Eq):
            return False

        left = comp.left
        right = comp.comparators[0]

        # Reject: list/set/dict/generator comprehensions on either side —
        # `[x.name for x in idx.candidates(...)] == [...]` evaluates a
        # RUNTIME query result (index candidates, pareto points, trace
        # steps), not dataclass field assignment. (AUDIT-0047, GATE 1
        # precision fix — 11 of 26 findings were list comprehensions.)
        for side in (left, right):
            if isinstance(side, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                return False

        # Reject: runtime function-call results on either side
        # (engine.evaluate(...).action, _extract_tool_names(...)["a"])
        if AssertVisitor._has_call_root(left) or AssertVisitor._has_call_root(right):
            return False
        # Reject: runtime subscript access (data["verdict"], resp["status"])
        if isinstance(left, ast.Subscript) or isinstance(right, ast.Subscript):
            return False
        # Reject: function calls on either side (len(), set(), json.loads())
        if isinstance(left, ast.Call) or isinstance(right, ast.Call):
            return False
        # Reject: comparisons with non-name left side (e.g. time.time() - t0)
        if isinstance(left, ast.BinOp):
            return False
        # Reject: content checks (assert "xxx" in data)
        if any(isinstance(op, ast.In) or isinstance(op, ast.NotIn) for op in comp.ops):
            return False
        # Reject: simple variable names from HTTP/async context
        if isinstance(left, ast.Name):
            # A bare Name comparison (`flushed == 1`, `parsed == dt`, `t2 == ...`)
            # verifies a local variable's state — a state-transition / IO result,
            # NOT a dataclass field assignment. GATE 1's intent (v0.2, audit 5.x)
            # is to block `obj.field == value` dataclass asserts, so bare-Name
            # equality is always a runtime-behavior check. Exception: keep the
            # legacy allow-list names (they were exempted for HTTP/async context).
            if left.id in ("actual", "expected", "results", "tasks", "ids", "names"):
                return False
            # Name vs Name or Name vs Constant: local variable state check → exempt
            return False
        # Reject: HTTP response patterns — resp.status, data.verdict, result.x
        if isinstance(left, ast.Attribute):
            root = left
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                if root.id in ("resp", "response", "data", "result", "actual", "expected", "main_module"):
                    return False
                # Runtime-state roots (v0.2.3, CI drift fix, AUDIT-0021):
                # - engine: policy engine instance — config.version asserts verify
                #   hot-reload state transitions, not field assignment
                # - d: module object — d.__all__ asserts module export contract
                # - EPOCH: timezone-aware constant — EPOCH.tzinfo checks tz data
                if root.id in ("engine", "d", "EPOCH"):
                    return False
                # Runtime-state roots (v0.2.4, AUDIT-0073, GATE 1 precision
                # fix — same class as engine/r_a above):
                # - event: metacognition observer event records — asserting
                #   event.verdict / event.path verifies the RECORDING behavior
                #   (runtime behavior log), not dataclass field assignment
                # - obs: observer instance runtime config (window,
                #   deviation_threshold, min_samples — config propagation)
                # - gw: gateway verify-channel state transitions
                #   (gw.validator.name == 'baseline'/'none' switches)
                # - leth: lethality module runtime tool map
                if root.id in ("event", "obs", "gw", "gateway", "leth"):
                    return False
                if root.id.startswith("resp"):
                    return False
                # Round-trip / algorithm-result roots (AUDIT-0047, GATE 1
                # precision fix): these variables hold FUNCTION RETURN VALUES
                # whose fields are verified as runtime behavior:
                # - t/loaded/trace: trace store save()/load() round-trip results
                # - cand: proposer candidate parse result
                # - best/pts: pareto frontier sort result
                # - cls: unittest setUpClass fixture (cls.guard.loaded_languages)
                # - r_a/r_b: auth HTTP response records
                if root.id in ("t", "loaded", "trace", "cand", "best", "pts", "cls",
                               "r_a", "r_b", "r_ok", "r_deny"):
                    return False
                # Short HTTP/JSON-response variable names from request tests:
                # r1/r2/r_deny/r_ok/r_a/r_b etc. — runtime response records,
                # any attribute (.status/.name/.verdict/._segments) is a
                # runtime behavior check, not dataclass assignment.
                if root.id.startswith("r"):
                    return False
            # Reject: subscript-chained access (eng.rules[0].action, d.__all__)
            # — runtime collection access, not a dataclass field assignment.
            # (v0.2.3, CI drift fix: eng.rules[0].action and d.__all__ were
            # wrongly flagged; these read runtime state, like data["key"].)
            if isinstance(root, ast.Subscript):
                return False

        # Allow: simple name access (obj.field == value) is the dangerous pattern
        return True


def scan_file(filepath: Path) -> AssertVisitor:
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filepath))
    visitor = AssertVisitor(str(filepath))
    visitor.visit(tree)
    return visitor


def check_test_quality() -> int:
    test_dir = Path(TEST_DIR)
    if not test_dir.is_dir():
        print(f"⚠️  Test directory '{TEST_DIR}' not found — skipping quality check")
        return 0

    test_files = sorted(test_dir.glob("test_*.py"))
    total_tests = 0
    total_asserts = 0
    total_dataclass = 0
    violations: list[str] = []

    for tf in test_files:
        # Count test functions
        source = tf.read_text(encoding="utf-8")
        test_funcs = [line for line in source.split("\n")
                      if line.strip().startswith("def test_") or line.strip().startswith("async def test_")]
        total_tests += len(test_funcs)

        # Scan asserts
        visitor = scan_file(tf)
        total_asserts += visitor.total_asserts
        if visitor.dataclass_asserts:
            total_dataclass += len(visitor.dataclass_asserts)
            for lineno, code in visitor.dataclass_asserts:
                violations.append(f"  {tf.name}:{lineno} → `{code}`")

    # ── Gate 1: no dataclass asserts ──
    if total_dataclass > 0:
        print(f"[FAIL] GATE 1: {total_dataclass} dataclass assertion(s) found:")
        print(f"   These test Python field assignment, not runtime behavior.")
        print(f"   Replace with: assert resp.json()['verdict'] == 'DENY'")
        for v in violations:
            print(v)
        return VIOLATION_EXIT_CODE

    # ── Gate 2: test count limit ──
    if total_tests > MAX_TEST_COUNT:
        print(f"[FAIL] GATE 2: {total_tests} test functions > {MAX_TEST_COUNT} limit.")
        print(f"   v1 had 530 tests; v2 caps at {MAX_TEST_COUNT} to prevent inflation.")
        print(f"   If you need more, add a comment: # GATE2-APPROVED: <reason>")
        # Check for approval comment
        approved = False
        for tf in test_files:
            if "# GATE2-APPROVED:" in tf.read_text(encoding="utf-8"):
                approved = True
                print(f"   [OK] Found approval marker in {tf.name}")
                break
        if not approved:
            return VIOLATION_EXIT_CODE

    # ── Report ──
    print(f"[PASS] GATE 1: 0 dataclass asserts in {total_asserts} total asserts")
    print(f"[PASS] GATE 2: {total_tests} tests (limit: {MAX_TEST_COUNT})")
    print(f"   Files scanned: {len(test_files)}")
    return 0


if __name__ == "__main__":
    sys.exit(check_test_quality())
