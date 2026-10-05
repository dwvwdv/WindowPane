"""Domain models（規格 §4–§6、§12、§28）。

純 stdlib dataclass，無 DB / Web 依賴。
角色數量為 1..N；不存在 partner_id，關係一律以 CharacterRelationship 建模（§12、§31-12）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import IntEnum
from typing import Any
from zoneinfo import ZoneInfo

from . import defaults


class Priority(IntEnum):
    """規格 §14 固定優先級（數字越小越優先）。"""

    FIXED = 1  # Fixed / mandatory event（Base Schedule：上學、上班）
    MEAL = 2
    SHARED = 3
    TEMPORARY = 4  # Work / School temporary event
    LEISURE = 5  # Individual leisure event
    IDLE = 6


class Layer:
    """Event 所在圖層。

    base：Base Schedule（location 背景，例如 SCHOOL 08:30~17:30）。
    foreground：會覆蓋 Base 的事件（用餐、摸魚、個人／共同事件）。
    """

    BASE = "base"
    FOREGROUND = "foreground"


class EventKind:
    BASE = "base"
    MEAL = "meal"
    TEMPORARY = "temporary"
    LEISURE = "leisure"
    SHARED = "shared"


@dataclass(frozen=True)
class CharacterProfile:
    """生活規則（§6）。與外觀完全分離。"""

    id: str
    schedule_config: dict[str, Any] = field(default_factory=dict)
    meal_config: dict[str, Any] = field(default_factory=dict)
    leave_config: dict[str, Any] = field(default_factory=dict)
    event_config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Character:
    """World 成員（§5）。appearance_key 只影響顯示，不影響行為。"""

    id: str
    world_id: str
    appearance_key: str
    display_name: str
    profile: CharacterProfile


@dataclass(frozen=True)
class CharacterRelationship:
    """角色關係（§12）。無方向性：a↔b。"""

    character_a_id: str
    character_b_id: str
    relationship_type: str
    world_id: str = ""
    id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def pair(self) -> frozenset[str]:
        return frozenset((self.character_a_id, self.character_b_id))


@dataclass(frozen=True)
class World:
    """Aggregate Root（§4）。所有日期、星期、月份皆以 timezone 計算。"""

    id: str
    name: str
    simulation_start_date: date
    timezone: str = defaults.DEFAULT_TIMEZONE
    simulation_version: str = defaults.DEFAULT_SIMULATION_VERSION
    # 假日行事曆 hook：列入此集合的日期視為 holiday（國定假日等）。週末本來就是 holiday。
    holiday_dates: frozenset[date] = frozenset()
    # World 層級 Shared / Group Event Rules（§4、§11）。
    shared_event_config: dict[str, Any] = field(
        default_factory=defaults.default_shared_event_config
    )

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@dataclass
class Event:
    """Event Log 一筆（§17、§28）。Shared Event 為單一 Event + 2..N participants。"""

    id: str
    world_id: str
    type: str
    scene: str
    location: str
    activity: str
    start_at: datetime
    end_at: datetime
    priority: int
    participants: list[str]
    metadata: dict[str, Any]
    simulation_version: str
    layer: str = Layer.FOREGROUND
    status: str = "scheduled"

    @property
    def kind(self) -> str:
        return self.metadata.get("kind", "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "world_id": self.world_id,
            "type": self.type,
            "scene": self.scene,
            "location": self.location,
            "activity": self.activity,
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
            "priority": int(self.priority),
            "participants": list(self.participants),
            "metadata": dict(self.metadata),
            "simulation_version": self.simulation_version,
            "layer": self.layer,
            "status": self.status,
        }


@dataclass(frozen=True)
class CharacterState:
    """Display 用 Semantic State（§19）。"""

    character_id: str
    scene: str
    activity: str
    location: str
    started_at: datetime | None
    ends_at: datetime | None
    event_id: str | None = None
    event_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "scene": self.scene,
            "activity": self.activity,
            "location": self.location,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "event_id": self.event_id,
            "event_type": self.event_type,
        }
