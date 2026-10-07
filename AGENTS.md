# WorldPane（窗間）— AI 協作規範

> **本檔是 Claude Code 與 Codex 共用的唯一專案規範**。`CLAUDE.md` 只有一行 `@AGENTS.md`，
> 讓讀不到 `AGENTS.md` 的 Claude Code session 也拿得到同一份內容——**不要在 `CLAUDE.md` 寫任何東西**。
>
> **本檔只放索引與全域規則，細節一律寫進 `docs/` 或各 package 的 README** ⚠️：Codex 讀 `AGENTS.md` 的預設上限是 32 KiB，
> 超過的部分會被直接截掉，而 Claude 每次對話都會整份載入本檔。`tests/test_docs_consistency.py` 擋下超過 30 KiB 的本檔。
> 新功能的設計理由、踩過的坑（⚠️ 段落）寫進下方「改 X 前先讀 Y」對應的那份文件，本檔頂多加一行連結。

## 項目簡介

**WorldPane（窗間）**：多人微型生活世界。World 在 Backend 持續運作，一台或多台 ESP32 裝置是觀看同一個 World 的窗口。

- **版本**：各 package 的 `pyproject.toml`（`worldpane-core/`、`worldpane-server/` 各自獨立）
- **技術棧**：Python（3.12 以上，CI 跑 3.12～3.14）+ FastAPI + psycopg 3 + Supabase Postgres 15（`worldpane` schema）+ Docker；ESP32-S3（ESP-IDF + C/C++，尚未開始）
- **規格**：[WorldPane_專案規格.md](WorldPane_專案規格.md)（產品規則與 Phase 的唯一來源；§ 編號引用的都是這份）
- **現況與尚未完成的項目**：[README.md](README.md)

### 資料與安全說明 ⚠️

- **ESP32 只跟 `worldpane-server` 溝通，從不直接連 Supabase**。Backend 用 service-role 連線字串存取資料庫，那個字串只存在伺服器的環境變數，不進 repo、不進 image。
- **共用的 Supabase 專案**：同一個 Supabase Project 裡跑了多個 App，WorldPane 的所有物件都在 `worldpane` schema。**只動 `worldpane` schema**，migration 與 SQL 都不得碰 `public` 或其他 App 的 schema。
- 每張表都啟用 RLS 且沒有 policy（deny-by-default），`worldpane` 不在 Exposed Schemas。要開放 PostgREST 之前必須先寫好 policy（見 [supabase/README.md](supabase/README.md)「關於 Exposed Schemas」）。
- **Device token 只存 sha256；pairing code 只存 HMAC-SHA256**（6 碼只有 10^6 種，純 sha256 可被暴力還原）。token、pairing code、secret 一律不寫進 log（`dev` 模式印出 demo 配對碼是唯一例外）。
- `/dashboard` 內嵌的 Supabase URL 與 anon key 本來就是給瀏覽器用的公開值，不是 secret；admin token 只存在分頁的 `sessionStorage`。
- 撰寫文件或對外說明時，不要寫成「ESP32 連 Supabase」或「資料存在裝置上」：World 的狀態與歷史都在後端，裝置只顯示後端給的 Semantic State。

## 改 X 前先讀 Y ⚠️

不要只根據目前的 diff 推測專案規則：下列文件記錄了刻意的設計決策與已接受的 trade-off，動到對應的程式前先讀完相關段落。

