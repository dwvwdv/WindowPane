"""Write the OpenAPI document to worldpane-server/openapi.json (consumed by the ESP32 side).

Usage:  python scripts/export_openapi.py [--check]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OUT = ROOT / "openapi.json"


def render() -> str:
    from worldpane_server.config import Settings
    from worldpane_server.main import create_app

    app = create_app(Settings(env="test", pairing_code_secret="export", seed_demo_world=False))
    return json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=False) + "\n"


def main() -> int:
    text = render()
    if "--check" in sys.argv:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            print("openapi.json is stale; run: python scripts/export_openapi.py", file=sys.stderr)
            return 1
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
