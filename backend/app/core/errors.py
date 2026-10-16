"""全局异常处理器：本进程内**唯一**的异常处理注册入口。

为什么要合并在一处
------------------
Starlette 的异常处理器是存成一个 ``{异常类: 处理函数}`` 的字典的，键就是异常类
本身。如果两个地方各写一个 ``register_exception_handlers`` 并且都注册
``RequestValidationError``，后注册的那个会**直接覆盖**前一个——不是叠加，是覆盖。
之前 ``/kv`` 在 ``app/kv/server.py`` 里自己注册了一份，把 Pydantic 默认的 422 改写成
400；现在 ``/api`` 也要定制 422（改成信封），如果继续在别处另写一份，KV 那份会被顶掉，
``tests/test_kv_server.py`` 里那条「缺字段返回 400」的用例就会红。所以两个分支必须写在
**同一个**处理函数里，按路径分流。

为什么按路径分流
----------------
两套接口的错误格式在契约里是分开定的：

- ``/api``（契约 §1.2）：统一信封 ``{code, message, data}``，失败时 ``data`` 为 ``null``；
- ``/kv``（契约 §3.1、§3.3）：不套信封，错误体固定是 ``{"detail": "<字符串>"}``，
  且只允许 400 / 404 / 500，不能出现 422。

其余路径（比如文档示例里的未匹配路由）保持 FastAPI / Starlette 的默认行为不动，
免得为了两套接口把框架的默认语义也改了。
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def register_exception_handlers(app: FastAPI) -> None:
    """把两个全局异常处理器注册到 app 上。

    注册的是：

    1. ``RequestValidationError``——请求体 / 查询参数校验失败；
    2. ``HTTPException``——路由里主动抛的业务错误。

    两个都在内部按 ``request.url.path`` 分流。注意这里注册的 ``HTTPException``
    是 ``fastapi.HTTPException``（它继承自 Starlette 的同名类），路由里 ``raise`` 的
    也是它，所以 Starlette 内部自己抛的 404（路由没匹配上）仍然走框架默认处理器。
    """

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """校验失败：按路径决定错误体的形状和状态码。

        ``/api`` 走 422 + 信封，``/kv`` 走 400 + 纯 detail 字符串，两者拼接消息的
        方式一样（每条错误的 ``msg`` 用 ``"; "`` 连起来，加中文前缀），只是外层
        壳子不同。其余路径还原成 FastAPI 默认的 422 + 结构化 detail 列表——
        这本来就是框架原来的行为，只是因为我们接管了这个异常类，得手动补回来。

        ``jsonable_encoder`` 是给最后一支用的：``exc.errors()`` 里可能带非 JSON
        原生类型（比如 ``ctx`` 里塞了异常对象），直接丢进 JSONResponse 会序列化失败。
        """
        messages: list[str] = [str(err.get("msg", "")) for err in exc.errors()]
        detail: str = "参数校验失败：" + "; ".join(messages)

        if request.url.path.startswith("/api"):
            # 契约 §1.2：失败时 data 必须是 null，不要把 errors 列表塞进 data
            return JSONResponse(
                status_code=422,
                content={"code": 422, "message": detail, "data": None},
            )
        if request.url.path.startswith("/kv"):
            return JSONResponse(status_code=400, content={"detail": detail})
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder({"detail": exc.errors()}),
        )

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """主动抛出的 HTTPException：``/api`` 包成信封，其余保持默认形状。

        ``/api`` 分支里 ``code`` 直接取 ``exc.status_code``，和契约 §1.2 的状态码 /
        业务码对应表一致（401→401、404→404、422→422）。两个分支都把
        ``exc.headers`` 透传给 JSONResponse，这样 ``WWW-Authenticate`` 之类的
        响应头不会被吞掉——FastAPI 默认处理器也是这么做的。

        ``/kv`` 现在依赖默认行为返回 ``{"detail": "key not found"}``，这里非 ``/api``
        的分支就是把默认行为原样写了一遍，一个字不能变。
        """
        if request.url.path.startswith("/api"):
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "code": exc.status_code,
                    "message": str(exc.detail),
                    "data": None,
                },
                headers=exc.headers,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers,
        )
