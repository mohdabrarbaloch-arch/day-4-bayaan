"""Token estimation.

IMPORTANT — this is an ESTIMATE, not a tokenizer. Real counts come from the
model's own tokenizer (tiktoken for OpenAI-compatible endpoints, sentencepiece
for Llama/Mistral). We don't ship those vocabularies, so we approximate and say
so. Everywhere this number surfaces in the UI it is labelled "est.".

The heuristic: split on word boundaries and punctuation, charge ~4 characters
per token for alphanumeric runs (close to the BPE average for English), 1 token
per CJK character (CJK is roughly 1:1), and a fraction of a token for isolated
punctuation, which BPE usually merges into a neighbouring token.
"""

import re

_WORD_RE = re.compile(r"\w+|[^\w\s]")

_CJK_RANGES = (
    (0x4E00, 0x9FFF),  # CJK Unified Ideographs
    (0x3040, 0x30FF),  # Hiragana + Katakana
    (0xAC00, 0xD7AF),  # Hangul
)


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def estimate_tokens(text: str) -> int:
    """Approximate the BPE token count of `text`."""
    if not text:
        return 0

    total = 0.0
    for chunk in _WORD_RE.findall(text):
        if chunk.isalnum():
            if any(_is_cjk(ch) for ch in chunk):
                cjk = sum(1 for ch in chunk if _is_cjk(ch))
                other = len(chunk) - cjk
                total += cjk + max(1.0, other / 4.0)
            else:
                total += max(1.0, len(chunk) / 4.0)
        else:
            total += 0.5

    total += len(re.findall(r"\s+", text)) / 6.0
    return max(1, round(total))


def token_budget(
    system_prompt: str, user_prompt: str, max_tokens: int, context_window: int
) -> dict:
    """Break the request down against the model's context window."""
    system_tokens = estimate_tokens(system_prompt)
    user_tokens = estimate_tokens(user_prompt)
    prompt_tokens = system_tokens + user_tokens
    total = prompt_tokens + max_tokens

    return {
        "system_tokens": system_tokens,
        "user_tokens": user_tokens,
        "prompt_tokens": prompt_tokens,
        "reserved_for_completion": max_tokens,
        "context_window": context_window,
        "total_needed": total,
        "fits": total <= context_window,
        "headroom": context_window - total,
        "utilization_pct": round(100 * total / context_window, 1) if context_window else 0.0,
    }


def estimate_cost(
    prompt_tokens: int, completion_tokens: int, in_per_mtok: float, out_per_mtok: float
) -> float:
    """Cost in USD for the given token counts at the supplied per-1M rates."""
    cost = (prompt_tokens / 1_000_000) * in_per_mtok + (
        completion_tokens / 1_000_000
    ) * out_per_mtok
    return round(cost, 8)
