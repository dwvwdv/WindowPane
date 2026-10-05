"""Calendar Context（規格 §13、§15 step 1）。

假日不建立另一套引擎，只改變 Context：weekday / holiday（/ leave）。
週末 = holiday；World.holiday_dates 為假日行事曆 hook（國定假日、連假等）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class CalendarContext:
    local_date: date
    weekday: bool
    holiday: bool

    @property
    def key(self) -> str:
        return "holiday" if self.holiday else "weekday"


@dataclass(frozen=True)
class DayContext:
    """單一角色當日 Context = Calendar + Leave。"""

    calendar: CalendarContext
    on_leave: bool

    @property
    def key(self) -> str:
        """個人事件池使用的 context key：holiday > leave > weekday。"""
        if self.calendar.holiday:
            return "holiday"
        if self.on_leave:
            return "leave"
        return "weekday"

    @property
    def tags(self) -> frozenset[str]:
        tags = {self.calendar.key}
        if self.on_leave:
            tags.add("leave")
        return frozenset(tags)


def resolve_calendar_context(local_date: date, holiday_dates: frozenset[date] | set[date] = frozenset()) -> CalendarContext:
    is_holiday = local_date.weekday() >= 5 or local_date in holiday_dates
    return CalendarContext(local_date=local_date, weekday=not is_holiday, holiday=is_holiday)
