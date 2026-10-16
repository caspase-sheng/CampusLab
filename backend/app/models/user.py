"""用户模型。契约见 docs/CONTRACT.md §5.1。"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.course import Course
    from app.models.deadline import Deadline
    from app.models.note import Note


class User(Base):
    """用户表。关联 courses / deadlines / notes 三张表，均为一对多。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # created_at 用「本地 naive 时间」，和 deadlines.due_time 保持一致，也与契约
    # §5.1 写的 DateTime（没有 timezone=True）对齐。原来声明成 DateTime(timezone=True)
    # 且默认 datetime.now(timezone.utc)：SQLite 存时间不保留 tz 偏移，只留 UTC 的
    # 钟面值，读回来是 naive，前端 new Date("...") 会按本地时区解析，于是比实际晚 8 小时。
    # 不保持 UTC 的原因：本项目有 due_time 是用户在 datetime-local 里按本地时间选的，
    # 全项目统一成本地 naive 才不会出现「一部分字段 UTC、一部分本地」的混乱。
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now()
    )

    # passive_deletes=True：删除用户时把级联交给数据库的 ON DELETE CASCADE 执行，
    # 而不是让 ORM 先把子行 SELECT 出来再逐条 DELETE。配合 DB 层的 ondelete 使用。
    courses: Mapped[list["Course"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    deadlines: Mapped[list["Deadline"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    notes: Mapped[list["Note"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
