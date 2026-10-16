"""笔记相关的请求 / 响应模型。契约见 docs/CONTRACT.md §4.4、§5.4。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, model_validator


class NoteCreate(BaseModel):
    """``POST /api/notes`` 的请求体。

    ``tags`` 是逗号分隔字符串（契约 §1.4 的例子 "算法,KV,后端"），可选。契约没规定
    长度或分隔格式，这里就不加额外约束。

    同样没有 ``user_id``：归属由 JWT 决定，不从请求体取。
    """

    title: str
    content_md: str
    tags: str | None = None


class NoteUpdate(BaseModel):
    """``PUT /api/notes/{id}`` 的请求体，字段全部可选。

    ``tags`` 不在非空集合里：它在库里是可空的，显式传 ``null`` 表示清空标签，是合法
    更新，不能被校验器误伤。
    """

    title: str | None = None
    content_md: str | None = None
    tags: str | None = None

    @model_validator(mode="after")
    def _reject_null_on_required_fields(self) -> "NoteUpdate":
        """拒绝对非空字段显式传 null。

        这些字段在数据库里是 NOT NULL，允许传 null 只会在 commit 时撞上
        IntegrityError 变成 500；在这里提前拦成 422，错误语义才对。
        判断用 model_fields_set 而不是看值是否为 None，才能区分「没传这个字段」
        和「显式传了 null」——前者是合法的部分更新，后者必须拒绝。
        """
        for field in ("title", "content_md"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} 不能为 null")
        return self


class NoteOut(BaseModel):
    """笔记对外暴露的字段，对应契约 §4.4 响应里的 ``data``。

    ``updated_at`` 会在每次更新记录时被模型上的 ``onupdate`` 自动刷新，路由层不用管。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    content_md: str
    tags: str | None
    created_at: datetime
    updated_at: datetime
