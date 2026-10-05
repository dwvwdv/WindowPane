"""Postgres / Supabase Repository against the ``worldpane`` schema (``/supabase/migrations``).

Connect with the service-role DSN (``WORLDPANE_DATABASE_URL``) server-side only; RLS denies
everyone else. Works through Supabase's transaction pooler too (no prepared statements).

Simulation config is read from the database on every load, so tuning a weight or adding an
event definition needs no deploy: it applies to the next daily plan that gets generated.
Persisted plans are immutable history (spec §15, §17).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from psycopg import errors
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from worldpane_core.catalog import EventDefinition, PoolEntry

from ..domain import (
    Character,
    CharacterProfile,
    CharacterRelationship,
    Device,
    DeviceInput,
    Event,
    PairingCode,
    World,
)
from .base import PairingCodeRejected

log = logging.getLogger(__name__)

# worldpane.event_priority enum, in spec §14 order (core Priority 1..6).
_PRIORITIES = ["fixed", "meal", "shared", "temporary", "individual_leisure", "idle"]


def _priority_to_db(value: int) -> str:
    return _PRIORITIES[min(max(int(value), 1), len(_PRIORITIES)) - 1]


def _definition(row: dict[str, Any]) -> EventDefinition:
    return EventDefinition(
        id=str(row["def_id"]),
        key=row["key"],
        category=row["category"],
        label=row["label"],
        scene=row["scene"],
        location=row["location"],
        activity=row["activity"],
        params=row["params"] or {},
        enabled=row["def_enabled"],
        sort_order=row["sort_order"],
    )


class PostgresRepository:
    def __init__(self, database_url: str, *, min_size: int = 1, max_size: int = 10) -> None:
        if not database_url:
            raise RuntimeError("WORLDPANE_DATABASE_URL is required for the postgres repository")
        self._pool = ConnectionPool(
            database_url,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row, "prepare_threshold": None, "options": "-c timezone=UTC"},
            open=True,
        )

    def close(self) -> None:
        self._pool.close()

    # --- official content ---------------------------------------------------------------
    def install_official_content(
        self, definitions: list[EventDefinition], profiles: list[CharacterProfile]
    ) -> None:
        with self._pool.connection() as conn, conn.transaction():
            for d in definitions:
                conn.execute(
                    """insert into worldpane.event_definitions
                         (id, world_id, key, category, label, scene, location, activity, params, enabled, sort_order)
                       values (%s, null, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       on conflict do nothing""",
                    (d.id, d.key, d.category, d.label, d.scene, d.location, d.activity,
                     Jsonb(dict(d.params)), d.enabled, d.sort_order),
                )
            for p in profiles:
                conn.execute(
                    """insert into worldpane.character_profiles
                         (id, world_id, key, name, schedule_config, meal_config, leave_config, event_config)
                       values (%s, null, %s, %s, %s, %s, %s, %s)
                       on conflict do nothing""",
                    (p.id, p.key, p.name or p.key, Jsonb(p.schedule_config), Jsonb(p.meal_config),
                     Jsonb(p.leave_config), Jsonb(p.event_config)),
                )
                for entry in p.event_pool:
                    conn.execute(
                        """insert into worldpane.profile_event_pools (profile_id, event_definition_id, overrides)
                           select %s, %s, %s
                            where exists (select 1 from worldpane.character_profiles
                                           where id = %s and world_id is null)
                              and exists (select 1 from worldpane.event_definitions
                                           where id = %s and world_id is null)
                           on conflict do nothing""",
                        (p.id, entry.definition.id, Jsonb(dict(entry.overrides)), p.id, entry.definition.id),
                    )

    # --- worlds -----------------------------------------------------------------------
    def create_world(
        self,
        world: World,
        characters: Sequence[Character] = (),
        relationships: Sequence[CharacterRelationship] = (),
        devices: Sequence[Device] = (),
        pairing_codes: Sequence[PairingCode] = (),
    ) -> None:
        with self._pool.connection() as conn, conn.transaction():
            try:
                with conn.transaction():
                    conn.execute(
                        """insert into worldpane.worlds
                             (id, name, timezone, simulation_version, simulation_start_date,
                              shared_event_config, created_at)
                           values (%s, %s, %s, %s, %s, %s, %s)""",
                        (world.id, world.name, world.timezone, world.simulation_version,
                         world.simulation_start_date, Jsonb(world.shared_event_config), world.created_at),
                    )
            except errors.UniqueViolation as exc:
                raise ValueError(f"world {world.id} already exists") from exc
            for c in characters:
                self._insert_character(conn, c)
            for r in relationships:
                self._insert_relationship(conn, r)
            for d in devices:
                self._insert_device(conn, d)
            for code in pairing_codes:
                self._insert_pairing_code(conn, code)

    def get_world(self, world_id: str) -> World | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """select w.*, r.revision, r.state_fingerprint
                     from worldpane.worlds w
                     join worldpane.world_revisions r on r.world_id = w.id
                    where w.id = %s""",
                (world_id,),
            ).fetchone()
            if row is None:
                return None
            # Official shared definitions, shadowed by this world's own (same category + key).
            defs = conn.execute(
                """select distinct on (d.category, d.key)
                          d.id as def_id, d.key, d.category, d.label, d.scene, d.location,
                          d.activity, d.params, d.enabled as def_enabled, d.sort_order
                     from worldpane.event_definitions d
                    where d.category = 'shared' and (d.world_id is null or d.world_id = %s)
                    order by d.category, d.key, d.world_id nulls last""",
                (world_id,),
            ).fetchall()
        return World(
            id=str(row["id"]),
            name=row["name"],
            timezone=row["timezone"],
            simulation_version=row["simulation_version"],
            simulation_start_date=row["simulation_start_date"],
            created_at=row["created_at"],
            revision=row["revision"],
            state_fingerprint=row["state_fingerprint"],
            shared_event_config=row["shared_event_config"] or {},
            shared_event_definitions=[_definition(d) for d in defs],
        )

    def bump_world_revision(self, world_id: str) -> int:
        with self._pool.connection() as conn:
            row = conn.execute(
                """update worldpane.world_revisions set revision = revision + 1, updated_at = now()
                    where world_id = %s returning revision""",
                (world_id,),
            ).fetchone()
        if row is None:
            raise KeyError(world_id)
        return row["revision"]

    def record_state_fingerprint(self, world_id: str, fingerprint: str) -> int:
        with self._pool.connection() as conn:
            conn.execute(
                """update worldpane.world_revisions
                      set revision = revision + 1, state_fingerprint = %s, updated_at = now()
                    where world_id = %s and state_fingerprint is distinct from %s""",
                (fingerprint, world_id, fingerprint),
            )
            row = conn.execute(
                "select revision from worldpane.world_revisions where world_id = %s", (world_id,)
            ).fetchone()
        if row is None:
            raise KeyError(world_id)
        return row["revision"]

    # --- characters / relationships ------------------------------------------------------
    def _ensure_profile(self, conn, profile: CharacterProfile, world_id: str) -> None:
        exists = conn.execute(
            "select 1 from worldpane.character_profiles where id = %s", (profile.id,)
        ).fetchone()
        if exists:
            return
        # Unknown profile: store it as a profile owned by this world, with its event pool.
        conn.execute(
            """insert into worldpane.character_profiles
                 (id, world_id, key, name, schedule_config, meal_config, leave_config, event_config)
               values (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (profile.id, world_id, profile.key, profile.name or profile.key or "custom",
             Jsonb(profile.schedule_config), Jsonb(profile.meal_config),
             Jsonb(profile.leave_config), Jsonb(profile.event_config)),
        )
        for entry in profile.event_pool:
            d = entry.definition
            def_id = d.id
            known = def_id and conn.execute(
                "select 1 from worldpane.event_definitions where id = %s", (def_id,)
            ).fetchone()
            if not known:
                row = conn.execute(
                    """insert into worldpane.event_definitions
                         (world_id, key, category, label, scene, location, activity, params, enabled, sort_order)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       on conflict (world_id, category, key) where world_id is not null
                       do update set label = excluded.label
                       returning id""",
                    (world_id, d.key, d.category, d.label, d.scene, d.location, d.activity,
                     Jsonb(dict(d.params)), d.enabled, d.sort_order),
                ).fetchone()
                def_id = row["id"]
            conn.execute(
                """insert into worldpane.profile_event_pools (profile_id, event_definition_id, overrides, enabled)
                   values (%s, %s, %s, %s)""",
                (profile.id, def_id, Jsonb(dict(entry.overrides)), entry.enabled),
            )

    def add_character(self, character: Character) -> None:
        with self._pool.connection() as conn, conn.transaction():
            self._insert_character(conn, character)

    def _insert_character(self, conn, character: Character) -> None:
        self._ensure_profile(conn, character.profile, character.world_id)
        conn.execute(
            """insert into worldpane.characters
                 (id, world_id, appearance_key, display_name, profile_id, sort_order)
               values (%s, %s, %s, %s, %s, %s)""",
            (character.id, character.world_id, character.appearance_key,
             character.display_name, character.profile.id, character.sort_order),
        )

    def list_characters(self, world_id: str, include_archived: bool = False) -> list[Character]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """select c.id, c.world_id, c.appearance_key, c.display_name, c.sort_order, c.archived_at,
                          p.id as profile_id, p.key as profile_key, p.name as profile_name,
                          p.schedule_config, p.meal_config, p.leave_config, p.event_config
                     from worldpane.characters c
                     join worldpane.character_profiles p on p.id = c.profile_id
                    where c.world_id = %s and (%s or c.archived_at is null)
                    order by c.sort_order, c.id""",
                (world_id, include_archived),
            ).fetchall()
            profile_ids = list({r["profile_id"] for r in rows})
            pools = conn.execute(
                """select pp.profile_id, pp.overrides, pp.enabled as pool_enabled,
                          d.id as def_id, d.key, d.category, d.label, d.scene, d.location,
                          d.activity, d.params, d.enabled as def_enabled, d.sort_order,
                          d.world_id as def_world_id
                     from worldpane.profile_event_pools pp
                     join worldpane.event_definitions d on d.id = pp.event_definition_id
                    where pp.profile_id = any(%s)""",
                (profile_ids,),
            ).fetchall() if profile_ids else []
            # A world-owned definition shadows the official one with the same (category, key),
            # also inside the (global) official profiles' pools.
            shadows = {
                (r["category"], r["key"]): r
                for r in conn.execute(
                    """select d.id as def_id, d.key, d.category, d.label, d.scene, d.location,
                              d.activity, d.params, d.enabled as def_enabled, d.sort_order
                         from worldpane.event_definitions d
                        where d.world_id = %s and d.category in ('temporary', 'leisure')""",
                    (world_id,),
                ).fetchall()
            } if pools else {}
        by_profile: dict[Any, list[PoolEntry]] = {}
        for p in pools:
            source = shadows.get((p["category"], p["key"]), p) if p["def_world_id"] is None else p
            by_profile.setdefault(p["profile_id"], []).append(
                PoolEntry(_definition(source), p["overrides"] or {}, p["pool_enabled"])
            )
        return [
            Character(
                id=str(r["id"]),
                world_id=str(r["world_id"]),
                appearance_key=r["appearance_key"],
                display_name=r["display_name"],
                sort_order=r["sort_order"],
                archived_at=r["archived_at"],
                profile=CharacterProfile(
                    id=str(r["profile_id"]),
                    key=r["profile_key"],
                    name=r["profile_name"],
                    schedule_config=r["schedule_config"],
                    meal_config=r["meal_config"],
                    leave_config=r["leave_config"],
                    event_config=r["event_config"],
                    event_pool=by_profile.get(r["profile_id"], []),
                ),
            )
            for r in rows
        ]

    def add_relationship(self, relationship: CharacterRelationship) -> None:
        with self._pool.connection() as conn:
            self._insert_relationship(conn, relationship)

    @staticmethod
    def _insert_relationship(conn, relationship: CharacterRelationship) -> None:
        conn.execute(
            """insert into worldpane.character_relationships
                 (id, world_id, character_a_id, character_b_id, relationship_type, metadata)
               values (%s, %s, %s, %s, %s, %s)""",
            (relationship.id, relationship.world_id, relationship.character_a_id,
             relationship.character_b_id, relationship.relationship_type,
             Jsonb(relationship.metadata)),
        )

    def list_relationships(self, world_id: str) -> list[CharacterRelationship]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                """select * from worldpane.character_relationships where world_id = %s order by id""",
                (world_id,),
            ).fetchall()
        return [
            CharacterRelationship(
                id=str(r["id"]), world_id=str(r["world_id"]),
                character_a_id=str(r["character_a_id"]), character_b_id=str(r["character_b_id"]),
                relationship_type=r["relationship_type"], metadata=r["metadata"] or {},
            )
            for r in rows
        ]

    # --- events ------------------------------------------------------------------------
    def get_daily_plan(self, world_id: str, local_date: date) -> list[Event] | None:
        """The current plan for that date, whatever simulation_version produced it:
        history never changes retroactively when the version is bumped."""
        with self._pool.connection() as conn:
            plan = conn.execute(
                """select id, simulation_version from worldpane.daily_plans
                    where world_id = %s and local_date = %s and superseded_at is null""",
                (world_id, local_date),
            ).fetchone()
            if plan is None:
                return None
            rows = conn.execute(
                """select e.*, array_agg(p.character_id::text order by p.character_id) as participant_ids
                     from worldpane.events e
                     join worldpane.event_participants p on p.event_id = e.id
                    where e.daily_plan_id = %s and e.status = 'scheduled'
                    group by e.id
                    order by e.start_at, e.id""",
                (plan["id"],),
            ).fetchall()
        return [
            Event(
                id=str(r["id"]), world_id=str(r["world_id"]), type=r["type"], scene=r["scene"],
                activity=r["activity"], start_at=r["start_at"], end_at=r["end_at"],
                participant_ids=list(r["participant_ids"]), local_date=local_date,
                simulation_version=plan["simulation_version"],
                priority=_PRIORITIES.index(r["priority"]) + 1, status=r["status"],
                metadata=r["metadata"] or {}, location=r["location"], layer=r["layer"],
            )
            for r in rows
        ]

    def save_daily_plan(self, world_id: str, local_date: date, events: list[Event]) -> bool:
        version = events[0].simulation_version if events else None
        with self._pool.connection() as conn, conn.transaction():
            if version is None:
                row = conn.execute(
                    "select simulation_version from worldpane.worlds where id = %s", (world_id,)
                ).fetchone()
                version = row["simulation_version"]
            plan = conn.execute(
                """insert into worldpane.daily_plans (world_id, local_date, simulation_version)
                   values (%s, %s, %s)
                   on conflict do nothing
                   returning id""",
                (world_id, local_date, version),
            ).fetchone()
            if plan is None:
                return False  # someone else persisted it first; generation is deterministic
            with conn.cursor() as cur:
                cur.executemany(
                    """insert into worldpane.events
                         (id, world_id, daily_plan_id, type, scene, location, activity, layer,
                          priority, status, start_at, end_at, metadata)
                       values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    [
                        (e.id, world_id, plan["id"], e.type, e.scene, e.location, e.activity, e.layer,
                         _priority_to_db(e.priority), e.status, e.start_at, e.end_at, Jsonb(e.metadata))
                        for e in events
                    ],
                )
                cur.executemany(
                    """insert into worldpane.event_participants (event_id, character_id, world_id)
                       values (%s, %s, %s)""",
                    [(e.id, cid, world_id) for e in events for cid in e.participant_ids],
                )
        return True

    # --- devices -----------------------------------------------------------------------
    def add_device(self, device: Device) -> None:
        with self._pool.connection() as conn:
            self._insert_device(conn, device)

    @staticmethod
    def _insert_device(conn, device: Device) -> None:
        conn.execute(
            """insert into worldpane.devices
                 (id, world_id, device_token_hash, firmware_version, paired_at, created_at)
               values (%s, %s, %s, %s, %s, %s)""",
            (device.id, device.world_id, device.device_token_hash, device.firmware_version,
             device.created_at, device.created_at),
        )

    @staticmethod
    def _device(r: dict[str, Any]) -> Device:
        return Device(
            id=str(r["id"]), world_id=str(r["world_id"]) if r["world_id"] else "",
            device_token_hash=r["device_token_hash"], created_at=r["created_at"],
            firmware_version=r["firmware_version"], last_seen_at=r["last_seen_at"],
        )

    def get_device_by_token_hash(self, token_hash: str) -> Device | None:
        with self._pool.connection() as conn:
            r = conn.execute(
                """select * from worldpane.devices
                    where device_token_hash = %s and revoked_at is null and world_id is not null""",
                (token_hash,),
            ).fetchone()
        return self._device(r) if r else None

    def touch_device(self, device_id: str, seen_at: datetime) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                "update worldpane.devices set last_seen_at = %s where id = %s", (seen_at, device_id)
            )

    def list_devices(self, world_id: str) -> list[Device]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "select * from worldpane.devices where world_id = %s order by created_at, id", (world_id,)
            ).fetchall()
        return [self._device(r) for r in rows]

    # --- pairing codes ---------------------------------------------------------------------
    @staticmethod
    def _code(r: dict[str, Any]) -> PairingCode:
        return PairingCode(
            id=str(r["id"]), world_id=str(r["world_id"]), code_hash=r["code_hash"],
            expires_at=r["expires_at"], max_uses=r["max_uses"], used_count=r["used_count"],
            created_at=r["created_at"],
        )

    def add_pairing_code(self, code: PairingCode) -> None:
        with self._pool.connection() as conn, conn.transaction():
            self._insert_pairing_code(conn, code)

    @staticmethod
    def _insert_pairing_code(conn, code: PairingCode) -> None:
        # Retire an expired-but-unconsumed code with the same value so the value can be reused.
        conn.execute(
            """update worldpane.pairing_codes set consumed_at = %s, consumed_reason = 'expired'
                where code_hash = %s and consumed_at is null and expires_at <= %s""",
            (code.created_at, code.code_hash, code.created_at),
        )
        try:
            with conn.transaction():
                conn.execute(
                    """insert into worldpane.pairing_codes
                         (id, world_id, code_hash, expires_at, max_uses, used_count, created_at)
                       values (%s, %s, %s, %s, %s, %s, %s)""",
                    (code.id, code.world_id, code.code_hash, code.expires_at, code.max_uses,
                     code.used_count, code.created_at),
                )
        except errors.UniqueViolation as exc:
            raise ValueError("an active pairing code with this value already exists") from exc

    def get_pairing_code_by_hash(self, code_hash: str) -> PairingCode | None:
        with self._pool.connection() as conn:
            r = conn.execute(
                """select * from worldpane.pairing_codes where code_hash = %s
                    order by (consumed_at is null) desc, created_at desc limit 1""",
                (code_hash,),
            ).fetchone()
        return self._code(r) if r else None

    def redeem_pairing_code(self, code_id: str, device: Device, now: datetime) -> PairingCode:
        with self._pool.connection() as conn:
            with conn.transaction():
                r = conn.execute(
                    """update worldpane.pairing_codes
                          set used_count = used_count + 1,
                              consumed_at = case when used_count + 1 >= max_uses then %s end,
                              consumed_reason = case when used_count + 1 >= max_uses
                                                     then 'exhausted'::worldpane.pairing_consumed_reason end
                        where id = %s and consumed_at is null and expires_at > %s and used_count < max_uses
                        returning *""",
                    (now, code_id, now),
                ).fetchone()
                if r is not None:
                    # Same transaction: if this insert fails, the use above is rolled back.
                    self._insert_device(conn, device)
                    return self._code(r)
            row = conn.execute(
                "select * from worldpane.pairing_codes where id = %s", (code_id,)
            ).fetchone()
            if row is None or row["consumed_reason"] in ("exhausted", "revoked") or (
                row["used_count"] >= row["max_uses"]
            ):
                raise PairingCodeRejected("exhausted")
            if row["consumed_at"] is None:
                conn.execute(
                    """update worldpane.pairing_codes set consumed_at = %s, consumed_reason = 'expired'
                        where id = %s and consumed_at is null""",
                    (now, code_id),
                )
            raise PairingCodeRejected("expired")

    # --- device input ------------------------------------------------------------------
    def add_device_input(self, item: DeviceInput) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """insert into worldpane.device_inputs (id, device_id, world_id, type, button, payload, received_at)
                   values (%s, %s, %s, %s, %s, %s, %s)""",
                (item.id, item.device_id, item.world_id or None, item.type, item.button,
                 Jsonb(item.payload), item.received_at),
            )

    def list_device_inputs(self, world_id: str) -> list[DeviceInput]:
        """Not part of the Protocol; handy for tests/debugging."""
        with self._pool.connection() as conn:
            rows = conn.execute(
                "select * from worldpane.device_inputs where world_id = %s order by received_at, id", (world_id,)
            ).fetchall()
        return [
            DeviceInput(
                id=str(r["id"]), device_id=str(r["device_id"]), world_id=str(r["world_id"]),
                type=r["type"], button=r["button"], received_at=r["received_at"], payload=r["payload"],
            )
            for r in rows
        ]
