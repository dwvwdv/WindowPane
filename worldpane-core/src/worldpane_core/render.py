"""把 DailyPlan 轉成人類可讀的 Timeline 文字（規格 §17 範例格式）。"""

from __future__ import annotations

from .models import Character, EventKind, Layer
from .planner import DailyPlan
from .timeline import build_segments

_WEEKDAY_ZH = "一二三四五六日"


def _hhmm(dt) -> str:
    return dt.strftime("%H:%M")


def format_timeline(plan: DailyPlan, characters: list[Character], show_details: bool = True) -> str:
    names = {c.id: c.display_name for c in characters}
    d = plan.local_date
    header = f"{d.isoformat()}（{_WEEKDAY_ZH[d.weekday()]}）{'假日' if plan.calendar.holiday else '平日'}"
    lines = [header]
    for c in sorted(characters, key=lambda c: c.id):
        ctx = plan.contexts.get(c.id)
        tag = "  （請假）" if ctx and ctx.on_leave else ""
        lines.append("")
        lines.append(f"{c.display_name}{tag}")
        entries: list[tuple[object, int, str]] = []
        seen_base: set[str] = set()
        for seg in build_segments(plan.events, c.id):
            e = seg.event
            if e is None:
                continue
            if e.layer == Layer.BASE:
                label = e.metadata.get("resume_label") if e.id in seen_base else e.metadata.get("label")
                seen_base.add(e.id)
            elif e.kind == EventKind.SHARED:
                others = "、".join(names.get(p, p) for p in e.participants if p != c.id)
                label = f"和{others}{e.metadata.get('label', e.type)}"
            else:
                label = e.metadata.get("label", e.type)
            detail = f"  [{e.location} · {e.activity}]" if show_details else ""
            entries.append((seg.start, 1, f"{_hhmm(seg.start)}–{_hhmm(seg.end)}  {label}{detail}"))
        for e in plan.events:
            if e.layer == Layer.BASE and c.id in e.participants and e.metadata.get("end_label"):
                entries.append((e.end_at, 0, f"{_hhmm(e.end_at)}        {e.metadata['end_label']}"))
        if not entries:
            lines.append("  （整天閒置）")
        for _, _, text in sorted(entries, key=lambda t: (t[0], t[1])):
            lines.append(f"  {text}")
    return "\n".join(lines)
