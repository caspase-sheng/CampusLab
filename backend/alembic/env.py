"""Alembic 迁移环境。契约见 docs/CONTRACT.md §5。

连接串不写死在 alembic.ini 里，而是运行时从 settings.DATABASE_URL 取：这样
同一份 env.py 既能跑 SQLite 也能跑 MySQL，切库只改 .env 的 DATABASE_URL，
不用动迁移代码。
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401  导入即注册全部模型，autogenerate 才扫得到表
from app.core.config import settings
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 用 settings 里的连接串覆盖 alembic.ini 中留空的 sqlalchemy.url
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# autogenerate 对比的目标元数据
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只把迁移渲染成 SQL 文本，不连数据库。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连上数据库，逐条执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
