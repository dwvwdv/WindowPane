# worldpane-core

Worldpane（窗間）的 **Simulation Core**：純 Python 3.11 套件，無 DB、無 Web、無第三方依賴。

給定 `World + Characters(1..N) + Relationships + 當地日期`，決定性地產生當日完整 Event Timeline
（規格 §4–§17、§31、§34、§35 Phase 1）。

## 安裝 / 執行

```bash
cd worldpane-core
python3 -m pip install -e '.[dev]'     # 或不安裝，直接 PYTHONPATH=src
python3 -m pytest
```

CLI（使用內建示範 World：char_1=小白、char_2=小雞毛（couple），其餘角色為朋友）：

```bash
python -m worldpane_core timeline --date 2026-10-05
python -m worldpane_core timeline --date 2026-10-10 --characters 5
python -m worldpane_core timeline --date 2026-10-05 --json
python -m worldpane_core state --date 2026-10-05 --time 18:42
```

選項：`--characters N`（預設 2）、`--world-id`、`--version`（simulation_version）、`--json`。

## 公開 API

```python
from datetime import date, datetime
from worldpane_core import demo_world, generate_daily_plan, plan_day, current_state

world, characters, relationships = demo_world(3)
events = generate_daily_plan(world, characters, relationships, date(2026, 10, 5))  # list[Event]

now = datetime(2026, 10, 5, 18, 42, tzinfo=world.tz)
states = current_state(events, now, [c.id for c in characters])
# {"char_1": CharacterState(scene, activity, location, started_at, ends_at, ...), ...}
```

- `generate_daily_plan(world, characters, relationships, local_date) -> list[Event]`
- `plan_day(...) -> DailyPlan`：額外包含 calendar context、每位角色是否請假、被取消的事件。
- `current_state(events, now, character_ids=None) -> dict[str, CharacterState]`：
  取覆蓋 `now` 的最高優先 foreground 事件，否則 Base Schedule，否則 idle fallback。
- `Event.to_dict()`：給 Backend 持久化（`events` + `event_participants`）用。

## 模型

| 類別 | 說明 |
|---|---|
| `World` | id、name、timezone（預設 Asia/Taipei）、simulation_version、simulation_start_date、`holiday_dates`（假日行事曆 hook）、`shared_event_config`（World 層級共同事件規則） |
| `Character` | id、world_id、appearance_key、display_name、profile。外觀與行為分離，**沒有 partner_id** |
| `CharacterProfile` | schedule_config、meal_config、leave_config、event_config（temporary + leisure） |
| `CharacterRelationship` | character_a_id ↔ character_b_id、relationship_type |
| `Event` | id、world_id、type、scene、location、activity、start_at/end_at（tz-aware）、priority、participants（1..N）、metadata、simulation_version、layer（base / foreground） |

## 生成流程（§15）

1. Calendar Context（週末 = holiday；`World.holiday_dates` 亦為 holiday）
2. Leave（monthly / 固定 anchor 的 N-day cycle）
3. Base Schedule（location + activity；請假日與假日沒有）
4. Meals（window 內開始、15~20 分、skip 機率、與上一個「有吃」的餐間隔 ≥ 90 分）
5. Work / School temporary events（摸魚、上課睡覺、上課玩遊戲；在 Base block 內插入）
6. Evening / Holiday individual events（weight、duration、allowed_time、allowed_context、cooldown）
7. Shared / Group events（World 層級 seed；單一 Event + 2..N participants；一次鎖定全部參與者）
8. Conflict Resolution（§14 優先級：Fixed > Meal > Shared > Temporary > Leisure > Idle；先移動、移不動就取消）

## 決定性

- Character-local seed = `sha256(world_id | character_id | local_date | simulation_version)`
- Shared seed = `sha256(world_id | local_date | "shared" | simulation_version)`
- 月請假 seed = `sha256(world_id | character_id | "leave-month" | YYYY-MM | version)`
- Cycle 請假 seed = `sha256(world_id | character_id | "leave-cycle" | cycle_index | version)`
- 每個階段由 seed 衍生獨立 `random.Random`（meals / temporary / leisure），不使用全域 `random`、不使用 `hash()`。
- Event id 為 uuid5，由 world/date/version/類型/參與者決定 → 重算得到相同 id。

## 設定值（TBD）

所有機率、權重、頻率、cooldown、休閒事件時段皆集中在
[`src/worldpane_core/defaults.py`](src/worldpane_core/defaults.py)，標記 `# TBD §34` 者為 **placeholder**，
正式數值待需求方定案。Engine 不 hard-code 任何數值。

## 檔案結構

```
src/worldpane_core/
  models.py        Domain models
  defaults.py      所有預設 config（TBD placeholder）
  seeds.py         sha256 seed / RNG / weighted choice
  calendar_ctx.py  Calendar & Day context
  leave.py         月請假 / N-day cycle 請假
  generators.py    Base / Meal / Temporary / Leisure / Shared generators
  conflicts.py     Conflict resolver
  planner.py       generate_daily_plan / plan_day
  timeline.py      事件疊加成角色狀態區段
  state.py         current_state
  profiles.py      官方預設 Profile（小白、小雞毛）+ demo_world
  render.py, cli.py, __main__.py
tests/             pytest
```
