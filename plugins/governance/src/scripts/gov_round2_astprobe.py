# -*- coding: utf-8 -*-
"""GOV Round 2 step 1: in-process ast_guard.check_request on the miss cases."""
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from src.ast_guard import ASTGuard

g = ASTGuard()

CASES = [
    ("A4  DROP DATABASE", "DROP DATABASE appdb;"),
    ("A6  UPDATE no WHERE", "UPDATE users SET active=0;"),
    ("A7  UPDATE WHERE 1=1", "UPDATE users SET active=0 WHERE 1=1;"),
    ("A8  UPDATE WHERE TRUE", "UPDATE users SET active=0 WHERE TRUE;"),
    ("A10 INSERT xfil sqlite_master", "INSERT INTO users SELECT * FROM sqlite_master;"),
    ("C6  DROP TRIGGER", "DROP TRIGGER trg1;"),
    ("C7  DROP FUNCTION", "DROP FUNCTION f1;"),
    ("C8  ALTER DROP COLUMN", "ALTER TABLE users DROP COLUMN email;"),
    ("C9  ALTER DROP CONSTRAINT", "ALTER TABLE users DROP CONSTRAINT uq_email;"),
    ("C10 UPDATE var tautology", "UPDATE users SET role='admin' WHERE id=id;"),
    ("D1  information_schema", "SELECT * FROM information_schema.tables;"),
    ("D2  sqlite_master", "SELECT * FROM sqlite_master;"),
    ("E5  DELETE bounded", "DELETE FROM users WHERE id=5;"),
    ("A1  DELETE no WHERE (ctrl)", "DELETE FROM users;"),
    ("E1  SELECT bounded (ctrl)", "SELECT * FROM users WHERE id=1;"),
]

for label, sql in CASES:
    try:
        r = g.check_request({"sql": {"query": sql}})
        print(f"{label:<28} -> {r}")
    except Exception as e:
        print(f"{label:<28} -> EXC {type(e).__name__}: {e}")
