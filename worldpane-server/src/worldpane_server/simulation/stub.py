"""A deliberately small, deterministic stand-in for worldpane-core.

It produces a plausible full-day timeline per character so the Display/History API can be
developed end to end. It is NOT the V1 simulation: no leave rules, no meal skip, no
temporary events, no conflict resolver. It only reads a couple of generic profile keys
(``schedule_config.day_block`` / ``weekdays``) and never branches on character identity.

Seeds follow spec §15:
  character-local: hash(world_id + character_id + local_date + simulation_version)
  shared:          hash(world_id + local_date + "shared" + simulation_version)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ..domain import Character, CharacterRelationship, Event, World

HOME_SCENES = {
    "bedroom": "home_bedroom",
    "bathroom": "home_bathroom",
    "living": "home_living_room",
    "dining": "home_dining_room",
}


def _seed(*parts: object) -> bytes:
    return hashlib.sha256("|".join(str(p) for p in parts).encode("utf-8")).digest()


class _Rng:
    """Tiny deterministic integer source derived from a seed (no global random state)."""

    def __init__(self, seed: bytes) -> None:
        self._seed = seed
        self._n = 0

    def randint(self, lo: int, hi: int) -> int:
        self._n += 1
        h = hashlib.sha256(self._seed + self._n.to_bytes(4, "big")).digest()
        return lo + int.from_bytes(h[:8], "big") % (hi - lo + 1)


@dataclass
class _Slot:
    start: int  # minutes since local midnight
    end: int
    type: str
    scene: str
    activity: str
    priority: int = 0


def _hm(value: str) -> int:
    h, m = value.split(":")
    return int(h) * 60 + int(m)


class StubSimulationProvider:
    def generate_daily_plan(
        self,
        world: World,
        characters: list[Character],
        relationships: list[CharacterRelationship],
        local_date: date,
    ) -> list[Event]:
        tz = ZoneInfo(world.timezone)
        shared_rng = _Rng(_seed(world.id, local_date.isoformat(), "shared", world.simulation_version))
        evening_shared_start = _hm("20:00") + shared_rng.randint(0, 10)
        has_group = len(characters) >= 2

        events: list[Event] = []
        evening_slots: dict[str, list[_Slot]] = {}
        for char in characters:
            rng = _Rng(_seed(world.id, char.id, local_date.isoformat(), world.simulation_version))
            slots = self._character_day(char, local_date, rng, evening_shared_start, has_group)
            evening_slots[char.id] = slots
            for idx, s in enumerate(slots):
                events.append(self._event(world, local_date, tz, s, [char.id], f"{char.id}:{idx}"))

        if has_group:
            movie = _Slot(evening_shared_start, evening_shared_start + 100, "shared", HOME_SCENES["living"],
                          "watching_movie", priority=10)
            events.append(
                self._event(world, local_date, tz, movie, [c.id for c in characters], "shared:movie")
            )

        events.sort(key=lambda e: (e.start_at, e.id))
        return events

    def current_state(self, events: list[Event], now: datetime) -> dict[str, Event]:
        result: dict[str, Event] = {}
        for ev in events:
            if not (ev.start_at <= now < ev.end_at):
                continue
            for cid in ev.participant_ids:
                cur = result.get(cid)
                if cur is None or (ev.priority, ev.start_at) > (cur.priority, cur.start_at):
                    result[cid] = ev
        return result

    # ------------------------------------------------------------------------------------
    def _character_day(
        self, char: Character, local_date: date, rng: _Rng, shared_start: int, has_group: bool
    ) -> list[_Slot]:
        sched = char.profile.schedule_config
        block = sched.get("day_block")
        weekdays = sched.get("weekdays", [0, 1, 2, 3, 4])
        working_day = bool(block) and local_date.weekday() in weekdays
        leisure = char.profile.event_config.get("evening_activity", "reading")
        free_time = char.profile.event_config.get("free_time_activity", "relaxing")

        s: list[_Slot] = []
        if working_day:
            wake = _hm("07:20") + rng.randint(0, 20)
            start, end = _hm(block.get("start", "08:30")), _hm(block.get("end", "17:30"))
            lunch = _hm("12:00") + rng.randint(0, 30)
            lunch_end = lunch + rng.randint(15, 20)
            s += [
                _Slot(0, wake, "sleep", HOME_SCENES["bedroom"], "sleeping"),
                _Slot(wake, start - 30, "routine", HOME_SCENES["bathroom"], "getting_ready"),
                _Slot(start - 30, start, "commute", "street", "commuting"),
                _Slot(start, lunch, block["type"], block["scene"], block["activity"]),
                _Slot(lunch, lunch_end, "meal", block.get("lunch_scene", block["scene"]), "eating_lunch"),
                _Slot(lunch_end, end, block["type"], block["scene"], block["activity"]),
                _Slot(end, end + 30, "commute", "street", "commuting"),
            ]
            cursor = end + 30
        else:
            wake = _hm("09:00") + rng.randint(0, 30)
            breakfast = wake + 20
            lunch = _hm("12:30") + rng.randint(0, 30)
            s += [
                _Slot(0, wake, "sleep", HOME_SCENES["bedroom"], "sleeping"),
                _Slot(wake, breakfast, "routine", HOME_SCENES["bathroom"], "getting_ready"),
                _Slot(breakfast, breakfast + 20, "meal", HOME_SCENES["dining"], "eating_breakfast"),
                _Slot(breakfast + 20, lunch, "leisure", HOME_SCENES["living"], free_time),
                _Slot(lunch, lunch + 20, "meal", HOME_SCENES["dining"], "eating_lunch"),
            ]
            cursor = lunch + 20

        dinner = max(cursor, _hm("18:30") + rng.randint(0, 20))
        dinner_end = dinner + rng.randint(15, 20)
        if dinner > cursor:
            s.append(_Slot(cursor, dinner, "leisure", HOME_SCENES["living"], free_time))
        s.append(_Slot(dinner, dinner_end, "meal", HOME_SCENES["dining"], "eating_dinner"))
        bed = _hm("23:00") + rng.randint(0, 30)
        if has_group:
            # Individual slots leave a hole for the shared event generated at World level.
            s.append(_Slot(dinner_end, shared_start, "leisure", HOME_SCENES["living"], leisure))
            s.append(_Slot(shared_start + 100, bed, "leisure", HOME_SCENES["bedroom"], "using_phone"))
        else:
            s.append(_Slot(dinner_end, bed, "leisure", HOME_SCENES["living"], leisure))
        s.append(_Slot(bed, 24 * 60, "sleep", HOME_SCENES["bedroom"], "sleeping"))
        return [x for x in s if x.end > x.start]

    @staticmethod
    def _event(world: World, local_date: date, tz: ZoneInfo, slot: _Slot, participants: list[str],
               key: str) -> Event:
        midnight = datetime.combine(local_date, time(0), tzinfo=tz)

        def at(minutes: int) -> datetime:
            if minutes >= 24 * 60:
                nxt = datetime.combine(local_date + timedelta(days=1), time(0), tzinfo=tz)
                return nxt.astimezone(timezone.utc)
            return (midnight + timedelta(minutes=minutes)).astimezone(timezone.utc)

        eid = "evt_" + hashlib.sha256(
            f"{world.id}|{local_date.isoformat()}|{world.simulation_version}|{key}".encode()
        ).hexdigest()[:16]
        return Event(
            id=eid,
            world_id=world.id,
            type=slot.type,
            scene=slot.scene,
            activity=slot.activity,
            start_at=at(slot.start),
            end_at=at(slot.end),
            participant_ids=list(participants),
            local_date=local_date,
            simulation_version=world.simulation_version,
            priority=slot.priority,
            metadata={"generator": "stub"},
        )
