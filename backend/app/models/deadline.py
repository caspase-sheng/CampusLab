"""DDL（截止事项）模型。契约见 docs/CONTRACT.md §5.3。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.user import User


class Deadline(Base):
    """截止事项表。

    ``status`` 取值只有 pending / done 两种，默认 pending。
    ``course_id`` 可空，删掉课程时置 NULL（ON DELETE SET NULL），DDL 本身保留。
    """

    __tablename__ = "deadlines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    # due_time 本来就是用户在 datetime-local 里按本地时间选的（如 23:59），契约
    # §5.3 写的是 DateTime（无 timezone=True）。去掉 timezone=True 后，存进去和读
    # 回来都是同一个本地钟面值，前后端语义一致。
    due_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # created_at 同样用「本地 naive 时间」，理由同 user.created_at。
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now()
    )

    user: Mapped["User"] = relationship(back_populates="deadlines")
    course: Mapped["Course | None"] = relationship(back_populates="deadlines")
