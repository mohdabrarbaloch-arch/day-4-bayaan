"""The prompt inspector — deterministic analysis, no randomness."""

from __future__ import annotations

from app.services import inspector
from app.services.catalog import get_model

LLAMA = get_model("llama-3.1-8b-instruct")


def _titles(findings):
    return [f.title for f in findings]


def test_missing_system_prompt_is_flagged():
    findings = inspector.analyse(LLAMA, "", "Write a haiku.", 0.7, 0.95, 256)
    assert "No system prompt" in _titles(findings)


def test_unspecified_output_format_is_flagged():
    findings = inspector.analyse(LLAMA, "You help.", "Tell me about databases.", 0.7, 0.95, 256)
    assert "Output format is unspecified" in _titles(findings)


def test_specified_output_format_is_not_flagged():
    findings = inspector.analyse(
        LLAMA, "You help.", "Return JSON with keys title and summary.", 0.7, 0.95, 256
    )
    assert "Output format is unspecified" not in _titles(findings)


def test_vague_quality_words_are_caught():
    findings = inspector.analyse(
        LLAMA, "You help.", "Write a good summary that is appropriate.", 0.7, 0.95, 256
    )
    assert "Undefined quality words" in _titles(findings)


def test_high_temperature_on_json_is_flagged():
    findings = inspector.analyse(LLAMA, "You help.", "Return JSON only.", 1.5, 0.95, 256)
    assert "High temperature on a precision task" in _titles(findings)


def test_low_temperature_is_noted_not_warned():
    findings = inspector.analyse(LLAMA, "S", "Return JSON.", 0.0, 0.95, 256)
    near_greedy = [f for f in findings if f.title == "Near-greedy sampling"]
    assert near_greedy and near_greedy[0].severity == "info"


def test_context_overflow_is_warned():
    gemma = get_model("gemma-2-9b-it")
    findings = inspector.analyse(gemma, "", "hello " * 3000, 0.7, 0.95, 4000)
    assert "Request exceeds the context window" in _titles(findings)


def test_chained_tasks_are_caught():
    prompt = "Summarise this, then translate it and also format it as a table."
    findings = inspector.analyse(LLAMA, "S", prompt, 0.7, 0.95, 256)
    assert "Several tasks chained together" in _titles(findings)


def test_analysis_is_deterministic():
    a = inspector.analyse(LLAMA, "sys", "user prompt", 0.7, 0.95, 256)
    b = inspector.analyse(LLAMA, "sys", "user prompt", 0.7, 0.95, 256)
    assert [(f.severity, f.title, f.detail) for f in a] == [
        (f.severity, f.title, f.detail) for f in b
    ]


def test_report_never_claims_to_be_a_model_reply():
    findings = inspector.analyse(LLAMA, "s", "u", 0.7, 0.95, 256)
    budget = {
        "prompt_tokens": 10,
        "reserved_for_completion": 256,
        "context_window": 131072,
        "utilization_pct": 1.0,
        "headroom": 130000,
    }
    report = inspector.render_report(LLAMA, findings, budget, "<rendered>")
    assert "No model was called" in report
    assert "PROMPT INSPECTION" in report
    assert "<rendered>" in report


def test_deepseek_gets_a_reasoning_note():
    ds = get_model("deepseek-r1-distill-32b")
    findings = inspector.analyse(ds, "s", "Solve this step by step.", 0.6, 0.95, 256)
    assert "Reasoning model: expect long output" in _titles(findings)


def test_gemma_system_prompt_note_only_when_system_given():
    gemma = get_model("gemma-2-9b-it")
    with_sys = inspector.analyse(gemma, "You are a poet.", "Hi", 0.9, 0.95, 128)
    without = inspector.analyse(gemma, "", "Hi", 0.9, 0.95, 128)
    assert "Gemma has no system role" in _titles(with_sys)
    assert "Gemma has no system role" not in _titles(without)
