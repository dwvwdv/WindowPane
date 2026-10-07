# worldpane-server

WorldPane（窗間）Backend API 骨架：Display API、World History、Device Pairing。
規格依據：`../WorldPane_專案規格.md` §18–23、§27、§29、§31。

- Python 3.14（最低 3.12）/ FastAPI / pydantic v2 / pydantic-settings
- 模擬引擎：**worldpane-core**（`simulation/core.py` adapter；server 不含任何生活規則）
- 持久層：**Postgres / Supabase**（`WORLDPANE_REPOSITORY=postgres`），或 in-memory（預設，重啟即清空）
- 所有可調數值（§34 TBD）與事件定義都在 DB，改資料即生效於「之後產生」的 daily plan，不需部署
- 啟動時確保 Demo World（小白 + 小雞毛）存在，並印出一組 Pairing Code

## Docker 一鍵部署

預設接 Supabase：

1. 確認 `supabase/migrations` 已套用到 Supabase 專案（目前的共用專案已套用，作法見 `../supabase/README.md`）。
2. 把根目錄的 `.env.example` 複製成 `.env`，在 `WORLDPANE_DATABASE_URL` 填 service-role 的 Postgres 連線字串（Project Settings → Database，pooler 可用）。
3. 在 repo 根目錄執行：

```bash
docker compose up -d --build
curl http://127.0.0.1:8000/healthz   # {"status":"ok"}
```

server 以 `WORLDPANE_ENV=prod`、非 root 身分執行，啟動時會自動補上官方事件目錄和 Profile 模板。Pairing code 的 HMAC key 若未設定，會在第一次啟動時產生，存在 `server-data` volume，重啟後沿用。

沒有 Supabase（本機或離線測試）時，可以加上 `--profile local-db`，順便起一個 Postgres 15（與 Supabase 專案相同版本）。第一次建立 volume 時，它會自動建立 Supabase 的 `service_role` 等角色，並套用同一份 migrations 和 `seed.sql`：

```bash
docker compose --profile local-db up -d --build
```

> 從 Postgres 16 版的 `local-db` 換過來：舊的 `db-data` volume 是 16 的資料格式，15 無法直接讀取。要保留資料，先在舊版本執行 `docker compose exec db pg_dump -U postgres -d worldpane --clean --if-exists > worldpane.sql`，`docker compose --profile local-db down -v` 後用新版啟動，再 `docker compose exec -T db psql -U postgres -d worldpane < worldpane.sql`（`--clean` 會先刪掉新 volume 自動建立的物件再匯入）。只是測試資料的話，直接 `down -v` 重建即可。

部署後用 `POST /api/v1/world` 建立 World，回應裡有第一台裝置的 token，以及給第二台裝置用的 pairing code（見下方 curl 範例）。Demo World 預設不發 code（`WORLDPANE_SEED_DEMO_WORLD=false`）。

只建 image：`docker build -f worldpane-server/Dockerfile -t worldpane-server .`（必須在 repo 根目錄執行，因為要一起裝 worldpane-core）。

## 安裝與執行

```bash
cd worldpane-server
python3 -m pip install -e ../worldpane-core -e ".[dev]"   # worldpane-core 需一起安裝

# 開發模式：固定 demo pairing code 方便測試（不設定則隨機，並印在 log）
WORLDPANE_DEMO_PAIRING_CODE=824917 uvicorn worldpane_server.main:app --reload
```

不安裝套件也可以：`PYTHONPATH=src:../worldpane-core/src uvicorn worldpane_server.main:app`。

接 Postgres（先依 `../supabase/README.md` 套用 migrations + seed）：

```bash
WORLDPANE_REPOSITORY=postgres \
WORLDPANE_DATABASE_URL='postgresql://...'   # Supabase 的 service-role 連線字串，勿 commit \
WORLDPANE_PAIRING_CODE_SECRET=... uvicorn worldpane_server.main:app
```

Swagger UI：<http://127.0.0.1:8000/docs>

