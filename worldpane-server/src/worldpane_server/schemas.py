"""Public API models (pydantic v2). These define the contract the ESP32 firmware parses."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


# --- Display state (spec §19) -----------------------------------------------------------
class CharacterState(BaseModel):
    id: str
    appearance: str = Field(description="Appearance key; the device maps it to local assets.")
    scene: str
    activity: str
    started_at: datetime | None = Field(description="World-local ISO 8601 with offset.")
    ends_at: datetime | None


class WorldState(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "server_time": "2026-10-05T18:42:10+08:00",
                "revision": 18291,
                "world_id": "wld_demo",
                "characters": [
                    {
                        "id": "chr_a",
                        "appearance": "xiaobai",
                        "scene": "home_living_room",
                        "activity": "reading",
                        "started_at": "2026-10-05T18:31:00+08:00",
                        "ends_at": "2026-10-05T19:03:00+08:00",
                    }
                ],
            }
        }
    )

    server_time: datetime
    revision: int = Field(description="Bumps whenever anything in `characters` changes.")
    world_id: str
    characters: list[CharacterState] = Field(description="1..N characters, stable order.")


# --- History (spec §17) -----------------------------------------------------------------
class HistoryEvent(BaseModel):
    id: str
    type: str
    scene: str
    activity: str
    started_at: datetime
    ends_at: datetime
    participants: list[str] = Field(description="All participant character ids (2..N if shared).")


class CharacterHistory(BaseModel):
    id: str
    appearance: str
    display_name: str
    events: list[HistoryEvent]


class WorldHistory(BaseModel):
    world_id: str
    date: date
    timezone: str
    characters: list[CharacterHistory]


# --- Device input -----------------------------------------------------------------------
class DeviceInputIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"type": "button_press", "button": "A"}})

    type: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    button: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_]{1,16}$")


class DeviceInputAccepted(BaseModel):
    accepted: Literal[True] = True
    input_id: str


# --- Pairing / world creation (spec §22) -------------------------------------------------
class PairIn(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"pairing_code": "824917"}})

    pairing_code: str = Field(pattern=r"^\d{6}$")
    firmware_version: str | None = Field(default=None, max_length=64)


class DeviceCredentials(BaseModel):
    device_id: str
    world_id: str
    device_token: str = Field(description="Shown once. Send as `Authorization: Bearer <token>`.")
    token_type: Literal["Bearer"] = "Bearer"


class PairingCodeOut(BaseModel):
    pairing_code: str
    expires_at: datetime
    max_uses: int


class PairingCodeIn(BaseModel):
    max_uses: int | None = Field(default=None, ge=1, le=20)


def _check_tz(v: str | None) -> str | None:
    if v is None:
        return v
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone: {v}") from exc
    return v


class CreateWorldIn(BaseModel):
    name: str = Field(default="My World", min_length=1, max_length=80)
    timezone: str | None = Field(default=None, description="IANA tz; defaults to Asia/Taipei.")
    pairing_max_uses: int | None = Field(default=None, ge=1, le=20)
    firmware_version: str | None = Field(default=None, max_length=64)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, v: object) -> object:
        # Same rule as the DB check (btrim): a blank name is a 422, not a 500.
        return v.strip() if isinstance(v, str) else v

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str | None) -> str | None:
        return _check_tz(v)


class CreateWorldOut(BaseModel):
    world_id: str
    device: DeviceCredentials = Field(description="Credentials for the creating (first) device.")
    pairing: PairingCodeOut = Field(description="Code for additional devices to join this World.")


# --- Admin / dashboard ------------------------------------------------------------------
# Not part of the device contract: these routes are left out of openapi.json.
def _strip(v: object) -> object:
    return v.strip() if isinstance(v, str) else v


class AdminProfile(BaseModel):
    key: str
    name: str


class AdminCharacterIn(BaseModel):
    display_name: str = Field(min_length=1, max_length=50)
    appearance: str = Field(pattern=r"^[a-z0-9_-]{1,64}$", description="Appearance key, e.g. xiaobai")
    profile_key: str = Field(description="Official profile key from GET /admin/profiles")

    _strip_name = field_validator("display_name", mode="before")(_strip)


class AdminCharacterPatch(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=50)
    appearance: str | None = Field(default=None, pattern=r"^[a-z0-9_-]{1,64}$")
    sort_order: int | None = Field(default=None, ge=-1000, le=1000)

    _strip_name = field_validator("display_name", mode="before")(_strip)


class AdminCharacter(BaseModel):
    id: str
    display_name: str
    appearance: str
    profile_key: str | None
    profile_name: str
    sort_order: int
    archived_at: datetime | None


class AdminDevice(BaseModel):
    id: str
    firmware_version: str | None
    created_at: datetime
    last_seen_at: datetime | None


class AdminWorldSummary(BaseModel):
    id: str
    name: str
    timezone: str
    simulation_start_date: date
    created_at: datetime
    revision: int
    character_count: int
    device_count: int


class AdminSharedEvent(BaseModel):
    key: str
    label: str
    enabled: bool
    weight: float | None


class AdminWorld(BaseModel):
    id: str
    name: str
    timezone: str
    simulation_start_date: date
    created_at: datetime
    revision: int
    shared_event_config: dict = Field(description="attempts, trigger_probability, slot_step_min, "
                                                  "max_slot_tries, overrides.<event key>")
    shared_events: list[AdminSharedEvent] = Field(
        description="Shared events visible to this World, with their defaults (before `overrides`)")
    characters: list[AdminCharacter] = Field(description="Active first, then archived")
    devices: list[AdminDevice]


class AdminCreateWorldIn(BaseModel):
    name: str = Field(default="My World", min_length=1, max_length=80)
    timezone: str | None = Field(default=None, description="IANA tz; defaults to Asia/Taipei.")
    pairing_max_uses: int | None = Field(default=None, ge=1, le=20)
    characters: list[AdminCharacterIn] | None = Field(
        default=None, min_length=1, max_length=12,
        description="Defaults to the official pair (小白 + 小雞毛).")

    _strip_name = field_validator("name", mode="before")(_strip)
    _valid_tz = field_validator("timezone")(_check_tz)


class AdminCreateWorldOut(BaseModel):
    world: AdminWorld
    pairing: PairingCodeOut


class AdminWorldPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    shared_event_config: dict | None = None

    _strip_name = field_validator("name", mode="before")(_strip)


class MonitorCharacter(CharacterState):
    display_name: str


class MonitorWorld(BaseModel):
    world_id: str
    name: str
    timezone: str
    server_time: datetime
    revision: int
    characters: list[MonitorCharacter]


class Monitor(BaseModel):
    worlds: list[MonitorWorld]
