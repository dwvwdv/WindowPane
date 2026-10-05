from collections import Counter
from datetime import date, timedelta

from worldpane_core import demo_world, plan_day
from worldpane_core.leave import (
    cycle_bounds,
    cycle_index_for,
    cycle_leave_days,
    is_on_leave,
    monthly_leave_days,
)

from helpers import days, with_profile


def _leave_cfg(c, **kw):
    cfg = dict(c.profile.leave_config)
    cfg.update(kw)
    return with_profile(c, leave_config=cfg)


def test_monthly_leave_at_most_one_per_month_across_year():
    world, chars, _ = demo_world(1)
    xiaobai = chars[0]
    per_month = Counter(d.month for d in days(date(2026, 1, 1), 365) if is_on_leave(world, xiaobai, d))
    assert all(v <= 1 for v in per_month.values())


def test_monthly_leave_probability_one_exactly_one_weekday_each_month():
    world, chars, _ = demo_world(1)
    c = _leave_cfg(chars[0], probability=1.0)
    leaves = [d for d in days(date(2026, 1, 1), 365) if is_on_leave(world, c, d)]
    assert len(leaves) == 12
    assert len({d.month for d in leaves}) == 12
    assert all(d.weekday() < 5 for d in leaves)
    # 與查詢日無關：月份的決策只依 (world, character, year-month, version)
    assert monthly_leave_days(world, c, 2026, 3) == monthly_leave_days(world, c, 2026, 3)


def test_monthly_leave_probability_zero_never():
    world, chars, _ = demo_world(1)
    c = _leave_cfg(chars[0], probability=0.0)
    assert not any(is_on_leave(world, c, d) for d in days(date(2026, 1, 1), 365))


def test_leave_day_has_no_base_schedule():
    world, chars, rels = demo_world(2)
    chars = [_leave_cfg(chars[0], probability=1.0), _leave_cfg(chars[1], probability=1.0)]
    found = 0
    for d in days(date(2026, 10, 1), 60):
        plan = plan_day(world, chars, rels, d)
        for c in chars:
            if plan.contexts[c.id].on_leave:
                found += 1
                assert not [e for e in plan.events if c.id in e.participants and e.kind in ("base", "temporary")]
    assert found >= 4


def test_cycle_leave_at_most_one_per_cycle_and_anchor_not_reset():
    world, chars, _ = demo_world(2)
    xjm = _leave_cfg(chars[1], probability=1.0)
    anchor = world.simulation_start_date
    leaves = [d for d in days(anchor, 14 * 26) if is_on_leave(world, xjm, d)]
    # probability=1 → 每個 cycle 恰好一天
    assert len(leaves) == 26
    per_cycle = Counter((d - anchor).days // 14 for d in leaves)
    assert set(per_cycle) == set(range(26))
    assert all(v == 1 for v in per_cycle.values())
    # Cycle 邊界只由 anchor 決定，不因請假日改變
    for d in leaves:
        k = cycle_index_for(world, xjm, d)
        start, end = cycle_bounds(world, xjm, k)
        assert start == anchor + timedelta(days=14 * k)
        assert start <= d <= end
        assert d.weekday() < 5
    # 若 cycle 從請假日重新起算，相鄰請假日間隔必 >= 14；固定 anchor 下可以 < 14
    gaps = [(b - a).days for a, b in zip(leaves, leaves[1:])]
    assert min(gaps) < 14


def test_cycle_leave_default_probability_respects_max():
    world, chars, _ = demo_world(2)
    xjm = chars[1]
    anchor = world.simulation_start_date
    leaves = [d for d in days(anchor, 14 * 26) if is_on_leave(world, xjm, d)]
    per_cycle = Counter((d - anchor).days // 14 for d in leaves)
    assert all(v <= 1 for v in per_cycle.values())


def test_cycle_custom_anchor_and_negative_index():
    world, chars, _ = demo_world(2)
    xjm = _leave_cfg(chars[1], probability=1.0, anchor_date="2026-10-05")
    assert cycle_index_for(world, xjm, date(2026, 10, 4)) == -1
    assert cycle_bounds(world, xjm, 0) == (date(2026, 10, 5), date(2026, 10, 18))
    assert len(cycle_leave_days(world, xjm, -1)) == 1
