from datetime import date

from worldpane_core import demo_world, generate_daily_plan
from worldpane_core.timeutil import parse_hhmm

from helpers import days, with_profile


def _minutes(dt):
    return dt.hour * 60 + dt.minute


def _meals(events, cid):
    return sorted(
        (e for e in events if e.kind == "meal" and cid in e.participants), key=lambda e: e.start_at
    )


def test_meals_in_window_duration_and_gap():
    world, chars, rels = demo_world(3)
    for d in days(date(2026, 10, 1), 120):
        events = generate_daily_plan(world, chars, rels, d)
        for c in chars:
            meals = _meals(events, c.id)
            for m in meals:
                lo, hi = (parse_hhmm(x) for x in m.metadata["window"])
                assert lo <= _minutes(m.start_at) <= hi
                assert 15 <= (m.end_at - m.start_at).total_seconds() / 60 <= 20
            for prev, nxt in zip(meals, meals[1:]):
                if nxt.metadata["meal_index"] == prev.metadata["meal_index"] + 1:
                    assert (nxt.start_at - prev.end_at).total_seconds() / 60 >= 90


def _set_skip(character, probs, windows=None):
    meal_config = dict(character.profile.meal_config)
    meal_config["meals"] = [dict(m) for m in meal_config["meals"]]
    for m, p in zip(meal_config["meals"], probs):
        m["skip_probability"] = p
    if windows:
        for m, w in zip(meal_config["meals"], windows):
            m["window"] = w
    return with_profile(character, meal_config=meal_config)


def test_skip_probability_one_means_no_meal():
    world, chars, rels = demo_world(2)
    chars = [_set_skip(c, [1.0, 0.0, 1.0]) for c in chars]
    for d in days(date(2026, 10, 1), 30):
        events = generate_daily_plan(world, chars, rels, d)
        for c in chars:
            assert [m.type for m in _meals(events, c.id)] == ["lunch"]


def test_skip_probability_zero_means_three_meals_never_cancelled():
    world, chars, rels = demo_world(5)
    chars = [_set_skip(c, [0.0, 0.0, 0.0]) for c in chars]
    for d in days(date(2026, 10, 1), 60):
        events = generate_daily_plan(world, chars, rels, d)
        for c in chars:
            assert [m.type for m in _meals(events, c.id)] == ["breakfast", "lunch", "dinner"]


def test_skipped_previous_meal_removes_gap_constraint():
    # 早餐只能 11:00 開始，午餐 11:30~12:00：若有吃早餐，午餐不可能滿足 +90 分鐘
    windows = [["11:00", "11:00"], ["11:30", "12:00"], ["17:00", "20:00"]]
    world, chars, rels = demo_world(1)
    eaten = [_set_skip(chars[0], [0.0, 0.0, 0.0], windows)]
    skipped = [_set_skip(chars[0], [1.0, 0.0, 0.0], windows)]
    for d in days(date(2026, 10, 1), 20):
        e1 = [m.type for m in _meals(generate_daily_plan(world, eaten, [], d), "char_1")]
        assert e1 == ["breakfast", "dinner"]  # 午餐無合法開始時間 → 不發生
        e2 = [m.type for m in _meals(generate_daily_plan(world, skipped, [], d), "char_1")]
        assert e2 == ["lunch", "dinner"]  # 早餐跳過 → 午餐不受 +90 限制


def test_meal_end_may_exceed_window():
    windows = [["08:00", "08:00"], ["13:59", "14:00"], ["20:00", "20:00"]]
    world, chars, rels = demo_world(1)
    c = [_set_skip(chars[0], [0.0, 0.0, 0.0], windows)]
    events = generate_daily_plan(world, c, [], date(2026, 10, 5))
    dinner = [m for m in _meals(events, "char_1") if m.type == "dinner"][0]
    assert dinner.start_at.strftime("%H:%M") == "20:00"
    assert dinner.end_at.strftime("%H:%M") > "20:00"
