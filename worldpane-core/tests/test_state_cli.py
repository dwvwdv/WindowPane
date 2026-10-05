from datetime import date, datetime

from worldpane_core import current_state, demo_world, plan_day
from worldpane_core.cli import main


def test_current_state_school_hours_and_idle_fallback():
    world, chars, rels = demo_world(2)
    d = date(2026, 10, 5)
    plan = plan_day(world, chars, rels, d)
    ids = [c.id for c in chars]
    states = current_state(plan.events, datetime(2026, 10, 5, 10, 0, tzinfo=world.tz), ids)
    for cid in ids:
        if not plan.contexts[cid].on_leave:
            assert states[cid].location in ("SCHOOL", "OFFICE")
            assert states[cid].started_at <= datetime(2026, 10, 5, 10, 0, tzinfo=world.tz) < states[cid].ends_at
    night = current_state(plan.events, datetime(2026, 10, 5, 3, 0, tzinfo=world.tz), ids)
    for s in night.values():
        assert s.activity == "idle" and s.location == "HOME"


def test_current_state_matches_highest_priority_event():
    world, chars, rels = demo_world(3)
    plan = plan_day(world, chars, rels, date(2026, 10, 6))
    for e in plan.events:
        if e.layer == "base":
            continue
        mid = e.start_at + (e.end_at - e.start_at) / 2
        for cid in e.participants:
            s = current_state(plan.events, mid, [cid])[cid]
            assert s.event_id == e.id
            assert (s.activity, s.location, s.scene) == (e.activity, e.location, e.scene)


def test_character_without_events_is_idle():
    world, chars, rels = demo_world(1)
    s = current_state([], datetime(2026, 10, 5, 12, tzinfo=world.tz), ["char_x"])
    assert s["char_x"].activity == "idle"


def test_cli_timeline(capsys):
    assert main(["timeline", "--date", "2026-10-05", "--characters", "3"]) == 0
    out = capsys.readouterr().out
    assert "小白" in out and "小雞毛" in out and "阿毛" in out
    assert "上學" in out and "上班" in out


def test_cli_json_and_state(capsys):
    assert main(["timeline", "--date", "2026-10-05", "--json"]) == 0
    assert '"participants"' in capsys.readouterr().out
    assert main(["state", "--date", "2026-10-05", "--time", "18:42"]) == 0
    assert "小白" in capsys.readouterr().out
