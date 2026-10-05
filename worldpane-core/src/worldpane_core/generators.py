"""各階段 Generator（規格 §15 step 3–7）。

每個 generator 只接收自己的 random.Random 實例，不使用全域 random。
"""

from __future__ import annotations

import random
from typing import Any

from .calendar_ctx import CalendarContext, DayContext
from .draft import Draft, is_free
from .models import Character, CharacterRelationship, EventKind, Layer, Priority, World
from .catalog import for_context
from .seeds import weighted_choice
from .timeutil import parse_window

# ---------------------------------------------------------------------------
# Step 3: Base Schedule（§9：location + activity 拆分）
# ---------------------------------------------------------------------------


def build_base_schedule(character: Character, ctx: DayContext) -> list[Draft]:
    if ctx.on_leave:
        return []  # 請假日：沒有上學 / 上班 Base Schedule
    drafts: list[Draft] = []
    weekday = ctx.calendar.local_date.weekday()
    for block in character.profile.schedule_config.get("blocks", []):
        if weekday not in block.get("days", []):
            continue
        if ctx.calendar.holiday and not block.get("include_holidays", False):
            continue
        start, end = parse_window([block["start"], block["end"]])
        drafts.append(
            Draft(
                kind=EventKind.BASE,
                type=block["type"],
                label=block.get("label", block["type"]),
                scene=block.get("scene", block["location"].lower()),
                location=block["location"],
                activity=block.get("activity", block["type"]),
                start=start,
                end=end,
                priority=Priority.FIXED,
                participants=(character.id,),
                layer=Layer.BASE,
                metadata={
                    "resume_label": block.get("resume_label"),
                    "end_label": block.get("end_label"),
                    "meal_location": block.get("meal_location", block["location"]),
                    "meal_scene": block.get("meal_scene", block.get("scene")),
                },
            )
        )
    return sorted(drafts, key=lambda d: d.start)


def _base_at(base: list[Draft], minute: int) -> Draft | None:
    for b in base:
        if b.start <= minute < b.end:
            return b
    return None


# ---------------------------------------------------------------------------
# Step 4: Meals（§8）
# ---------------------------------------------------------------------------


def generate_meals(rng: random.Random, character: Character, base: list[Draft]) -> list[Draft]:
    cfg = character.profile.meal_config
    gap = int(cfg.get("min_gap_min", 90))
    meals = sorted(cfg.get("meals", []), key=lambda m: parse_window(m["window"])[0])
    drafts: list[Draft] = []
    prev_end: int | None = None
    for index, meal in enumerate(meals):
        w_start, w_end = parse_window(meal["window"])
        # 固定抽取順序：skip → duration → start
        skipped = rng.random() < float(meal.get("skip_probability", 0.0))
        duration = rng.randint(int(meal.get("min_duration", 15)), int(meal.get("max_duration", 20)))
        if skipped:
            prev_end = None  # 上一餐跳過 → 不套用 +90 分鐘限制
            continue
        earliest = w_start if prev_end is None else max(w_start, prev_end + gap)
        if earliest > w_end:
            # 上一餐太晚，本餐已無合法開始時間 → 本餐不發生（視同跳過）
            prev_end = None
            continue
        start = rng.randint(earliest, w_end)
        end = start + duration  # 結束時間可超出 window 尾端
        block = _base_at(base, start)
        if block is not None:
            location = block.metadata["meal_location"]
            scene = block.metadata["meal_scene"]
        else:
            location = cfg.get("home_location", "HOME")
            scene = cfg.get("home_scene", "home_kitchen")
        drafts.append(
            Draft(
                kind=EventKind.MEAL,
                type=meal["type"],
                label=meal.get("label", meal["type"]),
                scene=scene,
                location=location,
                activity="eating",
                start=start,
                end=end,
                priority=Priority.MEAL,
                participants=(character.id,),
                overlay_base=True,
                move_window=None,
                metadata={"meal_index": index, "window": list(meal["window"])},
            )
        )
        prev_end = end
    return drafts


# ---------------------------------------------------------------------------
# Step 5: Work / School temporary events（§7、§9）
# ---------------------------------------------------------------------------


