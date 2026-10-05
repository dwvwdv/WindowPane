"""預設設定值。

!!! 注意 !!!
本檔中所有「機率 / 權重 / 頻率 / cooldown / 持續時間」數值皆為 PLACEHOLDER，
依規格 §34「尚未決定但不阻塞架構的設定」，正式數值為 TBD，需由需求方定案。
Simulation Engine 不得 hard-code 這些數值；一律經由 Profile / World Config 傳入。

標記 `# TBD §34` 的欄位為尚未定案的 placeholder。
時間一律以 World timezone 的當地時間 "HH:MM" 表示。
"""

from __future__ import annotations

import copy
from typing import Any

DEFAULT_TIMEZONE = "Asia/Taipei"
DEFAULT_SIMULATION_VERSION = "1"

# 每餐之間最小間隔（§8：下一餐開始 >= 上一餐結束 + 90 分鐘）— 規格已定案
MEAL_MIN_GAP_MIN = 90

# 衝突解決時，移動事件的搜尋步距（分鐘）
CONFLICT_MOVE_STEP_MIN = 5

# Idle fallback 狀態（§14 priority 6）
IDLE_STATE = {"scene": "home_living_room", "location": "HOME", "activity": "idle"}

# ---------------------------------------------------------------------------
# Meal（§8）。時段與 15~20 分鐘為規格定案；skip_probability 為 TBD。
# ---------------------------------------------------------------------------
_MEAL_CONFIG: dict[str, Any] = {
    "min_gap_min": MEAL_MIN_GAP_MIN,
    "meals": [
        {
            "type": "breakfast",
            "label": "早餐",
            "window": ["08:00", "11:00"],
            "min_duration": 15,
            "max_duration": 20,
            "skip_probability": 0.15,  # TBD §34 breakfast_skip_probability
        },
        {
            "type": "lunch",
            "label": "午餐",
            "window": ["11:00", "14:00"],
            "min_duration": 15,
            "max_duration": 20,
            "skip_probability": 0.05,  # TBD §34 lunch_skip_probability
        },
        {
            "type": "dinner",
            "label": "晚餐",
            "window": ["17:00", "20:00"],
            "min_duration": 15,
            "max_duration": 20,
            "skip_probability": 0.05,  # TBD §34 dinner_skip_probability
        },
    ],
    # 用餐地點：若用餐開始時位於 Base block 內，沿用該 block 的 meal_location/meal_scene。
    "home_location": "HOME",
    "home_scene": "home_kitchen",
}

# ---------------------------------------------------------------------------
# Leave（§7）
# ---------------------------------------------------------------------------
_MONTHLY_LEAVE: dict[str, Any] = {
    "type": "monthly",
    "probability": 0.5,  # TBD §34 leave_probability_per_month（小白）
    "max_per_month": 1,  # 規格定案
}

_CYCLE_LEAVE: dict[str, Any] = {
    "type": "cycle",
    # None → 使用 World.simulation_start_date 作為 anchor
    "anchor_date": None,
    "cycle_days": 14,  # 規格定案
    "max_per_cycle": 1,  # 規格定案
    "probability": 0.4,  # TBD §34 leave_probability_per_14_day_cycle（小雞毛）
}

# ---------------------------------------------------------------------------
# Schedule（§7）
# days: 0=Mon ... 6=Sun
# ---------------------------------------------------------------------------
_STUDENT_SCHEDULE: dict[str, Any] = {
    "blocks": [
        {
            "type": "school",
            "days": [0, 1, 2, 3, 4],
            "start": "08:30",
            "end": "17:30",
            "location": "SCHOOL",
            "activity": "in_class",
            "scene": "school_classroom",
            "label": "上學",
            "resume_label": "繼續上課",
            "end_label": "放學",
            "meal_location": "SCHOOL",
            "meal_scene": "school_cafeteria",
            "include_holidays": False,
        }
    ]
}

_OFFICE_SCHEDULE: dict[str, Any] = {
    "blocks": [
        {
            "type": "work",
            "days": [0, 1, 2, 3, 4],
            "start": "08:30",
            "end": "17:30",
            "location": "OFFICE",
            "activity": "working",
            "scene": "office_desk",
            "label": "上班",
            "resume_label": "繼續工作",
            "end_label": "下班",
            "meal_location": "OFFICE",
            "meal_scene": "office_pantry",
            "include_holidays": False,
        }
    ]
}

# 範例：非官方的第三種 Profile（展示 1..N 與不同作息；§5 World B 範例）
_FREELANCER_SCHEDULE: dict[str, Any] = {
    "blocks": [
        {
            "type": "freelance_work",
            "days": [0, 1, 2, 3],
            "start": "10:00",
            "end": "16:00",
            "location": "CAFE",
            "activity": "working",
            "scene": "cafe_laptop",
            "label": "在咖啡廳接案",
            "resume_label": "繼續接案",
            "end_label": "收工",
            "meal_location": "CAFE",
            "meal_scene": "cafe_table",
            "include_holidays": False,
        }
    ]
}

