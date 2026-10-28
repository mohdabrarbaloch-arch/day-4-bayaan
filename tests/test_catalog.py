"""The model catalog and its metadata."""

from __future__ import annotations

import pytest

from app.services.catalog import DEFAULT_MODEL_ID, MODELS, all_models, get_model


def test_catalog_is_not_empty():
    assert len(MODELS) >= 8


def test_every_id_is_unique():
    ids = [m.id for m in MODELS]
    assert len(ids) == len(set(ids))


def test_every_model_has_the_required_metadata():
    for m in MODELS:
        assert m.label and m.family and m.params
        assert m.context_window > 0
        assert m.license, f"{m.id} has no license — that's a legal problem, not a cosmetic one"
        assert m.ollama_tag and ":" in m.ollama_tag
        assert m.chat_template


def test_every_chat_template_is_one_we_can_render():
    from app.services.templates import TEMPLATES

    for m in MODELS:
        assert m.chat_template in TEMPLATES, f"{m.id} uses an unrenderable template"


def test_lookup_by_id():
    assert get_model("llama-3.1-8b-instruct") is not None
    assert get_model("does-not-exist") is None


def test_default_model_exists():
    assert get_model(DEFAULT_MODEL_ID) is not None


def test_all_models_returns_the_same_objects():
    assert all_models() == MODELS


@pytest.mark.parametrize("model_id", [m.id for m in MODELS])
def test_context_windows_are_plausible(model_id):
    # Nothing in this catalog is below 8k; anything smaller would be a typo.
    m = get_model(model_id)
    assert 8_000 <= m.context_window <= 2_000_000


def test_licenses_are_real_sounding_not_placeholders():
    allowed = ("MIT", "Apache", "Llama", "Gemma")
    for m in MODELS:
        assert any(f in m.license for f in allowed), m.license


def test_listing_endpoint_reports_every_model(client):
    r = client.get("/api/models")
    assert r.status_code == 200
    assert len(r.json()) == len(MODELS)
    assert {"id", "label", "context_window", "license"} <= set(r.json()[0])


def test_capabilities_endpoint_is_honest_about_no_model(client):
    r = client.get("/api/models/capabilities")
    assert r.status_code == 200
    body = r.json()
    # No key configured in tests, so it must NOT claim a real model is wired up.
    assert body["active_backend"] == "inspector"
    assert body["cloud_configured"] is False


def test_unknown_model_template_is_404(client):
    assert client.get("/api/models/nope/template").status_code == 404


def test_template_endpoint_returns_stop_sequences(client):
    r = client.get("/api/models/mistral-7b-instruct/template")
    assert r.status_code == 200
    body = r.json()
    assert body["template"] == "mistral"
    assert body["stop_sequences"]


def test_preview_endpoint_renders(client):
    r = client.post(
        "/api/models/preview?model_id=llama-3.1-8b-instruct",
        json={"system_prompt": "Be terse.", "user_prompt": "Hi"},
    )
    assert r.status_code == 200
    assert "<|begin_of_text|>" in r.json()["rendered"]


def test_budget_endpoint_flags_overflow(client):
    # Gemma's window is 8192. 3000 words of "hello" is ~3000 tokens, plus 6000
    # reserved for the completion, which cannot fit.
    r = client.post(
        "/api/models/budget",
        json={
            "model_id": "gemma-2-9b-it",
            "system_prompt": "",
            "user_prompt": "hello " * 3000,
            "max_tokens": 4000,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fits"] is False
    assert body["headroom"] < 0
