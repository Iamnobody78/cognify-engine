# -*- coding: utf-8 -*-
"""GOV Round 2 step 2: dump tree-sitter SQL parse trees for the 7 FN cases."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from src.ast_guard import get_parser

parser = get_parser("sql")

def dump(sql):
    tree = parser.parse(bytes(sql, "utf-8"))
    out = []
    def walk(n, depth):
        if n.type == "ERROR":
            out.append("  " * depth + f"<ERROR> text={n.text[:40]!r}")
            return
        out.append("  " * depth + f"{n.type} '{n.text[:50]}'")
        for c in n.children:
            walk(c, depth + 1)
    walk(tree.root_node, 0)
    return "\n".join(out)

for label, sql in [
    ("A4 DROP DATABASE", "DROP DATABASE appdb;"),
    ("C6 DROP TRIGGER", "DROP TRIGGER trg1;"),
    ("C7 DROP FUNCTION", "DROP FUNCTION f1;"),
    ("C8 ALTER DROP COLUMN", "ALTER TABLE users DROP COLUMN email;"),
    ("C9 ALTER DROP CONSTRAINT", "ALTER TABLE users DROP CONSTRAINT uq_email;"),
    ("C10 UPDATE id=id", "UPDATE users SET role='admin' WHERE id=id;"),
    ("C11 UPDATE IN-subquery", "UPDATE users SET role='admin' WHERE id IN (SELECT id FROM users);"),
    ("E4 UPDATE bounded (ctrl)", "UPDATE users SET active=0 WHERE id=5;"),
]:
    print(f"===== {label}: {sql}")
    print(dump(sql))
    print()
