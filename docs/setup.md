# Setup

## Requirements

- Python 3.11 or newer
- pip
- Optional: Docker (for the compose path), Ollama (for a local model)

## Local, from source

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-4-bayaan.git
cd day-4-bayaan

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -e ".[dev]"
```

Create your environment file:

```bash
cp .env.example .env
```

Generate a real secret — the app will refuse to start in production without one:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste it into `SECRET_KEY` in `.env`.

Run it:

```bash
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. The database is created on first boot.

## Connecting a real model

Out of the box you get the **inspector** — real prompt analysis, no generation.
That's intentional, and the UI says so in a banner. To get actual text:

### Option A — Ollama (local, free)

```bash
# install from https://ollama.com, then:
ollama pull llama3.1:8b
ollama serve
```

In `.env`:

```
OLLAMA_BASE_URL=http://localhost:11434
```

Restart the app. The banner disappears and the pill in the header reads `ollama`.

### Option B — any OpenAI-compatible API

Together, Groq, Fireworks, OpenRouter, vLLM, LM Studio — all the same shape.

```
CLOUD_BASE_URL=https://api.together.xyz/v1
CLOUD_API_KEY=your-key-here
CLOUD_MODEL_MAP={"llama-3.1-8b-instruct":"meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo"}
```

`CLOUD_MODEL_MAP` is how a catalog id becomes a provider model name. Any model
missing from the map falls back to the catalog id itself, which works for
providers that use the same names.

## Docker

```bash
docker compose up --build
```

App on `:8000`, Postgres on `:5432`. The app waits for the database healthcheck.

Set `SECRET_KEY` in your shell or a `.env` file next to `docker-compose.yml`:

```bash
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))") docker compose up
```

## Verifying the install

```bash
curl -s localhost:8000/api/health
# {"status":"ok","app":"Bayaan","version":"1.0.0","backend":"inspector",...}

curl -s localhost:8000/api/models/capabilities
# tells you exactly which backend is live
```

## Running the tests

```bash
pytest -q
ruff check .
black --check .
```

## Common problems

**`SECRET_KEY must be set`** — you're in production mode with the default key.
Set a real one, or set `ENVIRONMENT=development`.

**Runs return inspector output** — no backend is configured. Check
`/api/models/capabilities`; it names the active backend.

**`database is locked`** — SQLite with concurrent writers. Use Postgres, or run a
single worker.

**Streaming stops after a few tokens behind nginx** — add
`proxy_buffering off;` for that location. The app already sends
`X-Accel-Buffering: no`, but some proxies ignore it.