# ---------------------------------------------------------------------------
# Work / School temporary events（§7、§9）。全部 weight / 頻率皆 TBD §34。
# 每個 Base block 嘗試 attempts_per_block 次，每次以 trigger_probability 判定是否發生。
# ---------------------------------------------------------------------------
_STUDENT_TEMPORARY: dict[str, Any] = {
    "attempts_per_block": 3,  # TBD §34
    "trigger_probability": 0.5,  # TBD §34
    "events": [
        {
            "type": "sleeping_in_class",
            "label": "睡覺",
            "activity": "sleeping",
            "weight": 50,  # TBD §34 上課睡覺 weight
            "min_duration": 10,
            "max_duration": 30,
            "cooldown_min": 60,
        },
        {
            "type": "gaming_in_class",
            "label": "玩遊戲",
            "activity": "gaming",
            "weight": 50,  # TBD §34 上課玩遊戲 weight
            "min_duration": 10,
            "max_duration": 25,
            "cooldown_min": 60,
        },
    ],
}

_OFFICE_TEMPORARY: dict[str, Any] = {
    "attempts_per_block": 3,  # TBD §34
    "trigger_probability": 0.5,  # TBD §34
    "events": [
        {
            "type": "slacking",
            "label": "摸魚",
            "activity": "slacking",
            "weight": 100,  # TBD §34 摸魚 weight / frequency
            "min_duration": 10,
            "max_duration": 30,
            "cooldown_min": 45,
        }
    ],
}

_FREELANCER_TEMPORARY: dict[str, Any] = {
    "attempts_per_block": 2,  # TBD §34
    "trigger_probability": 0.4,  # TBD §34
    "events": [
        {
            "type": "slacking",
            "label": "摸魚",
            "activity": "slacking",
            "weight": 100,  # TBD §34
            "min_duration": 10,
            "max_duration": 25,
            "cooldown_min": 45,
        }
    ],
}

# ---------------------------------------------------------------------------
# Individual leisure events（§10、§13）。weight / duration / cooldown / allowed_time 皆 TBD §34。
# windows：該 context 下個人事件池開放時段（會自動避開 Base / 用餐等不可覆蓋時段）。
# allowed_context：weekday / holiday / leave。
# ---------------------------------------------------------------------------
_LEISURE_EVENTS: list[dict[str, Any]] = [
    {
        "type": "shower",
        "label": "洗澡",
        "scene": "home_bathroom",
        "location": "HOME",
        "activity": "shower",
        "weight": 20,  # TBD §34
        "min_duration": 10,
        "max_duration": 25,
        "allowed_time": [["17:30", "23:30"]],
        "allowed_context": ["weekday", "holiday", "leave"],
        "cooldown_min": 24 * 60,  # 一天一次
    },
    {
        "type": "phone",
        "label": "滑手機",
        "scene": "home_living_room",
        "location": "HOME",
        "activity": "phone",
        "weight": 30,  # TBD §34
        "min_duration": 10,
        "max_duration": 40,
        "allowed_time": [["07:00", "23:30"]],
        "allowed_context": ["weekday", "holiday", "leave"],
        "cooldown_min": 30,
    },
    {
        "type": "reading",
        "label": "看小說",
        "scene": "home_bedroom",
        "location": "HOME",
        "activity": "reading",
        "weight": 20,  # TBD §34
        "min_duration": 15,
        "max_duration": 60,
        "allowed_time": [["09:00", "23:30"]],
        "allowed_context": ["weekday", "holiday", "leave"],
        "cooldown_min": 90,
    },
    {
        "type": "gaming",
        "label": "玩遊戲",
        "scene": "home_living_room",
        "location": "HOME",
        "activity": "gaming",
        "weight": 20,  # TBD §34
        "min_duration": 20,
        "max_duration": 60,
        "allowed_time": [["09:00", "23:30"]],
        "allowed_context": ["weekday"],
        "cooldown_min": 90,
    },
    {
        "type": "gaming_long",
        "label": "長時間打電動",
        "scene": "home_living_room",
        "location": "HOME",
        "activity": "gaming",
        "weight": 20,  # TBD §34
        "min_duration": 60,
        "max_duration": 180,
        "allowed_time": [["09:00", "23:30"]],
        "allowed_context": ["holiday", "leave"],
        "cooldown_min": 180,
    },
    {
        "type": "shopping",
        "label": "出門逛街",
        "scene": "mall",
        "location": "MALL",
        "activity": "shopping",
        "weight": 15,  # TBD §34
        "min_duration": 60,
        "max_duration": 150,
        "allowed_time": [["10:00", "21:00"]],
        "allowed_context": ["holiday", "leave"],
        "cooldown_min": 24 * 60,
    },
]

