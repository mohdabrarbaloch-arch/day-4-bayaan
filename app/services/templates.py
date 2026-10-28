"""Chat template rendering.

Every open model expects a different wrapping. Getting this wrong is one of the
most common reasons a self-hosted model "seems dumb" — it's not dumb, it's been
handed a prompt it can't parse. Bayaan renders the template so you can see
exactly what string would be sent.

These follow each family's published template. A server may add its own default
system prompt on top; where that's known it's noted in `template_note`.
"""

TEMPLATES = ("llama3", "mistral", "chatml", "gemma", "phi")

TEMPLATE_LABELS = {
    "llama3": "Llama 3 header format",
    "mistral": "[INST] block",
    "chatml": "ChatML",
    "gemma": "Gemma turn format",
    "phi": "Phi chat format",
}

TEMPLATE_NOTES = {
    "llama3": (
        "Uses <|start_header_id|> / <|end_header_id|> blocks. Llama 3.1+ injects a "
        "default system prompt about being helpful unless you supply your own — so an "
        "empty system prompt does not mean no system prompt."
    ),
    "mistral": (
        "Mistral v0.3 puts the system message inside the first [INST] block, separated "
        "by a blank line. There's no dedicated system role."
    ),
    "chatml": (
        "Qwen and DeepSeek distills use ChatML: <|im_start|>role ... <|im_end|>. "
        "Straightforward, and the easiest template to hand-write."
    ),
    "gemma": (
        "Gemma has no system role at all — the system prompt is prepended to the first "
        "user turn. Long system prompts therefore eat into the user message."
    ),
    "phi": ("Phi-4 uses <|system|>, <|user|>, <|assistant|> markers with <|end|> terminators."),
}


def _system_or_default(system_prompt: str) -> str:
    return system_prompt.strip() if system_prompt.strip() else "You are a helpful assistant."


def render_llama3(system_prompt: str, user_prompt: str) -> str:
    system = _system_or_default(system_prompt)
    return (
        "<|begin_of_text|>"
        "<|start_header_id|>system<|end_header_id|>\n\n"
        f"{system}<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_prompt}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def render_mistral(system_prompt: str, user_prompt: str) -> str:
    system = system_prompt.strip()
    body = f"{system}\n\n{user_prompt}" if system else user_prompt
    return f"<s>[INST] {body} [/INST]"


def render_chatml(system_prompt: str, user_prompt: str) -> str:
    system = _system_or_default(system_prompt)
    return (
        f"<|im_start|>system\n{system}<|im_end|>\n"
        f"<|im_start|>user\n{user_prompt}<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def render_gemma(system_prompt: str, user_prompt: str) -> str:
    system = system_prompt.strip()
    body = f"{system}\n\n{user_prompt}" if system else user_prompt
    return f"<start_of_turn>user\n{body}<end_of_turn>\n<start_of_turn>model\n"


def render_phi(system_prompt: str, user_prompt: str) -> str:
    system = _system_or_default(system_prompt)
    return f"<|system|>\n{system}<|end|>\n" f"<|user|>\n{user_prompt}<|end|>\n" "<|assistant|>\n"


_RENDERERS = {
    "llama3": render_llama3,
    "mistral": render_mistral,
    "chatml": render_chatml,
    "gemma": render_gemma,
    "phi": render_phi,
}


def render(template: str, system_prompt: str, user_prompt: str) -> str:
    """Render `template` with the given prompts. Unknown templates fall back to ChatML."""
    renderer = _RENDERERS.get(template, render_chatml)
    return renderer(system_prompt, user_prompt)


def stops_for(template: str) -> list[str]:
    """Stop sequences that end a turn for this template."""
    return {
        "llama3": ["<|eot_id|>", "<|end_of_text|>"],
        "mistral": ["</s>"],
        "chatml": ["<|im_end|>"],
        "gemma": ["<end_of_turn>"],
        "phi": ["<|end|>"],
    }.get(template, ["<|im_end|>"])
