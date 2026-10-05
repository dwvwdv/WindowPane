"""Official default content (spec §7) and the dev demo world.

Everything here is *data* taken from worldpane-core's official catalog / profiles — the same
source ``supabase/seed.sql`` is generated from — so in-memory and Postgres worlds behave
identically. Any number of characters can be added to a World; nothing assumes two.
"""

from __future__ import annotations

from datetime import date, datetime

from worldpane_core import defaults
from worldpane_core.catalog import (
    PoolEntry,
    official_definitions,
    official_profile_id,
    shared_settings,
    split_event_config,
)
from worldpane_core.profiles import OFFICIAL_PROFILES

from .domain import Character, CharacterProfile, CharacterRelationship, World
from .repositories.base import Repository
from .security import new_id

# Same fixed ids / start date as the demo world in supabase/seed.sql, so the in-memory and
# Postgres demo worlds produce the very same timelines.
DEMO_WORLD_ID = "00000000-0000-4000-a000-000000000001"
DEMO_CHARACTER_IDS = ("00000000-0000-4000-a000-000000000201", "00000000-0000-4000-a000-000000000202")
DEMO_START_DATE = date(2026, 10, 1)


def official_profile(key: str) -> CharacterProfile:
    name, factory = OFFICIAL_PROFILES[key]
    source = factory()
    settings, pool = split_event_config(source.event_config)
    defs = {(d.category, d.key): d for d in official_definitions()}
    return CharacterProfile(
        id=official_profile_id(key),
        key=key,
        name=name,
        schedule_config=source.schedule_config,
        meal_config=source.meal_config,
        leave_config=source.leave_config,
        event_config=settings,
        event_pool=[PoolEntry(defs[(cat, k)], overrides) for cat, k, overrides in pool],
    )


def official_shared_definitions():
    return [d for d in official_definitions() if d.category == "shared"]


def official_default_characters(world_id: str, ids: tuple[str, str] | None = None) -> list[Character]:
    """小白 (student profile) + 小雞毛 (office-worker profile), as fresh instances for ``world_id``."""
    a, b = ids or (new_id(), new_id())
    return [
        Character(id=a, world_id=world_id, appearance_key="xiaobai",
                  display_name="小白", profile=official_profile("official.student.v1"), sort_order=0),
        Character(id=b, world_id=world_id, appearance_key="xiaojimao",
                  display_name="小雞毛", profile=official_profile("official.office_worker.v1"), sort_order=1),
    ]


def create_world_with_defaults(
    repo: Repository,
    *,
    world_id: str,
    name: str,
    timezone: str,
    created_at: datetime,
    start_date: date,
    characters: list[Character] | None = None,
) -> World:
    shared = shared_settings(defaults.default_shared_event_config())
    shared["overrides"] = {}
    world = World(
        id=world_id,
        name=name,
        timezone=timezone,
        simulation_version=1,
        simulation_start_date=start_date,
        created_at=created_at,
        shared_event_config=shared,
        shared_event_definitions=official_shared_definitions(),
    )
    repo.create_world(world)
    chars = characters if characters is not None else official_default_characters(world_id)
    for c in chars:
        repo.add_character(c)
    # Pairwise relationships for every pair (2..N); demo default is "couple" only for exactly
    # the official pair — otherwise a neutral "friend". Purely data.
    for i, a in enumerate(chars):
        for b in chars[i + 1:]:
            rel_type = "couple" if {a.appearance_key, b.appearance_key} == {"xiaobai", "xiaojimao"} else "friend"
            repo.add_relationship(CharacterRelationship(
                id=new_id(), world_id=world_id, character_a_id=a.id, character_b_id=b.id,
                relationship_type=rel_type, affinity=0.0,
            ))
    return repo.get_world(world_id) or world
