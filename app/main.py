"""FastAPI application factory.

Two things here exist specifically because of how serverless platforms behave:

1. `init_db()` runs at import time, not only in a lifespan handler. Vercel's
   Python runtime never fires startup events, so a lifespan-only init means the
   first request hits "no such table: users".

2. The static mount is guarded by a directory check. `StaticFiles(directory=...)`
   raises at import when the directory is missing, which produces a build that
   deploys fine and then 500s on every single route with no useful log.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .config import settings
from .database import init_db
from .routers import auth, models, prompts, runs

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Import-time DB init: Vercel/Lambda skip lifespan, so this cannot live only there.
init_db()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Bayaan API",
        version="1.0.0",
        summary="An open-model prompt playground: catalog, templates, token budgets, runs.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=False,  # bearer tokens, not cookies
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    if settings.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=settings.allowed_hosts_list,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # `detail` is a readable string so a plain client (curl, the SPA) can show
        # something useful without parsing the structured list underneath.
        errors = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
            for e in exc.errors()
        ]
        summary = "; ".join(f"{e['field']}: {e['message']}" for e in errors) or "Invalid request."
        return JSONResponse(
            status_code=422,
            content={"detail": summary, "errors": errors},
        )

    app.include_router(auth.router)
    app.include_router(models.router)
    app.include_router(runs.router)
    app.include_router(prompts.router)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {
            "status": "ok",
            "app": settings.app_name,
            "version": "1.0.0",
            "environment": settings.environment,
            "backend": (
                "ollama"
                if settings.ollama_enabled
                else ("cloud" if settings.cloud_enabled else "inspector")
            ),
            "simulated": not (settings.ollama_enabled or settings.cloud_enabled),
        }

    # --- static SPA ---------------------------------------------------------
    if STATIC_DIR.is_dir():
        # The SPA's assets live directly in app/static (index.html, app.js, style.css).
        # Mounting the directory itself at /assets keeps the URLs in index.html honest
        # without a second nested folder.
        app.mount("/assets", StaticFiles(directory=str(STATIC_DIR)), name="assets")

        @app.get("/", include_in_schema=False)
        def index() -> FileResponse:
            return FileResponse(str(STATIC_DIR / "index.html"))

    else:

        @app.get("/", include_in_schema=False)
        def index_missing() -> JSONResponse:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "The web UI isn't bundled in this deployment, but the API is up.",
                    "api_docs": "/api/docs",
                    "health": "/api/health",
                    "hint": "STATIC_DIR resolves to app/static — make sure it's included in "
                    "the deployment bundle (see vercel.json includeFiles).",
                },
            )

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> FileResponse:
        return FileResponse(str(STATIC_DIR / "favicon.svg"), media_type="image/svg+xml")

    # JSON 404 for unmatched paths. Returning the SPA shell for unknown paths makes
    # a broken route look healthy from curl — that mistake cost real debugging time.
    #
    # Careful: this must NOT rewrite 404s that a route raised on purpose ("no run
    # with that id"). Those carry a real detail message, and clobbering it turns a
    # useful error into "no route matches" — which is actively misleading.
    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404 and exc.detail in ("Not Found", None):
            return JSONResponse(
                status_code=404,
                content={
                    "detail": f"No route matches {request.method} {request.url.path}.",
                    "api_docs": "/api/docs",
                },
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    return app


app = create_app()
