"""数据库模型的单元测试。契约见 docs/CONTRACT.md §5。

不连真实的 campuslab.db：每个用例用 ``create_engine("sqlite://")`` 建一个内存库，
``Base.metadata.create_all`` 建表，用完销毁。内存库上的 SQLite 默认同样不强制
外键，所以这里复用 ``app.db.session.enable_sqlite_foreign_keys`` 把 PRAGMA 打开——
不然级联删除的用例会假绿。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.models import Course, Deadline, Note, User

TABLE_NAMES = {"users", "courses", "deadlines", "notes"}


@pytest.fixture
def engine() -> Iterator[Engine]:
    """每个用例一个内存库：建表 -> 跑用例 -> dispose。"""
    eng = create_engine("sqlite://", future=True)
    enable_sqlite_foreign_keys(eng)
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """绑在同一个 engine 上的 Session，用完 close。"""
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = factory()
    try:
        yield db
    finally:
        db.close()


def _make_user(**overrides) -> User:
    """造一个最小可用的 User，测试里按需覆盖字段。"""
    data = {
        "username": "alice",
        "email": "alice@example.com",
        "hashed_password": "hashed",
    }
    data.update(overrides)
    return User(**data)


def _make_course(user_id: int, **overrides) -> Course:
    """造一门最小可用的 Course。"""
    data = {
        "user_id": user_id,
        "name": "数据结构",
        "day_of_week": 1,
        "start_time": "08:00",
        "end_time": "09:40",
    }
    data.update(overrides)
    return Course(**data)


def test_tables_created(engine: Engine) -> None:
    """四张表都建出来了，表名与契约一致。"""
    names = set(inspect(engine).get_table_names())
    assert names == TABLE_NAMES


def test_insert_and_read_back(session: Session) -> None:
    """插入 user + course + deadline + note，各字段能正确读写。"""
    user = _make_user()
    session.add(user)
    session.flush()

    course = _make_course(
        user.id,
        teacher="张老师",
        location="教三-201",
        week_range="1-16",
    )
    session.add(course)
    session.flush()

    # deadline 不传 status，验证默认值 "pending"
    deadline = Deadline(
        user_id=user.id,
        title="数据结构作业3",
        course_id=course.id,
        due_time=datetime(2026, 10, 20, 23, 59),
    )
    note = Note(user_id=user.id, title="KV 学习笔记", content_md="# WAL\n...", tags="KV,存储")
    session.add_all([deadline, note])
    session.commit()

    assert user.id is not None
    fetched_course = session.get(Course, course.id)
    assert fetched_course is not None
    assert fetched_course.name == "数据结构"
    assert fetched_course.teacher == "张老师"
    assert fetched_course.location == "教三-201"
    assert fetched_course.week_range == "1-16"
    assert fetched_course.day_of_week == 1
    assert fetched_course.start_time == "08:00"
    assert fetched_course.end_time == "09:40"
    assert fetched_course.created_at is not None

    fetched_deadline = session.get(Deadline, deadline.id)
    assert fetched_deadline is not None
    assert fetched_deadline.title == "数据结构作业3"
    assert fetched_deadline.status == "pending"
    # 两边都是 naive，直接比较
    assert fetched_deadline.due_time == datetime(2026, 10, 20, 23, 59)
    assert fetched_deadline.created_at is not None

    fetched_note = session.get(Note, note.id)
    assert fetched_note is not None
    assert fetched_note.title == "KV 学习笔记"
    assert fetched_note.content_md == "# WAL\n..."
    assert fetched_note.tags == "KV,存储"
    assert fetched_note.created_at is not None


def test_note_updated_at_refreshes_on_update(session: Session) -> None:
    """note.updated_at 在更新记录后变大。"""
    user = _make_user()
    session.add(user)
    session.flush()

    note = Note(user_id=user.id, title="标题", content_md="正文")
    session.add(note)
    session.commit()

    before = note.updated_at
    note.title = "改过的标题"
    session.commit()
    session.refresh(note)

    assert note.title == "改过的标题"
    assert note.updated_at > before


def test_delete_user_cascades_children(session: Session) -> None:
    """删 user -> 该用户的 courses / deadlines / notes 全部级联删除。

    这是验证 PRAGMA foreign_keys=ON 真的生效的关键用例：SQLite 不打开外键开关时，
    下面三个子行会全部残留。
    """
    user = _make_user()
    session.add(user)
    session.flush()

    course = _make_course(user.id)
    session.add(course)
    session.flush()

    deadline = Deadline(
        user_id=user.id,
        title="DDL",
        course_id=course.id,
        due_time=datetime(2026, 10, 20, 23, 59),
    )
    note = Note(user_id=user.id, title="笔记", content_md="正文")
    session.add_all([deadline, note])
    session.commit()

    user_id, course_id, deadline_id, note_id = user.id, course.id, deadline.id, note.id

    session.delete(user)
    session.commit()

    assert session.get(User, user_id) is None
    assert session.get(Course, course_id) is None
    assert session.get(Deadline, deadline_id) is None
    assert session.get(Note, note_id) is None


def test_delete_course_sets_deadline_course_id_null(session: Session) -> None:
    """删 course -> 关联 deadline 还在，但 course_id 变成 NULL（SET NULL）。"""
    user = _make_user()
    session.add(user)
    session.flush()

    course = _make_course(user.id)
    session.add(course)
    session.flush()

    deadline = Deadline(
        user_id=user.id,
        title="DDL",
        course_id=course.id,
        due_time=datetime(2026, 10, 20, 23, 59),
    )
    session.add(deadline)
    session.commit()
    deadline_id = deadline.id

    session.delete(course)
    session.commit()
    session.expire_all()

    survived = session.get(Deadline, deadline_id)
    assert survived is not None
    assert survived.course_id is None


def test_duplicate_username_raises(session: Session) -> None:
    """username 重复要抛 IntegrityError。"""
    session.add(_make_user(username="alice", email="a@example.com"))
    session.commit()

    session.add(_make_user(username="alice", email="b@example.com"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_duplicate_email_raises(session: Session) -> None:
    """email 重复要抛 IntegrityError。"""
    session.add(_make_user(username="alice", email="a@example.com"))
    session.commit()

    session.add(_make_user(username="bob", email="a@example.com"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_note_tags_optional_and_roundtrip(session: Session) -> None:
    """note.tags 允许 None；传 "算法,KV" 能原样读回。"""
    user = _make_user()
    session.add(user)
    session.flush()

    no_tags = Note(user_id=user.id, title="无标签", content_md="正文")
    with_tags = Note(user_id=user.id, title="有标签", content_md="正文", tags="算法,KV")
    session.add_all([no_tags, with_tags])
    session.commit()

    fetched_none = session.get(Note, no_tags.id)
    assert fetched_none is not None
    assert fetched_none.tags is None

    fetched_tags = session.get(Note, with_tags.id)
    assert fetched_tags is not None
    assert fetched_tags.tags == "算法,KV"


def test_day_of_week_stores_integers(session: Session) -> None:
    """day_of_week 用整数，1（周一）和 7（周日）都能正常读写。"""
    user = _make_user()
    session.add(user)
    session.flush()

    monday = _make_course(user.id, name="周一的课", day_of_week=1, start_time="08:00", end_time="09:40")
    sunday = _make_course(user.id, name="周日的课", day_of_week=7, start_time="14:00", end_time="15:40")
    session.add_all([monday, sunday])
    session.commit()

    assert session.get(Course, monday.id).day_of_week == 1
    assert session.get(Course, sunday.id).day_of_week == 7
