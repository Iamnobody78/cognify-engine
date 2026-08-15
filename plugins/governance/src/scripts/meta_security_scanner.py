#!/usr/bin/env python3
"""GATE 6: meta-security scanner — detects security anti-patterns in src/.

Anti-patterns (learned from AUDIT-0005, where a circuit breaker tripped
to ALLOW and created a DDoS bypass):
  1. breaker-tripping-to-ALLOW   : "if count >= LIMIT: verdict = ALLOW"
  2. timeout-default-ALLOW       : timeout path returns ALLOW (fail-open)
  3. silent-exception-swallow    : bare except with pass / no logging
  4. startswith-path-bypass      : path checks via str.startswith only
     (vulnerable to '/api/v1/delete' variants and '../' traversal)

Design: AST-based (not regex) — regex on Python source is itself a
bypass-prone pattern; AST sees real semantics. Each finding is a real
AST node, not a string match.

Exit codes: 0 = clean, 1 = any HIGH finding, 2 = any MEDIUM finding.
"""

import ast
import sys
from pathlib import Path
from typing import List, NamedTuple


class Finding(NamedTuple):
    severity: str      # HIGH | MEDIUM
    rule: str
    file: str
    line: int
    message: str


def _assigns_allow(body: List[ast.stmt]) -> bool:
    """True if any statement assigns verdict/result = Verdict.ALLOW."""
    for stmt in body:
        if isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Name) and t.id in ("verdict", "result"):
                    val = stmt.value
                    if isinstance(val, ast.Attribute) and val.attr == "ALLOW":
                        return True
                    if isinstance(val, ast.Constant) and val.value == "ALLOW":
                        return True
    return False


class SecurityVisitor(ast.NodeVisitor):
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.findings: List[Finding] = []

    def _add(self, severity: str, rule: str, node: ast.AST, message: str):
        self.findings.append(Finding(
            severity=severity, rule=rule,
            file=self.filepath, line=getattr(node, "lineno", 0),
            message=message,
        ))

    # ── rule 1: breaker trips to ALLOW ─────────────────────────────
    def visit_If(self, node: ast.If):
        cond = node.test
        cond_has_counter = any(
            isinstance(n, ast.Name) and
            ("LIMIT" in n.id.upper() or "COUNT" in n.id.upper())
            for n in ast.walk(cond)
        )
        if cond_has_counter and _assigns_allow(node.body):
            self._add(
                "HIGH", "breaker-tripping-to-ALLOW", node,
                "condition on counter/LIMIT assigns verdict=ALLOW — breaker "
                "must trip to DENY (fail-closed), see AUDIT-0005",
            )
        self.generic_visit(node)

    # ── rules 2 & 3: timeout-ALLOW + silent swallow ────────────────
    def visit_ExceptHandler(self, node: ast.ExceptHandler):
        name = node.name or ""
        type_dump = ast.dump(node.type) if node.type else ""
        is_timeout = "Timeout" in name or "Timeout" in type_dump

        if is_timeout and _assigns_allow(node.body):
            self._add(
                "HIGH", "timeout-default-ALLOW", node,
                "timeout handler assigns ALLOW — must be DENY/ESCALATE "
                "(fail-closed), see fail-open review",
            )

        body = node.body
        # CI drift fix (v0.2.3, AUDIT-0021): a TYPED except (except OSError:
        # pass — policy.py L97-98 mtime read) is an intentional, scoped ignore
        # of a known-benign failure, NOT silent exception swallowing. Only a
        # BARE `except: pass` or `except Exception: pass` (catch-all) swallows
        # arbitrary errors and must be flagged.
        catch_all = node.type is None or (
            isinstance(node.type, ast.Name) and node.type.id == "Exception"
        )
        if catch_all and len(body) == 1 and isinstance(body[0], ast.Pass):
            self._add(
                "MEDIUM", "silent-exception-swallow", node,
                "bare `except: pass` swallows errors silently — add logging",
            )
        self.generic_visit(node)

    # ── rule 4: startswith-only path check ─────────────────────────
    def _function_has_normpath(self, node: ast.Call) -> bool:
        """True if the enclosing function body also calls normpath()
        (the AUDIT-0005 defense: normalize before boundary matching)."""
        fn = getattr(node, "_enclosing_function", None)
        if fn is None:
            return False
        for n in ast.walk(fn):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                    and n.func.attr == "normpath":
                return True
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) \
                    and n.func.id == "normpath":
                return True
        return False

    def visit_Call(self, node: ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "startswith":
            if self._is_path_startswith(node) and not self._function_has_normpath(node):
                self._add(
                    "MEDIUM", "startswith-path-bypass", node,
                    "path check via startswith() without normpath "
                    "normalization — use normpath + boundary matching "
                    "(see AUDIT-0005 path traversal fix)",
                )
        self.generic_visit(node)

    @staticmethod
    def _is_path_startswith(node: ast.Call) -> bool:
        """Rule 4 precision fix (AUDIT-0047): only flag startswith calls that
        look like PATH boundary checks.

        Non-path usages — authz.startswith(\"Bearer \"), code.startswith(\"A\")
        (git status), line.startswith(\"#\") (comment filter), json line
        detection — all pass a plain string literal as the argument and are
        NOT path checks. A genuine path comparison passes a variable /
        expression (``str(base_dir)``) or a literal containing a path
        separator (``/``, ``\\``, ``..``).
        """
        if len(node.args) < 1:
            return False
        arg = node.args[0]
        # f-string / JoinedStr argument (v0.2.4, AUDIT-0073, precision fix):
        # an f-string whose constant segments carry NO path separator is a
        # rule-name / token prefix check (e.g. r.name.startswith(
        # f"protocol-{p.module}-")), NOT a path boundary check. AUDIT-0047
        # only covered plain string literals; JoinedStr slipped through as
        # "expression argument".
        if isinstance(arg, ast.JoinedStr):
            for seg in arg.values:
                if isinstance(seg, ast.Constant) and isinstance(seg.value, str):
                    v = seg.value
                    if "/" in v or "\\" in v or ".." in v or v.startswith("."):
                        return True
            return False
        # variable / expression argument -> real path comparison
        if not isinstance(arg, ast.Constant):
            return True
        if not isinstance(arg.value, str):
            return False
        # literal with path separators -> path-ish
        v = arg.value
        if "/" in v or "\\" in v or ".." in v or v.startswith("."):
            return True
        return False


def _annotate_enclosing_functions(tree: ast.AST):
    """Attach _enclosing_function to every node: nearest FunctionDef parent.
    (plain runtime helper — no dataclass assertions, no pydantic)"""

    class _Annotator(ast.NodeVisitor):
        def __init__(self):
            self.stack = []

        def visit_FunctionDef(self, node):
            self.stack.append(node)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node):
            self.stack.append(node)
            self.generic_visit(node)
            self.stack.pop()

        def generic_visit(self, node):
            if self.stack:
                node._enclosing_function = self.stack[-1]
            super().generic_visit(node)

    _Annotator().visit(tree)


