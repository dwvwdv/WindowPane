"""Write the browser demo as one standalone HTML file (offline playback of the demo world).

    python scripts/build_demo_html.py --start 2026-10-05 --days 7 -o demo.html

The page is the same one the server serves at ``/demo``; standalone, only the offline
playback works (live mode needs the page to be served by the backend).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src")]

from worldpane_server.demo import demo_payload, page_document, page_fragment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 10, 5))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--timezone", default="Asia/Taipei")
    parser.add_argument("--fragment", action="store_true", help="omit doctype/head (for hosts that add them)")
    parser.add_argument("-o", "--output", type=Path, required=True)
    args = parser.parse_args()
    payload = demo_payload(args.start, args.days, args.timezone)
    html = page_fragment(payload) if args.fragment else page_document(payload)
    args.output.write_text(html, encoding="utf-8")
    print(f"wrote {args.output} ({len(html) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
