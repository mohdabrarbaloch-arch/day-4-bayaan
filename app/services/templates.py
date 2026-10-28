"""Chat template rendering.

Every open model expects a different wrapping. Getting it wrong doesn't raise —
the model just answers worse, and you spend the evening blaming the quantisation.
So the templates live here, in one place, and the UI can show you the exact
string before you send it.
"""

from dataclasses import dataclass

from .catalog import ModelSpec


@dataclass(frozen=True)
class Rendered:
    text: str
    template_name: str
    note: str
    stop_sequences: list[str]


def _llama3(system: str, user: str) -> str:
    # Llama 3.x uses header blocks. The system block is optional in the spec but
    # most servers expect it present, so we always emit it.
    return (
        "<|begin_of_text|>"
        "<|start_header_id|>system<|end_header_id|>\n\n"
        f"{system}<|eot_id|>"
        "<|start_header_id|>user<|end_header_id|>\n\n"
        f"{user}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def _mistral(system: str, user: str) -> str:
    # Mistral folds the system prompt into the first user turn — there is no
    # separate system role in the v0.3 template.
    merged = f"{system}\n\n{user}" if system else user
    return f"<s>[INST] {merged} [/INST]"


def _chatml(system: str, user: str) -> str:
    parts = []
    if system:
        parts.append(f"<|im_start|>system\n{system}<|im_end|>\n")
    parts.append(f"<|im_start|>user\n{user}<|im_end|>\n")
    parts.append("<|im_start|>assistant\n")
    return "".join(parts)


def _gemma(system: str, user: str) -> str:
    # Gemma 2 has no system role; the instruction is prepended to the user turn.
    merged = f"{system}\n\n{user}" if system else user
    return f"<start_of_turn>user\n{merged}<end_of_turn>\n<start_of_turn>model\n"


def _deepseek(system: str, user: str) -> str:
    parts = []
    if system:
        parts.append(f"{system}\n\n")
    parts.append(f"User: {user}\n\nAssistant: ")
    return "".join(parts)


def _command(system: str, user: str) -> str:
    return (
        "<|START_OF_TURN_TOKEN|><|SYSTEM_TOKEN|>"
        f"{system}<|END_OF_TURN_TOKEN|>"
        "<|START_OF_TURN_TOKEN|><|USER_TOKEN|>"
        f"{user}<|END_OF_TURN_TOKEN|>"
        "<|START_OF_TURN_TOKEN|><|CHATBOT_TOKEN|>"
    )


_RENDERERS = {
    "llama3": (_llama3, "Llama 3.x", "Header blocks terminated by <|eot_id|>."),
    "mistral": (_mistral, "Mistral [INST]", "System prompt is folded into the user turn."),
    "chatml": (_chatml, "ChatML", "Qwen / Phi style <|im_start|> blocks."),
    "gemma": (_gemma, "Gemma turns", "No system role — instruction is prepended."),
    "deepseek": (_deepseek, "DeepSeek plain", "Plain User/Assistant turns."),
    "command": (_command, "Command R", "Cohere's token-block format."),
}


def render(model: ModelSpec, system_prompt: str, user_prompt: str) -> Rendered:
    """Render a prompt through the model's template."""
    renderer, name, note = _RENDERERS.get(model.template, _RENDERERS["chatml"])
    return Rendered(
        text=renderer(system_prompt.strip(), user_prompt.strip()),
        template_name=name,
        note=note,
        stop_sequences=list(model.stop_sequences),
    )


def template_for(model: ModelSpec) -> Rendered:
    """The template with placeholder text, for the inspector dialog."""
    return render(
        model,
        "{system_prompt}",
        "{user_prompt}",
    )
