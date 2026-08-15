# -*- coding: utf-8 -*-
"""Verify parse + guard behavior for existing test cases affected by R2."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from src.ast_guard import ASTGuard, get_parser

g = ASTGuard()
parser = get_parser("sql")

def has_error(sql):
    tree = parser.parse(bytes(sql, "utf-8"))
    out = []
    def walk(n):
        if n.type == "ERROR":
            out.append(n.text.decode("utf-8", "replace"))
            return
        for c in n.children:
            walk(c)
    walk(tree.root_node)
    return out

CASES = [
    ("T67 subquery different-table bounded", "UPDATE t SET x=1 WHERE id IN (SELECT id FROM s WHERE y>0);"),
    ("C11 subquery same-table tautology", "UPDATE users SET role='admin' WHERE id IN (SELECT id FROM users);"),
    ("IN literal tuple", "UPDATE t SET x=1 WHERE id IN (1,2,3);"),
    ("JOIN benign", "SELECT * FROM orders JOIN users ON orders.uid = users.id;"),
    ("C12 RENAME", "RENAME TABLE users TO users_old;"),
    ("E6 SHOW", "SHOW TABLES;"),
    ("E7 DESCRIBE", "DESCRIBE users;"),
    ("E8 EXPLAIN", "EXPLAIN SELECT * FROM users;"),
]
for label, sql in CASES:
    errs = has_error(sql)
    blocked = g.check_request({"query": sql})
    kinds = sorted({f.kind for f in blocked.findings}) if blocked else []
    print(f"{label:<36} errs={errs if errs else 'NONE'} blocked={blocked is not None} kinds={kinds}")
