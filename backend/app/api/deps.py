"""``/api`` 路由的公共依赖：JWT 解析 + 取当前用户。契约见 docs/CONTRACT.md §1.3。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User

# 契约 §1.3：未登录或 token 无效一律 401，消息统一用这一句
UNAUTHORIZED_DETAIL = "未登录或 token 无效"

# auto_error=False 是必须的：OAuth2PasswordBearer 默认在缺 Authorization 头时
# 直接抛 403，而契约 §1.2 的错误码表里「未登录或 token 无效」对应的是 401。
# 关掉自动报错后，缺头时它返回 None，由下面的 get_current_user 统一转成 401。
# tokenUrl 只用于 OpenAPI 文档里的 Authorize 按钮，实际登录走 JSON 请求体。
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    """从 Authorization 头解析 JWT，查出并返回当前登录的 ORM ``User``。

    三种失败都归到同一个 401：没带 token、token 解析不出来（签名不对或已过期）、
    解析出来但用户在库里不存在。消息都用 ``UNAUTHORIZED_DETAIL``，不向调用方区分
    失败原因。

    契约 §1.3 提到的 JWT 黑名单（存自研 KV，key 为 ``jwt:blacklist:<token>``）
    本阶段没实现：现在没有 logout 接口，黑名单永远是空的，写在这里就是一段跑不到
    的死代码。等加 logout 时，在这个函数里 ``decode_access_token`` 之后补一次
    KV 查询即可（命中就同样抛 401）。
    """
    if token is None:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)

    subject = payload.get("sub")
    if subject is None:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)

    # sub 存的是 user_id（见 security.create_access_token）
    user = db.get(User, int(subject))
    if user is None:
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)
    return user
