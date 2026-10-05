"""Domain records used by the API layer, repositories and simulation providers.

These mirror the conceptual data model in spec §28. They are plain dataclasses so the
persistence layer (in-memory today, Supabase/Postgres later) can map them freely.

All datetimes are timezone-aware and stored in UTC; they are rendered in the World
timezone only at the API boundary (spec §4 Timezone).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from worldpane_core.catalog import EventDefinition, PoolEntry


@dataclass
class World:
    id: str
    name: str
    timezone: str
    simulation_version: int
    simulation_start_date: date
    created_at: datetime
    # Monotonic counter bumped on every write that can change what devices see
    # (events persisted, characters changed, ...). Drives the Display API `revision`/ETag.
    revision: int = 1
    # Fingerprint of the last Display State served (everything except server_time).
    # When the visible state changes, revision is bumped (see Repository.record_state_fingerprint).
    state_fingerprint: str | None = None
    # Shared-event knobs as stored (worlds.shared_event_config: attempts, trigger_probability,
    # per-event "overrides", ...) plus the shared event definitions visible to this world.
    # worldpane-core assembles both into its generator config.
    shared_event_config: dict[str, Any] = field(default_factory=dict)
    shared_event_definitions: list[EventDefinition] = field(default_factory=list)


@dataclass
class CharacterProfile:
    """Behaviour config (spec §6), stored in the DB and consumed by worldpane-core.

    ``event_config`` holds only the knobs (attempts, windows, ...); the events a profile can
    draw come from ``event_pool`` (rows of ``profile_event_pools`` joined with their
    ``event_definitions``). Adding an event is a data change, never a code change.
    """

    id: str
    schedule_config: dict[str, Any] = field(default_factory=dict)
    meal_config: dict[str, Any] = field(default_factory=dict)
    leave_config: dict[str, Any] = field(default_factory=dict)
    event_config: dict[str, Any] = field(default_factory=dict)
    event_pool: list[PoolEntry] = field(default_factory=list)
    key: str | None = None
    name: str = ""


@dataclass
class Character:
    """A Character *instance* inside one World (spec §5). Appearance and behaviour are separate."""

    id: str
    world_id: str
    appearance_key: str
    display_name: str
    profile: CharacterProfile
    sort_order: int = 0


@dataclass
class CharacterRelationship:
    """Pairwise relationship (spec §12). Never modelled as a single partner_id."""

    id: str
    world_id: str
    character_a_id: str
    character_b_id: str
    relationship_type: str
    affinity: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Event:
    """One event in the World's event log (spec §17). Shared events have 2..N participants."""

    id: str
    world_id: str
    type: str
    scene: str
    activity: str
    start_at: datetime
    end_at: datetime
    participant_ids: list[str]
    local_date: date
    simulation_version: int
    priority: int = 0
    status: str = "scheduled"
    metadata: dict[str, Any] = field(default_factory=dict)
    location: str | None = None
    # "base" = background schedule block (SCHOOL 08:30–17:30) that foreground events overlay.
    layer: str = "foreground"

    @property
    def is_shared(self) -> bool:
        return len(self.participant_ids) >= 2


@dataclass
class Device:
    id: str
    world_id: str
    device_token_hash: str
    created_at: datetime
    firmware_version: str | None = None
    last_seen_at: datetime | None = None


@dataclass
class PairingCode:
    id: str
    world_id: str
    code_hash: str
    expires_at: datetime
    max_uses: int
    used_count: int
    created_at: datetime

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def is_exhausted(self) -> bool:
        return self.used_count >= self.max_uses


@dataclass
class DeviceInput:
    id: str
    device_id: str
    world_id: str
    type: str
    button: str | None
    received_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)
