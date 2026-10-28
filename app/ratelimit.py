"""Rate limiting — a small sliding-window limiter used as a FastAPI dependency.

Why not slowapi: its `@limiter.limit(...)` decorator re-signatures the wrapped
handler, and under `from __future__ import annotations` FastAPI then resolves the
body model as a query parameter — every POST comes back 422. A dependency never
touches the endpoint signature, so that class of bug can't happen.

Storage is in-process. With N workers you get N independent budgets; swap
`_HITS` for Redis if you need a shared one.
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status

_WINDOWS = {"second": 1, "seconds": 1, "minute": 60, "hour": 3600, "day": 86400}

_HITS: dict[str, deque[float]] = defaultdict(deque)
_LOCK = threading.Lock()


def reset_limits() -> None:
    """Clear every window. Used by tests and by nothing else."""
    with _LOCK:
        _HITS.clear()


@dataclass(frozen=True)
class Limit:
    count: int
    window_seconds: int

    @classmethod
    def parse(cls, spec: str) -> "Limit":
        """Parse '30/minute' into a Limit. Raises ValueError on anything else."""
        try:
            raw_count, raw_unit = spec.strip().split("/", 1)
            count = int(raw_count)
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"Bad rate limit spec: {spec!r} (expected e.g. '30/minute')") from exc

        unit = raw_unit.strip().lower()
        if unit not in _WINDOWS:
            raise ValueError(f"Unknown rate limit unit {unit!r} in {spec!r}")
        if count < 1:
            raise ValueError(f"Rate limit count must be positive, got {count}")
        return cls(count=count, window_seconds=_WINDOWS[unit])


class RateLimit:
    """Dependency factory: `Depends(RateLimit("30/minute", scope="runs"))`."""

    def __init__(self, spec: str, scope: str) -> None:
        self.limit = Limit.parse(spec)
        self.scope = scope

    def __call__(self, request: Request) -> None:
        from .deps import client_ip

        key = f"{self.scope}:{client_ip(request)}"
        now = time.monotonic()
        cutoff = now - self.limit.window_seconds

        with _LOCK:
            hits = _HITS[key]
            while hits and hits[0] < cutoff:
                hits.popleft()

            if len(hits) >= self.limit.count:
                retry_after = max(1, int(hits[0] + self.limit.window_seconds - now) + 1)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=(
                        f"Too many requests — {self.limit.count} per "
                        f"{self.limit.window_seconds}s. Try again in {retry_after}s."
                    ),
                    headers={"Retry-After": str(retry_after)},
                )

            hits.append(now)
