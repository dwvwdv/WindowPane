"""Conflict Resolver（規格 §14、§15 step 8）。

依 §14 固定優先級（Fixed > Meal > Shared > Temporary > Leisure > Idle）依序接受事件：
- 與已接受的較高 / 同優先事件 overlap → 嘗試在 move_window 內移動（由近到遠搜尋）。
- 無法移動 → 取消。
- 個人休閒與共同事件不可覆蓋 Base Schedule；用餐與上班/上課 temporary event 可覆蓋 Base。
- 移動後仍須遵守同 type 事件的 cooldown。
結果保證：每個角色的 foreground 事件互不重疊，不會產生矛盾的 Current State。
本模組不使用 RNG，因此結果完全由輸入決定。
"""

from __future__ import annotations

from .defaults import CONFLICT_MOVE_STEP_MIN
from .draft import Draft
from .models import EventKind, Layer
from .timeutil import fmt_hhmm, overlaps


def _fits(d: Draft, start: int, accepted: list[Draft], base: list[Draft]) -> bool:
    end = start + d.duration
    for other in accepted:
        shares = bool(set(d.participants) & set(other.participants))
        # 同 type 事件須遵守 cooldown（含被移動過的事件）。共同事件的 cooldown 是整個 World 共用
        # （與 generate_shared 一致），即使參與者不重疊也要遵守；個人事件只看共用參與者。
        if other.type == d.type and other.kind == d.kind and (shares or d.kind == EventKind.SHARED):
            gap = max(d.cooldown, other.cooldown)
            if gap and start < other.end + gap and other.start < end + gap:
                return False
        if shares and overlaps(start, end, other.start, other.end):
            return False
    if not d.overlay_base:
        for b in base:
            if set(d.participants) & set(b.participants) and overlaps(start, end, b.start, b.end):
                return False
    return True


def _find_slot(d: Draft, accepted: list[Draft], base: list[Draft], step: int) -> int | None:
    if d.move_window is None:
        return None
    lo, hi = d.move_window
    if hi < lo:
        return None
    k = 1
    while True:
        later, earlier = d.start + k * step, d.start - k * step
        if later > hi and earlier < lo:
            return None
        for candidate in (later, earlier):
            if lo <= candidate <= hi and _fits(d, candidate, accepted, base):
                return candidate
        k += 1


def resolve_conflicts(
    drafts: list[Draft], step: int = CONFLICT_MOVE_STEP_MIN
) -> tuple[list[Draft], list[Draft]]:
    """回傳 (保留的事件, 被取消的事件)。"""
    base = [d for d in drafts if d.layer == Layer.BASE]
    foreground = sorted(
        (d for d in drafts if d.layer != Layer.BASE), key=lambda d: (int(d.priority), d.seq)
    )
    accepted: list[Draft] = []
    cancelled: list[Draft] = []
    for d in foreground:
        if _fits(d, d.start, accepted, base):
            accepted.append(d)
            continue
        new_start = _find_slot(d, accepted, base, step)
        if new_start is None:
            d.metadata["cancel_reason"] = "conflict"
            cancelled.append(d)
            continue
        d.metadata["moved_from"] = fmt_hhmm(d.start)
        duration = d.duration
        d.start, d.end = new_start, new_start + duration
        accepted.append(d)
    return base + accepted, cancelled
