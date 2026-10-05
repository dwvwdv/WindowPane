from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_openapi.py"


def _load():
    spec = importlib.util.spec_from_file_location("export_openapi", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_openapi_json_is_up_to_date():
    mod = _load()
    assert mod.OUT.exists(), "run python scripts/export_openapi.py"
    assert mod.OUT.read_text(encoding="utf-8") == mod.render(), "openapi.json is stale; re-export"


def test_openapi_paths():
    import json

    doc = json.loads(_load().render())
    assert set(doc["paths"]) == {
        "/api/v1/world/state",
        "/api/v1/world/history",
        "/api/v1/device/input",
        "/api/v1/device/pair",
        "/api/v1/world",
        "/api/v1/world/pairing-codes",
    }
    assert "HTTPBearer" in doc["components"]["securitySchemes"]
