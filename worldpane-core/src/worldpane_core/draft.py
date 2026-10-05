"""內部排程用的可變 Draft 事件（分鐘制），最後由 planner 轉為 Event。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import Layer, Priority
from .timeutil import overlaps


@dataclass
class Draft:
    kind: str
    type: str
    label: str
    scene: str
    location: str
    activity: str
    start: int
    end: int
    priority: Priority
    participants: tuple[str, ...]
    layer: str = Layer.FOREGROUND
    # 可否覆蓋 Base Schedule（用餐、上班/上課 temporary event 可以；個人休閒、共同事件不行）
    overlay_base: bool = False
    # 衝突時可移動的 start 範圍 (earliest_start, latest_start)；None 表示不可移動
    move_window: tuple[int, int] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    seq: int = 0  # 生成順序（衝突解決時同優先級的 tie-breaker）

    @property
    def duration(self) -> int:
        return self.end - self.start

    def overlaps(self, other: "Draft") -> bool:
        return overlaps(self.start, self.end, other.start, other.end)


def is_free(
    character_id: str,
    start: int,
    end: int,
    drafts: list[Draft],
    *,
    blocking_priority: int,
    overlay_base: bool,
) -> bool:
    """character 在 [start, end) 是否沒有「不可覆蓋」事件。

    不可覆蓋 = 同一角色、優先級數字 <= blocking_priority 的 foreground 事件；
    以及 Base 事件（除非 overlay_base=True）。
    """
    for d in drafts:
        if character_id not in d.participants:
            continue
        if not overlaps(start, end, d.start, d.end):
            continue
        if d.layer == Layer.BASE:
            if not overlay_base:
                return False
            continue
        if d.priority <= blocking_priority:
            return False
    return True
