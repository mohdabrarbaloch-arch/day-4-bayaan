"""The model registry.

These are real open-weight models with real metadata — parameter counts, context
windows and licenses come from each publisher's model card. `ollama_tag` is the
name you would `ollama pull` to run it locally. Nothing here invents a model.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    id: str
    label: str
    family: str
    params: str
    context_window: int
    license: str
    notes: str
    ollama_tag: str
    # Families whose chat template we know how to render.
    chat_template: str
    # Suggested sampling defaults from the model card, where one is documented.
    default_temperature: float = 0.7
    default_top_p: float = 0.95


MODELS: tuple[ModelSpec, ...] = (
    ModelSpec(
        id="llama-3.3-70b-instruct",
        label="Llama 3.3 70B Instruct",
        family="Llama",
        params="70B",
        context_window=131072,
        license="Llama 3.3 Community License",
        notes=(
            "Meta's strongest open instruct model. On most benchmarks it lands close to "
            "the much larger Llama 3.1 405B, which makes it the practical default for a "
            "serious local setup if you have the VRAM."
        ),
        ollama_tag="llama3.3:70b",
        chat_template="llama3",
        default_temperature=0.6,
    ),
    ModelSpec(
        id="llama-3.1-8b-instruct",
        label="Llama 3.1 8B Instruct",
        family="Llama",
        params="8B",
        context_window=131072,
        license="Llama 3.1 Community License",
        notes=(
            "The workhorse. Runs on a single consumer GPU and handles most instruction "
            "following well. This is the model to start with if you're new to self-hosting."
        ),
        ollama_tag="llama3.1:8b",
        chat_template="llama3",
        default_temperature=0.6,
    ),
    ModelSpec(
        id="llama-3.2-3b-instruct",
        label="Llama 3.2 3B Instruct",
        family="Llama",
        params="3B",
        context_window=131072,
        license="Llama 3.2 Community License",
        notes=(
            "Small enough to run on a laptop CPU, though you'll feel it on anything "
            "requiring multi-step reasoning. Good for classification and short rewrites."
        ),
        ollama_tag="llama3.2:3b",
        chat_template="llama3",
    ),
    ModelSpec(
        id="mistral-7b-instruct",
        label="Mistral 7B Instruct v0.3",
        family="Mistral",
        params="7B",
        context_window=32768,
        license="Apache 2.0",
        notes=(
            "Truly permissive licensing — no acceptable-use rider, no monthly active user "
            "cap. If you're shipping commercially and want to avoid license review, this "
            "and Qwen are the two to look at first."
        ),
        ollama_tag="mistral:7b",
        chat_template="mistral",
    ),
    ModelSpec(
        id="mixtral-8x7b-instruct",
        label="Mixtral 8x7B Instruct",
        family="Mistral",
        params="46.7B total / 12.9B active",
        context_window=32768,
        license="Apache 2.0",
        notes=(
            "A mixture-of-experts model: 8 experts, 2 active per token. Costs roughly like "
            "a 13B model to run but reasons closer to a 46B. Needs ~26GB in 4-bit."
        ),
        ollama_tag="mixtral:8x7b",
        chat_template="mistral",
    ),
    ModelSpec(
        id="qwen2.5-72b-instruct",
        label="Qwen2.5 72B Instruct",
        family="Qwen",
        params="72B",
        context_window=131072,
        license="Apache 2.0",
        notes=(
            "Strong multilingual coverage — noticeably better than the Llama family on "
            "Urdu, Arabic and Chinese. Apache 2.0 makes it easy to justify commercially."
        ),
        ollama_tag="qwen2.5:72b",
        chat_template="chatml",
    ),
    ModelSpec(
        id="qwen2.5-coder-32b-instruct",
        label="Qwen2.5 Coder 32B Instruct",
        family="Qwen",
        params="32B",
        context_window=32768,
        license="Apache 2.0",
        notes=(
            "Tuned for code. Comfortably the best open model at this size for filling in "
            "functions and reading unfamiliar codebases, and it fits in 24GB at 4-bit."
        ),
        ollama_tag="qwen2.5-coder:32b",
        chat_template="chatml",
        default_temperature=0.2,
    ),
    ModelSpec(
        id="gemma-2-9b-it",
        label="Gemma 2 9B Instruct",
        family="Gemma",
        params="9B",
        context_window=8192,
        license="Gemma Terms of Use",
        notes=(
            "Google's open release. Punchy for its size, but the 8k context is the "
            "smallest here and the license carries Google's usage restrictions."
        ),
        ollama_tag="gemma2:9b",
        chat_template="gemma",
        default_temperature=1.0,
    ),
    ModelSpec(
        id="phi-4-14b",
        label="Phi-4 14B",
        family="Phi",
        params="14B",
        context_window=16384,
        license="MIT",
        notes=(
            "Microsoft's small model trained heavily on synthetic textbook data. Strong on "
            "math and structured reasoning for its size; weaker on open-ended chat."
        ),
        ollama_tag="phi4:14b",
        chat_template="phi",
        default_temperature=0.3,
    ),
    ModelSpec(
        id="deepseek-r1-distill-32b",
        label="DeepSeek-R1 Distill Qwen 32B",
        family="DeepSeek",
        params="32B",
        context_window=131072,
        license="MIT",
        notes=(
            "A reasoning model distilled into Qwen 32B. Writes long chains of thought "
            "before answering, so it's slow and token-hungry — but it's the best open "
            "option for problems that need actual working out."
        ),
        ollama_tag="deepseek-r1:32b",
        chat_template="chatml",
        default_temperature=0.6,
    ),
)

MODELS_BY_ID: dict[str, ModelSpec] = {m.id: m for m in MODELS}

DEFAULT_MODEL_ID = "llama-3.1-8b-instruct"


def get_model(model_id: str) -> ModelSpec | None:
    return MODELS_BY_ID.get(model_id)


def all_models() -> tuple[ModelSpec, ...]:
    return MODELS
