"""Rate limiting — a small sliding-window limiter used as a FastAPI dependency.

Why not slowapi? Its decorator re-signatures the wrapped function, and that
breaks when the module uses `from __future__ import annotations`: the string
annotation for the body model can't be resolved, so FastAPI silently treats it
as a query parameter and every POST comes back 422 "field required". This
implementation sidesteps the whole class of bug — it's a dependency, so the
endpoint signature is never touched.

LIMITATION, stated plainly: the counter lives in this process's memory. With
several workers or several serverless instances you get one budget per instance,
not one global budget. That's fine for a playground. If you need a true global
limit, swap `_WINDOW.hit()` for a Redis INCR + EXPIRE and keep the interface.
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import HTTPException, Request, status


@dataclass(frozen=True)
class Limit:
    """A parsed limit like '30/minute'."""

    count: int
    window_seconds: float

    @classmethod
    def parse(cls, spec: str) -> "Limit":
        try:
            raw_count, unit = spec.split("/", 1)
            count = int(raw_count.strip())
        except (ValueError, AttributeError) as exc:
            raise ValueError(f"Bad limit spec {spec!r}; expected e.g. '30/minute'") from exc

        windows = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
        unit = unit.strip().lower().rstrip("s")
        if unit not in windows:
            raise ValueError(f"Unknown time unit in {spec!r}; use second/minute/hour/day.")
        return cls(count=count, window_seconds=windows[unit])


class _SlidingWindow:
    """In-process sliding window. Timestamps per key, pruned on every hit."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    def hit(self, key: str, limit: Limit) -> tuple[bool, float]:
        """Record a hit. Returns (allowed, seconds_until_a_slot_frees)."""
        now = time.monotonic()
        cutoff = now - limit.window_seconds

        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit.count:
                # The oldest hit has to age out before another is allowed.
                retry_after = bucket[0] + limit.window_seconds - now
                return False, max(0.1, retry_after)

            bucket.append(now)
            self._sweep(now, limit)
            return True, 0.0

    def _sweep(self, now: float, limit: Limit) -> None:
        """Drop empty buckets occasionally so memory doesn't creep."""
        if now - self._last_sweep < 300:
            return
        self._last_sweep = now
        cutoff = now - limit.window_seconds
        for key in [k for k, v in self._hits.items() if not v or v[-1] <= cutoff]:
            self._hits.pop(key, None)

    def reset(self) -> None:
        """Test hook."""
        with self._lock:
            self._hits.clear()


_WINDOW = _SlidingWindow()


def reset_limits() -> None:
    _WINDOW.reset()


def _client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RateLimit:
    """Use as a dependency: `Depends(RateLimit("30/minute"))`."""

    def __init__(self, spec: str, scope: str | None = None) -> None:
        self.spec = spec
        self.limit = Limit.parse(spec)
        self.scope = scope

    def __call__(self, request: Request) -> None:
        scope = self.scope or f"{request.method}:{request.url.path}"
        key = f"{scope}|{_client_key(request)}"
        allowed, retry_after = _WINDOW.hit(key, self.limit)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Rate limit reached ({self.spec}). "
                    f"Try again in {retry_after:.0f} second(s)."
                ),
                headers={"Retry-After": str(int(retry_after) + 1)},
            )


def describe(spec: str) -> str:
    """Human phrasing for the API's capability endpoint."""
    lim = Limit.parse(spec)
    unit = {1: "second", 60: "minute", 3600: "hour", 86400: "day"}[int(lim.window_seconds)]
    return f"{lim.count} requests per {unit}"
