"""The dry-run prompt inspector.

This is the backend that answers when you have no model wired up — and it is
NOT a fake LLM. It never pretends to be one. What it does instead is genuinely
useful: it reads your prompt the way a careful engineer would and reports
structural problems that predict bad output.

Every finding is a real, checkable property of the text you submitted. There is
no randomness and no invented "model reply". The UI labels this backend
"inspector (no model)" so nobody mistakes the output for generated text.
"""

import re
from dataclasses import dataclass

from .catalog import ModelSpec
from .tokens import token_budget


@dataclass(frozen=True)
class Finding:
    severity: str  # "warn" | "info" | "good"
    title: str
    detail: str


_OUTPUT_HINTS = (
    "return",
    "output",
    "respond with",
    "format",
    "json",
    "markdown",
    "bullet",
    "table",
    "list",
    "write",
    "summar",
    "explain",
    "code",
    "sql",
    "csv",
)

_EXAMPLE_HINTS = ("for example", "e.g.", "example:", "such as", "input:", "output:")

_VAGUE_WORDS = (
    "good",
    "nice",
    "better",
    "appropriate",
    "suitable",
    "some",
    "several",
    "various",
    "etc",
    "properly",
    "reasonable",
)

_HEDGES = ("maybe", "perhaps", "if possible", "try to", "kind of", "sort of")

_MULTI_TASK_RE = re.compile(
    r"\b(and also|also|then|after that|additionally|finally|moreover)\b", re.IGNORECASE
)


