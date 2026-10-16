"""课程模型。契约见 docs/CONTRACT.md §5.2。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.deadline import Deadline
    from app.models.user import User


class Course(Base):
    """课程表。

    ``day_of_week`` 用整数表示星期，1 = 周一 … 7 = 周日，和契约 §1.4 的约定一致。
    ``start_time`` / ``end_time`` 是 "HH:MM" 字符串。
    """

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    teacher: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)
    week_range: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # created_at 用「本地 naive 时间」，理由同 user.created_at：契约 §5.2 写的是
    # DateTime（无 timezone=True），且全项目统一成本地 naive 才不会和 due_time 打架。
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now()
    )

    user: Mapped["User"] = relationship(back_populates="courses")

    # deadlines.course_id 是 ON DELETE SET NULL：删课程时 DDL 要保留下来，只是把
    # 外键置空。所以这里只配 "save-update, merge"，绝不能配 delete-orphan，否则
    # ORM 会在删课程时把关联的 DDL 也一并删掉，和 DB 语义冲突。
    deadlines: Mapped[list["Deadline"]] = relationship(
        back_populates="course", cascade="save-update, merge"
    )
