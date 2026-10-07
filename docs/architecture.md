# 架構設計

> WorldPane（窗間）的分層與跨 package 契約。
>
> 本文只負責「分層、契約與為什麼這樣切」。逐檔職責寫在各 package 的 README（[worldpane-core](../worldpane-core/README.md) 的「檔案結構」、
> [worldpane-server](../worldpane-server/README.md) 的「架構」），schema 與 migration 寫在 [supabase/README.md](../supabase/README.md)，
> 這裡不重述，只放連結。全域規則見 [AGENTS.md](../AGENTS.md)。

## 目錄

- [設計取向：World 在後端，裝置只是窗口](#設計取向world-在後端裝置只是窗口)
- [整體架構](#整體架構)
- [分層設計](#分層設計)
- [決定性與不可改寫的歷史](#決定性與不可改寫的歷史)
- [跨層契約](#跨層契約)
- [想改什麼從哪裡開始](#想改什麼從哪裡開始)
- [測試策略](#測試策略)

## 設計取向：World 在後端，裝置只是窗口

World 必須在沒有任何裝置連線時照樣「過日子」，而且同一個 World 的每一扇窗（每一台裝置）看到的必須是同一件事。
因此 **所有模擬都在後端發生，ESP32 只顯示後端給的 Semantic State（`scene` / `activity`）**，不在裝置上模擬、也不在裝置上決定任何事件。

| 執行環境 | 做什麼 | 不做什麼 |
|----------|--------|----------|
| `worldpane-core`（純 Python 函式庫） | 給定 World + 角色 + 日期 + 設定，**決定性地**產生一天的事件與任一時刻的狀態 | I/O、時鐘、資料庫、網路 |
| `worldpane-server`（FastAPI） | 把 DB 的設定組成 core 的輸入、延遲生成並持久化 daily plan、提供 Display API／History／配對／Dashboard | 自己發明模擬規則（規則都在 core 與 DB 資料裡） |
| Supabase Postgres（`worldpane` schema） | World、角色、計畫、事件、裝置、事件目錄、§34 TBD 數值 | 被 ESP32 或瀏覽器直接存取（RLS deny-by-default） |
| ESP32（尚未開始） | 每 15 秒帶 `If-None-Match` 輪詢、在 304 之間用 NTP 時間自己推進時鐘 | 模擬、決定下一個事件 |

這是刻意的取捨：裝置因此可以很笨、可以離線、可以有很多台；代價是後端必須保證「同一個輸入永遠得到同一個結果」，
而且已經發生的事不能事後被改寫——否則兩台裝置、或同一台裝置的今天與明天，會看到互相矛盾的歷史。

## 整體架構

```text
┌────────────────────────┐   ┌──────────────────────────────────────┐
│ ESP32 裝置（1..N 台）   │   │ 瀏覽器                                │
│  GET /api/v1/world/state│   │  /demo       離線回放 + 模擬一台裝置   │
│  If-None-Match / ETag   │   │  /dashboard  監視牆 + World 管理       │
└───────────┬────────────┘   └───────────────┬──────────────────────┘
            │ Bearer device token             │ Supabase Auth session / admin token
┌───────────▼─────────────────────────────────▼──────────────────────┐
│ worldpane-server（FastAPI）                                         │
│  api/routes.py ─────────┐        api/admin_routes.py ─┐             │
│  api/deps.py（裝置／管理員驗證）                        │             │
│                          ▼                             ▼             │
│              services.py  WorldService         admin.py AdminService│
│              （ETag/revision、pairing、延遲生成 plan）               │
│                 │                       │                            │
│      Repository seam                SimulationProvider seam          │
│  repositories/base.py              simulation/provider.py            │
│   ├ memory.py                       └ core.py ──────────────┐        │
│   └ postgres.py ─────┐                                      │        │
│  static/ + theme.py：/dashboard、/demo（Offbeat）           │        │
└──────────────────────┼──────────────────────────────────────┼───────┘
                       │ psycopg（service role）              │ import
┌──────────────────────▼─────────────┐     ┌──────────────────▼───────┐
│ Supabase Postgres 15               │     │ worldpane-core（純 stdlib）│
│  worldpane schema（RLS 全拒）       │     │ catalog → planner →        │
│  migrations/ + seed.sql            │◀────│ timeline / state           │
└────────────────────────────────────┘ gen │ defaults.py → seed.sql     │
                                           └───────────────────────────┘
```

## 分層設計

### 1. worldpane-core：模擬引擎

純函式庫：沒有 I/O、沒有時鐘、只用標準函式庫。這讓同一份規則可以被 server、CLI、seed 產生器與測試重用，
也讓「相同輸入 → 相同輸出」可以被單元測試直接證明。

- **設定與規則分開**：`defaults.py` 只是官方預設與 `seed.sql` 的來源，正式數值是 DB 的資料；
  從 DB 讀進來的設定一律先經 `catalog.py` 驗證，無效的事件定義略過並回報，不讓整個 World 的計畫失敗。
- **新增事件 = 新增資料**：core 沒有任何針對個別事件的程式碼。

### 2. worldpane-server：編排與 API

由外而內單向依賴：`api/` → `services.py`／`admin.py` → 兩個 seam（`Repository`、`SimulationProvider`）。

- **兩個 seam 讓 server 可以在沒有資料庫的情況下完整測試**：`InMemoryRepository` 與 `PostgresRepository`
  實作同一個 Protocol，測試對兩者各跑一次；`CoreSimulationProvider` 是唯一把 DB 設定轉成 core 輸入的地方。
- **時間只從注入的 `Clock` 進來**：測試用 `FixedClock` 釘住「現在」，因此跨午夜、History 的「今天」邊界都能重現。
- 網頁是 `static/` 裡的單一 HTML 檔，外觀由 `theme.py` 內嵌 `static/offbeat.css`（見 [ui-conventions.md](ui-conventions.md)）。

### 3. 資料層：`worldpane` schema

完整欄位、RLS 與 function 見 [supabase/README.md](../supabase/README.md)。架構上要記得的兩件事：

- **共用 Supabase 專案**：同一個 Project 跑多個 App，WorldPane 只擁有 `worldpane` schema。
- **跨 World 完整性靠複合 FK**（`(id, world_id)`），不是靠應用層記得檢查。

## 決定性與不可改寫的歷史

這是整個系統最重要的 invariant，Review 時優先檢查（見 [AGENTS.md](../AGENTS.md) 的「Review 優先級」）。

- **seed**：每個角色、每一天、每個共同事件都有自己的 sha256 seed（公式見 [worldpane-core/README.md](../worldpane-core/README.md) 的「決定性」），
  每個生成階段由 seed 衍生獨立的 `random.Random`。Event id 是 uuid5，重算得到相同 id。
- **延遲生成、生成一次**：某一天第一次被需要時才產生計畫，寫入 DB 後同一天之後一律讀已存的事件。
  寫入是 `INSERT ... ON CONFLICT DO NOTHING`，多台裝置同時觸發也只會留下一份計畫。
- **調參不回溯**：改 `event_definitions`、Profile 或 World 設定只影響之後才產生的日期；已存的 plan 是歷史。
- **演算法改變要升 `simulation_version`**：同一組輸入產生不同計畫的修改，必須透過新的 `simulation_version` 明確地產生新版本
  （規格 §「修改 Simulation Algorithm 時可透過 `simulation_version` 明確產生新版本」），不能讓既有輸入悄悄改變結果。
- **revision 反映「看到的東西」而不是「寫入」**：事件開始或結束時沒有任何寫入，但畫面變了。
  因此 server 每次計算 state 都對角色狀態取 fingerprint，不同就原子地把 revision +1（細節見 server README 的「設計重點」）。

## 跨層契約

兩邊各自實作、靠契約與 CI 維持一致的地方。改其中一邊時，另一邊與守門的檢查要一起看。

| 契約 | 兩端 | 單一來源 | 守門 |
|------|------|----------|------|
| 官方事件目錄與預設數值 | core 的 `defaults.py` ↔ DB 的 `seed.sql` | core（`seed.sql` 由 `gen_seed_sql.py` 產生，不手改） | `core.yml` 的 `gen_seed_sql.py --check` |
| DB 設定的格式 | DB 的 JSON 欄位 ↔ core 的 `catalog.py` | `catalog.py` 的驗證 | `test_catalog.py`；無效定義在執行期略過並記 warning |
| Display API | server 的 `schemas.py` ↔ ESP32 韌體 | `worldpane-server/openapi.json` | `server.yml` 的 `export_openapi.py --check`；只做加法相容的變更 |
| 持久層 | `Repository` Protocol ↔ memory／Postgres 兩個實作 | `repositories/base.py` | server 測試對兩個實作各跑一次（CI 用 Postgres 15 套 migrations） |
| Schema | `supabase/migrations/` ↔ 共用的 Supabase 專案 | migrations 檔案（已套用的不改） | CI 用 `docker/db/init-worldpane.sh` 從零套用；正式專案目前手動套用 |
| Dashboard 管理員 | Supabase Auth ↔ `worldpane.admins` | `worldpane.admins` 白名單 | `test_dashboard_auth.py` |
| 網頁外觀 | `static/offbeat.css` ↔ `/dashboard`、`/demo` | `offbeat.css` 的語意 token | `test_theme.py`（頁面不得寫色碼） |
| 文件 ↔ 程式碼 | `AGENTS.md`、`docs/` ↔ repo 裡的檔案與版號 | 程式碼 | `tests/test_docs_consistency.py` |

## 想改什麼從哪裡開始

| 想做的事 | 從這裡開始 |
|----------|------------|
| 新增一個個人或共同事件 | 不改程式：`event_definitions` 新增一列（見 server README 的「事件可擴充性」）；要成為官方預設才改 `defaults.py` 並重新產生 `seed.sql` |
| 調整 §34 TBD 數值 | DB 的 `character_profiles.*_config`／`event_definitions.params`／`worlds.shared_event_config` |
| 改生成規則（作息、用餐、衝突解決） | `worldpane-core` 的 `generators.py`／`conflicts.py`／`planner.py`；會改變既有輸入的結果就升 `simulation_version` |
| 改裝置看到的狀態格式 | `schemas.py` + `services.py`，重新產生 `openapi.json`，只做加法 |
| 新增一個 API | `api/routes.py`（裝置）或 `api/admin_routes.py`（Dashboard）→ `services.py`／`admin.py` → 需要新資料時兩個 Repository 都實作 |
| 改 schema | 新增 `supabase/migrations/` 檔案 + `repositories/postgres.py` + `memory.py` |
| 改 Dashboard／Demo 的畫面 | `static/dashboard.html`／`static/demo.html`；顏色與元件樣式改 `static/offbeat.css`（見 [ui-conventions.md](ui-conventions.md)） |

## 測試策略

| 層 | 測什麼 | 位置 |
|----|--------|------|
| core | 決定性、invariant（不重疊、作息邊界）、請假、共同事件、catalog 驗證 | `worldpane-core/tests/` |
| server（in-memory） | API 合約、ETag／revision、配對、History 邊界、Dashboard 驗證與管理操作 | `worldpane-server/tests/` |
| server（Postgres 15） | 同一組測試換成 `PostgresRepository`（`WORLDPANE_TEST_DATABASE_URL`，必須是可丟棄的 DB） | 同上，CI 自動跑 |
| 部署 | image build 後用 `docker compose --profile local-db` 冒煙測試 | `.github/workflows/server.yml` |
| 文件 | 文件提到的路徑存在、版號一致、`AGENTS.md` 大小 | `tests/test_docs_consistency.py` |
