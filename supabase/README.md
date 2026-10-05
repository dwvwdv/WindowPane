# WorldPane — Supabase / PostgreSQL schema

WorldPane（窗間）的資料庫結構。所有物件都放在獨立的 **`worldpane` schema**（不是 `public`），因為同一個 Supabase Project 裡跑了多個 App，每個 App 各自用一個 schema 隔離。

```
supabase/
├── migrations/
│   ├── 20261005120000_init_worldpane.sql   # schema、table、index、trigger、function、RLS、權限
│   └── 20261005130000_event_catalog.sql    # 事件目錄 event_definitions、profile_event_pools、device_inputs
├── seed.sql                                 # 由 worldpane-core/scripts/gen_seed_sql.py 產生：官方事件目錄、官方 Profile、Demo World
└── README.md
```

## 存取模型（V1）

- V1 **沒有 User 帳號**（規格 §3），只有 `Device → World`。
- ESP32 只跟 FastAPI backend（`worldpane-server`）溝通；backend 用 Supabase **`service_role`**（BYPASSRLS）連資料庫。
- 每張表都 **啟用 RLS 且沒有任何 policy** → `anon` / `authenticated` 一律被拒（deny-by-default）。
- `worldpane` schema 的 `USAGE` 只授權給 `service_role`；所有 function 也撤銷了 PUBLIC 預設的 `EXECUTE`。
- 未來加入帳號（`User → World → Device`）時，再加 RLS policy 即可，Simulation Core 不受影響。

## ER 概覽

```text
character_profiles (world_id NULL = 官方模板)
        │1
        │N
worlds ─┬─1:N─ characters ─┬─ N:N (character_relationships, 無向、一對一列)
        │                  │
        ├─1:1─ world_revisions   (Display API revision / ETag)
        │                  │
        ├─1:N─ daily_plans ─1:N─ events ─1:N─ event_participants ─N:1─ characters
        │      UNIQUE(world_id, local_date, simulation_version)
        │
        ├─1:N─ devices ─1:1─ device_preferences (primary_character_id → characters)
        │      (world_id NULL = 已註冊未配對)
        │
        └─1:N─ pairing_codes (code_hash, expires_at, max_uses, used_count, consumed_*)
```

| Table | 用途 | 規格 |
|---|---|---|
| `worlds` | Aggregate root；timezone（trigger 驗證 IANA 名稱）、`simulation_version`、`simulation_start_date`、World 層級的 `shared_event_config` | §4, §11 |
| `world_revisions` | 每個 World 一列的遞增 `revision`，由 trigger 在 world / characters / relationships / events / participants 變動時遞增 | §19–20 |
| `character_profiles` | 行為規則（`schedule_config` / `meal_config` / `leave_config` / `event_config`，皆為 jsonb）。`world_id IS NULL` 為官方共用模板 | §6–10, §34 |
| `characters` | Character Instance = `appearance_key` + `profile_id`。數量不限（1..N），以 `archived_at` 軟刪除 | §5–6, 不變量 5–7 |
| `character_relationships` | 無向關係；`CHECK (a <> b)`、`UNIQUE (world_id, least(a,b), greatest(a,b))`；`relationship_type` 用 CHECK 列舉。**沒有 `partner_id`** | §12, 不變量 12 |
| `daily_plans` | 確定性每日計畫的表頭；`UNIQUE (world_id, local_date, simulation_version)`，另有「每天只有一個未 superseded 的計畫」partial unique | §15 |
| `events` | Event log / History；`priority`、`status` 為 enum；`end_at > start_at` | §14, §17 |
| `event_participants` | Event ↔ Character（Shared Event = 一筆 Event + 2..N participants） | §11, 不變量 8 |
| `devices` | 只存 `device_token_hash`（unique），**絕不存明文 token** | §18, §22 |
| `device_preferences` | 每台裝置獨立的 layout / brightness / primary character；自帶 `revision` | §23, §29 |
| `pairing_codes` | 只存 `code_hash`（HMAC），有 `expires_at`、`max_uses`、`used_count`、`consumed_at/consumed_reason` | §22 |

### 主要 function

- `worldpane.redeem_pairing_code(p_code_hash text, p_device_id uuid) → (status, world_id)`
  `SECURITY DEFINER`、`search_path = ''`。鎖住 device 與 code 列（`FOR UPDATE`），檢查到期 / 次數，`used_count + 1`（達上限時標記 `consumed_reason = 'exhausted'`），把 device 綁到 World、建立 `device_preferences`。
  回傳 `status`：`ok` / `already_paired`（同一 World 重送，不扣次數）/ `invalid` / `expired` / `exhausted` / `device_not_found` / `device_revoked`。
  **刻意不 raise**，讓「發現已過期 → 標記 consumed」能被 commit。Backend 回應裝置時不要區分 invalid 與 expired。
- `worldpane.create_pairing_code(world_id, code_hash, ttl, max_uses, created_by_device_id) → uuid`
  先把同 hash 的過期碼標記為 consumed，再插入；若同一碼仍在有效期內會丟 `23505`，backend 換一組碼重試。

## 在本機套用（Supabase CLI）

