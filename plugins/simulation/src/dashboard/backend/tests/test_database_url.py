"""GAP-2.1 生产级数据库支持测试：URL 优先级与向后兼容性。

设计原则: 单测只验 URL 解析逻辑（make_url 不加载驱动，psycopg 无需安装）；
真实 PostgreSQL 连通性由 CI postgres service / docker-compose 验证。
"""
import os

from sqlalchemy.engine import make_url

from database import DB_PATH, build_engine, resolve_db_url


def test_default_sqlite_engine(monkeypatch):
    """默认仍为 SQLite（向后兼容）。CI PG job 设置了 GOV_DASH_DB_URL，需 delenv 模拟无配置场景。"""
    monkeypatch.delenv("GOV_DASH_DB_URL", raising=False)
    monkeypatch.delenv("GOV_DASH_DB", raising=False)
    engine = build_engine()
    assert engine.url.get_backend_name() == "sqlite"


def test_positional_db_path_kept(monkeypatch):
    """第一位置参数必须仍为 db_path（governance_engine.py 依赖）。"""
    monkeypatch.delenv("GOV_DASH_DB_URL", raising=False)
    engine = build_engine(os.path.join(os.path.dirname(DB_PATH), "test_engine.db"))
    assert engine.url.get_backend_name() == "sqlite"
    assert "test_engine.db" in engine.url.database


def test_env_db_url_takes_precedence(monkeypatch):
    """GOV_DASH_DB_URL 环境变量优先于 SQLite（实时读取，monkeypatch 生效）。"""
    monkeypatch.setenv(
        "GOV_DASH_DB_URL",
        "postgresql+psycopg://user:pass@localhost:5432/bottlesumo_test",
    )
    assert resolve_db_url() == "postgresql+psycopg://user:pass@localhost:5432/bottlesumo_test"


def test_db_url_arg_overrides_env(monkeypatch):
    """显式 db_url 参数优先于环境变量。"""
    monkeypatch.setenv(
        "GOV_DASH_DB_URL",
        "postgresql+psycopg://user:pass@localhost:5432/env_db",
    )
    assert resolve_db_url(db_url="postgresql+psycopg://u:p@localhost:5432/arg_db") == (
        "postgresql+psycopg://u:p@localhost:5432/arg_db"
    )


def test_pg_url_semantics_via_make_url():
    """PG URL 语义用 make_url 纯解析验证（不加载 psycopg 驱动）。"""
    parsed = make_url("postgresql+psycopg://u:p@localhost:5432/parse_db")
    assert parsed.get_backend_name() == "postgresql"
    assert parsed.database == "parse_db"
    assert parsed.username == "u"
