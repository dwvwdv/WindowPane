"""Application services: glue between the HTTP layer, the Repository and the SimulationProvider.

No simulation rules live here — only orchestration (load/generate/persist plans, map events to
API shapes, pairing and token handling).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import schemas
from .clock import Clock
from .config import Settings
from .domain import Character, Device, DeviceInput, Event, PairingCode, World
from .repositories.base import PairingCodeRejected, Repository
from .security import (
    generate_device_token,
    generate_pairing_code,
    hash_device_token,
    hash_pairing_code,
    new_id,
)
from .seed import build_world_with_defaults
from .simulation.provider import SimulationProvider

# Rendered when the provider reports no active event for a character (should be rare).
FALLBACK_SCENE = "home_living_room"
FALLBACK_ACTIVITY = "idle"


class ServiceError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass
class StateResult:
    state: schemas.WorldState
    etag: str
    characters: list[Character]  # active characters, in the order of state.characters


class WorldService:
    def __init__(self, repo: Repository, sim: SimulationProvider, settings: Settings, clock: Clock) -> None:
        self.repo = repo
        self.sim = sim
        self.settings = settings
        self.clock = clock

    # --- helpers --------------------------------------------------------------------------
    def _world(self, world_id: str) -> World:
        world = self.repo.get_world(world_id)
        if world is None:
            raise ServiceError(404, "world_not_found", "World not found")
        return world

    @staticmethod
    def local_today(world: World, now: datetime) -> date:
        return now.astimezone(ZoneInfo(world.timezone)).date()

    def cast_on(self, world: World, local_date: date) -> list[Character]:
        """Characters that take part in ``local_date``: active ones plus any archived on or after it.

        Archiving only stops *future* plans (spec §17); a past date first materialised after the
        archive still includes the character, so their history does not depend on request order.
        """
        tz = ZoneInfo(world.timezone)
        return [
            c for c in self.repo.list_characters(world.id, include_archived=True)
            if c.archived_at is None or c.archived_at.astimezone(tz).date() >= local_date
        ]

    def ensure_plan(self, world: World, local_date: date) -> list[Event]:
        """Load the persisted plan for ``local_date`` or generate+persist it (lazy, deterministic).

        The World keeps running while devices are offline (spec §16): any date can be
        materialised on demand and will always produce the same events.
        """
        if local_date < world.simulation_start_date:
            return []
        plan = self.repo.get_daily_plan(world.id, local_date)
        if plan is not None:
            return plan
        characters = self.cast_on(world, local_date)
        relationships = self.repo.list_relationships(world.id)
        events = self.sim.generate_daily_plan(world, characters, relationships, local_date)
        if not self.repo.save_daily_plan(world.id, local_date, events):
            # Someone else persisted it first; theirs is authoritative (and identical).
            return self.repo.get_daily_plan(world.id, local_date) or events
        return events

    # --- display state --------------------------------------------------------------------
    def device_state(self, world_id: str, world: World | None = None) -> StateResult:
        """``world`` may be passed when the caller already loaded it (saves a query)."""
        world = world if world is not None and world.id == world_id else self._world(world_id)
        now = self.clock.now()
        tz = ZoneInfo(world.timezone)
        characters = self.repo.list_characters(world.id)
        today = self.local_today(world, now)
        # Include yesterday so events crossing local midnight are still found.
        events = self.ensure_plan(world, today - timedelta(days=1)) + self.ensure_plan(world, today)
        current = self.sim.current_state(events, now, [c.id for c in characters])

        def local(dt: datetime | None) -> datetime | None:
            return dt.astimezone(tz) if dt is not None else None

        char_states: list[schemas.CharacterState] = []
        for c in characters:
            cur = current.get(c.id)
            char_states.append(schemas.CharacterState(
                id=c.id, appearance=c.appearance_key,
                scene=cur.scene if cur else FALLBACK_SCENE,
                activity=cur.activity if cur else FALLBACK_ACTIVITY,
                started_at=local(cur.started_at) if cur else None,
                ends_at=local(cur.ends_at) if cur else None,
            ))

        fingerprint = hashlib.sha256(
            json.dumps([s.model_dump(mode="json") for s in char_states], sort_keys=True).encode()
        ).hexdigest()
        revision = self.repo.record_state_fingerprint(world.id, fingerprint)
        state = schemas.WorldState(
            server_time=now.astimezone(tz).replace(microsecond=0),
            revision=revision,
            world_id=world.id,
            characters=char_states,
        )
        return StateResult(state=state, etag=make_etag(world.id, revision), characters=characters)

    # --- history --------------------------------------------------------------------------
    def history(self, world_id: str, local_date: date) -> schemas.WorldHistory:
        world = self._world(world_id)
        now = self.clock.now()
        today = self.local_today(world, now)
        if local_date > today:
            raise ServiceError(422, "date_in_future", "History is only available up to today (World timezone)")
        tz = ZoneInfo(world.timezone)
        events = self.ensure_plan(world, local_date)
        # Archived characters stay in history for the days they took part in (spec §17).
        involved = {cid for e in events for cid in e.participant_ids}
        characters = [
            c for c in self.repo.list_characters(world.id, include_archived=True)
            if c.archived_at is None or c.id in involved
        ]
        # History = what has happened. For today, hide events that have not started yet.
        events = [e for e in events if e.start_at <= now]

        out: list[schemas.CharacterHistory] = []
        for c in characters:
            mine = sorted((e for e in events if c.id in e.participant_ids), key=lambda e: (e.start_at, e.id))
            out.append(schemas.CharacterHistory(
                id=c.id, appearance=c.appearance_key, display_name=c.display_name,
                events=[schemas.HistoryEvent(
                    id=e.id, type=e.type, scene=e.scene, activity=e.activity,
                    started_at=e.start_at.astimezone(tz), ends_at=e.end_at.astimezone(tz),
                    participants=list(e.participant_ids),
                ) for e in mine],
            ))
        return schemas.WorldHistory(world_id=world.id, date=local_date, timezone=world.timezone, characters=out)

    # --- devices / pairing ----------------------------------------------------------------
    def authenticate(self, token: str) -> Device | None:
        device = self.repo.get_device_by_token_hash(hash_device_token(token))
        if device is not None:
            self.repo.touch_device(device.id, self.clock.now())
        return device

    def _new_device(self, world_id: str, firmware_version: str | None) -> tuple[Device, schemas.DeviceCredentials]:
        token = generate_device_token()
        device = Device(
            id=new_id(), world_id=world_id, device_token_hash=hash_device_token(token),
            created_at=self.clock.now(), firmware_version=firmware_version,
        )
        return device, schemas.DeviceCredentials(device_id=device.id, world_id=world_id, device_token=token)

    def _new_pairing_code(self, world: World, max_uses: int | None,
                          code: str | None) -> tuple[PairingCode, schemas.PairingCodeOut]:
        now = self.clock.now()
        uses = max_uses or self.settings.pairing_code_max_uses
        expires = now + timedelta(seconds=self.settings.pairing_code_ttl_seconds)
        value = code or generate_pairing_code()
        pc = PairingCode(
            id=new_id(), world_id=world.id,
            code_hash=hash_pairing_code(value, self.settings.pairing_code_secret),
            expires_at=expires, max_uses=uses, used_count=0, created_at=now,
        )
        return pc, schemas.PairingCodeOut(
            pairing_code=value, expires_at=expires.astimezone(ZoneInfo(world.timezone)), max_uses=uses
        )

    def issue_pairing_code(self, world_id: str, max_uses: int | None = None,
                           code: str | None = None) -> schemas.PairingCodeOut:
        world = self._world(world_id)
        for _ in range(20):
            pc, out = self._new_pairing_code(world, max_uses, code)
            try:
                self.repo.add_pairing_code(pc)
            except ValueError:
                if code is not None:
                    raise
                continue  # collided with another active code; draw again
            return out
        raise ServiceError(503, "pairing_code_unavailable", "Could not allocate a pairing code, retry")

    def pair(self, code: str, firmware_version: str | None) -> schemas.DeviceCredentials:
        pc = self.repo.get_pairing_code_by_hash(hash_pairing_code(code, self.settings.pairing_code_secret))
        if pc is None:
            raise ServiceError(400, "invalid_pairing_code", "Pairing code is not valid")
        device, creds = self._new_device(pc.world_id, firmware_version)
        try:
            # One transaction: the code is only used up if the device row is created too.
            self.repo.redeem_pairing_code(pc.id, device, self.clock.now())
        except PairingCodeRejected as exc:
            if exc.reason == "expired":
                raise ServiceError(400, "pairing_code_expired", "Pairing code has expired") from exc
            raise ServiceError(400, "pairing_code_exhausted", "Pairing code has already been used") from exc
        return creds

    def create_world(self, body: schemas.CreateWorldIn) -> schemas.CreateWorldOut:
        now = self.clock.now()
        tz_name = body.timezone or self.settings.default_timezone
        start = now.astimezone(ZoneInfo(tz_name)).date()
        world, characters, relationships = build_world_with_defaults(
            world_id=new_id(), name=body.name, timezone=tz_name, created_at=now, start_date=start,
        )
        device, creds = self._new_device(world.id, body.firmware_version)
        for _ in range(20):
            pc, pairing = self._new_pairing_code(world, body.pairing_max_uses, None)
            try:
                # One transaction: a failure leaves no half-created world or orphaned device.
                self.repo.create_world(world, characters, relationships, [device], [pc])
            except ValueError:
                continue  # the pairing code collided with an active one; draw again
            return schemas.CreateWorldOut(world_id=world.id, device=creds, pairing=pairing)
        raise ServiceError(503, "pairing_code_unavailable", "Could not allocate a pairing code, retry")

    def record_input(self, device: Device, body: schemas.DeviceInputIn) -> schemas.DeviceInputAccepted:
        item = DeviceInput(
            id=new_id(), device_id=device.id, world_id=device.world_id, type=body.type,
            button=body.button, received_at=self.clock.now(), payload=body.model_dump(),
        )
        # V1: inputs are logged only; they do not alter the simulation.
        self.repo.add_device_input(item)
        return schemas.DeviceInputAccepted(input_id=item.id)


def make_etag(world_id: str, revision: int) -> str:
    return f'"{world_id}.{revision}"'


def etag_matches(if_none_match: str | None, etag: str) -> bool:
    """RFC 9110 weak comparison for If-None-Match."""
    if not if_none_match:
        return False
    if if_none_match.strip() == "*":
        return True
    target = etag.removeprefix("W/")
    return any(tag.strip().removeprefix("W/") == target for tag in if_none_match.split(","))
