"""Adapter around worldpane-core: server domain records <-> core models.

Configuration comes from the database (profiles, event catalog, world shared settings); this
module only assembles it with ``worldpane_core.catalog`` and maps types. No rules live here.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

import worldpane_core as core
from worldpane_core.catalog import build_event_config, build_shared_event_config

from ..domain import Character, CharacterRelationship, Event, World
from .provider import CharacterNow

log = logging.getLogger(__name__)


def _skip(owner: str):
    """Bad catalog data (after all overrides) is logged and skipped, never a 500."""
    return lambda error: log.warning("skipping invalid event for %s: %s", owner, error)


def to_core_world(world: World) -> core.World:
    return core.World(
        id=world.id,
        name=world.name,
        simulation_start_date=world.simulation_start_date,
        timezone=world.timezone,
        simulation_version=str(world.simulation_version),
        shared_event_config=build_shared_event_config(
            world.shared_event_config, world.shared_event_definitions, on_invalid=_skip(f"world {world.id}")
        ),
    )


def to_core_character(c: Character) -> core.Character:
    p = c.profile
    profile = core.CharacterProfile(
        id=p.id,
        schedule_config=p.schedule_config,
        meal_config=p.meal_config,
        leave_config=p.leave_config,
        event_config=build_event_config(p.event_config, p.event_pool, on_invalid=_skip(f"profile {p.id}")),
    )
    return core.Character(
        id=c.id, world_id=c.world_id, appearance_key=c.appearance_key,
        display_name=c.display_name, profile=profile,
    )


def _to_core_event(e: Event) -> core.Event:
    return core.Event(
        id=e.id, world_id=e.world_id, type=e.type, scene=e.scene, location=e.location or "",
        activity=e.activity, start_at=e.start_at, end_at=e.end_at, priority=e.priority,
        participants=list(e.participant_ids), metadata=dict(e.metadata),
        simulation_version=str(e.simulation_version), layer=e.layer, status=e.status,
    )


class CoreSimulationProvider:
    def generate_daily_plan(
        self,
        world: World,
        characters: list[Character],
        relationships: list[CharacterRelationship],
        local_date: date,
    ) -> list[Event]:
        rels = [
            core.CharacterRelationship(
                id=r.id, world_id=r.world_id, character_a_id=r.character_a_id,
                character_b_id=r.character_b_id, relationship_type=r.relationship_type,
            )
            for r in relationships
        ]
        events = core.generate_daily_plan(
            to_core_world(world), [to_core_character(c) for c in characters], rels, local_date
        )
        return [
            Event(
                id=e.id, world_id=world.id, type=e.type, scene=e.scene, activity=e.activity,
                start_at=e.start_at, end_at=e.end_at, participant_ids=list(e.participants),
                local_date=local_date, simulation_version=world.simulation_version,
                priority=int(e.priority), status=e.status, metadata=dict(e.metadata),
                location=e.location, layer=e.layer,
            )
            for e in events
        ]

    def current_state(
        self, events: list[Event], now: datetime, character_ids: list[str]
    ) -> dict[str, CharacterNow]:
        states = core.current_state([_to_core_event(e) for e in events], now, character_ids)
        return {
            cid: CharacterNow(
                scene=s.scene, activity=s.activity, location=s.location,
                started_at=s.started_at, ends_at=s.ends_at, event_id=s.event_id,
            )
            for cid, s in states.items()
        }