Dashboard：<http://127.0.0.1:8000/dashboard>（見下方「Dashboard」）。

瀏覽器 Demo：<http://127.0.0.1:8000/demo>。它會用和 API 相同的模擬，回放示範 World 從今天起一週的生活，也可以切到「連線後端」模式：輸入配對碼或建立新 World，像真正的裝置一樣輪詢 `/world/state`。要產生不需要後端的單檔版本，執行 `python scripts/build_demo_html.py -o demo.html`。

### 設定（環境變數，前綴 `WORLDPANE_`，或 `.env`；參考 `.env.example`）

| 變數 | 預設 | 說明 |
|---|---|---|
| `WORLDPANE_ENV` | `dev` | `dev` / `test` / `prod` |
| `WORLDPANE_PAIRING_CODE_SECRET` | 空 | Pairing code 的 HMAC key。`prod` 必填；`dev` 未設定時每次啟動隨機產生 |
| `WORLDPANE_PAIRING_CODE_TTL_SECONDS` | `600` | Pairing code 有效秒數 |
| `WORLDPANE_PAIRING_CODE_MAX_USES` | `1` | 預設可使用次數 |
| `WORLDPANE_DEFAULT_TIMEZONE` | `Asia/Taipei` | 新 World 預設時區 |
| `WORLDPANE_SEED_DEMO_WORLD` | `true` | 確保 Demo World 存在（id 與 `supabase/seed.sql` 相同）並發一組 code |
| `WORLDPANE_DEMO_PAIRING_CODE` | 空 | Demo World 的固定 6 碼（僅開發用；可用 10 次） |
| `WORLDPANE_REPOSITORY` | `memory` | `memory` / `postgres` |
| `WORLDPANE_DATABASE_URL` | 空 | `postgres` 時必填；service-role DSN（支援 Supabase pooler） |
| `WORLDPANE_SIMULATION_PROVIDER` | `core` | worldpane-core |
| `WORLDPANE_SUPABASE_URL` | 空 | Dashboard 用 Supabase Auth 登入：專案 URL（`https://<ref>.supabase.co`） |
| `WORLDPANE_SUPABASE_ANON_KEY` | 空 | 同上，anon（publishable）key；本來就是給瀏覽器用的公開值。URL 與 key 要一起設 |
| `WORLDPANE_ADMIN_TOKEN` | 空 | 選用：共用的 admin Bearer token（至少 16 字元），給腳本 / CI，或沒有 Supabase 時登入 Dashboard。兩種登入方式都沒設 = admin API 停用（503） |

Repo 中不含任何 secret。

## API（`/api/v1`）

| Method | Path | Auth | 說明 |
|---|---|---|---|
| `POST` | `/world` | 無 | 建立 World（第一台裝置流程），回傳該裝置的 token + 給其他裝置用的 pairing code |
| `POST` | `/device/pair` | 無 | 用 6 碼 pairing code 綁定 World，回傳 device token（只顯示一次） |
| `POST` | `/world/pairing-codes` | Bearer | 為目前 World 再發一組 pairing code（邀請其他裝置） |
| `GET` | `/world/state` | Bearer | 目前 Semantic State（§19），支援 `ETag` / `If-None-Match` → `304` |
| `GET` | `/world/history?date=YYYY-MM-DD` | Bearer | 指定日期（World 時區）每個角色的事件列表 |
| `POST` | `/device/input` | Bearer | 按鍵 / 本地操作，回 `202` |

錯誤格式：`{"detail": {"code": "...", "message": "..."}}`（驗證錯誤為 FastAPI 預設 422 格式）。

OpenAPI 文件：[`openapi.json`](./openapi.json)（給 ESP32 端用）。重新產生：

```bash
python3 scripts/export_openapi.py          # 寫入 openapi.json
python3 scripts/export_openapi.py --check  # CI 用：過期時 exit 1（tests 也會檢查）
```

## Dashboard

