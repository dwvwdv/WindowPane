"""The browser demo page is served and embeds a week of the demo world."""

from __future__ import annotations

import json
import re


def test_demo_page_embeds_a_week_of_the_demo_world(client):
    r = client.get("/demo")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    match = re.search(r"const DEMO = (\{.*?\});\n", r.text, re.S)
    assert match, "demo data not embedded"
    data = json.loads(match.group(1))
    assert [c["name"] for c in data["characters"]] == ["小白", "小雞毛"]
    assert len(data["days"]) == 7
    assert all(day["segments"] for day in data["days"])


def test_demo_page_is_not_in_the_api_schema(client):
    assert "/demo" not in client.get("/openapi.json").json()["paths"]
