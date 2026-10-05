"""把 Event（Base + Foreground 疊加）攤平成每個角色的狀態區段。

區段內的 active 事件 = 覆蓋該時段、優先級最高的 foreground 事件；沒有則為 Base；再沒有則 Idle。
current_state 與 CLI 都使用這份邏輯，確保兩者一致。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import Event, Layer


@dataclass(frozen=True)
class Segment:
    start: datetime
    end: datetime
    event: Event | None  # None = idle


def _active(events: list[Event], start: datetime) -> Event | None:
    covering = [e for e in events if e.start_at <= start < e.end_at]
    fg = [e for e in covering if e.layer != Layer.BASE]
    if fg:
        return min(fg, key=lambda e: (e.priority, e.start_at, e.id))
    base = [e for e in covering if e.layer == Layer.BASE]
    if base:
        return min(base, key=lambda e: (e.start_at, e.id))
    return None


def character_events(events: list[Event], character_id: str) -> list[Event]:
    return [e for e in events if character_id in e.participants and e.status != "cancelled"]


def build_segments(events: list[Event], character_id: str) -> list[Segment]:
    mine = character_events(events, character_id)
    if not mine:
        return []
    points = sorted({e.start_at for e in mine} | {e.end_at for e in mine})
    segments: list[Segment] = []
    for a, b in zip(points, points[1:]):
        active = _active(mine, a)
        if segments and segments[-1].event is active and segments[-1].end == a:
            segments[-1] = Segment(segments[-1].start, b, active)
        else:
            segments.append(Segment(a, b, active))
    return segments
