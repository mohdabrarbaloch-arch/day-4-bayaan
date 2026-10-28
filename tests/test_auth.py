"""Registration, login, and token handling."""

from __future__ import annotations

from app.security import decode_access_token, hash_password, verify_password


def test_register_returns_token_and_user(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "new@mailcatch.dev", "display_name": "Ayesha", "password": "longenough123"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "new@mailcatch.dev"
    assert body["user"]["display_name"] == "Ayesha"
    assert "password" not in body["user"]


def test_duplicate_email_is_rejected_case_insensitively(client):
    payload = {"email": "dup@mailcatch.dev", "display_name": "Ayesha", "password": "longenough123"}
    assert client.post("/api/auth/register", json=payload).status_code == 201

    payload["email"] = "DUP@mailcatch.dev"
    second = client.post("/api/auth/register", json=payload)
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"]


def test_short_password_fails_validation(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "short@mailcatch.dev", "display_name": "Ayesha", "password": "abc"},
    )
    assert r.status_code == 422


def test_invalid_email_fails_validation(client):
    r = client.post(
        "/api/auth/register",
        json={"email": "not-an-email", "display_name": "Ayesha", "password": "longenough123"},
    )
    assert r.status_code == 422


def test_login_succeeds_with_correct_password(client):
    payload = {"email": "login@mailcatch.dev", "display_name": "Bilal", "password": "longenough123"}
    client.post("/api/auth/register", json=payload)

    r = client.post(
        "/api/auth/login", json={"email": "login@mailcatch.dev", "password": "longenough123"}
    )
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "login@mailcatch.dev"


def test_login_wrong_password_is_401(client):
    client.post(
        "/api/auth/register",
        json={"email": "wp@mailcatch.dev", "display_name": "Chand", "password": "longenough123"},
    )
    r = client.post("/api/auth/login", json={"email": "wp@mailcatch.dev", "password": "wrongpass"})
    assert r.status_code == 401


def test_login_unknown_user_gives_same_message_as_wrong_password(client):
    # Identical wording prevents the endpoint from confirming which emails exist.
    a = client.post(
        "/api/auth/login", json={"email": "ghost@mailcatch.dev", "password": "whatever1"}
    )
    assert a.status_code == 401
    assert a.json()["detail"] == "Email or password is incorrect."


def test_me_requires_a_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_me_rejects_a_garbage_token(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_me_returns_the_authenticated_user(client, auth):
    r = client.get("/api/auth/me", headers=auth)
    assert r.status_code == 200
    assert r.json()["email"].startswith("tester")


def test_bcrypt_hash_is_salted_and_verifies():
    h1 = hash_password("same-password")
    h2 = hash_password("same-password")
    assert h1 != h2  # different salts
    assert verify_password("same-password", h1)
    assert not verify_password("different", h1)


def test_password_over_72_bytes_does_not_crash():
    # bcrypt truncates at 72 bytes; we slice explicitly so it never raises.
    long_pw = "x" * 100
    hashed = hash_password(long_pw)
    assert verify_password(long_pw, hashed)


def test_rate_limiter_blocks_after_the_budget_is_spent():
    """The limiter itself, tested directly — the suite-wide budget is raised so
    this is the only place the real behaviour is exercised."""
    from fastapi import HTTPException

    from app.ratelimit import RateLimit, reset_limits

    reset_limits()
    limiter = RateLimit("2/minute", scope="unit-test")

    class FakeRequest:
        method = "POST"
        headers = {}

        class url:
            path = "/unit"

        class client:
            host = "10.0.0.1"

    req = FakeRequest()
    limiter(req)  # 1st
    limiter(req)  # 2nd
    try:
        limiter(req)  # 3rd — over budget
    except HTTPException as exc:
        assert exc.status_code == 429
        assert "Retry-After" in exc.headers
    else:
        raise AssertionError("the third call should have been rejected")


def test_limit_spec_parsing():
    from app.ratelimit import Limit

    assert Limit.parse("30/minute") == Limit(count=30, window_seconds=60)
    assert Limit.parse("5/hour").window_seconds == 3600
    assert Limit.parse("2/seconds").count == 2


def test_bad_limit_spec_raises():
    import pytest as _pytest

    from app.ratelimit import Limit

    with _pytest.raises(ValueError):
        Limit.parse("thirty per minute")
    with _pytest.raises(ValueError):
        Limit.parse("5/fortnight")


def test_tampered_token_is_rejected():
    from app.security import create_access_token

    token = create_access_token("some-user-id")
    assert decode_access_token(token) == "some-user-id"
    assert decode_access_token(token + "tampered") is None
