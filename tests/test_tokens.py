"""Token estimation and budget maths."""

from __future__ import annotations

from app.services.tokens import estimate_cost, estimate_tokens, token_budget


def test_empty_string_is_zero_tokens():
    assert estimate_tokens("") == 0


def test_short_text_returns_at_least_one():
    # A single character is still a token; returning 0 would break the UI's maths.
    assert estimate_tokens("a") >= 1


def test_english_scales_roughly_four_chars_per_token():
    text = "The quick brown fox jumps over the lazy dog. " * 20
    count = estimate_tokens(text)
    # 4 chars/token is the heuristic; allow a wide band because it *is* a heuristic.
    assert 0.6 * (len(text) / 4) < count < 1.8 * (len(text) / 4)


def test_longer_text_costs_more_than_shorter():
    short = estimate_tokens("Summarise this.")
    long = estimate_tokens("Summarise this. " * 50)
    assert long > short


def test_cjk_counts_roughly_one_per_character():
    # Ten ideographs should land near ten tokens, not near 2.5.
    count = estimate_tokens("人工智能模型测试学习")
    assert 8 <= count <= 14


def test_budget_sums_prompt_and_completion():
    b = token_budget("You are terse.", "Explain WAL mode.", 512, 8192)
    assert b["prompt_tokens"] == b["system_tokens"] + b["user_tokens"]
    assert b["total_needed"] == b["prompt_tokens"] + 512
    assert b["fits"] is True


def test_budget_reports_overflow_when_max_tokens_too_large():
    b = token_budget("", "hi", 9000, 8192)
    assert b["fits"] is False
    assert b["headroom"] < 0


def test_budget_utilization_is_a_percentage():
    b = token_budget("", "a" * 400, 100, 1000)
    assert 0 <= b["utilization_pct"] <= 100


def test_cost_is_proportional_to_tokens():
    cheap = estimate_cost(1000, 1000, 0.15, 0.60)
    pricey = estimate_cost(1_000_000, 1_000_000, 0.15, 0.60)
    assert pricey > cheap
    assert pricey == estimate_cost(1_000_000, 1_000_000, 0.15, 0.60)


def test_zero_tokens_costs_nothing():
    assert estimate_cost(0, 0, 5.0, 15.0) == 0.0