`GET /dashboard` 是單頁管理介面，所有資料都來自 `/api/v1/admin`。

### 登入（Supabase Auth，做法同 Lazyrhythm 的文章發佈後台）

1. `.env` 設 `WORLDPANE_SUPABASE_URL` 與 `WORLDPANE_SUPABASE_ANON_KEY`（Supabase → Project Settings → API）。
2. 在 Supabase → Authentication → Users 建立 email / 密碼帳號。
3. 把帳號登錄成管理員（migration `20261006144203_dashboard_admins.sql` 建立的白名單表）：

   ```sql
   insert into worldpane.admins (user_id, display_name)
   select id, '你的名字' from auth.users where email = 'you@example.com';
   ```

流程：瀏覽器直接向 Supabase Auth（GoTrue REST）用 email / 密碼登入，session 存在 localStorage，
過期前 60 秒自動 refresh；呼叫 admin API 時帶 access token，後端用 `GET /auth/v1/user` 向 Supabase 確認身分
（結果快取 60 秒），再檢查 `worldpane.admins`。登入成功但不在名單內 → 403 `not_admin`；
Supabase 連不上 → 503 `auth_unavailable`。`worldpane.admins` 只有 service role 讀得到；在 Supabase 上
`user_id` 是 `auth.users` 的外鍵（刪除帳號會一併移除），本機 Postgres 沒有 `auth` schema 時則只是 uuid 欄位。

`WORLDPANE_ADMIN_TOKEN`（選用）是給腳本與 CI 的共用 token，也能在登入頁「改用管理 Token」登入；它只存在瀏覽器分頁的 sessionStorage。

### 功能

- **監視牆**：每 15 秒呼叫一次 `GET /admin/monitor`，同時顯示多個 World 的即時畫面（和裝置看到的 state 相同）；
  可選要看哪些 World、1–4 欄或自動版面、單一 World 放大、全螢幕。時鐘依各 World 的時區每秒走動。
- **World 管理**：新增 World（自訂 1..12 個角色與時區，回傳配對碼）、改名、新增 / 改名 / 換外觀 / 調順序 / 封存角色、
  調共同事件設定（表單或直接編 JSON）、發配對碼、看裝置列表與任一天的時間軸。

Admin API（不在 `openapi.json`，那份是給 ESP32 的裝置合約）：

| Method | Path | 說明 |
|---|---|---|
| `GET` | `/admin/me` | 目前登入的身分（`supabase` 帳號或 `token`） |
| `GET` | `/admin/profiles` | 可選的官方行為 Profile |
| `GET` | `/admin/worlds` | 所有 World（角色數、裝置數、revision） |
| `POST` | `/admin/worlds` | 建立 World（不建立裝置），回傳 World 與配對碼 |
| `GET` / `PATCH` | `/admin/worlds/{id}` | World 詳情；改 `name`、`shared_event_config` |
| `POST` | `/admin/worlds/{id}/characters` | 新增角色（和現有角色建立 `friend` 關係） |
| `PATCH` / `DELETE` | `/admin/worlds/{id}/characters/{cid}` | 改名稱 / 外觀 / 順序；`DELETE` = 封存（保留歷史，不能封存最後一位） |
| `POST` | `/admin/worlds/{id}/pairing-codes` | 發配對碼 |
| `GET` | `/admin/worlds/{id}/history?date=` | 同 `/world/history` |
| `GET` | `/admin/monitor?world_id=…` | 多個 World 的目前 state（不帶參數 = 全部，最多 48 個） |

調整的規則和 DB 調參一樣：已持久化的 daily plan 不會改寫。新增角色從「還沒產生計畫的日子」開始有行程
（今天的計畫已產生時，今天先顯示 idle）；`shared_event_config` 只影響之後產生的日子，
不合法的值（未知欄位、未知事件 key、超出範圍的機率…）直接回 422，不會存進 DB。
時區建立後不能改，因為每天的計畫是依 World 的當地日期存的。

## curl 範例

