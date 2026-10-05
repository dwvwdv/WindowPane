"""Future Supabase/Postgres Repository — seam only, no DB code yet.

TODO(postgres):
  * Implement every method of ``repositories.base.Repository`` against the schema under
    ``/supabase`` (tables per spec §28: worlds, characters, character_profiles,
    character_relationships, events, event_participants, devices, device_preferences,
    pairing_codes, plus a device_inputs log).
  * ``worlds`` needs a ``revision bigint`` column (or derive it from max(events.updated_at))
    so the Display API can produce ETags.
  * ``events`` has no ``activity`` column in the §28 sketch; store it as a column or in
    ``metadata->>'activity'``. Also store ``local_date`` so ``get_daily_plan`` is an index hit.
  * ``save_daily_plan`` must be idempotent under concurrency: insert inside one transaction,
    guarded by a unique (world_id, local_date) row in e.g. ``daily_plans``; on conflict do
    nothing and return False.
  * ``consume_pairing_code`` must be a single conditional UPDATE ... RETURNING (see base.py).
  * Only ``device_token_hash`` / ``code_hash`` are stored; never the raw values.
  * Connect with ``Settings.database_url`` (env ``WORLDPANE_DATABASE_URL``); use the
    service-role connection server-side only, never ship it to devices.
"""

from __future__ import annotations


class PostgresRepository:  # pragma: no cover - placeholder
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise RuntimeError("WORLDPANE_DATABASE_URL is required for the postgres repository")
        raise NotImplementedError(
            "PostgresRepository is not implemented yet; use WORLDPANE_REPOSITORY=memory"
        )
