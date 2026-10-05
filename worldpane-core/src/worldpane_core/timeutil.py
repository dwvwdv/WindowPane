"""時間工具。Simulation 內部以「當地當日分鐘數」(0..1440) 運算，輸出時轉為 tz-aware datetime。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

DAY_MINUTES = 24 * 60


def parse_hhmm(value: str) -> int:
    h, m = value.split(":")
    minutes = int(h) * 60 + int(m)
    if not 0 <= minutes <= DAY_MINUTES:
        raise ValueError(f"time out of range: {value}")
    return minutes


def fmt_hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def parse_window(window: list[str] | tuple[str, str]) -> tuple[int, int]:
    start, end = parse_hhmm(window[0]), parse_hhmm(window[1])
    if end < start:
        raise ValueError(f"invalid window: {window}")
    return start, end


def local_midnight(local_date: date, tz: ZoneInfo) -> datetime:
    return datetime(local_date.year, local_date.month, local_date.day, tzinfo=tz)


def to_datetime(local_date: date, minutes: int, tz: ZoneInfo) -> datetime:
    # aware datetime + timedelta 為 wall-clock 運算，符合「當地時間 HH:MM」語意
    return local_midnight(local_date, tz) + timedelta(minutes=minutes)


def overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end
