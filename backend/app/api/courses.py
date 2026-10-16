"""courses 接口。契约见 docs/CONTRACT.md §4.2。

五个接口：列表 / 创建 / 取单条 / 部分更新 / 删除。全部依赖 ``get_current_user``，
响应统一套 ``ApiResponse`` 信封（契约 §1.2）。所有按 id 取单条的操作都带
``user_id`` 条件，查不到一律 404，理由见 ``_get_owned_or_404``。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.course import Course
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.course import CourseCreate, CourseOut, CourseUpdate

router = APIRouter(prefix="/courses", tags=["courses"])


def _get_owned_or_404(db: Session, course_id: int, user_id: int) -> Course:
    """按 ``(id, user_id)`` 查课程，查不到就 404。

    查询条件里把 ``user_id`` 和 ``id`` 放在一起，而不是「先按 id 查出来、再比对
    user_id 是否相等、不等返回 403」。后者等于告诉调用方「这个 id 是存在的，只是
    不属于你」，属于越权信息泄露——对方可以借此探测别人数据的存在性。所以这两种
    情况在这里合并成同一个 404，消息也完全一致，调用方无法区分。
    """
    course = db.scalar(
        select(Course).where(Course.id == course_id, Course.user_id == user_id)
    )
    if course is None:
        raise HTTPException(status_code=404, detail="课程不存在")
    return course


@router.get("", response_model=ApiResponse[list[CourseOut]], summary="课程列表")
def list_courses(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[CourseOut]]:
    """返回当前用户的全部课程。

    查询始终带 ``user_id == current_user.id``，只可能拿到自己的行，别人的课程
    不会出现在列表里。
    """
    courses = db.scalars(
        select(Course).where(Course.user_id == current_user.id)
    ).all()
    return ApiResponse[list[CourseOut]](
        code=0,
        message="ok",
        data=[CourseOut.model_validate(course) for course in courses],
    )


@router.post("", response_model=ApiResponse[CourseOut], summary="创建课程")
def create_course(
    payload: CourseCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[CourseOut]:
    """新建课程。

    ``user_id`` 强制取 ``current_user.id``（从 JWT 解析），请求体里根本没有这个
    字段，也就无从伪造。创建成功后 ``db.refresh`` 把数据库生成的 id / created_at
    回填到对象上，再序列化返回。

    契约 §1.2 的状态码表里没有 201，创建成功也返回 200。
    """
    course = Course(user_id=current_user.id, **payload.model_dump())
    db.add(course)
    db.commit()
    db.refresh(course)
    return ApiResponse[CourseOut](
        code=0, message="ok", data=CourseOut.model_validate(course)
    )


@router.get("/{course_id}", response_model=ApiResponse[CourseOut], summary="课程详情")
def get_course(
    course_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[CourseOut]:
    """取单条课程。

    查询条件同时带 ``id`` 和 ``user_id``，查不到返回 404。"资源不存在" 和 "资源
    不属于当前用户" 是同一个 404、同一句消息，不向调用方区分——分开提示会泄露
    其他用户数据的存在性。
    """
    course = _get_owned_or_404(db, course_id, current_user.id)
    return ApiResponse[CourseOut](
        code=0, message="ok", data=CourseOut.model_validate(course)
    )


@router.put("/{course_id}", response_model=ApiResponse[CourseOut], summary="更新课程")
def update_course(
    course_id: int,
    payload: CourseUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[CourseOut]:
    """部分更新课程，只更新调用方传入的字段。

    先按 ``(id, user_id)`` 查、查不到 404（理由同上：不区分"不存在"与"别人的"）。

    拿字段用 ``payload.model_dump(exclude_unset=True)`` 而不是 ``exclude_none``：
    契约里 PUT 的语义是"字段可选，只更新传入字段"，调用方需要能把某个可空字段
    显式改成 ``null``（例如清空 teacher），``exclude_none`` 会把这种显式的 null 一起
    吞掉，等于没法清空字段。

    拿到字段后逐个 ``setattr`` 到 ORM 对象上，SQLAlchemy 会自己标记脏字段并在
    commit 时生成 UPDATE，不手写 SQL。
    """
    course = _get_owned_or_404(db, course_id, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(course, field, value)
    db.commit()
    db.refresh(course)
    return ApiResponse[CourseOut](
        code=0, message="ok", data=CourseOut.model_validate(course)
    )


@router.delete("/{course_id}", response_model=ApiResponse[None], summary="删除课程")
def delete_course(
    course_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    """删除课程。

    同样先按 ``(id, user_id)`` 查、查不到 404，避免越权删除别人的课程。

    课程下挂的 DDL 不会被一起删掉：``deadlines.course_id`` 在模型里配的是
    ``ondelete="SET NULL"``，删课程时数据库层只会把关联 DDL 的外键置为 NULL，
    DDL 记录本身保留。这个语义由 DB 层（和 ORM 的默认 nullify 行为）保证，
    路由层不重复处理。

    契约 §1.2 没有 204，删除成功也返回 200，``data`` 为 ``null``。
    """
    course = _get_owned_or_404(db, course_id, current_user.id)
    db.delete(course)
    db.commit()
    return ApiResponse[None](code=0, message="ok", data=None)
