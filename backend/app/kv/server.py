"""KV API 路由层：把自研 :class:`KVEngine` 包成 FastAPI 接口，落地契约 docs/CONTRACT.md §3。

这一层和 ``/api`` 下的后端接口不一样，几个约定单独记一下，免得写混：

- 不套 ``{code, message, data}`` 信封（契约 §1.2 的信封只用于 ``/api``），
  ``/kv`` 直接返回数据本身；
- 错误只用 400 / 404 / 500 三种状态码（契约 §3.3），不会出现 422；
  把 Pydantic 默认的 422 改写成 400 的那个校验异常处理器不在这里了，
  它和其他异常处理一起放在 ``app/core/errors.py``（全局只能有一处注册，
  否则同一异常类的处理器会被后注册的覆盖掉）；
- 错误体统一是 ``{"detail": "<人类可读字符串>"}``，``detail`` 是字符串不是列表。

引擎在进程内共用一份，惰性创建，应用关闭时由 ``close_engine()`` 统一收尾。
"""

from __future__ import annotations

import threading
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import settings
from app.kv.engine import KVEngine

router = APIRouter(prefix="/kv", tags=["kv"])

# ---------------------------------------------------------------- 引擎单例

_engine: KVEngine | None = None
_engine_lock: threading.Lock = threading.Lock()


def get_engine() -> KVEngine:
    """返回进程内共用的 KVEngine 单例，第一次调用时惰性创建。

    data_dir 取 ``settings.KV_DATA_DIR``；segment_max_bytes / cache_capacity
    都用 KVEngine 的默认值，不在这里额外覆盖。加锁是为了并发请求下
    只真正创建一次，避免两个请求各建一个引擎、后一个把前一个的文件句柄顶掉。

    测试里通过 ``app.dependency_overrides[get_engine]`` 换成临时目录的引擎，
    所以这个函数本身不会碰仓库目录。
    """
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                _engine = KVEngine(data_dir=settings.KV_DATA_DIR)
    return _engine


def close_engine() -> None:
    """关闭单例引擎并把 ``_engine`` 重置为 None。

    ``_engine`` 已经是 None 时是空操作；重复调用也不报错。应用关闭
    （lifespan 收尾）和测试退出时都会调它。
    """
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.close()
            _engine = None


# ------------------------------------------------------------- 请求 / 响应模型


class SetRequest(BaseModel):
    """``POST /kv/set`` 的请求体。

    ``ttl`` 可选，单位秒；不传表示永不过期。这里刻意不加 ``gt=0`` 之类的
    Pydantic 约束，让 ``ttl <= 0`` 由引擎抛 ValueError，路由再转成 400，
    这样错误信息更明确（见 kv_set 的说明）。
    """

    key: str
    value: str
    ttl: int | None = None


class SetResponse(BaseModel):
    """写 / 删操作的统一响应：``{"ok": true}``。"""

    ok: bool


class GetResponse(BaseModel):
    """``GET /kv/get/{key}`` 的响应。

    ``ttl`` 是剩余存活秒数（整数，向下取整）；永不过期时为 ``null``。
    """

    key: str
    value: str
    ttl: int | None


class KeysResponse(BaseModel):
    """``GET /kv/keys`` 的响应：当前所有未过期的键。"""

    keys: list[str]


class StatsResponse(BaseModel):
    """``GET /kv/stats`` 的响应，字段和引擎 stats() 一一对应。"""

    hits: int
    misses: int
    hit_rate: float
    keys: int
    wal_size: int
    files: int


class CompactResponse(BaseModel):
    """``POST /kv/compact`` 的响应：compaction 前后的段文件数量。"""

    ok: bool
    files_before: int
    files_after: int


# ---------------------------------------------------------------------- 路由


@router.post("/set", response_model=SetResponse, summary="写入或覆盖一个键")
def kv_set(
    payload: SetRequest,
    engine: Annotated[KVEngine, Depends(get_engine)],
) -> SetResponse:
    """写入或覆盖一个键。

    ``ttl`` 单位秒，不传表示永不过期。引擎在 ``ttl <= 0`` 时会抛 ValueError，
    这里捕获并转成 400（契约 §3.3 的「参数错误」），不往外漏 500。
    """
    try:
        engine.set(payload.key, payload.value, payload.ttl)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="ttl 必须是正整数秒") from exc
    return SetResponse(ok=True)


@router.get("/get/{key}", response_model=GetResponse, summary="读取一个键")
def kv_get(
    key: str,
    engine: Annotated[KVEngine, Depends(get_engine)],
) -> GetResponse:
    """读取一个键，顺带返回剩余 ttl。

    键不存在或已过期时返回 404，body 固定是 ``{"detail": "key not found"}``
    （契约 §3.2 给的示例），不区分「从来没写过」和「已过期」两种情况。
    """
    result = engine.get_with_ttl(key)
    if result is None:
        raise HTTPException(status_code=404, detail="key not found")
    value, ttl = result
    return GetResponse(key=key, value=value, ttl=ttl)


@router.delete("/del/{key}", response_model=SetResponse, summary="删除一个键")
def kv_del(
    key: str,
    engine: Annotated[KVEngine, Depends(get_engine)],
) -> SetResponse:
    """删除一个键，幂等——键不存在也返回 200 ``{"ok": true}``，不返回 404。

    这么定的理由：``/kv`` 是本地内部服务，删除一个本来就不存在的键不算错误。
    契约 §3.2 给 del 的响应示例只有 ``{"ok": true}``，也没有列 404 分支。
    实际使用里，前端重试删除、或者清理一个已经过期的会话键时，都会删到
    不存在的东西，如果这时报 404，调用方还得写「404 也算成功」的特判，
    反而别扭。所以这里统一返回成功，把「到底存不存在」交给 get 去回答。
    """
    engine.delete(key)
    return SetResponse(ok=True)


@router.get("/keys", response_model=KeysResponse, summary="列出所有未过期的键")
def kv_keys(
    engine: Annotated[KVEngine, Depends(get_engine)],
) -> KeysResponse:
    """列出当前所有未过期的键，顺序不保证。"""
    return KeysResponse(keys=engine.keys())


@router.get("/stats", response_model=StatsResponse, summary="引擎统计信息")
def kv_stats(
    engine: Annotated[KVEngine, Depends(get_engine)],
) -> StatsResponse:
    """返回引擎统计信息，固定六个字段（见 StatsResponse）。"""
    return StatsResponse(**engine.stats())


@router.post("/compact", response_model=CompactResponse, summary="触发 compaction")
def kv_compact(
    engine: Annotated[KVEngine, Depends(get_engine)],
) -> CompactResponse:
    """触发一次 compaction，把段文件里的历史记录合并成每个存活键一条。"""
    return CompactResponse(**engine.compact())
