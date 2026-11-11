"""Write docs/openapi.json from the API itself (the machine-readable contract the front end can generate types from).

    .venv/bin/python scripts/export_openapi.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app_api.main import create_app  # noqa: E402

if __name__ == "__main__":
    spec = create_app(warm_runtime=False).openapi()
    target = ROOT / "docs" / "openapi.json"
    target.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {target} ({len(spec['paths'])} paths)")
