from collections import Counter
from datetime import date

import pytest

from worldpane_core import CharacterRelationship, demo_world, generate_daily_plan
from worldpane_core.models import World

from helpers import assert_no_overlap, days


def _always_shared(world: World, **overrides) -> World:
    cfg = dict(world.shared_event_config)
    cfg.update({"attempts": 3, "trigger_probability": 1.0, **overrides})
    return World(
        id=world.id, name=world.name, simulation_start_date=world.simulation_start_date,
        timezone=world.timezone, simulation_version=world.simulation_version, shared_event_config=cfg,
    )


@pytest.mark.parametrize("n", [2, 3, 5])
def test_shared_events_single_event_all_participants_no_double_booking(n):
    world, chars, rels = demo_world(n)
    world = _always_shared(world)
    rules = {r["type"]: r for r in world.shared_event_config["rules"]}
    couples = {r.pair() for r in rels if r.relationship_type == "couple"}
    total = 0
    sizes = Counter()
    for d in days(date(2026, 10, 1), 60):
        events = generate_daily_plan(world, chars, rels, d)
        shared = [e for e in events if e.kind == "shared"]
        total += len(shared)
        for e in shared:
            rule = rules[e.type]
            ps = e.participants
            sizes[len(ps)] += 1
            assert len(ps) == len(set(ps))
            assert len(ps) >= rule["min_participants"]
            if rule["max_participants"] is not None:
                assert len(ps) <= rule["max_participants"]
            if rule["relationship_required"] == "couple":
                assert frozenset(ps) in couples
            if rule["type"] == "basketball":
                assert d.weekday() >= 5
        for c in chars:
            assert_no_overlap(events, c.id)
    assert total > 0
    if n == 5:
        assert max(sizes) > 2  # 支援 2..N 人


def test_shared_uses_world_seed_not_character_order():
    world, chars, rels = demo_world(5)
    world = _always_shared(world)
    d = date(2026, 10, 10)
    a = [e.to_dict() for e in generate_daily_plan(world, chars, rels, d) if e.kind == "shared"]
    b = [e.to_dict() for e in generate_daily_plan(world, chars[::-1], rels, d) if e.kind == "shared"]
    assert a and a == b


def test_relationship_required_blocks_date_without_couple():
    world, chars, rels = demo_world(3)
    friends_only = [
        CharacterRelationship(r.character_a_id, r.character_b_id, "friend", world_id=world.id) for r in rels
    ]
    only_date = [r for r in world.shared_event_config["rules"] if r["type"] == "date"]
    world = _always_shared(world, rules=only_date)
    for d in days(date(2026, 10, 1), 30):
        assert not [e for e in generate_daily_plan(world, chars, friends_only, d) if e.kind == "shared"]
    # 有 couple 關係時則會產生
    assert any(
        e.kind == "shared" for d in days(date(2026, 10, 1), 30) for e in generate_daily_plan(world, chars, rels, d)
    )


def test_shared_event_displaces_lower_priority_but_not_meals():
    world, chars, rels = demo_world(2)
    world = _always_shared(world)
    for d in days(date(2026, 10, 1), 30):
        events = generate_daily_plan(world, chars, rels, d)
        for s in (e for e in events if e.kind == "shared"):
            for m in (e for e in events if e.kind == "meal" and set(e.participants) & set(s.participants)):
                assert not (s.start_at < m.end_at and m.start_at < s.end_at)
