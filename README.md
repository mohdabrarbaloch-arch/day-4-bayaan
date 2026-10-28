# Bayaan

**An open-model prompt playground that shows you the working.**

Pick an open-weight model, tune the sampling, see the exact string it will
receive, and compare two models on the same question — before you spend a rupee
on tokens.

[![Python](https://img.shields.io/badge/python-3.11+-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Tests](https://img.shields.io/badge/tests-110%20passing-4ade80)](#tests)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

---

## Why this exists

I kept hitting the same three walls when running open models locally, and none of
them threw an error:

**The chat template was wrong.** Llama 3.1 wants `<|start_header_id|>`. Mistral
wants `[INST]`. Gemma wants `<start_of_turn>`. Feed a model the wrong wrapper and
it doesn't complain — it just answers worse, and you spend the evening convinced
the quantisation broke something.

**The context budget was a guess.** A 131k window feels infinite until you paste
a long document and the server quietly truncates from the front. You find out
when the answer ignores the first half of your input.

**Nobody recorded which backend answered.** Same prompt, three backends, three
different answers, and no way to tell which one produced the text you're staring
at.

Bayaan is built around those three. It renders the template, counts the tokens
before you send, and stamps every run with the backend that served it.

## What it does

**Model catalog with real metadata.** Ten open-weight models — Llama 3.3 70B,
Llama 3.1 8B, Mistral 7B, Mixtral 8x7B, Qwen 2.5 72B and 7B, Gemma 2 9B, Phi-3.5,
DeepSeek V2 Lite, Command R — with actual parameter counts, context windows and
licence names. Not placeholders.

**Template inspector.** One click shows the exact string the model receives,
including the special tokens, plus the stop sequences that template needs. This
is the feature that saves the most time.

**Live token budget.** As you type, a meter shows prompt tokens, reserved
completion tokens, and how much of the window is left. It turns red before you
hit the wall, not after.

**Three backends, one interface.** Ollama for local, any OpenAI-compatible
endpoint for cloud (Together, Groq, Fireworks, vLLM, LM Studio), and an
**inspector** fallback when neither is configured.

**Streaming.** Server-sent events, token by token, with the run persisted when
the stream closes.

**Side-by-side comparison.** Same prompt, two models, sequential execution — so a
single GPU doesn't thrash VRAM swapping weights.

**History and saved prompts.** Every run is stored with its backend, latency,
token count and cost. Saved prompts are the small library that makes a playground
usable on a Tuesday.

## The inspector, explained

If you run this without a model connected, it doesn't fake an answer. It does
real analysis on your prompt — token estimate, rendered template, budget check,
structural findings — and then tells you plainly that no model was called.

That's deliberate. A playground that invents plausible text when nothing is
connected teaches you the wrong thing about your prompt. The inspector is honest
and it's genuinely useful before you have a GPU.

## Screenshots

| Playground | A run |
|---|---|
| ![Playground](https://static.teamily.ai/sites/ec453c1f-bf5c-471c-a904-1b5a980b5925/documents/playground/playground.png) | ![Run](https://static.teamily.ai/sites/ec453c1f-bf5c-471c-a904-1b5a980b5925/documents/run/run.png) |

| Template inspector | Mobile |
|---|---|
| ![Template](https://static.teamily.ai/sites/ec453c1f-bf5c-471c-a904-1b5a980b5925/documents/template/template.png) | ![Mobile](https://static.teamily.ai/sites/ec453c1f-bf5c-471c-a904-1b5a980b5925/documents/mobile/mobile.png) |

## Live demo

**Not deployed yet.** There's no Vercel token in the build environment, so I'm
not going to paste a URL that doesn't resolve. The repo ships a `vercel.json` and
a serverless entrypoint, so it's a two-minute deploy once a token exists — see
[Deploying](#deploying).

## Quick start

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-4-bayaan.git
cd day-4-bayaan

python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# edit .env — at minimum set SECRET_KEY

uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. Register an account, pick a model, write a prompt.

Without a model configured you'll get the inspector. To connect a real one:

```bash
# local, via Ollama
ollama pull llama3.1:8b
export OLLAMA_BASE_URL=http://localhost:11434

# or cloud, any OpenAI-compatible endpoint
export CLOUD_BASE_URL=https://api.together.xyz/v1
export CLOUD_API_KEY=your-key
export CLOUD_MODEL_MAP='{"llama-3.1-8b-instruct":"meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"}'
```

## Docker

```bash
docker compose up --build
```

That brings up the app on `:8000` and Postgres on `:5432`. The app waits for the
database healthcheck before starting.

## Tests

```bash
pytest -q          # 110 tests
ruff check .       # clean
black --check .    # clean
```

The suite covers token maths, template rendering for every family, auth
(including case-insensitive duplicate emails and tampered tokens), the catalog,
run lifecycle, the inspector's findings, prompt CRUD with ownership checks, and
the rate limiter itself.

## API

Full reference in [`docs/api.md`](docs/api.md). The short version:

| Method | Path | What it does |
|---|---|---|
| `POST` | `/api/auth/register` | Create an account, returns a JWT |
| `POST` | `/api/auth/login` | Sign in |
| `GET` | `/api/auth/me` | Current user |
| `GET` | `/api/models` | The catalog |
| `GET` | `/api/models/{id}/template` | Rendered template + stop sequences |
| `POST` | `/api/models/budget` | Token budget for a prompt |
| `POST` | `/api/runs` | Run a prompt |
| `POST` | `/api/runs/stream` | Same, as SSE |
| `POST` | `/api/runs/compare` | Two models, one prompt |
| `GET` | `/api/runs` | History |
| `GET` | `/api/runs/stats/summary` | Aggregates |
| `GET/POST/PATCH/DELETE` | `/api/prompts` | Saved prompts |

Interactive docs at `/api/docs`.

## Deploying

**Vercel** (serverless):

```bash
vercel --prod --yes --token $VERCEL_TOKEN
```

Set `SECRET_KEY`, `DATABASE_URL=sqlite:////tmp/bayaan.db` (Vercel's filesystem is
read-only outside `/tmp`), and `VERCEL=1` in the project's environment variables.

⚠️ **SQLite on Vercel is ephemeral** — `/tmp` is wiped between cold starts, so
accounts and history vanish. Fine for a demo, not for real use. Point
`DATABASE_URL` at Postgres (Neon, Supabase) for anything persistent.

**Docker** anywhere else:

```bash
docker build -t bayaan .
docker run -p 8000:8000 --env-file .env bayaan
```

## Project layout

```
app/
  main.py          app factory, middleware, static mount, error handlers
  config.py        env-driven settings
  database.py      engine + session, SQLite/Postgres
  models.py        User, Run, SavedPrompt
  schemas.py       Pydantic request/response models
  security.py      bcrypt + JWT
  ratelimit.py     sliding-window limiter
  deps.py          current_user, client_ip
  routers/         auth, models, runs, prompts
  services/        catalog, templates, tokens, engines, inspector
  static/          the SPA — index.html, app.js, style.css
tests/             110 tests
docs/              setup, usage, api
```

## Licence

MIT — see [LICENSE](LICENSE).

---

Built as Day 4 of a 30-day run of shipping one real project a day. Day 1 was a
chat assistant, Day 2 a document Q&A tool, Day 3 a long-context reasoning
assistant. This one is about the plumbing underneath all of them.
