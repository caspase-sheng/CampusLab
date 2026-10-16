"""notes 接口的接口测试（契约 §4.4）。"""

from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient

from conftest import register_and_login

NOTE = {
    "title": "KV 学习笔记",
    "content_md": "# WAL\n...",
    "tags": "KV,存储",
}


def _create_note(client: TestClient, headers: dict[str, str], **overrides) -> dict:
    """按 NOTE 建一条笔记（可覆盖字段），断言 200，返回 data。"""
    payload = dict(NOTE)
    payload.update(overrides)
    r = client.post("/api/notes", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _me_id(client: TestClient, headers: dict[str, str]) -> int:
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


# ------------------------------------------------------------------ 创建 / 列表


def test_create_note_ok(client: TestClient, auth_headers: dict[str, str]) -> None:
    """创建成功：200，信封字段正确，user_id 等于当前用户。"""
    r = client.post("/api/notes", json=NOTE, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0

    data = body["data"]
    assert data["title"] == "KV 学习笔记"
    assert data["content_md"] == "# WAL\n..."
    assert data["tags"] == "KV,存储"
    assert isinstance(data["id"], int)
    assert data["created_at"]
    assert data["updated_at"]
    assert data["user_id"] == _me_id(client, auth_headers)


def test_list_only_own(client: TestClient, auth_headers: dict[str, str]) -> None:
    """列表只返回自己的笔记。"""
    _create_note(client, auth_headers, title="我的笔记")
    other = register_and_login(client)
    _create_note(client, other, title="别人的笔记")

    r = client.get("/api/notes", headers=auth_headers)
    assert r.status_code == 200
    titles = [n["title"] for n in r.json()["data"]]
    assert titles == ["我的笔记"]


def test_get_note_ok(client: TestClient, auth_headers: dict[str, str]) -> None:
    """取单条成功。"""
    note = _create_note(client, auth_headers)
    r = client.get(f"/api/notes/{note['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["id"] == note["id"]


# -------------------------------------------------------------------- 鉴权 / 404


def test_list_without_token_401(client: TestClient) -> None:
    """不带 token：401 信封。"""
    r = client.get("/api/notes")
    assert r.status_code == 401
    assert r.json()["code"] == 401
    assert r.json()["data"] is None


def test_get_unknown_id_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    """取不存在的 id：404 信封。"""
    r = client.get("/api/notes/999999", headers=auth_headers)
    assert r.status_code == 404
    assert r.json() == {"code": 404, "message": "笔记不存在", "data": None}


def test_get_other_users_note_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """越权：A 的笔记，B 去 GET → 404。"""
    note = _create_note(client, auth_headers)
    other = register_and_login(client)

    r = client.get(f"/api/notes/{note['id']}", headers=other)
    assert r.status_code == 404
    assert r.json() == {"code": 404, "message": "笔记不存在", "data": None}


# ------------------------------------------------------------------------ 更新


def test_partial_update_keeps_other_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """部分更新：只改 title，其他字段保持原值。"""
    note = _create_note(client, auth_headers)

    r = client.put(
        f"/api/notes/{note['id']}", json={"title": "新标题"}, headers=auth_headers
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["title"] == "新标题"
    assert data["content_md"] == "# WAL\n..."
    assert data["tags"] == "KV,存储"


def test_partial_update_can_set_null(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """部分更新能把可空字段 tags 显式置成 null。"""
    note = _create_note(client, auth_headers)

    r = client.put(
        f"/api/notes/{note['id']}", json={"tags": None}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["tags"] is None

    r = client.get(f"/api/notes/{note['id']}", headers=auth_headers)
    assert r.json()["data"]["tags"] is None


def test_update_other_users_note_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """更新不存在 / 别人的笔记：都 404，别人的没被改动。"""
    note = _create_note(client, auth_headers)
    other = register_and_login(client)

    r = client.put(
        f"/api/notes/{note['id']}", json={"title": "被篡改"}, headers=other
    )
    assert r.status_code == 404

    r = client.put("/api/notes/999999", json={"title": "x"}, headers=auth_headers)
    assert r.status_code == 404

    r = client.get(f"/api/notes/{note['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "KV 学习笔记"


# ------------------------------------------------------------------------ 删除


def test_delete_then_get_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    """删除成功：200 data 为 null，删完再 GET → 404。"""
    note = _create_note(client, auth_headers)

    r = client.delete(f"/api/notes/{note['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"code": 0, "message": "ok", "data": None}

    r = client.get(f"/api/notes/{note['id']}", headers=auth_headers)
    assert r.status_code == 404


def test_delete_other_users_note_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """删除别人的笔记：404，且笔记仍在。"""
    note = _create_note(client, auth_headers)
    other = register_and_login(client)

    r = client.delete(f"/api/notes/{note['id']}", headers=other)
    assert r.status_code == 404

    r = client.get(f"/api/notes/{note['id']}", headers=auth_headers)
    assert r.status_code == 200


# --------------------------------------------------------------------- 校验


def test_update_rejects_null_on_required_field(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """PUT 给非空字段（title / content_md）显式传 null：422；
    可空字段 tags 置 null 不能被误伤。
    """
    note = _create_note(client, auth_headers)

    r = client.put(
        f"/api/notes/{note['id']}", json={"title": None}, headers=auth_headers
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 422
    assert body["data"] is None

    r = client.put(
        f"/api/notes/{note['id']}", json={"content_md": None}, headers=auth_headers
    )
    assert r.status_code == 422
    assert r.json()["code"] == 422
    assert r.json()["data"] is None

    # tags 在库里可空，显式置 null 是合法更新，必须仍然 200
    r = client.put(
        f"/api/notes/{note['id']}", json={"tags": None}, headers=auth_headers
    )
    assert r.status_code == 200
    assert r.json()["data"]["tags"] is None


def test_create_missing_field_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """POST 缺必填字段 content_md：422 信封。"""
    r = client.post("/api/notes", json={"title": "x"}, headers=auth_headers)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 422
    assert body["data"] is None


def test_update_updated_at_grows(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """更新后 updated_at 变大（模型 onupdate 自动刷新）。"""
    note = _create_note(client, auth_headers)
    before = datetime.fromisoformat(note["updated_at"])

    r = client.put(
        f"/api/notes/{note['id']}", json={"title": "改过的标题"}, headers=auth_headers
    )
    assert r.status_code == 200
    after = datetime.fromisoformat(r.json()["data"]["updated_at"])
    assert after > before
