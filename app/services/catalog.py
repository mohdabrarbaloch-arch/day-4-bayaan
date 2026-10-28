"""The model registry.

These are real open-weight models with real metadata — parameter counts, context
windows and licence names are the published figures, not placeholders. If you add
a model, add its true context window; a wrong number here makes the budget meter
lie, which is worse than not having one.
"""

from dataclasses import dataclass, field


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
    template: str
    stop_sequences: tuple[str, ...] = field(default_factory=tuple)
    # Rough per-1M-token prices for hosted inference. Local runs cost 0.
    price_in: float = 0.0
    price_out: float = 0.0


CATALOG: tuple[ModelSpec, ...] = (
    ModelSpec(
        id="llama-3.3-70b-instruct",
        label="Llama 3.3 70B Instruct",
        family="Llama",
        params="70B",
        context_window=131072,
        license="Llama 3.3 Community License",
        notes=(
            "Meta's 70B, tuned to behave like the larger 405B. The strongest general "
            "open model most people can actually host. Needs ~40GB at 4-bit."
        ),
        ollama_tag="llama3.3:70b",
        template="llama3",
        stop_sequences=("<|eot_id|>", "<|end_of_text|>"),
        price_in=0.59,
        price_out=0.79,
    ),
    ModelSpec(
        id="llama-3.1-8b-instruct",
        label="Llama 3.1 8B Instruct",
        family="Llama",
        params="8B",
        context_window=131072,
        license="Llama 3.1 Community License",
        notes=(
            "The default workhorse. Runs on a single 8GB GPU at 4-bit and handles "
            "most drafting, extraction and classification work."
        ),
        ollama_tag="llama3.1:8b",
        template="llama3",
        stop_sequences=("<|eot_id|>", "<|end_of_text|>"),
        price_in=0.05,
        price_out=0.08,
    ),
    ModelSpec(
        id="mistral-7b-instruct",
        label="Mistral 7B Instruct v0.3",
        family="Mistral",
        params="7B",
        context_window=32768,
        license="Apache 2.0",
        notes=(
            "Apache 2.0, so no licence negotiation. Fast, terse, good at instruction "
            "following. The safest choice for commercial use."
        ),
        ollama_tag="mistral:7b",
        template="mistral",
        stop_sequences=("</s>",),
        price_in=0.03,
        price_out=0.06,
    ),
    ModelSpec(
        id="mixtral-8x7b-instruct",
        label="Mixtral 8x7B Instruct",
        family="Mistral",
        params="8x7B (MoE)",
        context_window=32768,
        license="Apache 2.0",
        notes=(
            "Mixture-of-experts: 47B total parameters but only ~13B active per token, "
            "so it runs near 13B speed. Strong multilingual."
        ),
        ollama_tag="mixtral:8x7b",
        template="mistral",
        stop_sequences=("</s>",),
        price_in=0.24,
        price_out=0.24,
    ),
    ModelSpec(
        id="qwen2.5-72b-instruct",
        label="Qwen 2.5 72B Instruct",
        family="Qwen",
        params="72B",
        context_window=131072,
        license="Qwen License",
        notes=(
            "Alibaba's flagship. Notably strong on maths and code, and the best of "
            "this set for non-English work."
        ),
        ollama_tag="qwen2.5:72b",
        template="chatml",
        stop_sequences=("<|im_end|>",),
        price_in=0.35,
        price_out=0.40,
    ),
    ModelSpec(
        id="qwen2.5-7b-instruct",
        label="Qwen 2.5 7B Instruct",
        family="Qwen",
        params="7B",
        context_window=131072,
        license="Qwen License",
        notes=(
            "The small Qwen. Punches above its weight on structured output and "
            "multilingual tasks; fits in 6GB at 4-bit."
        ),
        ollama_tag="qwen2.5:7b",
        template="chatml",
        stop_sequences=("<|im_end|>",),
        price_in=0.05,
        price_out=0.10,
    ),
    ModelSpec(
        id="gemma-2-9b-it",
        label="Gemma 2 9B IT",
        family="Gemma",
        params="9B",
        context_window=8192,
        license="Gemma Terms of Use",
        notes=(
            "Google's open release. Small context window (8k) — watch the budget "
            "meter, it fills faster than you expect."
        ),
        ollama_tag="gemma2:9b",
        template="gemma",
        stop_sequences=("<end_of_turn>",),
        price_in=0.03,
        price_out=0.06,
    ),
    ModelSpec(
        id="phi-3.5-mini-instruct",
        label="Phi-3.5 Mini Instruct",
        family="Phi",
        params="3.8B",
        context_window=131072,
        license="MIT",
        notes=(
            "MIT licensed and tiny. Trained heavily on synthetic textbook data, so it "
            "reasons well for its size but knows less trivia."
        ),
        ollama_tag="phi3.5:mini",
        template="chatml",
        stop_sequences=("<|end|>",),
        price_in=0.01,
        price_out=0.02,
    ),
    ModelSpec(
        id="deepseek-v2-lite",
        label="DeepSeek V2 Lite Chat",
        family="DeepSeek",
        params="16B (MoE)",
        context_window=65536,
        license="DeepSeek License",
        notes=(
            "16B total, 2.4B active. Extremely cheap to run for its quality — the "
            "value pick if you're paying per token."
        ),
        ollama_tag="deepseek-v2:16b",
        template="deepseek",
        stop_sequences=("<|EOT|>",),
        price_in=0.14,
        price_out=0.28,
    ),
    ModelSpec(
        id="command-r",
        label="Command R",
        family="Cohere",
        params="35B",
        context_window=131072,
        license="CC-BY-NC 4.0",
        notes=(
            "Built for RAG: trained to cite sources and handle long retrieved "
            "context. Non-commercial licence — check before shipping."
        ),
        ollama_tag="command-r:35b",
        template="command",
        stop_sequences=("<|END_OF_TURN_TOKEN|>",),
        price_in=0.15,
        price_out=0.60,
    ),
)

BY_ID: dict[str, ModelSpec] = {m.id: m for m in CATALOG}


def get(model_id: str) -> ModelSpec | None:
    return BY_ID.get(model_id)


def all_models() -> tuple[ModelSpec, ...]:
    return CATALOG


def default_model() -> ModelSpec:
    return BY_ID["llama-3.1-8b-instruct"]
