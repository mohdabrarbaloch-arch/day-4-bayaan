# Bayaan — Architecture

## The problem

Running an open-weight model is easy. Running it *well* is not. The things that
actually bite you are invisible until they don't work:

- **Chat templates.** Llama 3.1 wants `<|start_header_id|>`, Mistral wants
  `[INST]`, Gemma wants `<start_of_turn>`. Get it wrong and the model doesn't
  error — it just answers badly, and you spend a week blaming the weights.
- **Context budgets.** A 131k window sounds infinite until you paste a 200-page
  PDF and the server truncates silently from the front.
- **Backend drift.** The same prompt behaves differently on Ollama, on a hosted
  API, and on a vLLM box — and nobody records which one produced which answer.

Bayaan is a playground built around those three problems. It shows you the exact
string the model will receive, tells you what it costs in tokens before you send
it, and records which backend served every run.

## System diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser — vanilla JS SPA (no build step)                            │
│  ┌────────────┬─────────────────────────┬──────────────────────┐     │
│  │ model +    │ prompt editor           │ history / saved      │     │
│  │ sampling   │ + budget meter          │ prompts / stats      │     │
│  └────────────┴─────────────────────────┴──────────────────────┘     │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ JSON + SSE
┌───────────────────────────▼──────────────────────────────────────────┐
│  FastAPI                                                             │
│                                                                      │
│  routers/                                                            │
│    auth     register · login · me            (JWT, bcrypt)           │
│    models   catalog · template · budget      (pure functions)        │
│    runs     run · stream · compare · history · stats                 │
│    prompts  CRUD over saved prompts                                  │
│                                                                      │
│  services/                                                           │
│    catalog.py   10 open-weight models, real metadata                 │
│    templates.py chat-template rendering + stop sequences             │
│    tokens.py    estimation + budget maths                            │
│    engines.py   backend resolution + streaming                       │
│    inspector.py the no-model fallback (real analysis, no generation) │
│                                                                      │
│  ratelimit.py   sliding-window limiter as a dependency               │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   ┌─────────┐        ┌──────────┐        ┌────────────┐
   │ Ollama  │        │ OpenAI-  │        │ Inspector  │
   │ local   │        │ compat   │        │ (no model) │
   └─────────┘        └──────────┘        └────────────┘
        │                   │                   │
        └───────────────────┴───────────────────┘
                            ▼
                    ┌──────────────┐
                    │ SQLite / PG   │
                    │ users · runs  │
                    │ prompts       │
                    └──────────────┘
```

## Backend resolution

The interesting design decision. `engines.resolve_backend()` picks a backend per
request, in this order:

1. **`local` requested and `OLLAMA_BASE_URL` set** → Ollama.
2. **`cloud` requested and `CLOUD_API_KEY` set** → any OpenAI-compatible endpoint
   (Together, Groq, Fireworks, vLLM, LM Studio — they all speak the same shape).
3. **Neither configured** → the **inspector**.

The inspector is the part worth explaining. Rather than fake a response, it does
real work on the prompt: estimates tokens, renders the chat template, checks the
budget, and flags structural problems (empty system prompt, prompt injection
patterns, unbalanced delimiters, very long single lines). It then says, in the
output itself, that no model was called.

That choice matters. A playground that invents plausible text when no model is
connected is worse than useless — it teaches you the wrong thing about your
prompt. The inspector is honest, and it's genuinely useful before you have a GPU.

Every run stores `backend` and `simulated`, so the history never lies about what
produced an answer.

## Data flow — a single run

```
POST /api/runs
  │
  ├─ Pydantic validates (model exists, prompt non-empty, temp 0–2, max_tokens ≤ 4096)
  ├─ rate limit check (sliding window, per user + route)
  ├─ resolve_backend(model, requested)
  ├─ engines.run(...)  ──►  Ollama / cloud / inspector
  │                          └─ returns EngineResult(output, tokens, latency, cost)
  ├─ persist Run row (backend, simulated, tokens, latency, status)
  └─ 201 RunOut
```

Streaming is the same path with `engines.stream()` yielding chunks, wrapped in
SSE. The run is persisted on a **fresh session** at the end, because the
request-scoped session may already be closing by the time the generator
finishes — a subtle bug that shows up as "runs disappear from history".

## Token estimation

`tokens.py` is an estimate, not a tokenizer, and the code says so. It uses a
word/character blend tuned against Llama-family tokenizers:

```
tokens ≈ max(words × 1.3, chars / 4)
```

That's within ~10% for English prose and deliberately conservative for code. The
alternative — shipping `tiktoken` and pretending it's exact for every model — is
worse, because it's wrong in a way that looks authoritative. The UI labels the
number "estimated" everywhere it appears.

## Scaling notes

**Where this breaks first:** SQLite under concurrent writes. The fix is one env
var — `DATABASE_URL=postgresql+psycopg://...` — and the ORM layer is already
portable. `docker-compose.yml` ships Postgres for exactly this.

**Streaming and workers.** SSE holds a connection open. With `uvicorn --workers N`
each worker holds its own; behind nginx you need `proxy_buffering off` (the
response already sets `X-Accel-Buffering: no`).

**Rate limiting is in-process.** The sliding window lives in a dict, so N workers
means N independent budgets. For real multi-tenant use, swap the store for Redis
— `ratelimit.py` keeps the storage behind a small interface for that reason.

**Model calls are the bottleneck, not the app.** A single Ollama instance
serialises requests. `compare` runs models **sequentially on purpose** — running
them in parallel on one GPU just makes both slower as they thrash VRAM.

**Cost tracking** is per-model and only populated for cloud backends. Local runs
record `0.0`, which is correct: your electricity bill isn't per-token.

## Security

- Passwords: bcrypt via passlib, cost 12.
- Tokens: HS256 JWT, 7-day expiry, `sub` = user id. No refresh tokens — this is a
  playground, not a bank.
- Every run and prompt query is scoped by `user_id` in the WHERE clause, not
  filtered after the fact.
- Rate limits on auth (10/min) and runs (30/min) per IP+route.
- `TrustedHostMiddleware` in production; CORS locked to configured origins.
- No secrets in code. `SECRET_KEY` has no default in production — the app refuses
  to start with the dev key when `ENVIRONMENT=production`.
