"""Write the API's OpenAPI schema to apps/api/openapi.json (no database needed).
CI regenerates it and the TypeScript client, and fails if either drifts."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("API_JWT_SECRET", "schema-export")
# Engines are created at import but never connect; any well-formed URL will do.
os.environ.setdefault("API_DATABASE_URL", "postgresql://schema-export@localhost/schema-export")

from apps.api.main import app  # noqa: E402

out = ROOT / "apps" / "api" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"wrote {out}")
