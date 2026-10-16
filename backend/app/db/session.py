"""数据库 engine 与 Session 的创建。契约见 docs/CONTRACT.md §5。

开发期用 SQLite，部署切 MySQL。连接串统一从 settings.DATABASE_URL 取，
这里不写死任何方言，两种库共用同一份代码。
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine: Engine = create_engine(settings.DATABASE_URL, future=True)


def enable_sqlite_foreign_keys(target_engine: Engine) -> None:
    """给一个 engine 挂上 SQLite 外键开关，本模块和测试都复用这个函数。

    SQLite 默认**不强制外键**：不打开 ``PRAGMA foreign_keys=ON``，建表时写的
    ``ondelete CASCADE`` / ``ON DELETE SET NULL`` 都不会真正执行——删父行时子行
    原封不动地留着，级联相关的测试会假绿。所以每个新连接建立时都要把这个
    PRAGMA 打开。判断 ``isinstance(dbapi_connection, sqlite3.Connection)`` 是为了
    只在 SQLite 上执行，切到 MySQL 时这个监听器会直接跳过。
    """

    @event.listens_for(target_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:
        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()


enable_sqlite_foreign_keys(engine)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI 依赖：每个请求给一个 Session，请求结束在 finally 里关掉。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
