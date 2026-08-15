"""Verify behavior of test-affecting SQL queries against current ASTGuard (Round 2)."""
from src.ast_guard import ASTGuard

g = ASTGuard()
cases = {
    "T67 subquery (different table)": "UPDATE t SET x=1 WHERE id IN (SELECT id FROM s WHERE y>0);",
    "T67 subquery (same table)": "UPDATE t SET x=1 WHERE id IN (SELECT id FROM t WHERE y>0);",
    "DROP DATABASE": "DROP DATABASE prod;",
    "DROP TRIGGER": "DROP TRIGGER trg ON t;",
    "ALTER TABLE DROP": "ALTER TABLE t DROP COLUMN c;",
    "DELETE subquery": "DELETE FROM t WHERE id IN (SELECT id FROM s WHERE y>0);",
    "IN literal tuple": "UPDATE t SET x=1 WHERE id IN (1,2,3);",
    "bounded update": "UPDATE users SET status='disabled' WHERE id=1;",
    "DROP TABLE": "DROP TABLE users;",
    "TRUNCATE": "TRUNCATE TABLE session_log;",
    "no-where update": "UPDATE users SET status='disabled';",
    "tautology id=id": "UPDATE users SET active=0 WHERE id=id;",
    "benign select": "SELECT name FROM users WHERE id=1;",
}
for name, q in cases.items():
    blk = g.check_request({"query": q})
    kinds = sorted({f.kind for f in blk.findings}) if blk else []
    print(f"{name:32s} -> {kinds if kinds else 'ALLOWED'}")
