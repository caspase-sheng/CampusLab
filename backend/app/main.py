from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import APIRouter, FastAPI

from app.api.auth import router as auth_router
from app.api.courses import router as courses_router
from app.api.deadlines import router as deadlines_router
from app.api.notes import router as notes_router
from app.core.errors import register_exception_handlers
from app.kv.server import close_engine
from app.kv.server import router as kv_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：启动时不用做额外的事，关闭时收起 KV 引擎的文件句柄。

    引擎本身是惰性创建的（第一个 /kv 请求才建），所以这里只需要管关闭：
    调 ``close_engine()``，它在单例是 None 时是空操作，重复调用也不报错。
    """
    yield
    close_engine()


app = FastAPI(title="CampusLab", lifespan=lifespan)

# 契约 §4：后端 API 挂载点。子路由必须先 include 进 api_router，再把 api_router
# 挂到 app 上——FastAPI 的 include_router 是「调用时就复制路由」，顺序反了的话
# 后加的子路由不会生效（挂载那一刻已经拷贝完了）。
api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(courses_router)
api_router.include_router(deadlines_router)
api_router.include_router(notes_router)

app.include_router(api_router)

# 契约 §3：KV API，真实路由来自 app.kv.server
app.include_router(kv_router)

# 契约 §1.2 / §3.3：异常处理统一在 app/core/errors.py，这里只调一次。
# 不要在这里或别处再注册第二个异常处理器——同一异常类会被覆盖。
register_exception_handlers(app)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
