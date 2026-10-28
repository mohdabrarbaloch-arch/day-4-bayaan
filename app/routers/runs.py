"""Running prompts: single runs, streaming runs, comparison, and history."""

import json
import time
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..deps import current_user
from ..models import Run, User
from ..ratelimit import RateLimit
from ..schemas import RunOut, RunRequest, RunSummary
from ..services import engines
from ..services.catalog import get_model

router = APIRouter(prefix="/api/runs", tags=["runs"])

run_limit = RateLimit(settings.rate_limit_runs, scope="runs:create")
stream_limit = RateLimit(settings.rate_limit_runs, scope="runs:stream")
compare_limit = RateLimit("10/minute", scope="runs:compare")


def _record(
    db: Session,
    user: User,
    model_id: str,
    model_label: str,
    backend: str,
    simulated: bool,
    parts: dict,
    result: engines.EngineResult | None,
    error: str = "",
) -> Run:
    run = Run(
        user_id=user.id,
        model_id=model_id,
        model_label=model_label,
        backend=backend,
        simulated=simulated,
        system_prompt=parts["system_prompt"],
        user_prompt=parts["user_prompt"],
        output=result.output if result else "",
        temperature=parts["temperature"],
        top_p=parts["top_p"],
        max_tokens=parts["max_tokens"],
        prompt_tokens=result.prompt_tokens if result else 0,
        completion_tokens=result.completion_tokens if result else 0,
        latency_ms=result.latency_ms if result else 0,
        cost_usd=result.cost_usd if result else 0.0,
        status="ok" if result and not error else "error",
        error=error,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.post(
    "",
    response_model=RunOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(run_limit)],
)
async def create_run(
    payload: RunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> RunOut:
    model = get_model(payload.model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{payload.model_id}' isn't in the catalog. GET /api/models lists what is.",
        )

    backend = engines.resolve_backend(model, payload.backend)
    parts = payload.model_dump()

    try:
        result = await engines.run(
            model,
            payload.system_prompt,
            payload.user_prompt,
            payload.temperature,
            payload.top_p,
            payload.max_tokens,
            payload.backend,
        )
    except engines.EngineError as exc:
        # Record the failure too — a playground that hides errors is useless.
        _record(
            db, user, model.id, model.label, backend, backend == "inspector", parts, None, str(exc)
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    run = _record(db, user, model.id, model.label, result.backend, result.simulated, parts, result)
    return RunOut.model_validate(run)


@router.post("/stream", dependencies=[Depends(stream_limit)])
async def stream_run(
    payload: RunRequest,
    user: User = Depends(current_user),
) -> StreamingResponse:
    """Server-sent events. Each event is one JSON object; the last is `done`."""
    model = get_model(payload.model_id)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"'{payload.model_id}' is not in the catalog.",
        )

    backend = engines.resolve_backend(model, payload.backend)
    started = time.perf_counter()

    async def event_source() -> AsyncIterator[str]:
        collected: list[str] = []
        try:
            head = {"type": "start", "backend": backend, "model": model.label}
            yield f"data: {json.dumps(head)}\n\n"

            async for chunk in engines.stream(
                model,
                payload.system_prompt,
                payload.user_prompt,
                payload.temperature,
                payload.top_p,
                payload.max_tokens,
                payload.backend,
            ):
                collected.append(chunk)
                yield f"data: {json.dumps({'type': 'delta', 'text': chunk})}\n\n"

            text = "".join(collected)
            elapsed = int((time.perf_counter() - started) * 1000)

            # Persist on a fresh session — the request-scoped one may be closing.
            db = SessionLocal()
            try:
                run = _record(
                    db,
                    user,
                    model.id,
                    model.label,
                    backend,
                    backend == "inspector",
                    payload.model_dump(),
                    engines.EngineResult(
                        output=text,
                        backend=backend,
                        simulated=backend == "inspector",
                        prompt_tokens=0,
                        completion_tokens=0,
                        latency_ms=elapsed,
                        cost_usd=0.0,
                    ),
                )
                run_id = run.id
            finally:
                db.close()

            tail = {"type": "done", "run_id": run_id, "latency_ms": elapsed}
            yield f"data: {json.dumps(tail)}\n\n"
        except engines.EngineError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/compare", response_model=list[RunOut], dependencies=[Depends(compare_limit)])
async def compare(
    payload: RunRequest,
    model_ids: list[str] = Query(..., min_length=2, max_length=3),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[RunOut]:
    """Same prompt, several models. Runs sequentially so a single-GPU Ollama
    doesn't swap models in and out of VRAM on every call."""
    results: list[RunOut] = []
    parts = payload.model_dump()

    for model_id in model_ids:
        model = get_model(model_id)
        if model is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"'{model_id}' isn't in the catalog.",
            )
        backend = engines.resolve_backend(model, payload.backend)
        try:
            result = await engines.run(
                model,
                payload.system_prompt,
                payload.user_prompt,
                payload.temperature,
                payload.top_p,
                payload.max_tokens,
                payload.backend,
            )
        except engines.EngineError as exc:
            _record(db, user, model.id, model.label, backend, False, parts, None, str(exc))
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

        run = _record(
            db, user, model.id, model.label, result.backend, result.simulated, parts, result
        )
        results.append(RunOut.model_validate(run))

    return results


@router.get("", response_model=list[RunSummary])
def list_runs(
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    model_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> list[RunSummary]:
    stmt = select(Run).where(Run.user_id == user.id)
    if model_id:
        stmt = stmt.where(Run.model_id == model_id)
    rows = db.scalars(stmt.order_by(Run.created_at.desc()).limit(limit).offset(offset)).all()
    return [RunSummary.model_validate(r) for r in rows]


@router.get("/stats/summary")
def stats(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """Aggregate numbers for the dashboard header."""
    total = db.scalar(select(func.count(Run.id)).where(Run.user_id == user.id)) or 0

    by_backend = dict(
        db.execute(
            select(Run.backend, func.count()).where(Run.user_id == user.id).group_by(Run.backend)
        ).all()
    )
    by_model = dict(
        db.execute(
            select(Run.model_label, func.count())
            .where(Run.user_id == user.id)
            .group_by(Run.model_label)
        ).all()
    )

    avg_latency = db.scalar(
        select(func.avg(Run.latency_ms)).where(Run.user_id == user.id, Run.status == "ok")
    )
    total_tokens = db.scalar(
        select(func.sum(Run.prompt_tokens + Run.completion_tokens)).where(Run.user_id == user.id)
    )
    total_cost = db.scalar(select(func.sum(Run.cost_usd)).where(Run.user_id == user.id))

    return {
        "total_runs": total,
        "runs_by_backend": by_backend,
        "runs_by_model": by_model,
        "avg_latency_ms": int(avg_latency or 0),
        "total_tokens": int(total_tokens or 0),
        "total_cost_usd": round(float(total_cost or 0.0), 6),
        "top_model": max(by_model, key=by_model.get) if by_model else None,
    }


@router.get("/{run_id}", response_model=RunOut)
def get_run(
    run_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> RunOut:
    run = db.scalar(select(Run).where(Run.id == run_id, Run.user_id == user.id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No run with that id.")
    return RunOut.model_validate(run)


@router.delete("/{run_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_run(
    run_id: str, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> Response:
    run = db.scalar(select(Run).where(Run.id == run_id, Run.user_id == user.id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No run with that id.")
    db.delete(run)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
