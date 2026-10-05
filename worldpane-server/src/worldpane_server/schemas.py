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


class DeviceState(BaseModel):
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


class CreateWorldIn(BaseModel):
    name: str = Field(default="My World", min_length=1, max_length=80)
    timezone: str | None = Field(default=None, description="IANA tz; defaults to Asia/Taipei.")
    pairing_max_uses: int | None = Field(default=None, ge=1, le=20)
    firmware_version: str | None = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone: {v}") from exc
        return v


class CreateWorldOut(BaseModel):
    world_id: str
    device: DeviceCredentials = Field(description="Credentials for the creating (first) device.")
    pairing: PairingCodeOut = Field(description="Code for additional devices to join this World.")
