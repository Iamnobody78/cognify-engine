# 数据库架构 (database.md)

> 状态: v1.0 (ARCH T0.2 / GAP-2.1) | 2026-08-10

## 1. 选型

| 场景 | 引擎 | 说明 |
|------|------|------|
| 开发/测试（默认） | **SQLite** | 零配置、单文件；`dashboard/backend/db/governance.db` |
| 生产（推荐） | **PostgreSQL 16** | 高并发审计写入；docker-compose 一键拉起（见 deployment.md）|

选型依据:
- 审计日志高频写入（决策/裁决/声明）是主要瓶颈——SQLite 单写者模型在并发下退化明显
- PostgreSQL 成熟生态（PGVector/PGStat 后续可用于治理分析）
- SQLAlchemy ORM 抽象已隔离方言差异，切换成本 = 1 个环境变量

## 2. 切换方式（一键）

```bash
# 方式 B: SQLite（默认，零配置）
python dashboard/backend/main.py

# 方式 A: PostgreSQL（生产）
export GOV_DASH_DB_URL="postgresql+psycopg://bottlesumo:bottlesumo@localhost:5432/bottlesumo"
python dashboard/backend/main.py
```

优先级（database.py `build_engine`）:
1. `db_url` 参数（代码内显式传入，测试用）
2. `GOV_DASH_DB_URL` 环境变量（标准 SQLAlchemy URL）
3. `GOV_DASH_DB` 环境变量（SQLite 文件路径，向后兼容旧变量名）
4. 默认 `dashboard/backend/db/governance.db`

## 3. 依赖

- PostgreSQL 驱动: `psycopg[binary]`（requirements 可选组 `[postgres]`，未默认安装以保持零配置）
- 连接池: `pool_pre_ping=True`（PG 连接复用前探活，避免断连悬挂）

## 4. 迁移策略

- 当前: `Base.metadata.create_all()`（启动时建表，原型阶段足够）
- 生产演进: 引入 **Alembic** 管理 schema 版本（v2.2 候选，见 ROADMAP_PRODUCTION v2.x）

## 5. 备份与恢复

- SQLite: 停写后复制 db 文件 + WAL checkpoint（v2.x 补 backup 脚本）
- PostgreSQL: `pg_dump` / 定期归档（v2.x 补 backup 文档，GAP-5.3）

## 6. 测试矩阵

| 模式 | 命令 | 覆盖 |
|------|------|------|
| SQLite（默认） | `pytest` (CWD=backend) | 28/28 全量 |
| PostgreSQL（CI） | `GOV_DASH_DB_URL=postgresql+psycopg://...` `pytest` | 28/28（含 URL 优先级 5 例）|
| URL 优先级单测 | `pytest tests/test_database_url.py` | 5 例：默认/位置参数/env 优先/参数覆盖/可连性 |
