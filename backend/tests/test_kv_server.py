"""KV API 路由层的接口测试（契约 §3）。

每个用例都用 tmp_path 建一个独立引擎，并通过
``app.dependency_overrides[get_engine]`` 注入到 app 里，不往仓库目录写数据。
``with TestClient(app)`` 会触发 lifespan，退出时调 close_engine()；因为依赖
被覆盖了，真实单例始终是 None，close_engine() 走空操作分支，不该报错。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.kv.engine import KVEngine
from app.kv.server import get_engine
from app.main import app


@pytest.fixture
def client(tmp_path):
    """给每个用例一个临时目录的引擎，并把它注入 app 的依赖。"""
    engine = KVEngine(data_dir=str(tmp_path), segment_max_bytes=256, cache_capacity=8)
    app.dependency_overrides[get_engine] = lambda: engine
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.close()


def test_set_then_get_roundtrip(client) -> None:
    """set / get 往返：set 返回 ok，get 返回 key / value / ttl 三个字段。"""
    r = client.post("/kv/set", json={"key": "a", "value": "hello"})
    assert r.status_code == 200
    assert r.json() == {"ok": True}

    r = client.get("/kv/get/a")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"key", "value", "ttl"}
    assert body["key"] == "a"
    assert body["value"] == "hello"
    assert body["ttl"] is None


def test_get_missing_key_404(client) -> None:
    """get 不存在的键返回 404，body 恰好是 {"detail": "key not found"}。"""
    r = client.get("/kv/get/nope")
    assert r.status_code == 404
    assert r.json() == {"detail": "key not found"}


def test_get_ttl(client) -> None:
    """带 ttl 的键返回剩余秒数；永不过期的键 ttl 是 null。"""
    client.post("/kv/set", json={"key": "t", "value": "v", "ttl": 60})
    r = client.get("/kv/get/t")
    assert r.status_code == 200
    # 往返之间会有几十毫秒误差，向下取整后 59 / 60 都算对
    assert r.json()["ttl"] in (59, 60)

    client.post("/kv/set", json={"key": "p", "value": "v"})
    assert client.get("/kv/get/p").json()["ttl"] is None


@pytest.mark.parametrize("ttl", [0, -1])
def test_set_invalid_ttl_400(client, ttl: int) -> None:
    """ttl <= 0 返回 400，detail 是字符串，而不是 422。"""
    r = client.post("/kv/set", json={"key": "a", "value": "v", "ttl": ttl})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], str)
    assert body["detail"] == "ttl 必须是正整数秒"


def test_missing_field_400_not_422(client) -> None:
    """请求体缺字段时返回 400（KV 专用处理器把默认的 422 改掉了）。"""
    r = client.post("/kv/set", json={"key": "a"})
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], str)
    assert "参数校验失败" in body["detail"]


def test_del_is_idempotent(client) -> None:
    """del 幂等：存在的键和不存在的键都返回 200 {"ok": true}。"""
    client.post("/kv/set", json={"key": "a", "value": "v"})

    r = client.delete("/kv/del/a")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # 删完再 get 应该是 404
    assert client.get("/kv/get/a").status_code == 404

    r = client.delete("/kv/del/a")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_keys(client) -> None:
    """set 三个键后 keys 列表包含这三个。"""
    for k in ("k1", "k2", "k3"):
        client.post("/kv/set", json={"key": k, "value": "v"})

    r = client.get("/kv/keys")
    assert r.status_code == 200
    assert set(r.json()["keys"]) >= {"k1", "k2", "k3"}


def test_stats_fields_and_counts(client) -> None:
    """stats 恰好六个字段；set + get 之后 hits >= 1，keys 计数正确。"""
    client.post("/kv/set", json={"key": "a", "value": "v"})
    client.post("/kv/set", json={"key": "b", "value": "v"})
    client.get("/kv/get/a")

    r = client.get("/kv/stats")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"hits", "misses", "hit_rate", "keys", "wal_size", "files"}
    assert body["hits"] >= 1
    assert body["keys"] == 2


def test_compact(client) -> None:
    """覆盖写同一键多次后 compact，段数不增，且仍能拿到最新值。"""
    latest = "x" * 100 + "9"
    for i in range(10):
        client.post("/kv/set", json={"key": "same", "value": "x" * 100 + str(i)})

    r = client.post("/kv/compact")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["files_after"] <= body["files_before"]

    got = client.get("/kv/get/same")
    assert got.status_code == 200
    assert got.json()["value"] == latest


def test_response_has_no_envelope(client) -> None:
    """KV API 不套统一信封：响应顶层没有 code / message / data。"""
    body = client.get("/kv/stats").json()
    assert "code" not in body
    assert "message" not in body
    assert "data" not in body


def test_routes_mounted() -> None:
    """六个 KV 路由都挂到了 app 上（只看 OpenAPI，不发请求）。"""
    paths = app.openapi()["paths"]
    for path in (
        "/kv/set",
        "/kv/get/{key}",
        "/kv/del/{key}",
        "/kv/keys",
        "/kv/stats",
        "/kv/compact",
    ):
        assert path in paths
