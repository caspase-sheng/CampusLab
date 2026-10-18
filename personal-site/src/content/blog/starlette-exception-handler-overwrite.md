---
title: 同一个异常类注册两次，后注册的会直接顶掉前一个
description: /api 要定制 422、/kv 要定制 400，两套错误格式一度分在两个文件里各注册一份。后来发现 Starlette 的处理器是按异常类存的字典，同一类注册两次就是覆盖，不是叠加。
date: 2026-10-18
tags:
  - 后端
  - FastAPI
  - 异常处理
draft: false
---

给 /api 加统一错误信封的时候，差点顺手在路由文件里再写一个 RequestValidationError 的处理器。幸好在动手前翻了一眼 /kv 那边，发现它早就在 backend/app/kv/server.py 里自己注册过一份同样的东西，把 Pydantic 默认的 422 改写成 400。两份并存，晚注册的那份会把早的那份顶掉。

## 处理器是按异常类存的一张字典

Starlette 把异常处理器存成一个 `{异常类: 处理函数}` 的字典，键就是异常类本身。`@app.exception_handler(SomeError)` 底层调的是 `add_exception_handler`，往这张字典里写一条。同一个类写两次，后写的直接覆盖前一条，不是叠加成两条按顺序跑。

所以「每个模块管自己那段错误格式」这种看起来合理的分法，在框架这一层根本不成立。谁最后注册，谁就是唯一生效的那份，另一份进不了调用链。

## 合并到一个入口

现在全局只有 backend/app/core/errors.py 里的 `register_exception_handlers(app: FastAPI) -> None` 这一个注册入口，里面注册两个处理器：RequestValidationError 和 HTTPException。两个处理器内部都按 `request.url.path` 分流，把两套接口的错误形状分开。

RequestValidationError 这一支分三段：

- 路径以 /api 开头：422，信封 `{code: 422, message: "...", data: null}`；
- 路径以 /kv 开头：400，body 是 `{"detail": "<字符串>"}`，不套信封；
- 其余路径：保持 FastAPI 默认的那套 422，body 用 `jsonable_encoder({"detail": exc.errors()})`。

最后那一段是特意留的。因为异常类被我们接管了，框架原本的默认行为也得手动补回来，不然其余路径的错误形状会跟着变。

HTTPException 处理器是两段：/api 开头返回 `{code: exc.status_code, message: str(exc.detail), data: null}`，其余路径返回 `{"detail": exc.detail}`。两段都把 `exc.headers` 透传给响应，这样 `WWW-Authenticate` 这类头不会被吞掉。

## 有个细节容易看漏

这里注册的是 `fastapi.HTTPException`，它继承自 Starlette 的同名类。所以 Starlette 自己抛的 404——路由压根没匹配上的那种——并不会落到我们的处理器里，仍然走框架默认处理器。文档里那条「其余路径保持默认行为」的说法，靠的就是这个继承关系，不是我们写了什么特判。

## 原来那份已经删了

backend/app/kv/server.py 里那份自己注册的 RequestValidationError 处理器已经删掉，逻辑全搬到 app/core/errors.py 了。留在原地的话，两边各注册一次，谁覆盖谁就取决于 import 顺序，这种 bug 不报错，只是某天发现 /kv 的 400 变回 422。

## 锁住这块的测试

两条用例正好把分流的两个方向都钉住：

- backend/tests/test_kv_server.py 的 `test_missing_field_400_not_422`，断言 /kv 校验失败返回的是 400 而不是 422；
- backend/tests/test_auth.py 的 `test_error_handling_split_between_kv_and_api`，同一条用例里既断言 /kv 回来的是裸 `detail`，又断言 /api 回来的是 422 信封。

哪天有人把注册拆回两个地方，这两条会有一条先红，不至于让覆盖悄悄发生。
