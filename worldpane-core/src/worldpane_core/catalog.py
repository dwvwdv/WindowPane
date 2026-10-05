"""事件目錄（Event Catalog）：讓新事件只需要新增資料，不需要改 Simulation Core。

事件定義（EventDefinition）是純資料，通常存在 DB 的 ``event_definitions``：

* ``category``：``temporary``（上班 / 上學中的插曲）、``leisure``（個人生活事件）、
  ``shared``（2..N 人共同事件）。Base Schedule 與 Meal 屬於 Profile 結構，不在目錄內。
* ``params``：weight / duration / allowed_time / allowed_context / cooldown /
  participants … 等全部可調數值（規格 §34 的 TBD 一律放這裡，不 hard-code）。
* ``params.context_overrides``：依 Context（weekday / holiday / leave）覆寫
  ``enabled`` / ``weight`` / duration 等（規格 §13），未來的下雨、生日等 Context 也走這裡。

Profile 透過「事件池」挑選要用的 leisure / temporary 事件，並可對每個事件再覆寫參數；
World 的 shared 事件則取所有啟用中的 shared 定義，並可在 World 層級覆寫。

本模組把這些資料組裝成 Generator 吃的 config dict（見 :func:`build_event_config`、
:func:`build_shared_event_config`），並提供 :func:`validate_definition` 檢查資料是否可用。
"""

from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from . import defaults
from .timeutil import parse_window

CATEGORIES = ("temporary", "leisure", "shared")
CONTEXTS = ("weekday", "holiday", "leave")

# 定義欄位（非 params）中，可以被 overrides 覆寫的顯示欄位
_DISPLAY_FIELDS = ("label", "scene", "location", "activity")


@dataclass(frozen=True)
class EventDefinition:
    key: str
    category: str
    label: str
    params: Mapping[str, Any] = field(default_factory=dict)
    scene: str | None = None
    location: str | None = None
    activity: str | None = None
    enabled: bool = True
    # 抽籤順序會影響 RNG 結果，因此必須穩定：一律依 (sort_order, key) 排序。
    sort_order: int = 0
    # DB id（event_definitions.id）；官方定義為固定的 official_definition_id()。
    id: str | None = None


def _ordered(defs: Iterable[EventDefinition]) -> list[EventDefinition]:
    return sorted(defs, key=lambda d: (d.sort_order, d.key))


