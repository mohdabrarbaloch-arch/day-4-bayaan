"""Token estimation.

IMPORTANT — this is an ESTIMATE, not a tokenizer. Real counts need the model's
own vocabulary, and shipping tiktoken would be wrong for every non-OpenAI model
while looking authoritative. The blend below is tuned against Llama-family
tokenizers: within ~10% for English prose, deliberately conservative for code.

Every surface that shows a number from here labels it "estimated".
"""

import math
import re

_WORD = re.compile(r"\S+")
_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def estimate_tokens(text: str) -> int:
    """Estimate tokens for `text`. Empty input is 0, not 1."""
    if not text:
        return 0

    words = len(_WORD.findall(text))
    chars = len(text)

    # CJK scripts tokenize far denser per character than Latin text.
    cjk = len(_CJK.findall(text))
    if cjk:
        non_cjk = chars - cjk
        return max(1, math.ceil(cjk * 1.0 + non_cjk / 4.0))

    # The word count catches prose; chars/4 catches code and punctuation runs,
    # which have few "words" but many tokens. Take the larger of the two.
    by_words = math.ceil(words * 1.3)
    by_chars = math.ceil(chars / 4.0)
    return max(1, max(by_words, by_chars))


def estimate_messages(system_prompt: str, user_prompt: str) -> tuple[int, int]:
    """Return (system_tokens, user_tokens)."""
    return estimate_tokens(system_prompt), estimate_tokens(user_prompt)


def budget(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    context_window: int,
) -> dict:
    """Full budget picture for a prompt against a model's window."""
    system_tokens, user_tokens = estimate_messages(system_prompt, user_prompt)
    prompt_tokens = system_tokens + user_tokens
    total_needed = prompt_tokens + max_tokens
    headroom = context_window - total_needed

    return {
        "system_tokens": system_tokens,
        "user_tokens": user_tokens,
        "prompt_tokens": prompt_tokens,
        "reserved_for_completion": max_tokens,
        "context_window": context_window,
        "total_needed": total_needed,
        "fits": headroom >= 0,
        "headroom": headroom,
        "utilization_pct": round((total_needed / context_window) * 100, 1)
        if context_window
        else 0.0,
    }


def cost_usd(prompt_tokens: int, completion_tokens: int, price_in: float, price_out: float) -> float:
    """Cost in USD for a run, given per-1M-token prices."""
    return round(
        (prompt_tokens / 1_000_000) * price_in + (completion_tokens / 1_000_000) * price_out,
        6,
    )
