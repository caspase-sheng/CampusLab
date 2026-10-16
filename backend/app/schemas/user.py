"""auth 相关的请求 / 响应模型。契约见 docs/CONTRACT.md §4.1。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RegisterRequest(BaseModel):
    """``POST /api/auth/register`` 的请求体。

    password 这里刻意不加 ``min_length`` 之类的约束：契约 §4.1 只写了三个字符串
    字段，没规定长度下限，加了就属于契约之外的东西了。
    """

    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    """``POST /api/auth/login`` 的请求体。"""

    username: str
    password: str


class UserOut(BaseModel):
    """用户对外暴露的字段，对应契约 §4.1 响应里的 ``data``。

    只有 id / username / email 三个字段——``hashed_password`` 绝不出现在这里，
    它只留在数据库里。``from_attributes=True`` 是为了能用
    ``UserOut.model_validate(user)`` 直接从 ORM 的 ``User`` 对象转过来，
    不用手写一个 ``xx=user.xx`` 的构造函数。
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: str


class TokenOut(BaseModel):
    """``POST /api/auth/login`` 成功后放在信封 ``data`` 里的内容。"""

    access_token: str
    token_type: str
