"""课程相关的请求 / 响应模型。契约见 docs/CONTRACT.md §4.2、§5.2。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CourseCreate(BaseModel):
    """``POST /api/courses`` 的请求体。

    ``day_of_week`` 和 ``start_time`` / ``end_time`` 的约束都来自契约：§1.4 规定
    day_of_week 是 1-7 的整数、时间是 24 小时制 "HH:MM"，§5.2 的字段表也写了
    start_time / end_time 是 "HH:MM"。这属于契约内校验，所以放在这里；契约没提到的
    字段（name / teacher / location / week_range 的长度之类）一律不加额外约束。

    注意这里没有 ``user_id`` 字段：归属从 JWT 解析出来的当前用户拿，绝不由请求体传入，
    否则调用方可以伪造 user_id 往别人名下塞数据。
    """

    name: str
    day_of_week: int = Field(ge=1, le=7)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    teacher: str | None = None
    location: str | None = None
    week_range: str | None = None


class CourseUpdate(BaseModel):
    """``PUT /api/courses/{id}`` 的请求体，字段全部可选，只更新传入的字段。

    类型写成 ``str | None = None`` 而不是 ``str = None``：pydantic v2 里后者的类型
    注解仍是 ``str``，默认值 None 校验不过反而会报错，语义不一样。

    ``day_of_week`` 用 ``Field(default=None, ...)``：字段可缺省（部分更新），但一旦
    传了值就得通过 1-7 的范围校验；显式传 ``null`` 由下面的校验器拦下。
    """

    name: str | None = None
    teacher: str | None = None
    location: str | None = None
    day_of_week: int | None = Field(default=None, ge=1, le=7)
    start_time: str | None = None
    end_time: str | None = None
    week_range: str | None = None

    @model_validator(mode="after")
    def _reject_null_on_required_fields(self) -> "CourseUpdate":
        """拒绝对非空字段显式传 null。

        这些字段在数据库里是 NOT NULL，允许传 null 只会在 commit 时撞上
        IntegrityError 变成 500；在这里提前拦成 422，错误语义才对。
        判断用 model_fields_set 而不是看值是否为 None，才能区分「没传这个字段」
        和「显式传了 null」——前者是合法的部分更新，后者必须拒绝。
        """
        for field in ("name", "day_of_week", "start_time", "end_time"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} 不能为 null")
        return self


class CourseOut(BaseModel):
    """课程对外暴露的字段，对应契约 §4.2 响应里的 ``data``。

    ``from_attributes=True`` 让 ``CourseOut.model_validate(course)`` 能直接从 ORM
    的 ``Course`` 对象转过来，不用手写构造函数。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    name: str
    teacher: str | None
    location: str | None
    day_of_week: int
    start_time: str
    end_time: str
    week_range: str | None
    created_at: datetime
