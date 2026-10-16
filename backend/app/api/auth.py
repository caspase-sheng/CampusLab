"""auth 接口。契约见 docs/CONTRACT.md §4.1。

三个接口：注册、登录、查当前用户。所有响应都套 ``{code, message, data}`` 信封
（契约 §1.2），错误由 ``app/core/errors.py`` 里的全局处理器统一转成信封形状，
所以这里只管 ``raise HTTPException(...)``，不用自己拼错误体。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.user import LoginRequest, RegisterRequest, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ApiResponse[UserOut], summary="注册")
def register(
    payload: RegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[UserOut]:
    """注册新用户。

    用户名或邮箱重复时返回 422、信封 ``code`` 也是 422。这里用 422 而不是 409
    是个取舍：契约 §1.2 的错误码表里只有 200 / 401 / 403 / 404 / 422 / 500，
    没有 409（Conflict），最接近的就是 422「参数校验失败」——重复的用户名/邮箱
    也可以理解成一个校验没过的请求。等以后契约里补了 409，改一行就行。

    密码用 ``hash_password`` 存成 ``hashed_password``，入库的永远是哈希，
    明文只在内存里过一遍。返回的 ``UserOut`` 里没有这个字段，所以不会漏出去。
    """
    existing = db.scalar(select(User).where(User.username == payload.username))
    if existing is not None:
        raise HTTPException(status_code=422, detail="用户名已存在")

    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=422, detail="邮箱已被注册")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return ApiResponse[UserOut](
        code=0, message="ok", data=UserOut.model_validate(user)
    )


@router.post("/login", response_model=ApiResponse[TokenOut], summary="登录")
def login(
    payload: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> ApiResponse[TokenOut]:
    """登录换 token。

    「用户名不存在」和「密码不对」返回完全一样的 401「用户名或密码错误」，
    不做区分——分开提示等于告诉别人哪些用户名是存在的，没必要把这个信息
    泄露出去。

    token 的有效期由 ``create_access_token`` 里的配置决定，默认 24 小时
    （契约 §1.3）。
    """
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(subject=str(user.id))
    return ApiResponse[TokenOut](
        code=0,
        message="ok",
        data=TokenOut(access_token=token, token_type="bearer"),
    )


@router.get("/me", response_model=ApiResponse[UserOut], summary="当前登录用户")
def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApiResponse[UserOut]:
    """返回当前 token 对应的用户，未登录 / token 无效由依赖抛 401。"""
    return ApiResponse[UserOut](
        code=0, message="ok", data=UserOut.model_validate(current_user)
    )
