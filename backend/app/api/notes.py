"""notes 接口。契约见 docs/CONTRACT.md §4.4。

五个接口：列表 / 创建 / 取单条 / 部分更新 / 删除，全部依赖 ``get_current_user``，
响应套 ``ApiResponse`` 信封。按 id 取单条的操作都带 ``user_id`` 条件、查不到 404
（理由见 ``_get_owned_or_404``）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.note import Note
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.note import NoteCreate, NoteOut, NoteUpdate

router = APIRouter(prefix="/notes", tags=["notes"])


def _get_owned_or_404(db: Session, note_id: int, user_id: int) -> Note:
    """按 ``(id, user_id)`` 查笔记，查不到就 404。

    查询条件里带 ``user_id``，而不是先查出再判断属主后返回 403。"资源不存在" 和
    "资源属于别人" 合并成同一个 404、同一句消息，调用方无法据此区分，避免越权
    信息泄露。
    """
    note = db.scalar(
        select(Note).where(Note.id == note_id, Note.user_id == user_id)
    )
    if note is None:
        raise HTTPException(status_code=404, detail="笔记不存在")
    return note


@router.get("", response_model=ApiResponse[list[NoteOut]], summary="笔记列表")
def list_notes(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[list[NoteOut]]:
    """返回当前用户的全部笔记，只查 ``user_id == current_user.id`` 的行。"""
    notes = db.scalars(
        select(Note).where(Note.user_id == current_user.id)
    ).all()
    return ApiResponse[list[NoteOut]](
        code=0,
        message="ok",
        data=[NoteOut.model_validate(note) for note in notes],
    )


@router.post("", response_model=ApiResponse[NoteOut], summary="创建笔记")
def create_note(
    payload: NoteCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[NoteOut]:
    """新建笔记。

    ``user_id`` 强制取 ``current_user.id``，不从请求体取。创建后 ``refresh`` 回填
    id / created_at / updated_at，再序列化返回。
    """
    note = Note(user_id=current_user.id, **payload.model_dump())
    db.add(note)
    db.commit()
    db.refresh(note)
    return ApiResponse[NoteOut](
        code=0, message="ok", data=NoteOut.model_validate(note)
    )


@router.get("/{note_id}", response_model=ApiResponse[NoteOut], summary="笔记详情")
def get_note(
    note_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[NoteOut]:
    """取单条笔记。

    按 ``(id, user_id)`` 查，查不到返回 404。"资源不存在" 和 "资源不属于当前用户"
    是同一个 404、同一句消息，不向调用方区分，避免越权信息泄露。
    """
    note = _get_owned_or_404(db, note_id, current_user.id)
    return ApiResponse[NoteOut](
        code=0, message="ok", data=NoteOut.model_validate(note)
    )


@router.put("/{note_id}", response_model=ApiResponse[NoteOut], summary="更新笔记")
def update_note(
    note_id: int,
    payload: NoteUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[NoteOut]:
    """部分更新笔记，只更新调用方传入的字段。

    先按 ``(id, user_id)`` 查、查不到 404（理由同上）。字段用
    ``model_dump(exclude_unset=True)`` 取，支持把 ``tags`` 这类可空字段显式置成
    ``null``。``updated_at`` 由模型上的 ``onupdate`` 在 commit 时自动刷新，
    路由层不用手动赋值。
    """
    note = _get_owned_or_404(db, note_id, current_user.id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(note, field, value)
    db.commit()
    db.refresh(note)
    return ApiResponse[NoteOut](
        code=0, message="ok", data=NoteOut.model_validate(note)
    )


@router.delete("/{note_id}", response_model=ApiResponse[None], summary="删除笔记")
def delete_note(
    note_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[None]:
    """删除笔记。

    先按 ``(id, user_id)`` 查、查不到 404，避免越权删除别人的笔记。删除成功返回
    200、``data`` 为 ``null``（契约 §1.2 没有 204）。
    """
    note = _get_owned_or_404(db, note_id, current_user.id)
    db.delete(note)
    db.commit()
    return ApiResponse[None](code=0, message="ok", data=None)
