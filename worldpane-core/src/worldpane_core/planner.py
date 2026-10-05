"""Daily Plan Generator（規格 §15）。

生成順序（§15）：
1. Resolve Calendar Context
2. Resolve Leave
3. Build Base Schedule
4. Generate Meals
5. Generate Work / School temporary events
6. Generate Evening / Holiday individual events
7. Generate Shared Events（World 層級，shared seed）
8. Resolve Conflicts
9. Persist Events（本套件不碰 DB；回傳 Event list 由呼叫端持久化）

角色數量為 1..N，任何地方都不假設 2 人。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date

from .calendar_ctx import CalendarContext, DayContext, resolve_calendar_context
from .conflicts import resolve_conflicts
from .draft import Draft
from .generators import (
    RelationshipIndex,
    build_base_schedule,
    generate_leisure,
    generate_meals,
    generate_shared,
    generate_temporary,
)
from .leave import is_on_leave
from .models import Character, CharacterRelationship, Event, World
from .seeds import character_seed, make_rng, shared_seed
from .timeutil import to_datetime

_EVENT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://worldpane/events")


@dataclass
class DailyPlan:
    world_id: str
    local_date: date
    calendar: CalendarContext
    contexts: dict[str, DayContext]
    events: list[Event]
    cancelled: list[Event] = field(default_factory=list)


def _validate(world: World, characters: list[Character]) -> list[Character]:
    seen: set[str] = set()
    for c in characters:
        if c.world_id != world.id:
            raise ValueError(f"character {c.id} belongs to world {c.world_id}, not {world.id}")
        if c.id in seen:
            raise ValueError(f"duplicate character id: {c.id}")
        seen.add(c.id)
    # 輸入順序不影響結果
    return sorted(characters, key=lambda c: c.id)


def _to_event(world: World, local_date: date, d: Draft, original_start: int, status: str = "scheduled") -> Event:
    key = "|".join(
        [
            world.id,
            local_date.isoformat(),
            str(world.simulation_version),
            d.kind,
            d.type,
            str(original_start),
            ",".join(d.participants),
            str(d.seq),
        ]
    )
    tz = world.tz
    metadata = {"kind": d.kind, "label": d.label, "local_date": local_date.isoformat()}
    metadata.update({k: v for k, v in d.metadata.items() if v is not None})
    return Event(
        id=str(uuid.uuid5(_EVENT_NAMESPACE, key)),
        world_id=world.id,
        type=d.type,
        scene=d.scene,
        location=d.location,
        activity=d.activity,
        start_at=to_datetime(local_date, d.start, tz),
        end_at=to_datetime(local_date, d.end, tz),
        priority=int(d.priority),
        participants=list(d.participants),
        metadata=metadata,
        simulation_version=str(world.simulation_version),
        layer=d.layer,
        status=status,
    )


def plan_day(
    world: World,
    characters: list[Character],
    relationships: list[CharacterRelationship],
    local_date: date,
) -> DailyPlan:
    chars = _validate(world, characters)
    ids = {c.id for c in chars}
    rels = RelationshipIndex(
        [r for r in relationships if r.character_a_id in ids and r.character_b_id in ids]
    )
    version = str(world.simulation_version)

    # 1. Calendar Context
    calendar = resolve_calendar_context(local_date, world.holiday_dates)

    # 2. Leave
    contexts = {c.id: DayContext(calendar=calendar, on_leave=is_on_leave(world, c, local_date)) for c in chars}
    seeds = {c.id: character_seed(world.id, c.id, local_date, version) for c in chars}

    seq = 0
    all_drafts: list[Draft] = []

    def register(new: list[Draft]) -> list[Draft]:
        nonlocal seq
        for d in new:
            d.seq = seq
            seq += 1
        all_drafts.extend(new)
        return new

    # 3. Base Schedule
    base = {c.id: register(build_base_schedule(c, contexts[c.id])) for c in chars}
    # 4. Meals
    meals = {
        c.id: register(generate_meals(make_rng(seeds[c.id], "meals"), c, base[c.id])) for c in chars
    }
    # 5. Work / School temporary events
    temps = {
        c.id: register(
            generate_temporary(make_rng(seeds[c.id], "temporary"), c, base[c.id], meals[c.id])
        )
        for c in chars
    }
    # 6. Evening / Holiday individual events
    for c in chars:
        register(
            generate_leisure(
                make_rng(seeds[c.id], "leisure"),
                c,
                contexts[c.id],
                base[c.id] + meals[c.id] + temps[c.id],
            )
        )
    # 7. Shared / Group events（World 層級 seed，不依賴任何一位角色當主角）
    register(
        generate_shared(
            make_rng(shared_seed(world.id, local_date, version)),
            world,
            chars,
            rels,
            calendar,
            list(all_drafts),
        )
    )

    # 8. Resolve Conflicts
    original_starts = {id(d): d.start for d in all_drafts}
    kept, cancelled = resolve_conflicts(all_drafts)

    events = [_to_event(world, local_date, d, original_starts[id(d)]) for d in kept]
    events.sort(key=lambda e: (e.start_at, e.priority, e.participants, e.type))
    cancelled_events = [
        _to_event(world, local_date, d, original_starts[id(d)], status="cancelled") for d in cancelled
    ]
    return DailyPlan(
        world_id=world.id,
        local_date=local_date,
        calendar=calendar,
        contexts=contexts,
        events=events,
        cancelled=cancelled_events,
    )


def generate_daily_plan(
    world: World,
    characters: list[Character],
    relationships: list[CharacterRelationship],
    local_date: date,
) -> list[Event]:
    """公開 API：給定 World + Characters + Relationships + 當地日期 → 當日所有 Event。

    相同輸入（含 simulation_version）永遠得到相同結果。
    """
    return plan_day(world, characters, relationships, local_date).events


__all__ = ["DailyPlan", "plan_day", "generate_daily_plan"]