def _has(text: str, needles: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(n in low for n in needles)


def analyse(
    model: ModelSpec,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> list[Finding]:
    """Return every structural finding for this prompt. Deterministic by design."""
    findings: list[Finding] = []
    combined = f"{system_prompt}\n{user_prompt}"
    budget = token_budget(system_prompt, user_prompt, max_tokens, model.context_window)

    # --- context window ----------------------------------------------------
    if not budget["fits"]:
        findings.append(
            Finding(
                "warn",
                "Request exceeds the context window",
                f"You need {budget['total_needed']} tokens (est.) but {model.label} "
                f"only accepts {model.context_window}. Shorten the prompt or drop "
                f"max_tokens to about {max(1, model.context_window - budget['prompt_tokens'])}.",
            )
        )
    elif budget["utilization_pct"] > 85:
        findings.append(
            Finding(
                "warn",
                "Very little context headroom",
                f"You're at {budget['utilization_pct']}% of the window. Long model "
                f"replies may get cut off mid-sentence.",
            )
        )
    else:
        findings.append(
            Finding(
                "good",
                "Fits comfortably",
                f"{budget['utilization_pct']}% of the {model.context_window:,}-token "
                f"window used, {budget['headroom']:,} tokens spare.",
            )
        )

    # --- system prompt -----------------------------------------------------
    if not system_prompt.strip():
        findings.append(
            Finding(
                "warn",
                "No system prompt",
                "The model will fall back to its own default persona. That's fine for "
                "experiments, but for anything repeatable, pin the role and the "
                "constraints here instead of in the user turn.",
            )
        )
    elif len(system_prompt.split()) > 400:
        findings.append(
            Finding(
                "info",
                "Long system prompt",
                f"{len(system_prompt.split())} words of instructions. Models tend to "
                f"follow the last instruction they read most closely — important rules "
                f"belong at the end, not buried at the top.",
            )
        )

    # --- output shape ------------------------------------------------------
    if not _has(user_prompt, _OUTPUT_HINTS):
        findings.append(
            Finding(
                "warn",
                "Output format is unspecified",
                "Nothing in the prompt says what shape the answer should take. You'll "
                "get a different structure each run. Add one line like 'Answer in three "
                "bullet points' or 'Return JSON with keys title and summary'.",
            )
        )

    # --- examples ----------------------------------------------------------
    if len(user_prompt.split()) > 40 and not _has(combined, _EXAMPLE_HINTS):
        findings.append(
            Finding(
                "info",
                "No examples given",
                "For anything longer than a sentence or two, one worked example "
                "usually beats three paragraphs of description.",
            )
        )

    # --- precision ---------------------------------------------------------
    vague = [w for w in _VAGUE_WORDS if re.search(rf"\b{re.escape(w)}\b", combined, re.I)]
    if vague:
        shown = ", ".join(f"'{w}'" for w in vague[:4])
        findings.append(
            Finding(
                "warn",
                "Undefined quality words",
                f"Found {shown}. Words like these mean something different to every "
                f"reader. Replace them with a measurable criterion.",
            )
        )

    hedges = [h for h in _HEDGES if h in combined.lower()]
    if hedges:
        findings.append(
            Finding(
                "info",
                "Hedged instructions",
                f"Found {', '.join(repr(h) for h in hedges[:3])}. Hedges let the model "
                f"skip the work. State the requirement directly.",
            )
        )

    # --- task count --------------------------------------------------------
    joins = _MULTI_TASK_RE.findall(user_prompt)
    if len(joins) >= 2:
        findings.append(
            Finding(
                "warn",
                "Several tasks chained together",
                f"Found {len(joins)} sequential connectives. Models frequently complete "
                f"the first task and quietly drop the rest. Split this into separate "
                f"turns and check each one.",
            )
        )

    # --- sampling ----------------------------------------------------------
    if temperature >= 1.2 and _has(combined, ("json", "sql", "code", "exact", "verbatim")):
        findings.append(
            Finding(
                "warn",
                "High temperature on a precision task",
                f"temperature={temperature} with a request for exact/coded output. "
                f"Below 0.3 is the usual range for anything that must parse.",
            )
        )
    elif temperature <= 0.1:
        findings.append(
            Finding(
                "info",
                "Near-greedy sampling",
                f"temperature={temperature} makes runs almost identical. Good for tests, "
                f"bad for brainstorming — you'll see the same idea every time.",
            )
        )

    if top_p < 0.5:
        findings.append(
            Finding(
                "info",
                "Narrow nucleus sampling",
                f"top_p={top_p} discards most of the distribution. Combined with a low "
                f"temperature this can make output repetitive.",
            )
        )

    # --- model fit ---------------------------------------------------------
    if model.family == "Gemma" and system_prompt.strip():
        findings.append(
            Finding(
                "info",
                "Gemma has no system role",
                "Your system prompt gets prepended to the first user turn, so it competes "
                "for attention with the actual question. Keep it short on Gemma.",
            )
        )

    if model.family == "DeepSeek":
        findings.append(
            Finding(
                "info",
                "Reasoning model: expect long output",
                "R1 distills emit a long chain of thought before the answer. Give it "
                "max_tokens of at least 1024 or the final answer gets truncated.",
            )
        )

    return findings


def render_report(
    model: ModelSpec,
    findings: list[Finding],
    budget: dict,
    rendered_prompt: str,
) -> str:
    """Turn findings into the text the playground shows in the output pane."""
    warns = [f for f in findings if f.severity == "warn"]
    good = [f for f in findings if f.severity == "good"]

    lines = [
        f"PROMPT INSPECTION — {model.label}",
        "No model was called. This is a structural read of the prompt you submitted.",
        "",
        f"Estimated tokens   {budget['prompt_tokens']:,} in / "
        f"{budget['reserved_for_completion']:,} reserved",
        f"Context window     {budget['context_window']:,} " f"({budget['utilization_pct']}% used)",
        f"Findings           {len(warns)} to fix, {len(good)} good",
        "",
    ]

    if warns:
        lines.append("TO FIX")
        for i, f in enumerate(warns, 1):
            lines.append(f"  {i}. {f.title}")
            lines.append(f"     {f.detail}")
        lines.append("")

    others = [f for f in findings if f.severity != "warn"]
    if others:
        lines.append("WORTH KNOWING")
        for f in others:
            mark = "ok" if f.severity == "good" else "--"
            lines.append(f"  [{mark}] {f.title}: {f.detail}")
        lines.append("")

    lines.append("RENDERED PROMPT")
    lines.append("Exactly what a server using this template would receive:")
    lines.append("")
    lines.append(rendered_prompt)
    lines.append("")
    lines.append(
        "Point OLLAMA_BASE_URL at a running Ollama, or set CLOUD_API_KEY for any "
        "OpenAI-compatible endpoint, and this pane shows real model output instead."
    )
    return "\n".join(lines)
