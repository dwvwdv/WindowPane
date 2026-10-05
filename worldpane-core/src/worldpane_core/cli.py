"""CLI：python -m worldpane_core timeline --date 2026-10-05 [--characters 3]"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, time

from .planner import plan_day
from .profiles import demo_world
from .render import format_timeline
from .state import current_state


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--date", required=True, type=date.fromisoformat, help="World 當地日期 YYYY-MM-DD")
    p.add_argument("--characters", type=int, default=2, help="角色數（1..N，預設 2）")
    p.add_argument("--world-id", default="world_demo")
    p.add_argument("--version", default="1", help="simulation_version")
    p.add_argument("--json", action="store_true", help="輸出 JSON")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="worldpane_core", description="Worldpane Simulation Core")
    sub = parser.add_subparsers(dest="command", required=True)
    tl = sub.add_parser("timeline", help="印出指定日期每個角色的 Timeline")
    _common(tl)
    st = sub.add_parser("state", help="印出指定時間每個角色的 Current State")
    _common(st)
    st.add_argument("--time", required=True, type=time.fromisoformat, help="當地時間 HH:MM")
    args = parser.parse_args(argv)

    if args.characters < 1:
        parser.error("--characters must be >= 1")
    world, characters, relationships = demo_world(
        args.characters, world_id=args.world_id, simulation_version=args.version
    )
    plan = plan_day(world, characters, relationships, args.date)

    if args.command == "timeline":
        if args.json:
            print(json.dumps([e.to_dict() for e in plan.events], ensure_ascii=False, indent=2))
        else:
            print(format_timeline(plan, characters))
        return 0

    now = datetime.combine(args.date, args.time, tzinfo=world.tz)
    states = current_state(plan.events, now, [c.id for c in characters])
    if args.json:
        print(json.dumps({k: v.to_dict() for k, v in states.items()}, ensure_ascii=False, indent=2))
    else:
        names = {c.id: c.display_name for c in characters}
        print(now.isoformat())
        for cid, s in states.items():
            span = f"{s.started_at.strftime('%H:%M') if s.started_at else '--:--'}–{s.ends_at.strftime('%H:%M') if s.ends_at else '--:--'}"
            print(f"  {names[cid]}: {s.location} / {s.activity} ({s.scene}) {span}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
