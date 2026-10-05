"""事件目錄：DB 組裝出的 config 要與 inline config 等價，且新事件只需新增資料。"""

from __future__ import annotations

import dataclasses
from datetime import date

from helpers import days

from worldpane_core import demo_world, plan_day
from worldpane_core.catalog import (
    EventDefinition,
    PoolEntry,
    build_event_config,
    build_shared_event_config,
    official_definitions,
    shared_settings,
    split_event_config,
    validate_definition,
)

START = date(2026, 10, 1)


def _assemble(world, characters, extra_defs=(), extra_pool=(), shared_overrides=None):
    """模擬 server 從 DB 讀出 definitions / pools / settings 後組裝的流程。"""
    defs = {(d.category, d.key): d for d in [*official_definitions(), *extra_defs]}
    new_chars = []
    for c in characters:
        settings, pool = split_event_config(c.profile.event_config)
        entries = [PoolEntry(defs[(cat, key)], overrides) for cat, key, overrides in pool]
        entries += [PoolEntry(defs[(cat, key)], {}) for cat, key in extra_pool]
        profile = dataclasses.replace(c.profile, event_config=build_event_config(settings, entries))
        new_chars.append(dataclasses.replace(c, profile=profile))
    settings = shared_settings(world.shared_event_config)
    if shared_overrides:
        settings["overrides"] = shared_overrides
    shared = build_shared_event_config(settings, [d for (cat, _), d in defs.items() if cat == "shared"])
    return dataclasses.replace(world, shared_event_config=shared), new_chars


def _timeline(world, chars, rels, d):
    return [(e.type, e.start_at, e.end_at, tuple(e.participants)) for e in plan_day(world, chars, rels, d).events]


def test_official_definitions_are_valid():
    defs = official_definitions()
    assert {d.category for d in defs} == {"temporary", "leisure", "shared"}
    for d in defs:
        assert validate_definition(d) == [], d.key


def test_assembled_config_reproduces_inline_timeline():
    world, chars, rels = demo_world(5)
    a_world, a_chars = _assemble(world, chars)
    for d in days(START, 30):
        assert _timeline(world, chars, rels, d) == _timeline(a_world, a_chars, rels, d)


def test_new_leisure_event_is_pure_data():
    cooking = EventDefinition(
        key="cooking",
        category="leisure",
        label="煮飯",
        scene="home_kitchen",
        location="HOME",
        activity="cooking",
        params={
            "weight": 500,
            "min_duration": 20,
            "max_duration": 40,
            "allowed_time": [["17:30", "21:00"]],
            "allowed_context": ["weekday", "holiday", "leave"],
            "cooldown_min": 24 * 60,
        },
    )
    assert validate_definition(cooking) == []
    world, chars, rels = demo_world(2)
    a_world, a_chars = _assemble(world, chars, extra_defs=[cooking], extra_pool=[("leisure", "cooking")])
    seen = [
        e for d in days(START, 14) for e in plan_day(a_world, a_chars, rels, d).events if e.type == "cooking"
    ]
    assert seen, "new data-only event never scheduled"
    assert all(e.activity == "cooking" and e.scene == "home_kitchen" for e in seen)


def test_new_shared_event_is_pure_data():
    board_game = EventDefinition(
        key="board_game",
        category="shared",
        label="玩桌遊",
        scene="home_living_room",
        location="HOME",
        activity="board_game",
        params={
            "weight": 1000,
            "min_participants": 3,
            "max_participants": None,
            "min_duration": 60,
            "max_duration": 120,
            "allowed_time": [["13:00", "23:00"]],
            "allowed_context": ["holiday"],
        },
    )
    world, chars, rels = demo_world(4)
    a_world, a_chars = _assemble(world, chars, extra_defs=[board_game])
    events = [
        e for d in days(START, 21) for e in plan_day(a_world, a_chars, rels, d).events if e.type == "board_game"
    ]
    assert events
    assert all(len(e.participants) >= 3 for e in events)


def test_context_override_disables_event_on_holiday():
    world, chars, rels = demo_world(2)
    defs = [
        dataclasses.replace(
            d,
            params={**d.params, "context_overrides": {"holiday": {"enabled": False}}},
        )
        if d.category == "leisure" and d.key == "phone"
        else d
        for d in official_definitions()
    ]
    a_world, a_chars = _assemble(world, chars, extra_defs=defs)
    phones = {"weekday": 0, "holiday": 0}
    for d in days(START, 28):
        plan = plan_day(a_world, a_chars, rels, d)
        for e in plan.events:
            if e.type == "phone":
                phones["holiday" if plan.calendar.holiday else "weekday"] += 1
    assert phones["holiday"] == 0
    assert phones["weekday"] > 0


def test_world_override_disables_shared_event():
    world, chars, rels = demo_world(2)
    a_world, a_chars = _assemble(world, chars, shared_overrides={"date": {"enabled": False}})
    for d in days(START, 28):
        assert all(e.type != "date" for e in plan_day(a_world, a_chars, rels, d).events)


def test_validate_definition_reports_problems():
    bad = EventDefinition(
        key="broken",
        category="shared",
        label="壞掉",
        params={"min_duration": 30, "max_duration": 10, "min_participants": 1},
    )
    errors = validate_definition(bad)
    assert any("min_duration" in e for e in errors)
    assert any("allowed_time" in e for e in errors)
    assert any("min_participants" in e for e in errors)
