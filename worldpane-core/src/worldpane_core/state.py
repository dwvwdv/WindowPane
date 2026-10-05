"""Current State（規格 §19）：給定事件與時間點，回傳每個角色目前的 scene / activity / location。"""

from __future__ import annotations

from datetime import datetime

from .defaults import IDLE_STATE
from .models import CharacterState, Event
from .timeline import build_segments, character_events


def _idle(character_id: str, started_at: datetime | None, ends_at: datetime | None) -> CharacterState:
    return CharacterState(
        character_id=character_id,
        scene=IDLE_STATE["scene"],
        activity=IDLE_STATE["activity"],
        location=IDLE_STATE["location"],
        started_at=started_at,
        ends_at=ends_at,
    )


def current_state(
    events: list[Event], now: datetime, character_ids: list[str] | None = None
) -> dict[str, CharacterState]:
    """回傳 {character_id: CharacterState}。

    character_ids 未提供時，以事件 participants 推得角色列表；
    若提供，沒有任何事件的角色也會以 idle fallback 出現。
    now 必須是 tz-aware datetime。
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if character_ids is None:
        ids: set[str] = set()
        for e in events:
            ids.update(e.participants)
        character_ids = sorted(ids)

    result: dict[str, CharacterState] = {}
    for cid in character_ids:
        mine = character_events(events, cid)
        segment = next((s for s in build_segments(events, cid) if s.start <= now < s.end), None)
        if segment is not None and segment.event is not None:
            e = segment.event
            result[cid] = CharacterState(
                character_id=cid,
                scene=e.scene,
                activity=e.activity,
                location=e.location,
                started_at=segment.start,
                ends_at=segment.end,
                event_id=e.id,
                event_type=e.type,
            )
            continue
        # Idle fallback（§14 priority 6）
        before = [e.end_at for e in mine if e.end_at <= now]
        after = [e.start_at for e in mine if e.start_at > now]
        result[cid] = _idle(cid, max(before) if before else None, min(after) if after else None)
    return result
