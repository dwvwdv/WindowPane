"""Browser demo (``GET /demo``): renders a World the way a device screen would.

The page plays back a week of the demo world offline (computed here with worldpane-core, the
same code the Display API uses) and can also pair with this server and poll the live API.
``scripts/build_demo_html.py`` writes the same page as one standalone file.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from importlib import resources
from zoneinfo import ZoneInfo

from worldpane_core import timeline as core_timeline

from .clock import FixedClock
from .config import Settings
from .repositories.memory import InMemoryRepository
from .seed import (
    DEMO_CHARACTER_IDS,
    DEMO_START_DATE,
    DEMO_WORLD_ID,
    create_world_with_defaults,
    official_default_characters,
)
from .services import WorldService
from .simulation.core import CoreSimulationProvider, _to_core_event
from .theme import with_offbeat


def _minutes(dt: datetime, day_start: datetime) -> int:
    return round((dt - day_start).total_seconds() / 60)


def demo_payload(start: date, days: int = 7, timezone: str = "Asia/Taipei") -> dict:
    """``days`` consecutive days of the demo world (小白 + 小雞毛), as plain JSON data.

    Times are minutes from local midnight. ``segments`` is what a device shows (foreground
    over base, gaps are idle); ``events`` is the raw plan, as ``/world/history`` returns it.
    """
    tz = ZoneInfo(timezone)
    repo = InMemoryRepository()
    service = WorldService(
        repo=repo, sim=CoreSimulationProvider(), settings=Settings(env="test", seed_demo_world=False),
        clock=FixedClock(datetime.combine(start, datetime.min.time(), tz)),
    )
    world = create_world_with_defaults(
        repo, world_id=DEMO_WORLD_ID, name="窗間 Demo", timezone=timezone,
        created_at=service.clock.now(), start_date=DEMO_START_DATE,
        characters=official_default_characters(DEMO_WORLD_ID, DEMO_CHARACTER_IDS),
    )
    characters = repo.list_characters(world.id)
    out_days = []
    for i in range(days):
        d = start + timedelta(days=i)
        day_start = datetime.combine(d, datetime.min.time(), tz)
        events = sorted(service.ensure_plan(world, d), key=lambda e: (e.start_at, e.id))
        core_events = [_to_core_event(e) for e in events]
        segments = {}
        for c in characters:
            segments[c.id] = [
                [_minutes(s.start, day_start), _minutes(s.end, day_start), s.event.scene, s.event.activity,
                 s.event.type, s.event.metadata.get("label", s.event.type), len(s.event.participants) > 1]
                for s in core_timeline.build_segments(core_events, c.id) if s.event is not None
            ]
        out_days.append({
            "date": d.isoformat(),
            "weekday": d.isoweekday(),
            "events": [
                {"type": e.type, "label": e.metadata.get("label", e.type), "scene": e.scene,
                 "activity": e.activity, "start": _minutes(e.start_at, day_start),
                 "end": _minutes(e.end_at, day_start), "participants": e.participant_ids,
                 "layer": e.layer}
                for e in events
            ],
            "segments": segments,
        })
    return {
        "world": {"id": world.id, "name": world.name, "timezone": timezone},
        "characters": [
            {"id": c.id, "name": c.display_name, "appearance": c.appearance_key,
             "profile": c.profile.name or c.profile.key}
            for c in characters
        ],
        "days": out_days,
    }


def page_fragment(payload: dict | None) -> str:
    """The demo page body (no doctype/head), with ``payload`` embedded for offline playback."""
    template = resources.files("worldpane_server").joinpath("static/demo.html").read_text(encoding="utf-8")
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return with_offbeat(template).replace("/*__DEMO_DATA__*/null", data, 1)


def page_document(payload: dict | None) -> str:
    return (
        '<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        "</head><body>" + page_fragment(payload) + "</body></html>"
    )
