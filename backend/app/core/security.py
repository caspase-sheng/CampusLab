"""JWT 与密码哈希工具。契约见 docs/CONTRACT.md §1.3。"""

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# 契约 §1.3 未指定算法，先用 HS256
ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """注册时把明文密码转成 users.hashed_password。"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """登录时校验密码。"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    """签发 JWT。subject 放 user_id，有效期默认取配置里的 24 小时。"""
    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """解析 JWT，签名过期或不合法都返回 None，由调用方转成 401。"""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# 注销时的 token 黑名单（key 为 jwt:blacklist:<token>）在鉴权依赖里查 KV，
# 这里先不放，等 /api 路由和 KV 客户端接上再补。