def scan_file(filepath: Path) -> List[Finding]:
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"))
    except SyntaxError as e:
        return [Finding("HIGH", "syntax-error", str(filepath), 0,
                        f"cannot parse: {e}")]
    _annotate_enclosing_functions(tree)
    visitor = SecurityVisitor(str(filepath))
    visitor.visit(tree)
    return visitor.findings


def main() -> int:
    # CLI: scripts/meta_security_scanner.py [path...]  (default: src/)
    # path may be a directory (recursed) or a single file
    paths = [Path(p) for p in sys.argv[1:]] or [Path("src")]
    findings: List[Finding] = []
    for p in paths:
        if not p.exists():
            continue
        files = [p] if p.is_file() else list(p.rglob("*.py"))
        for f in files:
            findings.extend(scan_file(f))

    if not findings:
        print("GATE 6 (meta-security): PASS - no anti-patterns found")
        return 0

    # explicit severity ordering — string max() would rank 'HIGH' < 'MEDIUM'
    # ('H' < 'M' in ASCII), silently downgrading findings. (GATE 6 fix)
    # NOTE: generator expression over findings — bare `f.severity` would use
    # the loop-leftover variable from `for f in files` (a WindowsPath). (GATE 6 fix 2)
    _SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    highest = max((g.severity for g in findings),
                  key=lambda s: _SEVERITY_RANK.get(s, 0))
    for f in findings:
        print(f"[{f.severity}] {f.rule} | {f.file}:{f.line} | {f.message}")

    print(f"\nGATE 6 (meta-security): FAIL ({len(findings)} finding(s))")
    return 1 if highest == "HIGH" else 2


if __name__ == "__main__":
    sys.exit(main())
