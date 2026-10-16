"""笔记模型。契约见 docs/CONTRACT.md §5.4。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class Note(Base):
    """笔记表。

    ``content_md`` 存 Markdown 源文，``tags`` 是逗号分隔字符串（如 "算法,KV"），
    可空。``updated_at`` 在每次更新记录时自动刷新。
    """

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # created_at / updated_at 都用「本地 naive 时间」，理由同 user.created_at：
    # 契约 §5.4 写的是 DateTime（无 timezone=True），全项目统一成本地 naive。
    # onupdate 也一并改成 datetime.now()，否则更新时会写回 UTC 钟面值。
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(),
        onupdate=lambda: datetime.now(),
    )

    user: Mapped["User"] = relationship(back_populates="notes")
