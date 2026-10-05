"""官方預設 Profile / 角色與示範 World（規格 §7）。

Simulation Engine 不認識「小白」「小雞毛」；這裡只是預設資料。
"""

from __future__ import annotations

from datetime import date
from itertools import combinations

from . import defaults
from .models import Character, CharacterProfile, CharacterRelationship, World


def student_profile(profile_id: str = "student_profile") -> CharacterProfile:
    """小白預設：週一~週五 08:30~17:30 上學；每月最多請假一天。"""
    return CharacterProfile(
        id=profile_id,
        schedule_config=defaults.student_schedule_config(),
        meal_config=defaults.default_meal_config(),
        leave_config=defaults.default_monthly_leave_config(),
        event_config=defaults.student_event_config(),
    )


def office_worker_profile(
    profile_id: str = "office_worker_profile", anchor_date: date | None = None
) -> CharacterProfile:
    """小雞毛預設：週一~週五 08:30~17:30 上班；固定 Anchor 的 14 天 Cycle 請假。"""
    leave = defaults.default_cycle_leave_config()
    leave["anchor_date"] = anchor_date.isoformat() if anchor_date else None
    return CharacterProfile(
        id=profile_id,
        schedule_config=defaults.office_schedule_config(),
        meal_config=defaults.default_meal_config(),
        leave_config=leave,
        event_config=defaults.office_event_config(),
    )


def freelancer_profile(profile_id: str = "freelancer_profile") -> CharacterProfile:
    """非官方範例 Profile：週一~週四 10:00~16:00 在咖啡廳接案、不請假。"""
    return CharacterProfile(
        id=profile_id,
        schedule_config=defaults.freelancer_schedule_config(),
        meal_config=defaults.default_meal_config(),
        leave_config=defaults.no_leave_config(),
        event_config=defaults.freelancer_event_config(),
    )


# 官方 Profile 模板：key → (名稱, factory)。DB seed 與 server 都以此為準。
OFFICIAL_PROFILES = {
    "official.student.v1": ("學生（官方預設：小白）", student_profile),
    "official.office_worker.v1": ("上班族（官方預設：小雞毛）", office_worker_profile),
    "official.freelancer.v1": ("自由工作者（範例）", freelancer_profile),
}

_EXTRA_NAMES = ["阿毛", "小橘", "豆豆", "阿布", "米米", "可可", "小黑", "胖胖"]
_EXTRA_PROFILES = [freelancer_profile, student_profile, office_worker_profile]


def demo_world(
    num_characters: int = 2,
    world_id: str = "world_demo",
    simulation_version: str = defaults.DEFAULT_SIMULATION_VERSION,
    simulation_start_date: date = date(2026, 10, 1),
    timezone: str = defaults.DEFAULT_TIMEZONE,
) -> tuple[World, list[Character], list[CharacterRelationship]]:
    """建立示範 World：char_1=小白、char_2=小雞毛（couple），其餘角色為朋友。"""
    if num_characters < 1:
        raise ValueError("num_characters must be >= 1")
    world = World(
        id=world_id,
        name="WorldPane Demo",
        simulation_start_date=simulation_start_date,
        timezone=timezone,
        simulation_version=simulation_version,
    )
    characters: list[Character] = []
    for i in range(num_characters):
        cid = f"char_{i + 1}"
        if i == 0:
            appearance, name, profile = "xiaobai", "小白", student_profile()
        elif i == 1:
            appearance, name, profile = "xiaojimao", "小雞毛", office_worker_profile()
        else:
            j = i - 2
            name = _EXTRA_NAMES[j % len(_EXTRA_NAMES)]
            if j >= len(_EXTRA_NAMES):
                name = f"{name}{j // len(_EXTRA_NAMES) + 1}"
            appearance = "custom_character"
            profile = _EXTRA_PROFILES[j % len(_EXTRA_PROFILES)](f"profile_{cid}")
        characters.append(
            Character(id=cid, world_id=world.id, appearance_key=appearance, display_name=name, profile=profile)
        )
    relationships: list[CharacterRelationship] = []
    for a, b in combinations(characters, 2):
        rtype = "couple" if {a.id, b.id} == {"char_1", "char_2"} else "friend"
        relationships.append(
            CharacterRelationship(
                id=f"rel_{a.id}_{b.id}",
                world_id=world.id,
                character_a_id=a.id,
                character_b_id=b.id,
                relationship_type=rtype,
            )
        )
    return world, characters, relationships
