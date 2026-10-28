"""Saved prompts: CRUD, ownership, and name collisions."""

from __future__ import annotations


def test_prompts_require_auth(client):
    assert client.get("/api/prompts").status_code == 401
    assert client.post("/api/prompts", json={"name": "x"}).status_code == 401


def test_new_user_has_no_prompts(client, auth):
    r = client.get("/api/prompts", headers=auth)
    assert r.status_code == 200
    assert r.json() == []


def test_create_and_read_back(client, auth):
    r = client.post(
        "/api/prompts",
        json={
            "name": "Code reviewer",
            "system_prompt": "You review Python for correctness.",
            "user_prompt": "Review this function.",
        },
        headers=auth,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Code reviewer"
    assert body["id"]

    fetched = client.get(f"/api/prompts/{body['id']}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.json()["system_prompt"].startswith("You review")


def test_duplicate_name_conflicts(client, auth):
    payload = {"name": "Same name", "system_prompt": "s", "user_prompt": "u"}
    assert client.post("/api/prompts", json=payload, headers=auth).status_code == 201
    second = client.post("/api/prompts", json=payload, headers=auth)
    assert second.status_code == 409
    assert "already have" in second.json()["detail"]


def test_patch_updates_only_supplied_fields(client, auth):
    created = client.post(
        "/api/prompts",
        json={"name": "Original", "system_prompt": "keep me", "user_prompt": "also keep"},
        headers=auth,
    ).json()

    r = client.patch(f"/api/prompts/{created['id']}", json={"name": "Renamed"}, headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Renamed"
    # Fields we didn't send must survive untouched.
    assert body["system_prompt"] == "keep me"
    assert body["user_prompt"] == "also keep"


def test_delete_removes_the_prompt(client, auth):
    created = client.post("/api/prompts", json={"name": "Temp"}, headers=auth).json()
    assert client.delete(f"/api/prompts/{created['id']}", headers=auth).status_code == 204
    assert client.get(f"/api/prompts/{created['id']}", headers=auth).status_code == 404


def test_prompts_are_scoped_per_user(client, auth):
    created = client.post("/api/prompts", json={"name": "Private"}, headers=auth).json()

    other = client.post(
        "/api/auth/register",
        json={"email": "second@mailcatch.dev", "display_name": "Two", "password": "longenough123"},
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    # Other user sees none of them and can't read by id.
    assert client.get("/api/prompts", headers=other_headers).json() == []
    assert client.get(f"/api/prompts/{created['id']}", headers=other_headers).status_code == 404


def test_same_name_allowed_across_different_users(client, auth):
    assert client.post("/api/prompts", json={"name": "Shared"}, headers=auth).status_code == 201

    other = client.post(
        "/api/auth/register",
        json={"email": "third@mailcatch.dev", "display_name": "Three", "password": "longenough123"},
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    r = client.post("/api/prompts", json={"name": "Shared"}, headers=other_headers)
    assert r.status_code == 201


def test_blank_name_rejected(client, auth):
    assert client.post("/api/prompts", json={"name": ""}, headers=auth).status_code == 422


def test_overlong_name_rejected(client, auth):
    r = client.post("/api/prompts", json={"name": "x" * 200}, headers=auth)
    assert r.status_code == 422