| 要動的東西 | 先讀 |
|-----------|------|
| 模擬規則：作息、三餐、請假、插曲、休閒、共同事件、衝突解決、決定性 seed | [worldpane-core/README.md](worldpane-core/README.md)、[docs/architecture.md](docs/architecture.md) 的「決定性與不可改寫的歷史」 |
| 事件目錄、§34 TBD 數值、`supabase/seed.sql` | [worldpane-core/README.md](worldpane-core/README.md) 的「事件目錄」「設定值（TBD）」、[supabase/README.md](supabase/README.md) 的「設計備註」 |
| DB schema、migration、RLS、權限、共用 Supabase 專案 | [supabase/README.md](supabase/README.md) |
| Display API 合約、revision／ETag、History、裝置配對與 token | [worldpane-server/README.md](worldpane-server/README.md) 的「設計重點」、`worldpane-server/openapi.json` |
| Dashboard、`/api/v1/admin`、Supabase Auth 登入與 `worldpane.admins` | [worldpane-server/README.md](worldpane-server/README.md) 的「Dashboard」 |
| `/dashboard`、`/demo` 的外觀、顏色、字型（Offbeat） | [docs/ui-conventions.md](docs/ui-conventions.md) |
| 分層、跨 package 契約、「想改什麼從哪裡開始」 | [docs/architecture.md](docs/architecture.md) |
| Docker 部署、環境變數、CI/CD | [worldpane-server/README.md](worldpane-server/README.md) 的「Docker 一鍵部署」、[README.md](README.md) 的「CI/CD」 |
| 版本歷史 | [docs/changelog.md](docs/changelog.md) |

## 快速開始

```bash
python3 -m pip install -e worldpane-core -e "worldpane-server[dev]"   # 安裝（server 依賴 core）
(cd worldpane-core && python3 -m pytest)                               # core 測試（純 stdlib）
(cd worldpane-server && python3 -m pytest)                             # server 測試（in-memory）
python3 -m pytest tests                                                # 文件一致性守衛（repo 根目錄）
(cd worldpane-server && WORLDPANE_ENV=dev uvicorn worldpane_server.main:app --reload)  # /docs、/demo、/dashboard

# Postgres 測試：WORLDPANE_TEST_DATABASE_URL=postgresql://... python3 -m pytest（必須是可丟棄的 DB）
# 產物是否過期：
(cd worldpane-core && python3 scripts/gen_seed_sql.py --check ../supabase/seed.sql)
(cd worldpane-server && python3 scripts/export_openapi.py --check)
```

部署 → [worldpane-server/README.md](worldpane-server/README.md) 的「Docker 一鍵部署」。

## 開發規範

### 版本管理 ⚠️

**每次功能調整或修復都要更新「被改到的那個 package」的版本號**，格式 `major.minor.patch`，除非特別指定只加 `patch`。

- 版號寫在兩處且必須一致：`pyproject.toml` 的 `version` 與套件的 `__init__.py` 的 `__version__`（`tests/test_docs_consistency.py` 檢查）
- `worldpane-server` 的版號會進 `openapi.json`，升版後要跑 `scripts/export_openapi.py` 重新產生（CI 以 `--check` 擋下過期的檔案）
- 只改文件、CI、`supabase/` 而沒動任何 package 時不升版
- **同一個 PR 最多只疊代一次版本號**：PR 首個 commit 升版之後，同 PR 的後續修改（review 修復、追加調整）沿用同一版號，changelog 也合併記在同一條目下。禁止在單一 PR 內出現 vX → vX+1 → vX+2
- **每次升版都要在 [docs/changelog.md](docs/changelog.md) 最上方加條目**（測試檢查兩個 package 的目前版號都有條目）

### 代碼風格

- 每個模組開頭 `from __future__ import annotations`、公開函式寫型別註記；docstring 說「為什麼」，不重述程式碼
- **`worldpane-core` 只用標準函式庫**，不做 I/O、不讀時鐘、不碰資料庫——它是給定輸入就決定輸出的純函式庫，server 與 ESP32 以外的工具都靠這一點重用它
- 日誌一律 `logging.getLogger(...)`，不要 `print()`（唯一例外是 `worldpane_core/cli.py` 的終端輸出）
- 時間一律 tz-aware；「今天」以 World 的時區判斷。server 裡跟 World 有關的「現在」只從注入的 `Clock` 取得（`SystemClock`；測試用 `FixedClock`），不直接呼叫 `datetime.now()`（Supabase token 快取的過期判斷這類與 World 無關的 wall clock 例外）

### 模擬決定性 ⚠️

