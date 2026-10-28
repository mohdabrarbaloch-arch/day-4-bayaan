"""Running prompts, history, stats, and error handling."""

from __future__ import annotations

VALID = {
    "model_id": "llama-3.1-8b-instruct",
    "backend": "local",
    "system_prompt": "You are a careful technical writer.",
    "user_prompt": "Explain WAL mode in three bullet points.",
    "temperature": 0.4,
    "top_p": 0.9,
    "max_tokens": 256,
}


def test_run_requires_auth(client):
    assert client.post("/api/runs", json=VALID).status_code == 401


def test_run_with_no_model_configured_uses_inspector_and_says_so(client, auth):
    r = client.post("/api/runs", json=VALID, headers=auth)
    assert r.status_code == 201
    body = r.json()
    # The critical honesty check: it must NOT claim to be a real model.
    assert body["backend"] == "inspector"
    assert body["simulated"] is True
    assert body["status"] == "ok"
    assert body["output"]
    # And the output must be labelled as an inspection, not a chat reply.
    assert "PROMPT INSPECTION" in body["output"]
    assert "No model was called" in body["output"]


def test_inspector_output_includes_the_rendered_prompt(client, auth):
    r = client.post("/api/runs", json=VALID, headers=auth)
    assert "<|begin_of_text|>" in r.json()["output"]


def test_unknown_model_is_404(client, auth):
    payload = {**VALID, "model_id": "gpt-does-not-exist"}
    r = client.post("/api/runs", json=payload, headers=auth)
    assert r.status_code == 404
    assert "catalog" in r.json()["detail"]


def test_blank_prompt_fails_validation(client, auth):
    r = client.post("/api/runs", json={**VALID, "user_prompt": "   "}, headers=auth)
    assert r.status_code == 422


def test_empty_prompt_fails_validation(client, auth):
    r = client.post("/api/runs", json={**VALID, "user_prompt": ""}, headers=auth)
    assert r.status_code == 422


def test_out_of_range_temperature_fails(client, auth):
    r = client.post("/api/runs", json={**VALID, "temperature": 5.0}, headers=auth)
    assert r.status_code == 422


def test_out_of_range_top_p_fails(client, auth):
    r = client.post("/api/runs", json={**VALID, "top_p": 1.5}, headers=auth)
    assert r.status_code == 422


def test_max_tokens_upper_bound_enforced(client, auth):
    r = client.post("/api/runs", json={**VALID, "max_tokens": 99_999}, headers=auth)
    assert r.status_code == 422


def test_run_records_token_estimates(client, auth):
    r = client.post("/api/runs", json=VALID, headers=auth)
    body = r.json()
    assert body["prompt_tokens"] > 0
    assert body["completion_tokens"] > 0
    assert body["latency_ms"] >= 0


def test_history_lists_the_run(client, auth):
    created = client.post("/api/runs", json=VALID, headers=auth).json()
    listing = client.get("/api/runs", headers=auth)
    assert listing.status_code == 200
    ids = [r["id"] for r in listing.json()]
    assert created["id"] in ids


def test_single_run_is_retrievable(client, auth):
    created = client.post("/api/runs", json=VALID, headers=auth).json()
    r = client.get(f"/api/runs/{created['id']}", headers=auth)
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_another_users_run_is_invisible(client, auth):
    # Register a second user and try to read the first user's run.
    other = client.post(
        "/api/auth/register",
        json={"email": "other@mailcatch.dev", "display_name": "Other", "password": "longenough123"},
    ).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    created = client.post("/api/runs", json=VALID, headers=auth).json()
    r = client.get(f"/api/runs/{created['id']}", headers=other_headers)
    # 404, not 403 — we don't confirm the id exists.
    assert r.status_code == 404


def test_delete_run_returns_204_and_removes_it(client, auth):
    created = client.post("/api/runs", json=VALID, headers=auth).json()
    d = client.delete(f"/api/runs/{created['id']}", headers=auth)
    assert d.status_code == 204
    assert client.get(f"/api/runs/{created['id']}", headers=auth).status_code == 404


def test_history_pagination_limits_results(client, auth):
    for _ in range(3):
        client.post("/api/runs", json=VALID, headers=auth)
    r = client.get("/api/runs?limit=2", headers=auth)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_history_rejects_absurd_limit(client, auth):
    assert client.get("/api/runs?limit=1000", headers=auth).status_code == 422


def test_stats_summarise_the_users_runs(client, auth):
    client.post("/api/runs", json=VALID, headers=auth)
    r = client.get("/api/runs/stats/summary", headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["total_runs"] >= 1
    assert "inspector" in body["runs_by_backend"]
    assert body["top_model"] is not None


def test_streaming_emits_start_delta_and_done(client, auth):
    with client.stream("POST", "/api/runs/stream", json=VALID, headers=auth) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        text = "".join(resp.iter_text())

    assert '"type": "start"' in text
    assert '"type": "delta"' in text
    assert '"type": "done"' in text
    assert "PROMPT INSPECTION" in text


def test_compare_runs_two_models(client, auth):
    r = client.post(
        "/api/runs/compare?model_ids=llama-3.1-8b-instruct&model_ids=mistral-7b-instruct",
        json=VALID,
        headers=auth,
    )
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    assert body[0]["model_id"] == "llama-3.1-8b-instruct"
    assert body[1]["model_id"] == "mistral-7b-instruct"


def test_compare_needs_at_least_two_models(client, auth):
    r = client.post("/api/runs/compare?model_ids=llama-3.1-8b-instruct", json=VALID, headers=auth)
    assert r.status_code == 422
