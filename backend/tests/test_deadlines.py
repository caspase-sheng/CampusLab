"""deadlines 接口的接口测试（契约 §4.3），外加一条跨资源回归用例。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import register_and_login

DEADLINE = {
    "title": "数据结构作业3",
    "due_time": "2026-10-20T23:59:00",
    "status": "pending",
}

COURSE = {
    "name": "数据结构",
    "day_of_week": 1,
    "start_time": "08:00",
    "end_time": "09:40",
}


def _create_course(client: TestClient, headers: dict[str, str]) -> int:
    """建一门课，返回课程 id。"""
    r = client.post("/api/courses", json=COURSE, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


def _create_deadline(
    client: TestClient, headers: dict[str, str], **overrides
) -> dict:
    """按 DEADLINE 建一条 DDL（可覆盖字段），断言 200，返回 data。"""
    payload = dict(DEADLINE)
    payload.update(overrides)
    r = client.post("/api/deadlines", json=payload, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _me_id(client: TestClient, headers: dict[str, str]) -> int:
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


# ------------------------------------------------------------------ 创建 / 列表


def test_create_deadline_ok(client: TestClient, auth_headers: dict[str, str]) -> None:
    """创建成功：200，信封字段正确，user_id 等于当前用户。"""
    r = client.post("/api/deadlines", json=DEADLINE, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["code"] == 0

    data = body["data"]
    assert data["title"] == "数据结构作业3"
    assert data["due_time"].startswith("2026-10-20T23:59")
    assert data["status"] == "pending"
    assert data["course_id"] is None
    assert isinstance(data["id"], int)
    assert data["user_id"] == _me_id(client, auth_headers)


def test_list_only_own(client: TestClient, auth_headers: dict[str, str]) -> None:
    """列表只返回自己的 DDL。"""
    _create_deadline(client, auth_headers, title="我的DDL")
    other = register_and_login(client)
    _create_deadline(client, other, title="别人的DDL")

    r = client.get("/api/deadlines", headers=auth_headers)
    assert r.status_code == 200
    titles = [d["title"] for d in r.json()["data"]]
    assert titles == ["我的DDL"]


def test_get_deadline_ok(client: TestClient, auth_headers: dict[str, str]) -> None:
    """取单条成功。"""
    deadline = _create_deadline(client, auth_headers)
    r = client.get(f"/api/deadlines/{deadline['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["id"] == deadline["id"]


# -------------------------------------------------------------------- 鉴权 / 404


def test_list_without_token_401(client: TestClient) -> None:
    """不带 token：401 信封。"""
    r = client.get("/api/deadlines")
    assert r.status_code == 401
    assert r.json()["code"] == 401
    assert r.json()["data"] is None


def test_get_unknown_id_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    """取不存在的 id：404 信封。"""
    r = client.get("/api/deadlines/999999", headers=auth_headers)
    assert r.status_code == 404
    assert r.json() == {"code": 404, "message": "DDL 不存在", "data": None}


def test_get_other_users_deadline_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """越权：A 的 DDL，B 去 GET → 404。"""
    deadline = _create_deadline(client, auth_headers)
    other = register_and_login(client)

    r = client.get(f"/api/deadlines/{deadline['id']}", headers=other)
    assert r.status_code == 404
    assert r.json() == {"code": 404, "message": "DDL 不存在", "data": None}


# ------------------------------------------------------------------------ 更新


def test_partial_update_keeps_other_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """部分更新：只改 status，其他字段保持原值。"""
    deadline = _create_deadline(client, auth_headers)

    r = client.put(
        f"/api/deadlines/{deadline['id']}",
        json={"status": "done"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "done"
    assert data["title"] == "数据结构作业3"
    assert data["course_id"] is None


def test_partial_update_can_clear_course_id(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """部分更新能把 course_id 显式置成 null（解除关联）。"""
    course_id = _create_course(client, auth_headers)
    deadline = _create_deadline(client, auth_headers, course_id=course_id)
    assert deadline["course_id"] == course_id

    r = client.put(
        f"/api/deadlines/{deadline['id']}",
        json={"course_id": None},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["course_id"] is None

    r = client.get(f"/api/deadlines/{deadline['id']}", headers=auth_headers)
    assert r.json()["data"]["course_id"] is None


def test_update_other_users_deadline_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """更新不存在 / 别人的 DDL：都 404，别人的没被改动。"""
    deadline = _create_deadline(client, auth_headers)
    other = register_and_login(client)

    r = client.put(
        f"/api/deadlines/{deadline['id']}",
        json={"title": "被篡改"},
        headers=other,
    )
    assert r.status_code == 404

    r = client.put("/api/deadlines/999999", json={"title": "x"}, headers=auth_headers)
    assert r.status_code == 404

    r = client.get(f"/api/deadlines/{deadline['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["title"] == "数据结构作业3"


# ------------------------------------------------------------------------ 删除


def test_delete_then_get_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    """删除成功：200 data 为 null，删完再 GET → 404。"""
    deadline = _create_deadline(client, auth_headers)

    r = client.delete(f"/api/deadlines/{deadline['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"code": 0, "message": "ok", "data": None}

    r = client.get(f"/api/deadlines/{deadline['id']}", headers=auth_headers)
    assert r.status_code == 404


def test_delete_other_users_deadline_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """删除别人的 DDL：404，且 DDL 仍在。"""
    deadline = _create_deadline(client, auth_headers)
    other = register_and_login(client)

    r = client.delete(f"/api/deadlines/{deadline['id']}", headers=other)
    assert r.status_code == 404

    r = client.get(f"/api/deadlines/{deadline['id']}", headers=auth_headers)
    assert r.status_code == 200


# --------------------------------------------------------------------- 校验


def test_update_rejects_null_on_required_field(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """PUT 给非空字段（due_time / status）显式传 null：422；
    可空字段 course_id 置 null 不能被误伤。
    """
    course_id = _create_course(client, auth_headers)
    deadline = _create_deadline(client, auth_headers, course_id=course_id)

    r = client.put(
        f"/api/deadlines/{deadline['id']}",
        json={"due_time": None},
        headers=auth_headers,
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 422
    assert body["data"] is None

    r = client.put(
        f"/api/deadlines/{deadline['id']}",
        json={"status": None},
        headers=auth_headers,
    )
    assert r.status_code == 422
    assert r.json()["data"] is None

    # course_id 在库里可空，显式置 null 是合法更新，必须仍然 200
    r = client.put(
        f"/api/deadlines/{deadline['id']}",
        json={"course_id": None},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["data"]["course_id"] is None


def test_create_invalid_status_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """status 传非法值：422 信封。"""
    r = client.post(
        "/api/deadlines",
        json={**DEADLINE, "status": "cancelled"},
        headers=auth_headers,
    )
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == 422
    assert body["data"] is None


# ------------------------------------------------------------- course_id 归属校验


def test_course_id_own_course_ok(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """course_id 指向自己的课程：创建成功。"""
    course_id = _create_course(client, auth_headers)
    deadline = _create_deadline(client, auth_headers, course_id=course_id)
    assert deadline["course_id"] == course_id


def test_course_id_other_course_422(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """course_id 指向别人的课程：422（问题出在请求体引用的资源无效）。"""
    course_id = _create_course(client, auth_headers)
    other = register_and_login(client)

    r = client.post(
        "/api/deadlines",
        json={**DEADLINE, "course_id": course_id},
        headers=other,
    )
    assert r.status_code == 422
    assert r.json() == {
        "code": 422,
        "message": "课程不存在或不属于当前用户",
        "data": None,
    }


def test_course_id_null_ok(client: TestClient, auth_headers: dict[str, str]) -> None:
    """course_id 传 null：创建成功，course_id 为 None。"""
    deadline = _create_deadline(client, auth_headers, course_id=None)
    assert deadline["course_id"] is None


# ------------------------------------------------------------------- 跨资源回归


def test_delete_course_keeps_deadline_with_null_course_id(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """回归：删掉一门 course 后，挂在它下面的 deadline 还在，course_id 变成 None。

    验证的是数据库层的 ON DELETE SET NULL，不是路由层逻辑。
    """
    course_id = _create_course(client, auth_headers)
    deadline = _create_deadline(client, auth_headers, course_id=course_id)

    r = client.delete(f"/api/courses/{course_id}", headers=auth_headers)
    assert r.status_code == 200

    r = client.get(f"/api/deadlines/{deadline['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["data"]["course_id"] is None
