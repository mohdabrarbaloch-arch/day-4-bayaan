"""The model catalog, plus prompt-template preview and token budgeting."""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from ..config import settings
from ..schemas import ModelOut
from ..services import templates
from ..services.catalog import MODELS, get_model
from ..services.tokens import token_budget

router = APIRouter(prefix="/api/models", tags=["models"])


class PreviewRequest(BaseModel):
    system_prompt: str = Field(default="", max_length=8000)
    user_prompt: str = Field(default="", max_length=20000)


class BudgetRequest(BaseModel):
    model_id: str
    system_prompt: str = Field(default="", max_length=8000)
    user_prompt: str = Field(default="", max_length=20000)
    max_tokens: int = Field(default=512, ge=1, le=4096)


def _available_backends() -> list[str]:
    backends: list[str] = []
    if settings.ollama_enabled:
        backends.append("local")
    if settings.cloud_enabled:
        backends.append("cloud")
    return backends or ["local"]


@router.get("", response_model=list[ModelOut])
def list_models() -> list[ModelOut]:
    avail = _available_backends()
    return [
        ModelOut(
            id=m.id,
            label=m.label,
            family=m.family,
            params=m.params,
            context_window=m.context_window,
            license=m.license,
            notes=m.notes,
            available_backends=avail,  # type: ignore[arg-type]
            resolved_backend=avail[0],  # type: ignore[arg-type]
        )
        for m in MODELS
    ]


@router.get("/capabilities")
def capabilities() -> dict:
    """What this deployment can actually do right now — no guessing in the UI."""
    return {
        "models": len(MODELS),
        "local_configured": settings.ollama_enabled,
        "cloud_configured": settings.cloud_enabled,
        "active_backend": (
            "ollama"
            if settings.ollama_enabled
            else ("cloud" if settings.cloud_enabled else "inspector")
        ),
        "note": (
            "A real model is wired up."
            if (settings.ollama_enabled or settings.cloud_enabled)
            else "No model connected — runs use the built-in prompt inspector, which is "
            "real analysis but NOT generated text."
        ),
    }


@router.get("/{model_id}/template")
def model_template(model_id: str) -> dict:
    m = get_model(model_id)
    if m is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No model with id '{model_id}' in the catalog.",
        )
    return {
        "model_id": m.id,
        "template": m.chat_template,
        "template_name": templates.TEMPLATE_LABELS.get(m.chat_template, m.chat_template),
        "note": templates.TEMPLATE_NOTES.get(m.chat_template, ""),
        "stop_sequences": templates.stops_for(m.chat_template),
        "ollama_tag": m.ollama_tag,
    }


@router.post("/preview")
def preview(payload: PreviewRequest, model_id: str = "llama-3.1-8b-instruct") -> dict:
    """Render a prompt through a given model's chat template."""
    m = get_model(model_id)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown model.")
    return {
        "model_id": m.id,
        "template": m.chat_template,
        "rendered": templates.render(m.chat_template, payload.system_prompt, payload.user_prompt),
    }


@router.post("/budget")
def budget(payload: BudgetRequest) -> dict:
    m = get_model(payload.model_id)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown model.")
    result = token_budget(
        payload.system_prompt, payload.user_prompt, payload.max_tokens, m.context_window
    )
    return {"model_id": m.id, "model_label": m.label, **result}
