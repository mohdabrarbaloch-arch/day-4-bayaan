"""Vercel serverless entrypoint.

Two things matter here and both have bitten this project family before:

1. `includeFiles: "app/**"` in vercel.json resolves from the PROJECT ROOT with
   the modern `functions` config. The legacy `builds` block resolved it from the
   function's own directory, so `app/**` silently became `api/app/**` and the
   package never shipped — every /api/* route then died with
   FUNCTION_INVOCATION_FAILED while `/` still served a friendly page.

2. Vercel never fires ASGI lifespan events, so `init_db()` has to run at import
   time. Relying on a lifespan handler means the first request hits a database
   with no tables.
"""

import os
import sys
from pathlib import Path

# Make the project root importable regardless of how Vercel sets sys.path.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Vercel's filesystem is read-only outside /tmp, so SQLite must live there.
# Set this before importing the app — settings are read at import time.
os.environ.setdefault("VERCEL", "1")
if not os.environ.get("DATABASE_URL"):
    os.environ["DATABASE_URL"] = "sqlite:////tmp/bayaan.db"

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

# Create tables now, not on first request.
init_db()

# Vercel looks for a module-level `app` (ASGI) — it's imported above.
__all__ = ["app"]
