"""Pydantic request/response models. Validation lives here, not in the routes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

Backend = Literal["local", "cloud"]


# ── auth ────────────────────────────────────────────────────────────────────
class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("display_name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("display_name must be at least 2 characters")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── models ──────────────────────────────────────────────────────────────────
class ModelOut(BaseModel):
    id: str
    label: str
    family: str
    params: str
    context_window: int
    license: str
    notes: str
    available_backends: list[str]
    resolved_backend: str


class TemplateOut(BaseModel):
    model_id: str
    template: str
    template_name: str
    note: str
    stop_sequences: list[str]
    ollama_tag: str


class BudgetRequest(BaseModel):
    model_id: str
    system_prompt: str = ""
    user_prompt: str = ""
    max_tokens: int = Field(default=512, ge=1, le=32768)


class BudgetOut(BaseModel):
    model_id: str
    model_label: str
    system_tokens: int
    user_tokens: int
    prompt_tokens: int
    reserved_for_completion: int
    context_window: int
    total_needed: int
    fits: bool
    headroom: int
    utilization_pct: float


class PreviewRequest(BaseModel):
    system_prompt: str = ""
    user_prompt: str = ""


class PreviewOut(BaseModel):
    model_id: str
    template_name: str
    rendered: str
    stop_sequences: list[str]


class CapabilitiesOut(BaseModel):
    models: int
    local_configured: bool
    cloud_configured: bool
    active_backend: str
    note: str


# ── runs ────────────────────────────────────────────────────────────────────
class RunRequest(BaseModel):
    model_id: str
    backend: Backend = "local"
    system_prompt: str = Field(default="", max_length=20000)
    user_prompt: str = Field(min_length=1, max_length=20000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)
    max_tokens: int = Field(default=512, ge=1, le=4096)

    @field_validator("user_prompt")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("user_prompt cannot be blank")
        return v


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model_id: str
    model_label: str
    backend: str
    simulated: bool
    system_prompt: str
    user_prompt: str
    output: str
    temperature: float
    top_p: float
    max_tokens: int
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cost_usd: float
    status: str
    error: str
    created_at: datetime


class RunSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model_id: str
    model_label: str
    backend: str
    simulated: bool
    user_prompt: str
    latency_ms: int
    completion_tokens: int
    status: str
    created_at: datetime


class StatsOut(BaseModel):
    total_runs: int
    runs_by_backend: dict[str, int]
    runs_by_model: dict[str, int]
    avg_latency_ms: int
    total_tokens: int
    total_cost_usd: float
    top_model: str


# ── saved prompts ───────────────────────────────────────────────────────────
class PromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    system_prompt: str = Field(default="", max_length=20000)
    user_prompt: str = Field(default="", max_length=20000)
    notes: str = Field(default="", max_length=2000)

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be blank")
        return v


class PromptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    system_prompt: str | None = Field(default=None, max_length=20000)
    user_prompt: str | None = Field(default=None, max_length=20000)
    notes: str | None = Field(default=None, max_length=2000)


class PromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    system_prompt: str
    user_prompt: str
    notes: str
    created_at: datetime
    updated_at: datetime


class HealthOut(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    backend: str
    simulated: bool