- core 不得使用全域 `random`、內建 `hash()`、目前時間或 dict／set 的非決定性順序；所有亂數都從 `seeds.py` 的 sha256 seed 衍生
- **已持久化的 daily plan 是歷史，不回溯改寫**。調參只影響之後才產生的日期
- **會改變既有輸入生成結果的演算法修改，要升 `simulation_version`**（規格「修改 Simulation Algorithm 時可透過 `simulation_version` 明確產生新版本」），不要讓同一組輸入悄悄產生不同的計畫；`test_determinism.py` 守住「相同輸入 → 相同結果」
- 新增事件 = 新增資料（`event_definitions` 一列），不在 core 裡為個別事件寫分支

### 資料庫操作

- server 只透過 `Repository` Protocol（`repositories/base.py`）存取資料；**新增方法時 `InMemoryRepository` 與 `PostgresRepository` 都要實作**，測試會對兩者各跑一次
- SQL 一律用 psycopg 參數（`%s` + 參數 tuple），禁止把輸入串接或 f-string 進 SQL
- **已套用的 migration 不改**，變更一律新增檔案（`supabase/migrations/<timestamp>_<name>.sql`）；migration 目前要手動套到共用的 Supabase 專案（見 [supabase/README.md](supabase/README.md)）
- **`supabase/seed.sql` 不手改**：它由 `worldpane-core/scripts/gen_seed_sql.py` 從 core 的官方預設產生
- Postgres 版本對齊 Supabase 專案（15）；CI 與 `docker-compose.yml` 的 `local-db` 都釘在 15

### API 合約

- `worldpane-server/openapi.json` 是給 ESP32 端的合約：改到 `schemas.py` 或路由後重新產生，CI 擋下過期的檔案
- 對裝置的 API 只做**加法相容**的變更（新增欄位、新增 endpoint）；裝置韌體不會跟著 server 一起更新

### 網頁（`/dashboard`、`/demo`）

- 單一 HTML 檔、不引入建置流程與前端框架；外觀一律照 [docs/ui-conventions.md](docs/ui-conventions.md)：**頁面不寫色碼，只用 `static/offbeat.css` 的語意 token**（測試擋下頁面裡的 hex／rgb 色碼）
- 使用者輸入與 API 回傳的字串進 HTML 前一律經 `esc()`

## 文件維護

- **本檔與 `docs/`、各 README 不重複**：同一件事只寫在一個地方，其他地方放連結。兩份文件各自維護同一份說明，就是它們落後版本的原因
- 程式碼註解引用設計理由時，指向文件與段落名稱（例如「見 docs/architecture.md 的『決定性與不可改寫的歷史』」）；規格條文用 § 編號
- `tests/test_docs_consistency.py` 會掃描本檔與 `docs/` 的現況文件，提到的路徑與檔名都必須真的存在；改名或刪除時一併更新文件

---

以下為 Pull Request 與 Code Review 的規範，Codex 與 Claude 一體適用。

## GitHub Pull Request 語言規範

所有 GitHub Pull Request 的 title、body、comment、review 回覆與 review 結果，
一律使用繁體中文。技術識別字、程式碼、命令與 API 名稱可保留原文。

---

## Code Review 原則

進行 Pull Request Review 時，優先找出「實際值得修、會影響產品」的問題。

不要為了理論完整性，持續追查極低機率、刻意構造、正常使用幾乎不可能出現的邊界情況。

### 什麼問題值得提出

只有至少符合以下一項時，才應提出 finding：

- 正常使用流程或合理可預期的操作可能觸發
- 可能讓同一組輸入產生不同的計畫、或改寫已持久化的歷史（決定性被破壞）
- 可能造成資料錯誤、資料遺失、重複資料，或多台裝置看到不一致的狀態
- 可能造成安全問題（token、pairing code、admin 權限、跨 World 存取、碰到其他 App 的 schema）
- 可能造成 crash、World 整天沒有計畫，或核心功能（Display API、配對）無法使用
- 是本 PR 新增或明顯暴露出的 concurrency、migration 或 API 相容性問題
- 問題雖低機率，但一旦發生會造成嚴重且持久的資料完整性問題