def generate_temporary(
    rng: random.Random, character: Character, base: list[Draft], existing: list[Draft]
) -> list[Draft]:
    cfg = character.profile.event_config.get("temporary") or {}
    defs = for_context(cfg.get("events", []), None)
    if not defs or not base:
        return []
    attempts = int(cfg.get("attempts_per_block", 0))
    trigger = float(cfg.get("trigger_probability", 0.0))
    placed: list[Draft] = []
    for block in base:
        for _ in range(attempts):
            if rng.random() >= trigger:
                continue
            ev = weighted_choice(rng, defs)
            duration = rng.randint(int(ev["min_duration"]), int(ev["max_duration"]))
            latest = block.end - duration
            if latest < block.start:
                continue
            for _try in range(6):
                start = rng.randint(block.start, latest)
                end = start + duration
                cooldown = int(ev.get("cooldown_min", 0))
                # 同類事件需相隔 cooldown（雙向檢查，因為 start 是隨機位置而非依時間序）
                if any(p.type == ev["type"] and start < p.end + cooldown and p.start < end + cooldown for p in placed):
                    continue
                if not is_free(
                    character.id, start, end, existing + placed,
                    blocking_priority=Priority.LEISURE, overlay_base=True,
                ):
                    continue
                placed.append(
                    Draft(
                        kind=EventKind.TEMPORARY,
                        type=ev["type"],
                        label=ev.get("label", ev["type"]),
                        scene=block.scene,
                        location=block.location,
                        activity=ev.get("activity", ev["type"]),
                        start=start,
                        end=end,
                        priority=Priority.TEMPORARY,
                        participants=(character.id,),
                        overlay_base=True,
                        move_window=(block.start, latest),
                        metadata={"base_type": block.type},
                    )
                )
                break
    return placed


# ---------------------------------------------------------------------------
# Step 6: Evening / Holiday individual events（§10、§13）
# ---------------------------------------------------------------------------


def _allowed_end(ev: dict[str, Any], minute: int) -> tuple[int, int] | None:
    """回傳包含 minute 的 allowed_time window。"""
    for w in ev.get("allowed_time", [["00:00", "24:00"]]):
        s, e = parse_window(w)
        if s <= minute < e:
            return s, e
    return None


def generate_leisure(
    rng: random.Random, character: Character, ctx: DayContext, existing: list[Draft]
) -> list[Draft]:
    cfg = character.profile.event_config.get("leisure") or {}
    defs = for_context(cfg.get("events", []), ctx.key)
    windows_cfg = cfg.get("windows", {})
    windows = windows_cfg.get(ctx.key)
    if windows is None and ctx.key == "leave":
        windows = windows_cfg.get("holiday")
    if not defs or not windows:
        return []
    gap_min = int(cfg.get("gap_min", 0))
    gap_max = int(cfg.get("gap_max", 30))
    placed: list[Draft] = []
    last_end: dict[str, int] = {}

    def busy() -> list[Draft]:
        return [d for d in existing + placed if character.id in d.participants]

    for window in windows:
        ws, we = parse_window(window)
        cursor = ws
        guard = 0
        while cursor < we and guard < 500:
            guard += 1
            cursor += rng.randint(gap_min, gap_max)
            if cursor >= we:
                break
            current_busy = busy()
            blocking = [b for b in current_busy if b.start <= cursor < b.end]
            if blocking:
                cursor = max(b.end for b in blocking)
                continue
            next_busy = min((b.start for b in current_busy if b.start > cursor), default=we)
            limit = min(we, next_busy)
            eligible = []
            for ev in defs:
                aw = _allowed_end(ev, cursor)
                if aw is None:
                    continue
                if min(limit, aw[1]) - cursor < int(ev["min_duration"]):
                    continue
                prev = last_end.get(ev["type"])
                if prev is not None and cursor < prev + int(ev.get("cooldown_min", 0)):
                    continue
                eligible.append(ev)
            if not eligible:
                cursor += 15
                continue
            ev = weighted_choice(rng, eligible)
            duration = rng.randint(int(ev["min_duration"]), int(ev["max_duration"]))
            aw_start, aw_end = _allowed_end(ev, cursor)  # type: ignore[misc]
            end = min(cursor + duration, limit, aw_end)
            actual = end - cursor
            move_lo = max(ws, aw_start)
            move_hi = min(we, aw_end) - actual
            placed.append(
                Draft(
                    kind=EventKind.LEISURE,
                    type=ev["type"],
                    label=ev.get("label", ev["type"]),
                    scene=ev.get("scene", "home_living_room"),
                    location=ev.get("location", "HOME"),
                    activity=ev.get("activity", ev["type"]),
                    start=cursor,
                    end=end,
                    priority=Priority.LEISURE,
                    participants=(character.id,),
                    overlay_base=False,
                    move_window=(move_lo, move_hi) if move_hi >= move_lo else None,
                    metadata={},
                )
            )
            last_end[ev["type"]] = end
            cursor = end
    return placed


