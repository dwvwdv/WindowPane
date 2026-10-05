"""Simulation seam.

The real engine lives in ``worldpane-core`` (built separately). It will expose roughly::

    generate_daily_plan(world, characters, relationships, local_date) -> events
    current_state(events, now) -> per-character current event

The server talks to it only through ``SimulationProvider``. Swap implementations with
``WORLDPANE_SIMULATION_PROVIDER`` (``stub`` | ``core``).

TODO(core): implement ``CoreSimulationProvider`` as a thin adapter that converts the server's
domain dataclasses into worldpane-core's types, calls its two functions, and converts results
back into ``domain.Event``. Keep all schedule/meal/leave/event rules inside worldpane-core;
the server must not grow simulation logic (spec §30/§31).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol, runtime_checkable

from ..domain import Character, CharacterRelationship, Event, World


@runtime_checkable
class SimulationProvider(Protocol):
    def generate_daily_plan(
        self,
        world: World,
        characters: list[Character],
        relationships: list[CharacterRelationship],
        local_date: date,
    ) -> list[Event]:
        """Deterministic: same (world, characters, date, simulation_version) -> same events.

        ``local_date`` is a date in the World timezone. Returned events carry aware datetimes.
        Shared events are a single Event with 2..N participant ids.
        """
        ...

    def current_state(self, events: list[Event], now: datetime) -> dict[str, Event]:
        """Map character_id -> the event that character is in at ``now``.

        Characters with no active event are simply absent; the caller renders a fallback.
        """
        ...


class CoreSimulationProvider:  # pragma: no cover - placeholder
    """TODO(core): adapter around worldpane-core. Intentionally not importing it yet."""

    def __init__(self) -> None:
        raise NotImplementedError(
            "worldpane-core adapter not wired yet; use WORLDPANE_SIMULATION_PROVIDER=stub"
        )


def build_provider(name: str) -> SimulationProvider:
    if name == "stub":
        from .stub import StubSimulationProvider

        return StubSimulationProvider()
    if name == "core":
        return CoreSimulationProvider()
    raise ValueError(f"unknown simulation provider: {name}")