需要 Docker 與 [Supabase CLI](https://supabase.com/docs/guides/local-development)。

```bash
cd WorldPane                 # repo 根目錄（supabase/ 的上一層）
supabase init                # 只有在還沒有 supabase/config.toml 時；不會覆蓋 migrations/ 與 seed.sql
supabase start               # 啟動本機 stack
supabase db reset            # 重建本機 DB：依序套用 migrations/*.sql，再執行 seed.sql
```

確認 `supabase/config.toml` 的 seed 設定指向 `seed.sql`（CLI 預設即是）：

```toml
[db.seed]
enabled = true
sql_paths = ["./seed.sql"]
```

推到遠端專案：`supabase db push`（只推 migration，不會跑 seed）。**seed 只給本機開發用。** 遠端不需要 seed：`worldpane-server` 啟動時會自動補上官方事件目錄與 Profile 模板（`world_id = NULL`），已存在的列不會被覆蓋。

不用 CLI、直接用 psql 也可以（需要已存在 `service_role` 角色，Supabase 內建）：

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20261005120000_init_worldpane.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/migrations/20261005130000_event_catalog.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f supabase/seed.sql   # 選用：本機開發才需要
```

## 關於 Exposed Schemas

V1 **不需要**把 `worldpane` 加到 Dashboard → Settings → API → Exposed Schemas：backend 直接用 Postgres 連線（或 service_role）存取，ESP32 從不直接打 Supabase API。

只有在未來真的要讓 PostgREST / supabase-js 存取時才加入，並且**必須先**寫好 RLS policy 與對應的 `GRANT ... TO anon/authenticated`——目前沒有任何 policy，所以即使開放也只會全部被拒。

## 設計備註

- **每個角色不重疊（no-overlap）由應用層保證**：Simulation Core 的 Conflict Resolver（§14）在寫入前解決衝突。資料庫不加 exclusion constraint，因為 base schedule（WORK / SCHOOL）要存成切段還是當作底層、上面疊 temporary event，屬於 Core 的決定；若最後確定採完全不重疊的切段，可加：`btree_gist` + 在 `event_participants` 反正規化 `tstzrange` + `EXCLUDE USING gist (character_id WITH =, during WITH &&) WHERE (status = 'scheduled')`。
- **確定性寫入**：`INSERT INTO daily_plans ... ON CONFLICT DO NOTHING RETURNING id`，拿到 id 才寫 events（同一交易）。換 `simulation_version` 重算某天時，先把舊計畫設 `superseded_at`，再插入新版本。`events.simulation_version` 由 `daily_plans` 取得，不重複存。
- **Display API ETag**：`world_revisions.revision` 只反映「資料變動」，但「目前狀態」會隨時間改變（事件開始 / 結束）而沒有任何寫入。所以 server 每次計算 state 時對角色狀態取 fingerprint，與上次不同就原子地把 revision +1，ETag = `"<world_id>.<revision>"`（見 `worldpane-server/README.md`）。Device Preference 尚無 API，之後加入時再把 `device_preferences.revision` 併入該裝置的 ETag。
- **History 永久保存**：有參與過事件的角色無法硬刪（FK `NO ACTION`），請用 `archived_at`。刪除整個 World 時，`worlds_delete_events_first` trigger 會先刪 events 再讓 FK cascade 跑。
- **跨 World 完整性**：participants / relationships / events 都用 `(id, world_id)` 複合 FK，保證角色、事件、計畫屬於同一個 World；`device_preferences.primary_character_id` 由 trigger 檢查必須在該裝置目前的 World 內，重新配對到別的 World 時會自動清空。
- **Pairing code 雜湊**：6 位數碼只有 10^6 種，必須用 backend 的 HMAC secret（`WORLDPANE_PAIRING_CODE_SECRET`）雜湊，不可用單純 sha256。`pairing_codes_live_hash_uq` 只限制「尚未 consumed」的列，所以舊碼 consumed 後號碼可以重用。
- **TBD 數值放在 DB**：規格 §34 未定案的機率 / 權重 / 時長 / cooldown 全部是資料，不在程式碼裡：
  - `event_definitions.params`：每個事件的 weight、duration、allowed_time、allowed_context、cooldown、participants，以及 `context_overrides`（假日 / 請假日覆寫）
  - `profile_event_pools.overrides`：某個 Profile 對某事件的覆寫
  - `character_profiles.*_config`：作息、用餐（含 skip_probability）、請假機率、每個 block 的插曲次數
  - `worlds.shared_event_config`：共同事件的嘗試次數 / 觸發機率，`overrides` 可針對單一事件停用或調參
  seed 的數值全是佔位值。改動只影響之後才產生的 daily plan；已存的 plan 是歷史，不會改寫。
- **新增事件 = 新增一列**：`event_definitions` 是資料驅動的事件目錄，Simulation Core 沒有任何針對個別事件的程式碼。World 自己的定義（`world_id` 非 NULL）會蓋過同 `(category, key)` 的官方定義。
- **seed 不要手改**：`seed.sql` 由 `worldpane-core/scripts/gen_seed_sql.py` 從 core 的官方預設產生（`--check` 可驗證是否過期），確保 DB 與 core 預設一致。
- 不存進資料庫：sprite / 動畫 binary、Wi-Fi 密碼（§29）。
