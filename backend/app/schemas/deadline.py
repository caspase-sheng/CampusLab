"""DDL（截止事项）相关的请求 / 响应模型。契约见 docs/CONTRACT.md §4.3、§5.3。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class DeadlineCreate(BaseModel):
    """``POST /api/deadlines`` 的请求体。

    ``status`` 用 ``Literal["pending", "done"]`` 卡取值，只在这两个值里选，默认
    ``"pending"``——契约 §5.3 明确写了 status 只有 pending / done 两种取值，属于
    契约内校验。

    ``course_id`` 可选；若传了值，是否属于当前用户由路由层把关（请求体里引用的
    课程无效时返回 422，见 ``app/api/deadlines.py``）。

    同样没有 ``user_id``：归属由 JWT 决定，不从请求体取。
    """

    title: str
    due_time: datetime
    course_id: int | None = None
    status: Literal["pending", "done"] = "pending"


class DeadlineUpdate(BaseModel):
    """``PUT /api/deadlines/{id}`` 的请求体，字段全部可选。

    ``status`` 类型是 ``Literal["pending", "done"] | None``：不传表示不动，传了就必须
    是这两个值之一；显式传 ``null`` 由下面的校验器拦下（它在库里是 NOT NULL）。

    ``course_id`` 不在非空集合里：它对应数据库的可空外键，显式传 ``null`` 表示解除
    与课程的关联，是合法更新，不能被校验器误伤。
    """

    title: str | None = None
    course_id: int | None = None
    due_time: datetime | None = None
    status: Literal["pending", "done"] | None = None

    @model_validator(mode="after")
    def _reject_null_on_required_fields(self) -> "DeadlineUpdate":
        """拒绝对非空字段显式传 null。

        这些字段在数据库里是 NOT NULL，允许传 null 只会在 commit 时撞上
        IntegrityError 变成 500；在这里提前拦成 422，错误语义才对。
        判断用 model_fields_set 而不是看值是否为 None，才能区分「没传这个字段」
        和「显式传了 null」——前者是合法的部分更新，后者必须拒绝。
        """
        for field in ("title", "due_time", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} 不能为 null")
        return self


class DeadlineOut(BaseModel):
    """DDL 对外暴露的字段，对应契约 §4.3 响应里的 ``data``。

    ``course_id`` 可空：课程被删掉后数据库层会把它置为 NULL（ON DELETE SET NULL）。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    title: str
    course_id: int | None
    due_time: datetime
    status: str
    created_at: datetime
