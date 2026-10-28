"""Pydantic request/response models. Validation lives here, not in the routes."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# --------------------------------------------------------------------------- auth
class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("display_name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("display_name cannot be blank")
        return v


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    display_name: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


# ------------------------------------------------------------------------- models
class ModelOut(BaseModel):
    id: str
    label: str
    family: str
    params: str
    context_window: int
    license: str
    notes: str
    # Which backends can actually serve this model right now.
    available_backends: list[Literal["local", "cloud"]]
    resolved_backend: Literal["local", "cloud"]


# --------------------------------------------------------------------------- runs
class RunRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=80)
    backend: Literal["local", "cloud"] = "local"
    system_prompt: str = Field(default="", max_length=8000)
    user_prompt: str = Field(min_length=1)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, ge=0.0, le=1.0)
    max_tokens: int = Field(default=512, ge=1, le=4096)

    @field_validator("user_prompt")
    @classmethod
    def _prompt_size(cls, v: str) -> str:
        from .config import settings

        if len(v) > settings.max_prompt_chars:
            raise ValueError(f"user_prompt exceeds {settings.max_prompt_chars} characters")
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


# ------------------------------------------------------------------ saved prompts
class PromptCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    system_prompt: str = Field(default="", max_length=8000)
    user_prompt: str = Field(default="")
    notes: str = Field(default="", max_length=2000)


class PromptUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    system_prompt: str | None = Field(default=None, max_length=8000)
    user_prompt: str | None = None
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


# -------------------------------------------------------------------------- stats
class StatsOut(BaseModel):
    total_runs: int
    runs_by_backend: dict[str, int]
    runs_by_model: dict[str, int]
    avg_latency_ms: int
    total_tokens: int
    total_cost_usd: float
    top_model: str | None