```bash
BASE=http://127.0.0.1:8000/api/v1

# 1) 第一台裝置：建立 World
curl -s -X POST $BASE/world -H 'Content-Type: application/json' -d '{"name":"我們的房間"}'
# => {"world_id":"wld_…","device":{"device_id":"dev_…","world_id":"wld_…","device_token":"wpd_…","token_type":"Bearer"},
#     "pairing":{"pairing_code":"824917","expires_at":"2026-10-05T18:52:10+08:00","max_uses":1}}

# 2) 第二台裝置：輸入 pairing code 加入
curl -s -X POST $BASE/device/pair -H 'Content-Type: application/json' -d '{"pairing_code":"824917"}'
# => {"device_id":"dev_…","world_id":"wld_…","device_token":"wpd_…","token_type":"Bearer"}

TOKEN=wpd_...

# 3) 取得目前狀態（poll 約 15 秒一次）
curl -s -i $BASE/world/state -H "Authorization: Bearer $TOKEN"
# HTTP/1.1 200 OK
# etag: "wld_demo.2"
# {"server_time":"…","revision":2,"world_id":"…","characters":[…]}

# 4) 沒有變化時帶 If-None-Match → 304（無 body）
curl -s -o /dev/null -w '%{http_code}\n' $BASE/world/state \
  -H "Authorization: Bearer $TOKEN" -H 'If-None-Match: "wld_demo.2"'

# 5) 歷史
curl -s "$BASE/world/history?date=2026-10-05" -H "Authorization: Bearer $TOKEN"

# 6) 按鍵
curl -s -X POST $BASE/device/input -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"type":"button_press","button":"A"}'

# 7) 再發一組可用 2 次的 pairing code
curl -s -X POST $BASE/world/pairing-codes -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"max_uses":2}'
```

## 測試

```bash
python3 -m pytest
# 另外對 Postgres 跑一次（務必是可丟棄的 DB，已套用 supabase/migrations；每個測試會清空並重跑 seed.sql）
WORLDPANE_TEST_DATABASE_URL='postgresql://service_role:...@localhost:5432/wp_test' python3 -m pytest
```

## 架構

```text
src/worldpane_server/
├─ main.py              create_app() 工廠、demo seed；uvicorn 入口 `app`
├─ config.py            Settings（pydantic-settings, WORLDPANE_*）
├─ api/routes.py        HTTP endpoints（裝置）
├─ api/admin_routes.py  /api/v1/admin（Dashboard 用）
├─ admin.py             AdminService：列出 / 建立 / 調整 World、監視牆
├─ static/dashboard.html  /dashboard 單頁介面
├─ static/demo.html       /demo 瀏覽器 Demo
├─ static/offbeat.css     Offbeat 設計語言：網頁顏色的唯一來源（docs/ui-conventions.md）
├─ theme.py               把 offbeat.css 內嵌進頁面
├─ api/deps.py          Bearer device auth / admin auth（Supabase session 或 admin token）
├─ supabase_auth.py     向 Supabase Auth 驗證 access token（含短期快取）
├─ services.py          WorldService：編排 repo + simulation，ETag/revision、pairing
├─ schemas.py           API 合約（pydantic）
├─ domain.py            World / Character / Event / Device / PairingCode …（§28）
├─ security.py          token / pairing code 產生與雜湊
├─ clock.py             可注入時鐘（測試用 FixedClock）
├─ seed.py              官方預設角色（小白、小雞毛）與 demo world
├─ repositories/
│  ├─ base.py           Repository Protocol（持久層 seam）
│  ├─ memory.py         InMemoryRepository
│  └─ postgres.py       PostgresRepository（worldpane schema，psycopg 3 + pool）
└─ simulation/
   ├─ provider.py       SimulationProvider Protocol
   └─ core.py           CoreSimulationProvider：DB 設定 → worldpane-core → domain Event
```

### 兩個 seam