### 什麼問題通常不要提出

以下情況通常不應列為 Review finding：

- 必須輸入極端長文字、數千個角色或刻意構造巨大輸入才會發生
- 純粹為了撞 Postgres 參數數量、整數上限、collection size 等底層實作限制
- 需要極端不合理 timing 才可能發生，而且沒有明確產品影響的理論 race condition
- 必須手動破壞資料庫、繞過 Repository 直接改資料或違反既有 invariant 才能觸發
- 現有行為在正常產品使用範圍內已經正確，只是還可以做更多 defensive hardening
- 主要收益只是架構更漂亮、更加通用、未來可能更容易擴充，而不是修正實際問題
- 與本 PR 無直接關係的既有問題，除非它會直接讓這次修改無法正確運作
- 本檔、`docs/`、各 README 或 [README.md](README.md) 的「尚未完成」表格已明確記錄並接受的限制，且本 PR 沒有改變相關前提

### Edge case 處理原則

遇到極端 edge case 時，優先考慮**簡單的產品限制**，而不是增加大量實作機制。

例如角色名稱極端長可能讓畫面或 DB 出問題時，應優先：

- 限制合理的名稱長度（API schema 的 `max_length`）
- 限制合理的數量（例如每個 World 1..12 個角色）
- 回傳清楚的 422 錯誤

而不是為了支援每一個底層極限，加入更多分支、狀態與 recovery 邏輯。

---

## Finding 提出門檻

提出 finding 前，先確認：

1. 這個問題是本 PR 引入或明顯暴露的
2. 有具體、可描述的實際觸發流程
3. 有明確的使用者或資料影響
4. 問題的嚴重程度值得增加程式碼與長期維護成本
5. 沒有更簡單的產品限制能合理解決
6. 本檔與 `docs/` 沒有已經把這件事列為刻意接受的限制

每個 finding 應說明：

- **實際觸發方式**
- **具體影響**
- **為什麼值得在這個 PR 修**

不要只證明「理論上可能發生」。

---

## Review 優先級

優先檢查：

1. 決定性被破壞、已持久化的歷史被改寫
2. 靜默資料錯誤、資料遺失或重複寫入
3. Transaction / atomicity 問題（plan 與 events 同一交易、revision 原子遞增）
4. 正常操作可以觸發的 race condition（多台裝置同時輪詢、Dashboard 同時編輯）
5. Security（token、pairing、admin 驗證、RLS、跨 World 存取）
6. Migration / schema / API 相容性（裝置韌體不會跟著更新）
7. 核心 workflow regression
8. 明確且可重現的 UI 行為錯誤

低優先級：

- 純架構潔癖
- 理論 extensibility
- 極端輸入
- 微小 defensive hardening
- 幾乎不可能達到的 implementation limit

---

## 產品規模假設

這是一個**個人／小圈子使用的放置型生活模擬**：World 數量是個位數到數十個，每個 World 1..12 個角色、
幾台裝置，每台約 15 秒輪詢一次；Dashboard 只有少數幾位管理員。不是高併發的多租戶 SaaS。

Review 應以這個規模與正常的操作方式為前提。不要因為底層 library 理論上允許無限輸入，
就要求系統支援刻意構造的極端資料或流量（對外暴露的配對與建立 World 仍需要 rate limit，那是已列在 README 的已知限制）。

如果合理的產品限制可以解決，就採用產品限制。

---

## Review Scope

不要把 Review 變成無限延伸的全專案 audit。

當一個 finding 被修正後，應檢查：

- 修正本身是否正確
- 是否造成直接 regression
- 是否破壞本 PR 涉及的既有 invariant

不要因為修正了一個問題，就沿著所有理論依賴一路擴展到與本 PR 幾乎無關的歷史問題。

Review 的目標是：

> 判斷這個 PR 是否值得安全地合併。

不是：

> 證明整個程式在所有理論輸入與所有可能執行順序下都完美。

**寧可少報一個 technically correct 但實際沒有產品價值的問題，也不要為了找到問題而找問題。**
