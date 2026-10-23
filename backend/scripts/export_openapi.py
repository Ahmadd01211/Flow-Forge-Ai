"""Export/check API contracts without connecting to a database or broker."""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://schema:schema@localhost/schema_export")
os.environ.setdefault("SESSION_SIGNING_KEY", "schema-export-placeholder-not-a-runtime-secret")

from app.main import app  # noqa: E402

target = ROOT / "openapi.json"
content = json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
if "--check" in sys.argv:
    if not target.exists() or target.read_text(encoding="utf-8") != content:
        raise SystemExit("OpenAPI contract is stale. Run python scripts/export_openapi.py.")
    print("OpenAPI matches the backend.")
else:
    target.write_text(content, encoding="utf-8")
    print("Exported backend/openapi.json without external connections.")
