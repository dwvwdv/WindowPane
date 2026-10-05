"""Leave Generator（規格 §7、§15 step 2）。

兩種規則：
- monthly：每個 Calendar Month 最多 max_per_month 天（預設 1）。是否請假與請哪天，
  以 hash(world, character, "leave-month", YYYY-MM, version) 決定 → 對同一個月份永遠相同，
  與「目前查詢的是哪一天」無關。
- cycle：固定 Anchor Date 的 N 天 Cycle（預設 14 天）。cycle_index = (date - anchor) // N，
  以 cycle_index 作為 seed，Anchor 不因實際請假而重置。

可請假日 = 該角色在此日原本會有 Base Schedule 的日子（Profile 排班日且非 holiday）。
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

from .calendar_ctx import resolve_calendar_context
from .models import Character, World
from .seeds import seed_from, make_rng


def has_scheduled_block(schedule_config: dict[str, Any], world: World, d: date) -> bool:
    """此日是否有 Base Schedule（不考慮請假）。"""
    cal = resolve_calendar_context(d, world.holiday_dates)
    for block in schedule_config.get("blocks", []):
        if d.weekday() not in block.get("days", []):
            continue
        if cal.holiday and not block.get("include_holidays", False):
            continue
        return True
    return False


def _pick(rng, eligible: list[date], probability: float, max_count: int) -> list[date]:
    # 先抽「是否請假」，再抽日期；兩次抽取順序固定以確保可重現。
    roll = rng.random()
    if not eligible or max_count <= 0 or roll >= probability:
        return []
    k = min(max_count, len(eligible))
    return sorted(rng.sample(eligible, k))


def monthly_leave_days(world: World, character: Character, year: int, month: int) -> list[date]:
    cfg = character.profile.leave_config
    if cfg.get("type") != "monthly":
        return []
    _, ndays = calendar.monthrange(year, month)
    eligible = [
        date(year, month, day)
        for day in range(1, ndays + 1)
        if has_scheduled_block(character.profile.schedule_config, world, date(year, month, day))
    ]
    rng = make_rng(
        seed_from(world.id, character.id, "leave-month", f"{year:04d}-{month:02d}", world.simulation_version)
    )
    return _pick(rng, eligible, float(cfg.get("probability", 0.0)), int(cfg.get("max_per_month", 1)))


def cycle_anchor(world: World, character: Character) -> date:
    anchor = character.profile.leave_config.get("anchor_date")
    if anchor is None:
        return world.simulation_start_date
    if isinstance(anchor, date):
        return anchor
    return date.fromisoformat(str(anchor))


def cycle_index_for(world: World, character: Character, d: date) -> int:
    cycle_days = int(character.profile.leave_config.get("cycle_days", 14))
    return (d - cycle_anchor(world, character)).days // cycle_days  # floor：anchor 之前為負 index


def cycle_bounds(world: World, character: Character, cycle_index: int) -> tuple[date, date]:
    cycle_days = int(character.profile.leave_config.get("cycle_days", 14))
    start = cycle_anchor(world, character) + timedelta(days=cycle_index * cycle_days)
    return start, start + timedelta(days=cycle_days - 1)


def cycle_leave_days(world: World, character: Character, cycle_index: int) -> list[date]:
    cfg = character.profile.leave_config
    if cfg.get("type") != "cycle":
        return []
    start, end = cycle_bounds(world, character, cycle_index)
    eligible = []
    d = start
    while d <= end:
        if has_scheduled_block(character.profile.schedule_config, world, d):
            eligible.append(d)
        d += timedelta(days=1)
    rng = make_rng(seed_from(world.id, character.id, "leave-cycle", cycle_index, world.simulation_version))
    return _pick(rng, eligible, float(cfg.get("probability", 0.0)), int(cfg.get("max_per_cycle", 1)))


def is_on_leave(world: World, character: Character, d: date) -> bool:
    cfg = character.profile.leave_config
    kind = cfg.get("type", "none")
    if kind == "monthly":
        return d in monthly_leave_days(world, character, d.year, d.month)
    if kind == "cycle":
        return d in cycle_leave_days(world, character, cycle_index_for(world, character, d))
    return False
