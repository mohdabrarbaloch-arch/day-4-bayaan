"""Chat template rendering — the thing that silently breaks self-hosted models."""

from __future__ import annotations

import pytest

from app.services import templates


def test_llama3_wraps_both_turns_and_opens_assistant():
    out = templates.render("llama3", "You are terse.", "Hello")
    assert out.startswith("<|begin_of_text|>")
    assert "<|start_header_id|>system<|end_header_id|>" in out
    assert "<|start_header_id|>user<|end_header_id|>" in out
    # The generation prompt must end on the assistant header, or the model
    # continues the user turn instead of replying.
    assert out.endswith("<|start_header_id|>assistant<|end_header_id|>\n\n")
    assert "You are terse." in out


def test_mistral_puts_system_inside_first_inst_block():
    out = templates.render("mistral", "Be brief.", "What is WAL?")
    assert out.startswith("<s>[INST] ")
    assert out.endswith(" [/INST]")
    assert "Be brief.\n\nWhat is WAL?" in out


def test_mistral_without_system_has_no_leading_blank_line():
    out = templates.render("mistral", "   ", "Just the question")
    assert out == "<s>[INST] Just the question [/INST]"


def test_chatml_uses_im_markers():
    out = templates.render("chatml", "sys", "usr")
    assert "<|im_start|>system\nsys<|im_end|>" in out
    assert "<|im_start|>user\nusr<|im_end|>" in out
    assert out.endswith("<|im_start|>assistant\n")


def test_gemma_has_no_system_role():
    out = templates.render("gemma", "You are a poet.", "Say hi")
    assert "system" not in out.lower()
    # System text is folded into the user turn, which is the documented behaviour.
    assert out.startswith("<start_of_turn>user")
    assert "You are a poet." in out


def test_phi_uses_pipe_markers():
    out = templates.render("phi", "sys", "usr")
    assert "<|system|>" in out and "<|user|>" in out and "<|assistant|>" in out
    assert out.endswith("<|assistant|>\n")


def test_empty_system_falls_back_to_default_persona():
    # Llama/ChatML/Phi need *something* in the system slot.
    out = templates.render("chatml", "", "hi")
    assert "You are a helpful assistant." in out


def test_unknown_template_falls_back_to_chatml():
    out = templates.render("some-future-template", "s", "u")
    assert "<|im_start|>" in out


@pytest.mark.parametrize("name", templates.TEMPLATES)
def test_every_template_preserves_the_user_prompt(name):
    out = templates.render(name, "sys", "UNIQUE_MARKER_12345")
    assert "UNIQUE_MARKER_12345" in out


@pytest.mark.parametrize("name", templates.TEMPLATES)
def test_every_template_declares_stop_sequences(name):
    stops = templates.stops_for(name)
    assert stops and all(isinstance(s, str) and s for s in stops)
