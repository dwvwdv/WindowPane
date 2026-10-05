"""Official default content (spec §7) and the dev demo world.

The defaults are *data*, not code paths: any number of characters can be added to a World
and nothing downstream assumes there are exactly two.
"""

from __future__ import annotations

from datetime import date, datetime

from .domain import Character, CharacterProfile, CharacterRelationship, World
from .repositories.base import Repository
from .security import new_id

DEMO_WORLD_ID = "wld_demo"


def official_default_characters(world_id: str) -> list[Character]:
    """小白 (student profile) + 小雞毛 (office-worker profile), as fresh instances for ``world_id``."""
    student = CharacterProfile(
        id="profile_student_default",
        schedule_config={
            "weekdays": [0, 1, 2, 3, 4],
            "day_block": {
                "type": "school",
                "scene": "school_classroom",
                "activity": "attending_class",
                "lunch_scene": "school_cafeteria",
                "start": "08:30",
                "end": "17:30",
            },
        },
        # TBD values from spec §34 stay unset; worldpane-core owns them.
        leave_config={"mode": "calendar_month", "max_per_month": 1, "probability": None},
        event_config={"evening_activity": "reading", "free_time_activity": "playing_games"},
    )
    office = CharacterProfile(
        id="profile_office_worker_default",
        schedule_config={
            "weekdays": [0, 1, 2, 3, 4],
            "day_block": {
                "type": "work",
                "scene": "office_desk",
                "activity": "working",
                "lunch_scene": "office_pantry",
                "start": "08:30",
                "end": "17:30",
            },
        },
        leave_config={"mode": "fixed_cycle", "cycle_days": 14, "max_per_cycle": 1, "probability": None},
        event_config={"evening_activity": "watching_videos", "free_time_activity": "relaxing"},
    )
    return [
        Character(id=new_id("chr"), world_id=world_id, appearance_key="xiaobai",
                  display_name="小白", profile=student, sort_order=0),
        Character(id=new_id("chr"), world_id=world_id, appearance_key="xiaojimao",
                  display_name="小雞毛", profile=office, sort_order=1),
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
    world = World(
        id=world_id,
        name=name,
        timezone=timezone,
        simulation_version=1,
        simulation_start_date=start_date,
        created_at=created_at,
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
                id=new_id("rel"), world_id=world_id, character_a_id=a.id, character_b_id=b.id,
                relationship_type=rel_type, affinity=0.0,
            ))
    return world