1. **`SimulationProvider`**（`simulation/provider.py`）：
   `generate_daily_plan(world, characters, relationships, local_date) -> list[Event]`、
   `current_state(events, now, character_ids) -> {character_id: CharacterNow}`。
   `CoreSimulationProvider` 用 `worldpane_core.catalog` 把 DB 的 profile 設定 + 事件池 + World
   shared 設定組成 core 的 config，無效的事件定義會記 warning 並略過，不會讓整個 World 壞掉。
2. **`Repository`**（`repositories/base.py`）：`InMemoryRepository` 與 `PostgresRepository`
   實作同一個 Protocol。Postgres 版每次載入 World / 角色時讀取 `event_definitions` /
   `profile_event_pools`，所以調參不需重啟。

### 事件可擴充性（新增事件 = 新增資料）

| 想做的事 | 改哪裡 |
|---|---|
| 新增個人事件（例如煮飯） | `insert into worldpane.event_definitions (category='leisure', params=...)`，再加到 `profile_event_pools` |
| 新增共同事件（例如桌遊 3..N 人） | `insert into worldpane.event_definitions (category='shared', ...)`，所有 World 自動可用 |
| 假日 / 請假日改權重或停用 | `params.context_overrides = {"holiday": {"weight": 40}}` |
| 某個 Profile 的事件改參數 | `profile_event_pools.overrides` |
| 某個 World 停用某共同事件 | `worlds.shared_event_config.overrides = {"date": {"enabled": false}}` |
| 用餐跳過率、請假機率等 §34 TBD | `character_profiles.meal_config` / `leave_config` / `event_config` |

已持久化的 daily plan 不會被回溯改寫；變更只影響之後才產生的日期。

### 設計重點

- **revision / ETag**：每次計算 state 時對 `characters`（不含 `server_time`）取 fingerprint；
  與 World 上次記錄的不同時，`revision` +1（原子操作）。ETag = `"<world_id>.<revision>"`。
  因此事件轉換（例如 18:51 洗完澡）也會讓 revision 前進，多台裝置看到同一個 revision。
  304 不含 body，裝置需自行用 NTP 時間推進 `server_time`。
- **Daily plan 延遲生成**：第一次需要某日期時才呼叫 provider 生成並持久化；
  同一天之後一律讀已存的事件（可重現、World 離線時仍「持續運作」）。
  同時載入「昨天」的事件，以處理跨午夜事件。
- **History**：只回傳 `date <= 今天`（World 時區）；今天只回已開始的事件；
  早於 `simulation_start_date` 的日期回空列表；未來日期 → 422 `date_in_future`。
- **Device token**：`wpd_` + 256-bit 隨機；只存 sha256。
- **Pairing code**：6 位隨機數字，與 World ID 無關；儲存 `HMAC-SHA256(secret, code)`
  （6 碼只有 10^6 種，純 sha256 可被暴力還原）。有 TTL、`max_uses`、原子遞增 `used_count`；
  同值的有效 code 不會重複發出。
- **角色數 1..N**：API、repository、simulation 都以 list 處理；測試涵蓋 1 / 2 / 3 人 World。
- **跨午夜**：V1 沒有睡覺事件，也沒有跨午夜事件；夜間沒有事件時回傳 idle（`started_at` 為上一個事件結束時間，可能為 null）。
- **Device Preference（§23）**：屬於每台裝置、不影響共享 World State，本骨架尚未提供 endpoint。

### 已知限制 / TODO

- `/device/pair`、`/world` 未做 rate limit（6 碼可被暴力嘗試；上線前需加 IP / 全域限流）。
- `POST /world` 不需認證，任何人都能建立 World；上線前需評估（例如 firmware 簽章、限流）。
- `device/input` V1 只記錄，不影響模擬。
- 尚未提供 token 撤銷、裝置解綁、Device Preference API。
- 假日只有週末；國定假日行事曆（core 的 `World.holiday_dates`）尚未存進 DB。
- 沒有睡覺事件，夜間顯示 idle。
