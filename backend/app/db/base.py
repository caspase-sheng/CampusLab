"""SQLAlchemy 模型的公共基类。契约见 docs/CONTRACT.md §5。

所有模型都继承这里的 Base，共用同一个 MetaData。这里显式指定了命名约定
（naming convention）：Alembic autogenerate 会按这套规则给索引和约束起名，
名字固定下来，迁移脚本在不同机器上生成的结果才一致，不会出现名字漂移导致
后续迁移对不上。
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# SQLAlchemy 官方推荐的一套命名约定，五个键分别管索引 / 唯一约束 / 检查约束 /
# 外键 / 主键。%(table_name)s、%(column_0_name)s 这些占位符由 SQLAlchemy 填。
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """所有模型的基类，metadata 上挂了命名约定。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
