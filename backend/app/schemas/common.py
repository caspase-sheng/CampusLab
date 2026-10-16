"""统一响应信封。契约见 docs/CONTRACT.md §1.2。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """契约 §1.2 规定的统一响应信封。``/api`` 下的所有接口都套这个壳。

    三个字段的含义：

    - ``code``：业务码，0 表示成功，非 0 表示错误（和 HTTP 状态码对应，见契约表）；
    - ``message``：人类可读信息，成功固定 "ok"；
    - ``data``：业务数据，失败时为 ``null``。

    ``data`` 用 ``T | None`` 而不是 ``T``：失败分支本来就返回 ``null``，如果写死
    ``T``，pydantic 会因为 ``None`` 校验不过而把 500 抛出来——契约明确说失败时
    ``data`` 是 ``null``，这里得留出这个口子。

    用泛型的目的只是让 OpenAPI 里每个接口的 ``data`` 有具体结构（比如
    ``ApiResponse[UserOut]``），生成出来的文档比 ``data: Any`` 好读。
    """

    code: int = 0
    message: str = "ok"
    data: T | None = None
