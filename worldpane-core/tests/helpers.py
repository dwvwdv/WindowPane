from __future__ import annotations

import copy
import dataclasses
from datetime import date, timedelta

from worldpane_core import Character, Layer
from worldpane_core.timeline import character_events


def days(start: date, count: int):
    for i in range(count):
        yield start + timedelta(days=i)


def foreground(events, cid):
    return sorted(
        (e for e in character_events(events, cid) if e.layer != Layer.BASE), key=lambda e: e.start_at
    )


def base(events, cid):
    return [e for e in character_events(events, cid) if e.layer == Layer.BASE]


def assert_no_overlap(events, cid):
    fg = foreground(events, cid)
    for a, b in zip(fg, fg[1:]):
        assert a.end_at <= b.start_at, f"{cid}: overlap {a.type} {a.start_at}-{a.end_at} / {b.type} {b.start_at}-{b.end_at}"
    for e in fg:
        assert e.start_at < e.end_at
        if e.kind in ("leisure", "shared"):
            for b in base(events, cid):
                assert not (e.start_at < b.end_at and b.start_at < e.end_at), f"{cid}: {e.type} overlaps base"


def with_profile(character: Character, **changes) -> Character:
    """回傳替換 profile 欄位後的新 Character（deep copy config）。"""
    profile = dataclasses.replace(
        character.profile, **{k: copy.deepcopy(v) for k, v in changes.items()}
    )
    return dataclasses.replace(character, profile=profile)