_LEISURE_CONFIG: dict[str, Any] = {
    "windows": {
        "weekday": [["17:30", "23:30"]],
        "holiday": [["09:00", "23:30"]],
        "leave": [["09:00", "23:30"]],
    },
    "gap_min": 0,  # TBD §34 兩個個人事件間的 idle 間隔下限
    "gap_max": 40,  # TBD §34
    "events": _LEISURE_EVENTS,
}

# ---------------------------------------------------------------------------
# Shared / Group events（§11、§12、§13）— World 層級設定。
# weight / duration / cooldown / allowed_time / 觸發機率皆 TBD §34；participants 範圍依規格範例。
# relationship_required：None 或 relationship_type（例如 "couple"），要求所有參與者兩兩具此關係。
# ---------------------------------------------------------------------------
_SHARED_EVENT_CONFIG: dict[str, Any] = {
    "attempts": 2,  # TBD §34 每日嘗試次數
    "trigger_probability": 0.6,  # TBD §34 每次嘗試是否產生共同事件
    "slot_step_min": 5,
    "max_slot_tries": 12,
    "rules": [
        {
            "type": "watch_movie",
            "label": "看電影",
            "scene": "home_living_room_tv",
            "location": "HOME",
            "activity": "watch_movie",
            "weight": 30,  # TBD §34
            "min_participants": 2,
            "max_participants": None,  # None = N（不設上限）
            "relationship_required": None,
            "min_duration": 90,
            "max_duration": 150,
            "allowed_time": [["18:00", "23:30"]],
            "allowed_context": ["weekday", "holiday"],
            "max_per_day": 1,
            "cooldown_min": 0,
        },
        {
            "type": "date",
            "label": "約會",
            "scene": "city_cafe",
            "location": "CITY",
            "activity": "date",
            "weight": 25,  # TBD §34
            "min_participants": 2,
            "max_participants": 2,
            "relationship_required": "couple",
            "min_duration": 60,
            "max_duration": 180,
            "allowed_time": [["10:00", "23:00"]],
            "allowed_context": ["weekday", "holiday"],
            "max_per_day": 1,
            "cooldown_min": 0,
        },
        {
            "type": "group_dinner",
            "label": "一起出去吃飯",
            "scene": "restaurant",
            "location": "RESTAURANT",
            "activity": "dining_out",
            "weight": 20,  # TBD §34
            "min_participants": 2,
            "max_participants": 8,
            "relationship_required": None,
            "min_duration": 60,
            "max_duration": 120,
            "allowed_time": [["18:00", "22:30"]],
            "allowed_context": ["weekday", "holiday"],
            "max_per_day": 1,
            "cooldown_min": 0,
        },
        {
            "type": "basketball",
            "label": "打球",
            "scene": "basketball_court",
            "location": "PARK",
            "activity": "basketball",
            "weight": 25,  # TBD §34
            "min_participants": 2,
            "max_participants": 5,
            "relationship_required": None,
            "min_duration": 60,
            "max_duration": 120,
            "allowed_time": [["09:00", "18:00"]],
            "allowed_context": ["holiday"],
            "max_per_day": 1,
            "cooldown_min": 0,
        },
    ],
}


# ---------------------------------------------------------------------------
# Factory functions（回傳 deep copy，避免共享可變狀態）
# ---------------------------------------------------------------------------
def default_meal_config() -> dict[str, Any]:
    return copy.deepcopy(_MEAL_CONFIG)


def default_monthly_leave_config() -> dict[str, Any]:
    return copy.deepcopy(_MONTHLY_LEAVE)


def default_cycle_leave_config() -> dict[str, Any]:
    return copy.deepcopy(_CYCLE_LEAVE)


def no_leave_config() -> dict[str, Any]:
    return {"type": "none"}


def student_schedule_config() -> dict[str, Any]:
    return copy.deepcopy(_STUDENT_SCHEDULE)


def office_schedule_config() -> dict[str, Any]:
    return copy.deepcopy(_OFFICE_SCHEDULE)


def freelancer_schedule_config() -> dict[str, Any]:
    return copy.deepcopy(_FREELANCER_SCHEDULE)


def student_event_config() -> dict[str, Any]:
    return {
        "temporary": copy.deepcopy(_STUDENT_TEMPORARY),
        "leisure": copy.deepcopy(_LEISURE_CONFIG),
    }


def office_event_config() -> dict[str, Any]:
    return {
        "temporary": copy.deepcopy(_OFFICE_TEMPORARY),
        "leisure": copy.deepcopy(_LEISURE_CONFIG),
    }


def freelancer_event_config() -> dict[str, Any]:
    cfg = {
        "temporary": copy.deepcopy(_FREELANCER_TEMPORARY),
        "leisure": copy.deepcopy(_LEISURE_CONFIG),
    }
    cfg["leisure"]["windows"]["weekday"] = [["09:00", "23:30"]]
    return cfg


def default_shared_event_config() -> dict[str, Any]:
    return copy.deepcopy(_SHARED_EVENT_CONFIG)
