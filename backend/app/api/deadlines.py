"""deadlines 接口。契约见 docs/CONTRACT.md §4.3。

五个接口：列表 / 创建 / 取单条 / 部分更新 / 删除，全部依赖 ``get_current_user``，
响应套 ``ApiResponse`` 信封。按 id 取单条的操作都带 ``user_id`` 条件、查不到 404
（理由见 ``_get_owned_or_404``）。另外创建 / 更新时若传了 ``course_id``，要校验该
课程存在且属于当前用户，校验不过返回 422。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.course import Course
from app.models.deadline import Deadline
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.deadline import DeadlineCreate, DeadlineOut, DeadlineUpdate

router = APIRouter(prefix="/deadlines", tags=["deadlines"])


def _get_owned_or_404(db: Session, deadline_id: int, user_id: int) -> Deadline:
    """按 ``(id, user_id)`` 查 DDL，查不到就 404。

    查询条件同时带 ``id`` 和 ``user_id``，而不是先查出再比对属主后返回 403：
    "资源不存在" 与 "资源属于别人" 必须合并成同一个 404，否则会泄露别人数据的
    存在性。两者消息一致，调用方区分不了。
    """
    deadline = db.scalar(
        select(Deadline).where(Deadline.id == deadline_id, Deadline.user_id == user_id)
    )
    if deadline is None:
        raise HTTPException(status_code=404, detail="DDL 不存在")
    return deadline


def _ensure_course_owned(db: Session, course_id: int, user_id: int) -> None:
    """校验 ``course_id`` 指向的课程存在且属于当前用户。

    这里返回 422 而不是 404：出问题的不是 URI 里的资源，而是**请求体**里引用的
    课程无效（不存在或不属于自己），属于参数校验失败的范畴，契约 §1.2 里 422 就是
    "参数校验失败"。用 404 会让调用方以为要访问的 DDL 路径有问题，语义不对。

    顺带一提，这里同样不区分"课程不存在"和"课程是别人的"——都返回同一句 422，
    免得通过 422 / 404 的差别探测别人课程是否存在。
    """
    course = db.scalar(
        select(Course).where(Course.id == course_id, Course.user_id == user_id)
    )
    if course is None:
        raise HTTPException(status_code=422, detail="课程不存在或不属于当前用户")


@router.get("", response_model=ApiResponse[list[DeadlineOut]], summary="DDL 列表")
def list_deadlines(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[DeadlineOut]]:
    """返回当前用户的全部 DDL，只查 ``user_id == current_user.id`` 的行。"""
    deadlines = db.scalars(
        select(Deadline).where(Deadline.user_id == current_user.id)
    ).all()
    return ApiResponse[list[DeadlineOut]](
        code=0,
        message="ok",
        data=[DeadlineOut.model_validate(item) for item in deadlines],
    )


@router.post("", response_model=ApiResponse[DeadlineOut], summary="创建 DDL")
def create_deadline(
    payload: DeadlineCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DeadlineOut]:
    """新建 DDL。

    ``user_id`` 强制取 ``current_user.id``，不从请求体取。若请求体带了
    ``course_id``，先确认那门课程存在且属于当前用户，否则返回 422
    （见 ``_ensure_course_owned``）。
    """
    if payload.course_id is not None:
        _ensure_course_owned(db, payload.course_id, current_user.id)

    deadline = Deadline(user_id=current_user.id, **payload.model_dump())
    db.add(deadline)
    db.commit()
    db.refresh(deadline)
    return ApiResponse[DeadlineOut](
        code=0, message="ok", data=DeadlineOut.model_validate(deadline)
    )


@router.get(
    "/{deadline_id}", response_model=ApiResponse[DeadlineOut], summary="DDL 详情"
)
def get_deadline(
    deadline_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DeadlineOut]:
    """取单条 DDL。

    按 ``(id, user_id)`` 查，查不到返回 404。"资源不存在" 和 "资源不属于当前用户"
    是同一个 404、同一句消息，不向调用方区分，避免越权信息泄露。
    """
    deadline = _get_owned_or_404(db, deadline_id, current_user.id)
    return ApiResponse[DeadlineOut](
        code=0, message="ok", data=DeadlineOut.model_validate(deadline)
    )


@router.put(
    "/{deadline_id}", response_model=ApiResponse[DeadlineOut], summary="更新 DDL"
)
def update_deadline(
    deadline_id: int,
    payload: DeadlineUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[DeadlineOut]:
    """部分更新 DDL，只更新调用方传入的字段。

    先按 ``(id, user_id)`` 查、查不到 404（理由同上）。字段用
    ``model_dump(exclude_unset=True)`` 取，这样调用方能把 ``course_id`` 显式改成
    ``null`` 来解除关联；若传了非空的 ``course_id``，先校验课程归属，不通过返回 422。

    逐个 ``setattr`` 到 ORM 对象，commit 时由 SQLAlchemy 生成 UPDATE。
    """
    deadline = _get_owned_or_404(db, deadline_id, current_user.id)

    changes = payload.model_dump(exclude_unset=True)
    # course_id 显式传 null 是"解除关联"，只在传了非空值时才需要校验课程归属
    if changes.get("course_id") is not None:
        _ensure_course_owned(db, changes["course_id"], current_user.id)

    for field, value in changes.items():
        setattr(deadline, field, value)
    db.commit()
    db.refresh(deadline)
    return ApiResponse[DeadlineOut](
        code=0, message="ok", data=DeadlineOut.model_validate(deadline)
    )


@router.delete(
    "/{deadline_id}", response_model=ApiResponse[None], summary="删除 DDL"
)
def delete_deadline(
    deadline_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    """删除 DDL。

    先按 ``(id, user_id)`` 查、查不到 404，避免越权删除别人的 DDL。删除成功返回
    200、``data`` 为 ``null``（契约 §1.2 没有 204）。
    """
    deadline = _get_owned_or_404(db, deadline_id, current_user.id)
    db.delete(deadline)
    db.commit()
    return ApiResponse[None](code=0, message="ok", data=None)
