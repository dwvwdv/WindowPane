# 版本歷史

> `worldpane-core` 與 `worldpane-server` 各自有版號，條目標題寫明是哪個 package：`### server 0.1.1 (YYYY-MM-DD)`。
> 新條目一律加在本檔最上方；同一個 PR 只升一次版、只寫一個條目（規則見 [AGENTS.md](../AGENTS.md) 的「版本管理」）。
> 前綴標示類型：✨ 新功能／🐛 修復／🎨 UI／⚡ 優化／📝 文件與流程。
> 只改文件、CI 或 `supabase/` 而沒動 package 的 PR 不升版，但值得記的流程變更可以併進下一個版本條目。

## 最近版本

### server 0.1.1 (2026-10-07)
- 🎨 **`/dashboard` 與 `/demo` 改用 Offbeat 設計語言**（Nord × Brutalism，與無感記帳 App 的 Offbeat 主題同一套）：polar0 深色底、2px 裸邊框、frost3 偏移陰影塊、4px 低圓角；字型改為 Noto Sans TC + JetBrains Mono，移除楷體與 IBM Plex Mono
- 🎨 **網頁顏色集中到 `static/offbeat.css`**：Nord 色碼只寫在這個檔案，頁面與 JS 只用語意 token（`--panel`、`--muted`、`--home`、`--sky-day`、`--look-1`…），由 `theme.py` 在送出前內嵌，離線的 demo 檔照樣完整。時間軸、圖例與裝置畫面的地板改用同一組場景類別色
- 🎨 頁面固定深色（Offbeat 不使用白底），移除舊的淺色／深色兩組變數
- ⚡ `test_theme.py`：頁面不得寫 hex／`rgb()` 色碼、`offbeat.css` 的色碼必須來自 Nord 色票
- 📝 **專案規範移植自無感記帳**：`AGENTS.md` 為 Claude Code 與 Codex 共用的唯一規範（`CLAUDE.md` 只有 `@AGENTS.md`），含「改 X 前先讀 Y」對照表、開發規範、版本管理、PR 語言與 Code Review 原則；新增 `docs/architecture.md`、`docs/ui-conventions.md` 與本檔
- 📝 `tests/test_docs_consistency.py`（`docs.yml` workflow）：`AGENTS.md` ≤ 30 KiB、`CLAUDE.md` 只匯入 `AGENTS.md`、文件提到的路徑必須存在、兩個 package 的版號一致且都有 changelog 條目
- 📝 Claude Code 雲端 session 的 SessionStart hook：自動安裝 core 與 server（含 dev 依賴）

### core 0.1.0 / server 0.1.0 (2026-10-06)
- ✨ 規格 §35 Phase 1（Backend Simulation）與 Phase 2（Display API：current state、history、device registration、World pairing、revision／ETag）
- ✨ Docker 一鍵部署、瀏覽器 Demo（`/demo`）、管理 Dashboard（`/dashboard`，Supabase Auth 登入）與 CI/CD（GHCR image）
