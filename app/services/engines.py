"""The three inference backends, behind one interface.

`inspector`  — no network, deterministic prompt analysis (see inspector.py)
`ollama`     — a real request to a model you're running locally
`cloud`      — a real request to any OpenAI-compatible endpoint

Both real backends raise `EngineError` with a message that says what actually
went wrong, because a playground that swallows errors is useless for debugging.
"""

import time
from collections.abc import AsyncIterator
from dataclasses import dataclass

import httpx

from ..config import settings
from . import inspector, templates
from .catalog import ModelSpec
from .tokens import estimate_cost, estimate_tokens, token_budget


class EngineError(RuntimeError):
    """Raised when a backend is unreachable, misconfigured, or rejects the request."""


@dataclass
class EngineResult:
    output: str
    backend: str
    simulated: bool
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    cost_usd: float


def resolve_backend(model: ModelSpec, requested: str) -> str:
    """Turn a requested backend into the one that can actually serve this model."""
    if requested == "cloud":
        return "cloud" if settings.cloud_enabled else "inspector"
    return "ollama" if settings.ollama_enabled else "inspector"


# --------------------------------------------------------------------- inspector
def _run_inspector(
    model: ModelSpec,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> EngineResult:
    started = time.perf_counter()
    budget = token_budget(system_prompt, user_prompt, max_tokens, model.context_window)
    findings = inspector.analyse(model, system_prompt, user_prompt, temperature, top_p, max_tokens)
    rendered = templates.render(model.chat_template, system_prompt, user_prompt)
    output = inspector.render_report(model, findings, budget, rendered)
    elapsed = int((time.perf_counter() - started) * 1000)

    return EngineResult(
        output=output,
        backend="inspector",
        simulated=True,
        prompt_tokens=budget["prompt_tokens"],
        completion_tokens=estimate_tokens(output),
        latency_ms=elapsed,
        cost_usd=0.0,
    )


# ------------------------------------------------------------------------ ollama
async def _run_ollama(
    model: ModelSpec,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> EngineResult:
    base = settings.ollama_base_url.rstrip("/")
    payload = {
        "model": model.ollama_tag,
        "messages": [
            {"role": "system", "content": system_prompt or "You are a helpful assistant."},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
        "options": {
            "temperature": temperature,
            "top_p": top_p,
            "num_predict": max_tokens,
        },
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_seconds) as client:
            resp = await client.post(f"{base}/api/chat", json=payload)
    except httpx.ConnectError as exc:
        raise EngineError(
            f"Could not reach Ollama at {base}. Is it running? Start it with "
            f"`ollama serve` and pull the model with `ollama pull {model.ollama_tag}`."
        ) from exc
    except httpx.TimeoutException as exc:
        raise EngineError(
            f"Ollama did not answer within {settings.ollama_timeout_seconds:.0f}s. "
            f"A {model.params} model needs time on the first load — try again, or "
            f"raise OLLAMA_TIMEOUT_SECONDS."
        ) from exc

    elapsed = int((time.perf_counter() - started) * 1000)

    if resp.status_code == 404:
        raise EngineError(
            f"Ollama is running but doesn't have '{model.ollama_tag}'. "
            f"Run `ollama pull {model.ollama_tag}` first."
        )
    if resp.status_code >= 400:
        raise EngineError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:400]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise EngineError("Ollama returned something that isn't JSON.") from exc

    output = (data.get("message") or {}).get("content", "")
    if not output:
        raise EngineError("Ollama returned an empty message. Check the model's logs.")

    return EngineResult(
        output=output,
        backend="ollama",
        simulated=False,
        prompt_tokens=int(data.get("prompt_eval_count") or estimate_tokens(user_prompt)),
        completion_tokens=int(data.get("eval_count") or estimate_tokens(output)),
        latency_ms=elapsed,
        cost_usd=0.0,  # your own electricity, not a line item
    )


# ------------------------------------------------------------------------- cloud
async def _run_cloud(
    model: ModelSpec,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> EngineResult:
    base = settings.cloud_base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {settings.cloud_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        # The cloud endpoint needs the provider's model name, not our catalog id.
        "model": model.ollama_tag,
        "messages": [
            {"role": "system", "content": system_prompt or "You are a helpful assistant."},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
    }

    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=settings.cloud_timeout_seconds) as client:
            resp = await client.post(f"{base}/chat/completions", json=payload, headers=headers)
    except httpx.ConnectError as exc:
        raise EngineError(f"Could not reach {base}. Check CLOUD_BASE_URL.") from exc
    except httpx.TimeoutException as exc:
        raise EngineError(
            f"The provider did not answer within {settings.cloud_timeout_seconds:.0f}s."
        ) from exc

    elapsed = int((time.perf_counter() - started) * 1000)

    if resp.status_code == 401:
        raise EngineError("The provider rejected CLOUD_API_KEY (401). Check the key.")
    if resp.status_code == 404:
        raise EngineError(
            f"The provider has no model '{model.ollama_tag}' (404). Set the model name to "
            f"whatever your provider calls it — CLOUD_MODEL_MAP exists for this."
        )
    if resp.status_code == 429:
        raise EngineError("Rate limited by the provider (429). Wait a moment and retry.")
    if resp.status_code >= 400:
        raise EngineError(f"Provider returned HTTP {resp.status_code}: {resp.text[:400]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise EngineError("The provider returned something that isn't JSON.") from exc

    try:
        output = data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise EngineError("Unexpected response shape from the provider.") from exc

    usage = data.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or estimate_tokens(user_prompt))
    completion_tokens = int(usage.get("completion_tokens") or estimate_tokens(output))

    return EngineResult(
        output=output,
        backend="cloud",
        simulated=False,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_ms=elapsed,
        cost_usd=estimate_cost(
            prompt_tokens,
            completion_tokens,
            settings.price_input_per_mtok,
            settings.price_output_per_mtok,
        ),
    )


# ------------------------------------------------------------------------ facade
async def run(
    model: ModelSpec,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    requested_backend: str,
) -> EngineResult:
    """Dispatch to whichever backend can actually serve this request."""
    backend = resolve_backend(model, requested_backend)
    if backend == "ollama":
        return await _run_ollama(model, system_prompt, user_prompt, temperature, top_p, max_tokens)
    if backend == "cloud":
        return await _run_cloud(model, system_prompt, user_prompt, temperature, top_p, max_tokens)
    return _run_inspector(model, system_prompt, user_prompt, temperature, top_p, max_tokens)


async def stream(
    model: ModelSpec,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
    requested_backend: str,
) -> AsyncIterator[str]:
    """Yield text chunks. The inspector emits its report a line at a time so the
    UI behaves the same way regardless of which backend is actually serving."""
    backend = resolve_backend(model, requested_backend)

    if backend == "inspector":
        result = _run_inspector(model, system_prompt, user_prompt, temperature, top_p, max_tokens)
        for line in result.output.splitlines(keepends=True):
            yield line
        return

    if backend == "ollama":
        base = settings.ollama_base_url.rstrip("/")
        payload = {
            "model": model.ollama_tag,
            "messages": [
                {"role": "system", "content": system_prompt or "You are a helpful assistant."},
                {"role": "user", "content": user_prompt},
            ],
            "stream": True,
            "options": {"temperature": temperature, "top_p": top_p, "num_predict": max_tokens},
        }
        url, headers = f"{base}/api/chat", {}
    else:
        base = settings.cloud_base_url.rstrip("/")
        payload = {
            "model": model.ollama_tag,
            "messages": [
                {"role": "system", "content": system_prompt or "You are a helpful assistant."},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "stream": True,
        }
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.cloud_api_key}"}

    try:
        async with (
            httpx.AsyncClient(timeout=settings.cloud_timeout_seconds) as client,
            client.stream("POST", url, json=payload, headers=headers) as resp,
        ):
            if resp.status_code >= 400:
                body = (await resp.aread()).decode(errors="replace")[:300]
                raise EngineError(f"Backend returned HTTP {resp.status_code}: {body}")
            async for line in resp.aiter_lines():
                if not line.strip():
                    continue
                chunk = _parse_chunk(line)
                if chunk:
                    yield chunk
    except httpx.TimeoutException as exc:
        raise EngineError("The backend timed out mid-stream.") from exc
    except httpx.ConnectError as exc:
        raise EngineError("Could not connect to the backend.") from exc


def _parse_chunk(line: str) -> str:
    """Pull the text delta out of one SSE line from either provider format."""
    import json

    if line.startswith("data: "):
        line = line[6:]
    if line.strip() in ("[DONE]", ""):
        return ""
    try:
        data = json.loads(line)
    except ValueError:
        return ""
    # OpenAI-compatible
    choices = data.get("choices")
    if choices:
        delta = choices[0].get("delta") or {}
        return delta.get("content") or ""
    # Ollama
    message = data.get("message")
    if message:
        return message.get("content") or ""
    return ""