def _deep_merge(base: dict[str, Any], patch: Mapping[str, Any] | None) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (patch or {}).items():
        if isinstance(v, Mapping) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def materialize(defn: EventDefinition, overrides: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """把定義（+ Profile / World 覆寫）攤平成 Generator 使用的 event dict。"""
    ev: dict[str, Any] = {"type": defn.key, "label": defn.label, "enabled": defn.enabled}
    for name in ("scene", "location", "activity"):
        value = getattr(defn, name)
        if value is not None:
            ev[name] = value
    ev = _deep_merge(ev, defn.params)
    return _deep_merge(ev, overrides)


def for_context(events: Iterable[Mapping[str, Any]], context: str | None) -> list[dict[str, Any]]:
    """套用 ``context_overrides`` 並過濾掉在此 Context 不可用的事件。

    ``context`` 為 None 時只套用 ``enabled``（例如 temporary 事件只在 Base block 內發生）。
    沒有 ``allowed_context`` 的事件視為所有 Context 皆可用。
    """
    out: list[dict[str, Any]] = []
    for ev in events:
        resolved = dict(ev)
        if context is not None:
            override = (ev.get("context_overrides") or {}).get(context)
            if override:
                resolved = _deep_merge(resolved, override)
            allowed = resolved.get("allowed_context")
            if allowed is not None and context not in allowed:
                continue
        if not resolved.get("enabled", True):
            continue
        if float(resolved.get("weight", 1)) <= 0:
            continue
        out.append(resolved)
    return out


def validate_definition(defn: EventDefinition | Mapping[str, Any], category: str | None = None) -> list[str]:
    """回傳錯誤訊息清單；空清單代表可用。

    可傳 EventDefinition，或已 materialize（含 Profile / World 覆寫）的 event dict
    （此時需給 ``category``）。每個 ``context_overrides`` 套用後的版本也會一併檢查，
    因為 Generator 實際吃的是覆寫後的值。
    """
    if isinstance(defn, EventDefinition):
        category = defn.category
        ev = materialize(defn)
    else:
        category = category or str(defn.get("category", ""))
        ev = dict(defn)
    errors = _validate_effective(ev, category)
    overrides = ev.get("context_overrides") or {}
    if not isinstance(overrides, Mapping):
        return errors + [f"{ev.get('type', '?')}: context_overrides must be an object"]
    for ctx, patch in overrides.items():
        if not isinstance(patch, Mapping):
            errors.append(f"{ev.get('type', '?')}: context_overrides.{ctx} must be an object")
            continue
        errors += [f"{e} (context {ctx})" for e in _validate_effective(_deep_merge(ev, patch), category)]
    return errors


def _validate_effective(ev: Mapping[str, Any], category: str) -> list[str]:
    errors: list[str] = []
    key = ev.get("type", "?")
    if category not in CATEGORIES:
        errors.append(f"{key}: unknown category {category!r}")
    try:
        lo, hi = int(ev["min_duration"]), int(ev["max_duration"])
        if not 0 < lo <= hi:
            errors.append(f"{key}: need 0 < min_duration <= max_duration")
    except (KeyError, TypeError, ValueError):
        errors.append(f"{key}: min_duration / max_duration required")
    try:
        if float(ev.get("weight", 1)) < 0:
            errors.append(f"{key}: weight must be >= 0")
        int(ev.get("cooldown_min", 0))
    except (TypeError, ValueError):
        errors.append(f"{key}: weight / cooldown_min must be numbers")
    allowed_context = ev.get("allowed_context")
    if allowed_context is not None and (
        not isinstance(allowed_context, list) or not all(isinstance(c, str) for c in allowed_context)
    ):
        errors.append(f"{key}: allowed_context must be a list of strings")
    windows = ev.get("allowed_time")
    if category in ("leisure", "shared") and not windows:
        errors.append(f"{key}: allowed_time required for {category} events")
    for w in windows or []:
        try:
            start, end = parse_window(w)
            if start >= end:
                raise ValueError
        except (TypeError, ValueError, AttributeError, IndexError):
            errors.append(f"{key}: bad allowed_time window {w!r}")
    if category == "shared":
        min_p = ev.get("min_participants", 2)
        max_p = ev.get("max_participants")
        if not isinstance(min_p, int) or min_p < 2:
            errors.append(f"{key}: min_participants must be an integer >= 2")
        elif max_p is not None and (not isinstance(max_p, int) or max_p < min_p):
            errors.append(f"{key}: max_participants must be null (= N) or >= min_participants")
        try:
            int(ev.get("max_per_day", 1))
        except (TypeError, ValueError):
            errors.append(f"{key}: max_per_day must be an integer")
    return errors


OnInvalid = Callable[[str], None]


def _keep(ev: dict[str, Any], category: str, on_invalid: OnInvalid | None) -> bool:
    errors = validate_definition(ev, category)
    if not errors:
        return True
    if on_invalid is None:
        raise ValueError("; ".join(errors))
    on_invalid("; ".join(errors))
    return False


@dataclass(frozen=True)
class PoolEntry:
    """Profile 事件池的一筆：哪個定義 + 此 Profile 專屬覆寫。"""

    definition: EventDefinition
    overrides: Mapping[str, Any] = field(default_factory=dict)
    enabled: bool = True


def build_event_config(
    settings: Mapping[str, Any], pool: Iterable[PoolEntry], on_invalid: OnInvalid | None = None
) -> dict[str, Any]:
    """Profile 的 ``event_config`` 設定（不含事件清單）+ 事件池 → Generator 用的 event_config。

    ``settings`` 形如 ``{"temporary": {"attempts_per_block": 3, ...}, "leisure": {"windows": ...}}``。
    每個事件在套用所有覆寫後才驗證；無效者交給 ``on_invalid`` 並略過（未提供則 raise ValueError）。
    """
    cfg = copy.deepcopy(dict(settings))
    for category in ("temporary", "leisure"):
        cfg.setdefault(category, {})
        cfg[category]["events"] = []
    for entry in sorted(pool, key=lambda e: (e.definition.sort_order, e.definition.key)):
        cat = entry.definition.category
        if cat not in ("temporary", "leisure") or not entry.enabled:
            continue
        ev = materialize(entry.definition, entry.overrides)
        if _keep(ev, cat, on_invalid):
            cfg[cat]["events"].append(ev)
    return cfg


def build_shared_event_config(
    settings: Mapping[str, Any],
    definitions: Iterable[EventDefinition],
    on_invalid: OnInvalid | None = None,
) -> dict[str, Any]:
    """World 的 shared 設定 + 可見的 shared 定義 → Generator 用的 shared_event_config。

    ``settings.overrides`` 可依事件 key 覆寫（例如 ``{"date": {"enabled": false}}``）。
    """
    cfg = copy.deepcopy(dict(settings))
    overrides = cfg.pop("overrides", {}) or {}
    rules = [
        materialize(d, overrides.get(d.key))
        for d in _ordered(definitions)
        if d.category == "shared"
    ]
    cfg["rules"] = [r for r in rules if _keep(r, "shared", on_invalid)]
    return cfg


# ---------------------------------------------------------------------------
# 官方資料的固定 id（DB seed 與 server 共用，避免兩邊各自產生不同 id）
# ---------------------------------------------------------------------------

_ID_NAMESPACE = uuid.UUID("6f3b1c2e-8a4d-4c55-9a51-0c1f2d3e4b5a")


def official_definition_id(category: str, key: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, f"def/{category}/{key}"))


