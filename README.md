# WorldPane（窗間）

多人微型生活世界：World 在 Backend 持續運作，一台或多台 ESP32 裝置是觀看同一個 World 的窗口。
完整規格見 [`WorldPane_專案規格.md`](./WorldPane_專案規格.md)。

```text
ESP32 裝置 ──HTTPS polling──▶ worldpane-server（FastAPI）──▶ Supabase Postgres（worldpane schema）
                                     │
                                     └─ worldpane-core（純 Python 模擬引擎）
```

| 目錄 | 內容 | 文件 |
|---|---|---|
| [`worldpane-core/`](./worldpane-core) | Simulation Core：給定 World + 角色 + 日期，決定性產生一天的事件時間軸（純 stdlib） | [README](./worldpane-core/README.md) |
| [`worldpane-server/`](./worldpane-server) | Backend API：建立 World、裝置配對、`/world/state`、`/world/history`、瀏覽器 Demo | [README](./worldpane-server/README.md) |
| [`supabase/`](./supabase) | DB schema（migrations）、事件目錄、seed | [README](./supabase/README.md) |
| [`docker-compose.yml`](./docker-compose.yml) | 一鍵部署（預設接 Supabase；`--profile local-db` 改用本機 Postgres） | 見 server README |
| [`docs/`](./docs) | 架構與跨 package 契約、網頁外觀（Offbeat）、版本歷史 | [architecture](./docs/architecture.md)、[ui-conventions](./docs/ui-conventions.md)、[changelog](./docs/changelog.md) |

開發規範、「改 X 前先讀 Y」對照表與 Code Review 原則在 [`AGENTS.md`](./AGENTS.md)（Claude Code 與 Codex 共用；`CLAUDE.md` 只匯入它）。

## 快速開始

```bash
cp .env.example .env            # 填 WORLDPANE_DATABASE_URL（Supabase service-role 連線字串）
docker compose up -d --build    # 先把 supabase/migrations 套到 Supabase 專案
# 沒有 Supabase 時：docker compose --profile local-db up -d --build
```

- API 文件：<http://127.0.0.1:8000/docs>
- 瀏覽器 Demo：<http://127.0.0.1:8000/demo>（離線回放一週，或連線後端模擬一台裝置）
- Dashboard：<http://127.0.0.1:8000/dashboard>：用 Supabase Auth 帳號登入（設定見 [server README](./worldpane-server/README.md#dashboard)），新增 / 調整 World，監視牆一次看多個 World 的畫面

用 CI 發布的 image、不在本機 build：`.env` 設 `WORLDPANE_IMAGE=ghcr.io/dwvwdv/worldpane-server:latest`，再 `docker compose pull && docker compose up -d`。

不用 Docker、只跑模擬：

```bash
cd worldpane-core && PYTHONPATH=src python3 -m worldpane_core timeline --date 2026-10-05
```

## 後端負責什麼

- **模擬 World**：每天第一次被讀取時產生當天計畫（作息、三餐、請假、上班上課插曲、休閒、2..N 人共同事件、衝突解決），存進 DB 後不再改動。相同輸入永遠得到相同結果。
- **Display API**：回傳每個角色目前的 `scene` / `activity`（Semantic State），附 `revision` / `ETag`，裝置每 15 秒輪詢。
- **History**：查詢任一天的事件。
- **裝置配對**：建立 World、6 碼 Pairing Code、Device Token。裝置綁定的是 World，不是角色。
- **Dashboard**（`/dashboard` + `/api/v1/admin`）：列出 / 新增 World（自訂 1..12 個角色）、改名、新增 / 改名 / 封存角色、調共同事件設定、發配對碼、看時間軸；監視牆每 15 秒更新，一次顯示多個 World 的即時畫面。
- **調參不需部署**：所有機率、權重、時長、cooldown（規格 §34 TBD）與事件定義都是 DB 資料；新增事件只要新增一列。

## 現況（V1 Phase 1–2）

已完成：規格 §35 的 Phase 1（Backend Simulation）與 Phase 2（Display API：current state、history、
device registration、World pairing、revision / ETag），以及 Docker 部署、瀏覽器 Demo、管理 Dashboard 與 CI/CD。

尚未完成：

| 項目 | 說明 |
|---|---|
| §34 TBD 數值 | 跳餐機率、請假機率、各事件 weight / duration / cooldown 目前都是佔位值，待定案後直接改 DB |
| 國定假日 | 只把週末當假日；core 有 `World.holiday_dates`，但 DB / server 還沒有假日行事曆 |
| 夜間睡覺 | 沒有睡覺事件，最後一個事件結束後到隔天早上都是 idle |
| Device Preference API（§23） | 表已建立（`device_preferences`），但沒有 endpoint |
| 安全 | `/device/pair`、`POST /world` 沒有 rate limit；沒有 token 撤銷 / 裝置解綁（Dashboard 也還不能解綁裝置）|
| Dashboard 權限 | 登入用 Supabase Auth，`worldpane.admins` 裡的帳號全部是同等權限（沒有唯讀 / 分 World 授權）；admin API 沒有 rate limit |
| Migration 自動部署 | CI 只發布 image；新的 Supabase migration 仍需手動套用（共用專案，見 [supabase README](./supabase/README.md)） |
| `POST /device/input` | 只記錄，不影響模擬 |
| ESP32 firmware（Phase 3–5） | 尚未開始；API 合約在 [`worldpane-server/openapi.json`](./worldpane-server/openapi.json) |

## CI/CD（GitHub Actions）

| Workflow | 觸發 | 內容 |
|---|---|---|
| [`core.yml`](./.github/workflows/core.yml) | `worldpane-core/**`、`supabase/seed.sql` | Python 3.12 / 3.13 / 3.14 跑 core 測試；檢查 `seed.sql` 與 core 預設一致 |
| [`docs.yml`](./.github/workflows/docs.yml) | 每個 PR / push | 文件一致性：`AGENTS.md` 大小、文件提到的路徑存在、版號一致且有 changelog 條目 |
| [`server.yml`](./.github/workflows/server.yml) | `worldpane-server/**`、`worldpane-core/**`、`supabase/**`、`docker/**`、`docker-compose.yml` | server 測試（Python 3.14）同時跑 in-memory 與 Postgres 15（與 Supabase 專案相同）（用 `docker/db/init-worldpane.sh` 套 migrations）；檢查 `openapi.json`；build image 後用 `docker compose --profile local-db` 冒煙測試；push 到 `master` 時發布 `ghcr.io/dwvwdv/worldpane-server:latest` 與 `:sha-<commit>` |

PR 只跑測試和 build，不會 push image。

## 測試

```bash
(cd worldpane-core && python3 -m pytest)
(cd worldpane-server && python3 -m pip install -e ../worldpane-core -e ".[dev]" && python3 -m pytest)
python3 -m pytest tests          # 文件一致性守衛（repo 根目錄，只需要 pytest）
# Postgres 測試：WORLDPANE_TEST_DATABASE_URL=postgresql://... python3 -m pytest（必須是可丟棄的 DB）
```
