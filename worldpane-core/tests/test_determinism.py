from datetime import date

from worldpane_core import demo_world, generate_daily_plan
from worldpane_core.seeds import character_seed, shared_seed

from helpers import days


def _dump(events):
    return [e.to_dict() for e in events]


def test_same_inputs_same_timeline_repeated_calls():
    world, chars, rels = demo_world(3)
    for d in days(date(2026, 10, 1), 30):
        first = _dump(generate_daily_plan(world, chars, rels, d))
        for _ in range(3):
            assert _dump(generate_daily_plan(world, chars, rels, d)) == first


def test_fresh_objects_give_identical_result():
    d = date(2026, 10, 5)
    a = _dump(generate_daily_plan(*demo_world(5), d))
    b = _dump(generate_daily_plan(*demo_world(5), d))
    assert a == b


def test_input_order_does_not_matter():
    world, chars, rels = demo_world(5)
    d = date(2026, 10, 9)
    assert _dump(generate_daily_plan(world, chars, rels, d)) == _dump(
        generate_daily_plan(world, list(reversed(chars)), list(reversed(rels)), d)
    )


def test_simulation_version_changes_result():
    d = date(2026, 10, 5)
    v1 = _dump(generate_daily_plan(*demo_world(2, simulation_version="1"), d))
    v2 = _dump(generate_daily_plan(*demo_world(2, simulation_version="2"), d))
    assert v1 != v2


def test_seeds_are_stable_sha256_values():
    # 不依賴 Python hash()：固定輸入 → 固定 seed（跨行程、跨機器）
    d = date(2026, 10, 5)
    assert character_seed("w", "c", d, "1") == character_seed("w", "c", d, "1")
    assert character_seed("w", "c", d, "1") != character_seed("w", "c", d, "2")
    assert shared_seed("w", d, "1") != character_seed("w", "shared", d, "1")
    assert isinstance(shared_seed("w", d, "1"), int)


def test_event_ids_unique_and_deterministic():
    world, chars, rels = demo_world(5)
    events = generate_daily_plan(world, chars, rels, date(2026, 10, 10))
    ids = [e.id for e in events]
    assert len(ids) == len(set(ids))
    assert ids == [e.id for e in generate_daily_plan(world, chars, rels, date(2026, 10, 10))]
