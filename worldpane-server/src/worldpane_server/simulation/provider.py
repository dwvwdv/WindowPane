"""Simulation seam.

All schedule / meal / leave / event rules live in ``worldpane-core`` (spec §30/§31); the server
only talks to it through ``SimulationProvider`` and never grows simulation logic of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, runtime_checkable

from ..domain import Character, CharacterRelationship, Event, World


@dataclass(frozen=True)
class CharacterNow:
    """What one character is doing at a point in time (spec §19 semantic state).

    ``started_at`` / ``ends_at`` describe the visible segment (e.g. "back in class" after a
    nap starts when the nap ends) and may be None when idle with nothing before/after.
    """

    scene: str
    activity: str
    location: str | None
    started_at: datetime | None
    ends_at: datetime | None
    event_id: str | None = None


@runtime_checkable
class SimulationProvider(Protocol):
    def generate_daily_plan(
        self,
        world: World,
        characters: list[Character],
        relationships: list[CharacterRelationship],
        local_date: date,
    ) -> list[Event]:
        """Deterministic: same (world, characters, config, date, simulation_version) -> same events.

        ``local_date`` is a date in the World timezone. Returned events carry aware datetimes.
        Shared events are a single Event with 2..N participant ids.
        """
        ...

    def current_state(
        self, events: list[Event], now: datetime, character_ids: list[str]
    ) -> dict[str, CharacterNow]:
        """Map every id in ``character_ids`` to what that character is doing at ``now``."""
        ...


def build_provider(name: str) -> SimulationProvider:
    if name == "core":
        from .core import CoreSimulationProvider

        return CoreSimulationProvider()
    raise ValueError(f"unknown simulation provider: {name}")
