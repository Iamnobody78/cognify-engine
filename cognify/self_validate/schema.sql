-- SELF-VALIDATE-ITERATE 自使用验证数据库 Schema
-- 位置: ~/.aionui-tri-sync/self_validate/self_validate.db (运行时)
-- 说明: runs = 每次验证运行; scenarios = 每场景结果 (1 次运行 5 行)

CREATE TABLE IF NOT EXISTS self_validation_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT UNIQUE NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    version TEXT NOT NULL,
    overall_score REAL NOT NULL,
    passed_scenarios INTEGER,
    total_scenarios INTEGER,
    details JSON
);

CREATE TABLE IF NOT EXISTS self_validation_scenarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    scenario TEXT NOT NULL,
    success BOOLEAN NOT NULL,
    score REAL NOT NULL,
    details JSON,
    FOREIGN KEY (run_id) REFERENCES self_validation_runs(run_id)
);

-- 查询自使用验证趋势 (近 7 天)
SELECT
    date(timestamp) as day,
    AVG(overall_score) as avg_score,
    COUNT(*) as runs
FROM self_validation_runs
WHERE timestamp > datetime('now', '-7 days')
GROUP BY date(timestamp)
ORDER BY day;
