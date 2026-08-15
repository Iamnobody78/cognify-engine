"""数据库引擎与会话管理（SQLite 默认 / PostgreSQL 可选）。

优先级: GOV_DASH_DB_URL（标准 SQLAlchemy URL）> GOV_DASH_DB（SQLite 文件路径）> 默认 governance.db
"""
import os
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from models import Base  # noqa: E402

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")
# 兼容旧变量：GOV_DASH_DB 为 SQLite 文件路径
DB_PATH = os.getenv("GOV_DASH_DB", os.path.join(DB_DIR, "governance.db"))
# 生产级：标准 SQLAlchemy URL，如 postgresql+psycopg://user:pass@host:5432/bottlesumo
DB_URL = os.getenv("GOV_DASH_DB_URL")

_factory = None  # 模块级默认会话工厂缓存


def resolve_db_url(db_path: Optional[str] = None, db_url: Optional[str] = None) -> str:
    """解析最终数据库 URL（纯函数，不触发驱动加载——单测安全）。

    优先级（显式参数 > 环境变量，修复 CI PG job 中 db_path 被 env 覆盖导致的种子累计）:
      1. db_url 参数
      2. db_path 参数（显式指定 → SQLite 文件，测试隔离）
      3. GOV_DASH_DB_URL 环境变量（实时读取，支持测试 monkeypatch）
      4. GOV_DASH_DB / 默认 governance.db
    """
    if db_url:
        return db_url
    if db_path:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        return f"sqlite:///{db_path}"
    url = os.getenv("GOV_DASH_DB_URL")
    if url:
        return url
    path = os.getenv("GOV_DASH_DB") or DB_PATH
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return f"sqlite:///{path}"


def build_engine(db_path: Optional[str] = None, db_url: Optional[str] = None):
    """构建 SQLAlchemy engine。

    向后兼容: 第一位置参数仍为 db_path（governance_engine.py 以 build_engine(db_path) 调用）。
    """
    url = resolve_db_url(db_path, db_url)
    parsed = make_url(url)
    if parsed.get_backend_name() == "sqlite":
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


def build_session_factory(engine=None):
    engine = engine or build_engine()
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def get_session_factory():
    """模块级默认工厂 (FastAPI 依赖注入用)。"""
    global _factory
    if _factory is None:
        _factory = build_session_factory()
    return _factory
