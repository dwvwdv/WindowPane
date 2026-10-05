from datetime import date

import pytest

from worldpane_core import demo_world, generate_daily_plan, plan_day
from worldpane_core.models import World

from helpers import assert_no_overlap, base, days


@pytest.mark.parametrize("n", [1, 2, 3, 5, 8])
def test_no_overlap_per_character(n):
    world, chars, rels = demo_world(n)
    for d in days(date(2026, 9, 1), 90):
        events = generate_daily_plan(world, chars, rels, d)
        for c in chars:
            assert_no_overlap(events, c.id)


@pytest.mark.parametrize("n", [1, 2, 5])
def test_works_with_n_characters(n):
    world, chars, rels = demo_world(n)
    events = generate_daily_plan(world, chars, rels, date(2026, 10, 5))
    participants = {p for e in events for p in e.participants}
    assert participants == {c.id for c in chars}
    if n == 1:
        assert not [e for e in events if e.kind == "shared"]


def test_zero_characters_returns_empty():
    world, _, _ = demo_world(1)
    assert generate_daily_plan(world, [], [], date(2026, 10, 5)) == []


def test_character_from_other_world_rejected():
    world, chars, rels = demo_world(2)
    other = World(id="other", name="x", simulation_start_date=date(2026, 1, 1))
    with pytest.raises(ValueError):
        generate_daily_plan(other, chars, rels, date(2026, 10, 5))


@pytest.mark.parametrize("d", [date(2026, 10, 10), date(2026, 10, 11), date(2026, 10, 17)])
def test_weekend_has_no_school_or_work(d):
    world, chars, rels = demo_world(5)
    events = generate_daily_plan(world, chars, rels, d)
    assert not [e for e in events if e.kind in ("base", "temporary")]


def test_weekday_has_school_and_work_08_30_to_17_30():
    world, chars, rels = demo_world(2)
    for d in days(date(2026, 10, 5), 5):
        plan = plan_day(world, chars, rels, d)
        for c in chars:
            b = base(plan.events, c.id)
            if plan.contexts[c.id].on_leave:
                assert b == []
                continue
            assert len(b) == 1
            assert b[0].start_at.strftime("%H:%M") == "08:30"
            assert b[0].end_at.strftime("%H:%M") == "17:30"
            assert b[0].location == ("SCHOOL" if c.id == "char_1" else "OFFICE")


def test_temporary_events_inside_base_block():
    world, chars, rels = demo_world(3)
    seen = set()
    for d in days(date(2026, 10, 1), 60):
        events = generate_daily_plan(world, chars, rels, d)
        for e in events:
            if e.kind != "temporary":
                continue
            seen.add(e.type)
            (b,) = [x for x in base(events, e.participants[0])]
            assert b.start_at <= e.start_at and e.end_at <= b.end_at
            assert e.location == b.location
    assert {"slacking", "sleeping_in_class", "gaming_in_class"} <= seen


def test_holiday_calendar_hook():
    world, chars, rels = demo_world(2)
    d = date(2026, 10, 9)  # 週五
    holiday_world = World(
        id=world.id, name=world.name, simulation_start_date=world.simulation_start_date,
        holiday_dates=frozenset({d}),
    )
    plan = plan_day(holiday_world, chars, rels, d)
    assert plan.calendar.holiday
    assert not [e for e in plan.events if e.kind == "base"]


def test_events_are_timezone_aware_in_world_timezone():
    world, chars, rels = demo_world(2)
    for e in generate_daily_plan(world, chars, rels, date(2026, 10, 5)):
        assert e.start_at.tzinfo is not None
        assert e.start_at.utcoffset().total_seconds() == 8 * 3600
