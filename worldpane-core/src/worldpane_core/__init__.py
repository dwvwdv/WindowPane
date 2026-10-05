"""Worldpane（窗間）Simulation Core。

純 Python、無 DB、無 Web。給定 World + Characters(1..N) + Relationships + 日期，
決定性地產生當日 Event Timeline。
"""

from .calendar_ctx import CalendarContext, DayContext, resolve_calendar_context
from .leave import cycle_leave_days, is_on_leave, monthly_leave_days
from .models import (
    Character,
    CharacterProfile,
    CharacterRelationship,
    CharacterState,
    Event,
    EventKind,
    Layer,
    Priority,
    World,
)
from .planner import DailyPlan, generate_daily_plan, plan_day
from .profiles import demo_world, freelancer_profile, office_worker_profile, student_profile
from .render import format_timeline
from .seeds import character_seed, shared_seed
from .state import current_state

__version__ = "0.1.0"

__all__ = [
    "CalendarContext",
    "Character",
    "CharacterProfile",
    "CharacterRelationship",
    "CharacterState",
    "DailyPlan",
    "DayContext",
    "Event",
    "EventKind",
    "Layer",
    "Priority",
    "World",
    "character_seed",
    "current_state",
    "cycle_leave_days",
    "demo_world",
    "format_timeline",
    "freelancer_profile",
    "generate_daily_plan",
    "is_on_leave",
    "monthly_leave_days",
    "office_worker_profile",
    "plan_day",
    "resolve_calendar_context",
    "shared_seed",
    "student_profile",
]