def official_profile_id(key: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, f"profile/{key}"))


# ---------------------------------------------------------------------------
# 官方預設目錄（DB seed 的來源；見 scripts/gen_seed_sql.py）
# ---------------------------------------------------------------------------


def _from_inline(category: str, ev: Mapping[str, Any], sort_order: int) -> EventDefinition:
    params = {k: copy.deepcopy(v) for k, v in ev.items() if k not in ("type", *_DISPLAY_FIELDS)}
    return EventDefinition(
        key=ev["type"],
        category=category,
        label=ev.get("label", ev["type"]),
        scene=ev.get("scene"),
        location=ev.get("location"),
        activity=ev.get("activity"),
        params=params,
        sort_order=sort_order,
        id=official_definition_id(category, ev["type"]),
    )


def official_definitions() -> list[EventDefinition]:
    """官方事件定義。同一 key 在不同 category 可並存（例如 temporary 的 slacking）。"""
    seen: dict[tuple[str, str], EventDefinition] = {}
    temporaries = [
        *defaults.student_event_config()["temporary"]["events"],
        *defaults.office_event_config()["temporary"]["events"],
    ]
    sources = [
        ("temporary", temporaries),
        ("leisure", defaults.student_event_config()["leisure"]["events"]),
        ("shared", defaults.default_shared_event_config()["rules"]),
    ]
    for category, events in sources:
        for ev in events:
            if (category, ev["type"]) not in seen:
                seen[(category, ev["type"])] = _from_inline(category, ev, 10 * (len(seen) + 1))
    return list(seen.values())


def split_event_config(event_config: Mapping[str, Any]) -> tuple[dict[str, Any], list[tuple[str, str, dict[str, Any]]]]:
    """inline event_config → (settings, [(category, key, overrides)])。

    overrides 為 inline 事件與官方定義的差異，用於產生 Profile 事件池 seed。
    """
    official = {(d.category, d.key): materialize(d) for d in official_definitions()}
    settings: dict[str, Any] = {}
    pool: list[tuple[str, str, dict[str, Any]]] = []
    for category in ("temporary", "leisure"):
        section = copy.deepcopy(dict(event_config.get(category) or {}))
        events = section.pop("events", [])
        settings[category] = section
        for ev in events:
            base = official.get((category, ev["type"]), {})
            diff = {k: v for k, v in ev.items() if k != "type" and base.get(k) != v}
            pool.append((category, ev["type"], diff))
    return settings, pool


def shared_settings(shared_event_config: Mapping[str, Any]) -> dict[str, Any]:
    """inline shared_event_config → 不含 rules 的 World 設定。"""
    return {k: copy.deepcopy(v) for k, v in shared_event_config.items() if k != "rules"}


__all__ = [
    "CATEGORIES",
    "CONTEXTS",
    "EventDefinition",
    "OnInvalid",
    "PoolEntry",
    "build_event_config",
    "build_shared_event_config",
    "for_context",
    "materialize",
    "official_definition_id",
    "official_definitions",
    "official_profile_id",
    "shared_settings",
    "split_event_config",
    "validate_definition",
]
