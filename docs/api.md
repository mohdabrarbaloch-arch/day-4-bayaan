# API reference

Base URL: `http://127.0.0.1:8000`. Interactive docs at `/api/docs`.

All endpoints except `/api/health`, `/api/models*` and the auth pair require:

```
Authorization: Bearer <access_token>
```

Errors are always `{"detail": "..."}`. Validation errors (422) return FastAPI's
list form, where `detail` is an array of `{loc, msg, type}`.

---

## Health

### `GET /api/health`

```json
{
  "status": "ok",
  "app": "Bayaan",
  "version": "1.0.0",
  "environment": "development",
  "backend": "inspector",
  "simulated": true
}
```

`simulated: true` means no model is connected — runs will return inspector
output, not generated text.

---

## Auth

### `POST /api/auth/register` → `201`

```json
{ "email": "you@example.com", "display_name": "Your Name", "password": "at-least-8-chars" }
```

Returns:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "user": { "id": "...", "email": "...", "display_name": "...", "created_at": "..." }
}
```

| Status | When |
|---|---|
| `201` | Created |
| `409` | Email already registered (case-insensitive) |
| `422` | Bad email, password under 8 chars, name under 2 chars |
| `429` | More than 10 attempts per minute |

### `POST /api/auth/login` → `200`

```json
{ "email": "you@example.com", "password": "..." }
```

Same response shape as register. `401` on wrong credentials — deliberately the
same message for unknown email and wrong password.

### `GET /api/auth/me` → `200`

Returns the current `UserOut`.

---

## Models

### `GET /api/models` → `200`

Array of:

```json
{
  "id": "llama-3.1-8b-instruct",
  "label": "Llama 3.1 8B Instruct",
  "family": "Llama",
  "params": "8B",
  "context_window": 131072,
  "license": "Llama 3.1 Community License",
  "notes": "...",
  "available_backends": ["local"],
  "resolved_backend": "local"
}
```

### `GET /api/models/capabilities` → `200`

What this deployment can actually do. Use it instead of guessing.

```json
{
  "models": 10,
  "local_configured": false,
  "cloud_configured": false,
  "active_backend": "inspector",
  "note": "No model connected — runs use the built-in prompt inspector..."
}
```

### `GET /api/models/{model_id}/template` → `200`

```json
{
  "model_id": "llama-3.1-8b-instruct",
  "template": "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system}<|eot_id|>...",
  "template_name": "Llama 3.x",
  "note": "Uses header blocks with <|eot_id|> terminators.",
  "stop_sequences": ["<|eot_id|>", "<|end_of_text|>"],
  "ollama_tag": "llama3.1:8b"
}
```

`404` if the model id isn't in the catalog.

### `POST /api/models/budget` → `200`

```json
{
  "model_id": "llama-3.1-8b-instruct",
  "system_prompt": "You are terse.",
  "user_prompt": "Explain WAL.",
  "max_tokens": 512
}
```

Returns:

```json
{
  "model_id": "llama-3.1-8b-instruct",
  "model_label": "Llama 3.1 8B Instruct",
  "system_tokens": 4,
  "user_tokens": 5,
  "prompt_tokens": 9,
  "reserved_for_completion": 512,
  "context_window": 131072,
  "total_needed": 521,
  "fits": true,
  "headroom": 130551,
  "utilization_pct": 0.4
}
```

### `POST /api/models/preview` → `200`

Renders a prompt through a template. Query param `model_id` (default
`llama-3.1-8b-instruct`).

```json
{ "system_prompt": "...", "user_prompt": "..." }
```

---

## Runs

### `POST /api/runs` → `201`

```json
{
  "model_id": "llama-3.1-8b-instruct",
  "backend": "local",
  "system_prompt": "You are a careful technical writer.",
  "user_prompt": "Explain write-ahead logging.",
  "temperature": 0.7,
  "top_p": 0.95,
  "max_tokens": 512
}
```

Returns a full `RunOut`:

```json
{
  "id": "...",
  "model_id": "llama-3.1-8b-instruct",
  "model_label": "Llama 3.1 8B Instruct",
  "backend": "inspector",
  "simulated": true,
  "system_prompt": "...",
  "user_prompt": "...",
  "output": "...",
  "temperature": 0.7,
  "top_p": 0.95,
  "max_tokens": 512,
  "prompt_tokens": 28,
  "completion_tokens": 0,
  "latency_ms": 0,
  "cost_usd": 0.0,
  "status": "ok",
  "error": "",
  "created_at": "..."
}
```

| Status | When |
|---|---|
| `201` | Ran (check `status` — `error` is possible with a 201 if the backend failed) |
| `404` | Model id not in the catalog |
| `422` | Prompt empty, over `MAX_PROMPT_CHARS`, temp outside 0–2, max_tokens outside 1–4096 |
| `429` | Over the run budget |
| `502` | The backend itself failed (Ollama down, cloud 4xx/5xx) |

### `POST /api/runs/stream` → `200` (`text/event-stream`)

Same body. Events:

```
data: {"type": "start", "backend": "ollama", "model": "Llama 3.1 8B Instruct"}

data: {"type": "delta", "text": "Write-ahead "}

data: {"type": "delta", "text": "logging is..."}

data: {"type": "done", "run_id": "...", "latency_ms": 1840}
```

On failure mid-stream:

```
data: {"type": "error", "message": "The backend timed out mid-stream."}
```

The run is persisted when the stream completes, on a fresh database session.

### `POST /api/runs/compare` → `200`

Query params: `model_ids` (repeatable, 2–3 values).

```
POST /api/runs/compare?model_ids=llama-3.1-8b-instruct&model_ids=mistral-7b-instruct
```

Body is a normal `RunRequest`; `model_id` in the body is ignored. Returns an array
of `RunOut`, one per model, in the order requested. Runs sequentially.

### `GET /api/runs` → `200`

Query: `limit` (1–100, default 25), `offset` (≥0), `model_id` (optional filter).

Returns `RunSummary[]` — the lighter shape without the full output.

### `GET /api/runs/stats/summary` → `200`

```json
{
  "total_runs": 4,
  "runs_by_backend": { "inspector": 4 },
  "runs_by_model": { "Llama 3.1 8B Instruct": 2, "Mistral 7B Instruct v0.3": 2 },
  "avg_latency_ms": 0,
  "total_tokens": 825,
  "total_cost_usd": 0.0,
  "top_model": "Llama 3.1 8B Instruct"
}
```

### `GET /api/runs/{run_id}` → `200`

Full `RunOut`. `404` if it doesn't exist **or belongs to another user** — the
query is scoped by `user_id`, so ownership failures are indistinguishable from
missing rows. That's intentional.

### `DELETE /api/runs/{run_id}` → `204`

No body. `404` as above.

---

## Saved prompts

### `GET /api/prompts` → `200`

Array of `PromptOut`, newest first.

### `POST /api/prompts` → `201`

```json
{
  "name": "WAL explainer",
  "system_prompt": "You are a careful technical writer.",
  "user_prompt": "Explain write-ahead logging.",
  "notes": ""
}
```

`409` if you already have a prompt with that name.

### `PATCH /api/prompts/{id}` → `200`

Any subset of `name`, `system_prompt`, `user_prompt`, `notes`.

### `DELETE /api/prompts/{id}` → `204`

---

## Rate limits

| Route | Default |
|---|---|
| `/api/auth/register`, `/api/auth/login` | 10/minute |
| `/api/runs`, `/api/runs/stream` | 30/minute |
| `/api/runs/compare` | 10/minute |

Exceeding one returns `429` with a `Retry-After` header. Limits are per IP and
per route, configured in `.env`.