# ---------------------------------------------------------------------------
# Step 7: Shared / Group events（§11、§12）— World 層級，使用 shared seed
# ---------------------------------------------------------------------------


class RelationshipIndex:
    def __init__(self, relationships: list[CharacterRelationship]):
        self._pairs: dict[frozenset[str], set[str]] = {}
        for r in relationships:
            self._pairs.setdefault(r.pair(), set()).add(r.relationship_type)

    def types(self, a: str, b: str) -> set[str]:
        return self._pairs.get(frozenset((a, b)), set())

    def satisfies(self, a: str, b: str, required: str | None) -> bool:
        if required is None:
            return True
        types = self.types(a, b)
        if required == "any":
            return bool(types)
        return required in types


def _build_group(
    rng: random.Random, free: list[str], rule: dict[str, Any], rels: RelationshipIndex
) -> list[str] | None:
    min_p = int(rule.get("min_participants", 2))
    max_p = rule.get("max_participants")
    max_p = len(free) if max_p is None else min(int(max_p), len(free))
    if max_p < min_p:
        return None
    target = rng.randint(min_p, max_p)
    order = list(free)
    rng.shuffle(order)
    required = rule.get("relationship_required")
    # 輪流以每位候選人作為起點，貪婪加入滿足 relationship constraint 的人
    for i in range(len(order)):
        rotated = order[i:] + order[:i]
        group: list[str] = []
        for cid in rotated:
            if len(group) >= target:
                break
            if all(rels.satisfies(cid, g, required) for g in group):
                group.append(cid)
        if len(group) >= min_p:
            return sorted(group)
    return None


def generate_shared(
    rng: random.Random,
    world: World,
    characters: list[Character],
    relationships: RelationshipIndex,
    calendar: CalendarContext,
    existing: list[Draft],
) -> list[Draft]:
    cfg = world.shared_event_config or {}
    rules = for_context(cfg.get("rules", []), calendar.key)
    n = len(characters)
    if n < 2 or not rules:
        return []
    attempts = int(cfg.get("attempts", 0))
    trigger = float(cfg.get("trigger_probability", 0.0))
    step = int(cfg.get("slot_step_min", 5))
    max_tries = int(cfg.get("max_slot_tries", 12))
    char_ids = [c.id for c in characters]
    placed: list[Draft] = []
    count: dict[str, int] = {}

    for _ in range(attempts):
        if rng.random() >= trigger:
            continue
        eligible = [
            r for r in rules
            if count.get(r["type"], 0) < int(r.get("max_per_day", 1))
            and n >= int(r.get("min_participants", 2))
        ]
        if not eligible:
            continue
        rule = weighted_choice(rng, eligible)
        duration = rng.randint(int(rule["min_duration"]), int(rule["max_duration"]))
        min_p = int(rule.get("min_participants", 2))
        cooldown = int(rule.get("cooldown_min", 0))
        all_drafts = existing + placed

        # 找出所有「至少 min_participants 人同時可用」的候選開始時間
        candidates: list[tuple[int, tuple[int, int], list[str]]] = []
        for window in rule.get("allowed_time", []):
            ws, we = parse_window(window)
            for start in range(ws, we - duration + 1, step):
                end = start + duration
                if any(
                    p.type == rule["type"] and start < p.end + cooldown and p.start < end + cooldown
                    for p in placed
                ):
                    continue
                free = [
                    cid for cid in char_ids
                    if is_free(cid, start, end, all_drafts,
                               blocking_priority=Priority.SHARED, overlay_base=False)
                ]
                if len(free) >= min_p:
                    candidates.append((start, (ws, we), free))
        tries = 0
        while candidates and tries < max_tries:
            tries += 1
            start, (ws, we), free = candidates.pop(rng.randrange(len(candidates)))
            group = _build_group(rng, free, rule, relationships)
            if group is None:
                continue
            # 成功 → 一次鎖定所有 Participant
            placed.append(
                Draft(
                    kind=EventKind.SHARED,
                    type=rule["type"],
                    label=rule.get("label", rule["type"]),
                    scene=rule.get("scene", rule["type"]),
                    location=rule.get("location", "HOME"),
                    activity=rule.get("activity", rule["type"]),
                    start=start,
                    end=start + duration,
                    priority=Priority.SHARED,
                    participants=tuple(group),
                    overlay_base=False,
                    move_window=(ws, we - duration),
                    metadata={
                        "relationship_required": rule.get("relationship_required"),
                        "min_participants": min_p,
                        "max_participants": rule.get("max_participants"),
                    },
                )
            )
            count[rule["type"]] = count.get(rule["type"], 0) + 1
            break
    return placed
