# 外觀：Offbeat 設計語言

> `/dashboard` 與 `/demo` 的外觀規範。全域規則見 [AGENTS.md](../AGENTS.md)，分層見 [architecture.md](architecture.md)。
> 內容是刻意的設計決策與踩過的坑（⚠️ 標記），改動對應程式前請先讀完相關段落。

## 風格

**Offbeat** 是 lazyrhythm 的個人設計語言（與「無感記帳」App 的 Offbeat 主題同一套）：**Nord × Brutalism**。
冷靜的北歐苔原色票（Nord Palette）＋ 刻意的結構暴力感（偏移陰影、2px 裸邊框、低圓角）——有稜角但不刺眼，有個性但不吵鬧。

命名來源：偏移陰影（**off**set）＋ 反拍節奏（**offbeat**）——結構刻意錯開，落點不在正拍上。

WorldPane 的網頁是工具型介面（監視牆、管理表單、回放控制），旋鈕設在 `STRUCTURE_WEIGHT 6 / MOTION_INTENSITY 3`：
圓角 4px（裝置畫面裡的窗 2px）、偏移 4px、幾乎不做動畫（只有角色呼吸與按鈕按下的位移，且尊重 `prefers-reduced-motion`）。

## 檔案與內嵌方式

- **`worldpane-server/src/worldpane_server/static/offbeat.css` 是網頁顏色的唯一來源**：Nord 色碼只出現在這個檔案，
  其餘元件（面板、按鈕、輸入框、分頁、chip、表格、dialog、toast、裝置畫面的天空）也在這裡定義
- 每個頁面的 `<style>` 第一行是 `/*__OFFBEAT_CSS__*/` 佔位註解，`worldpane_server/theme.py` 的 `with_offbeat()` 在送出前把整份 CSS 內嵌進去
- **刻意內嵌而不是 `<link>` 一個 `/static/offbeat.css`** ⚠️：`scripts/build_demo_html.py` 會把 `/demo` 寫成一個可以單獨打開的 HTML 檔，
  外連樣式表在離線檔案裡會失效；內嵌也讓兩個頁面都維持「一個請求就拿到完整畫面」
- 頁面裡只放版面（grid、尺寸、位置）與頁面專屬元件，**顏色一律用語意 token**

## Token 分兩層

| 層 | 例子 | 誰可以用 |
|----|------|----------|
| Nord 色票 | `--nord-polar0`、`--nord-frost1`、`--nord-red` | **只有 `offbeat.css` 自己** |
| 語意 token | `--bg`、`--panel`、`--line`、`--ink`、`--muted`、`--accent`、`--primary`、`--ok`、`--warn`、`--danger`、`--home`、`--sky-day`、`--look-1` | 頁面 CSS 與 JS |

**頁面不寫色碼、也不直接引用 `--nord-*`** ⚠️：頁面以「這是面板的底」「這是次要文字」「這是危險操作」表達意圖，由 `offbeat.css` 決定它是哪個顏色。
要調整外觀（甚至日後換一套色票）只改 `offbeat.css` 的對應，兩個頁面零改動——與無感記帳「頁面不判斷主題身分、只讀主題提供的能力」同一個原則。
JS 需要顏色時也一樣：字串寫成 `var(--look-xiaobai)`、`var(--home)`，或設 `data-sky="day"` 讓 CSS 對應，不寫 `#xxxxxx`。

`worldpane-server/tests/test_theme.py` 擋下頁面（HTML、CSS、JS）裡的 hex／`rgb()` 色碼，並檢查 `offbeat.css` 的每一個色碼都來自 Nord 色票。

## 用色規則

| 用途 | token | 色票 |
|------|-------|------|
| 頁面底 | `--bg` | polar0 `#2E3440`（永遠最深，不用純黑） |
| 面板、卡片、裝置外框 | `--panel`、`--bezel` | polar1 `#3B4252` |
| 標題欄、選中的列 | `--panel-head` | polar2 `#434C5E` |
| 面板裡的輸入框 | `--field` | polar0（比面板深一階才分得出來） |
| 邊框、分隔線 | `--line` | polar3 `#4C566A` |
| 主要文字／標題／最亮 | `--ink`／`--ink-strong`／`--ink-bright` | snow0／snow1／snow2 |
| 次要文字、placeholder | `--muted` | dim `#9AA0AD` |
| 強調、連結、focus、時鐘 | `--accent` | frost1 `#88C0D0` |
| 主要按鈕底、選中的分頁 | `--primary` | frost3 `#5E81AC` |
| 成功／警告／危險／資訊／注意 | `--ok`／`--warn`／`--danger`／`--info`／`--notice` | Aurora green／orange／red、frost2、Aurora yellow |

- **次要文字用 dim `#9AA0AD`，絕不用 polar3** ⚠️：polar3 疊在 polar0／polar1 上對比只有 2.3:1（未達 WCAG AA 4.5:1），只適合邊框與分隔線
- **Aurora 只作語意點綴，不作大面積背景**：危險按鈕是一般按鈕＋紅色邊框＋紅色偏移塊，不是整顆紅底；狀態用 `.pill` 的字與邊框表現
- **Aurora red 不當文字色** ⚠️：`#BF616A` 疊在 polar1 只有 2.46:1、polar2 只有 2.11:1（WCAG AA 要 4.5:1），最需要被讀懂的錯誤訊息反而最難讀。危險與錯誤一律是 snow 文字＋紅色的邊框、左側 bar 或偏移塊（`.err`、`.btn.danger`、`.toast.err`）。其他 Aurora 色當字前也先算對比：green／yellow 疊在 polar1 夠（4.9／6.4:1），orange／purple 只有約 3.5:1，只適合大字或非文字標記
- 不用純白背景、不用純白文字（最亮是 snow2）
- **陰影一律是 Nord 色的實色塊（無模糊）**，不用 `rgba(0,0,0,…)` 灰色陰影；dialog 背後的遮罩也是半透明 polar0（`--scrim`）
- 同一個畫面最多兩個強調色同時出現（frost 系 + 一個 Aurora 語意色）

### 場景類別色

時間軸色條、圖例與裝置畫面的地板共用同一組 token，三者必須一致：

| 類別 | token | 色票 |
|------|-------|------|
| 家裡 | `--home` | Aurora orange |
| 學校 | `--school` | Aurora green |
| 公司 | `--office` | frost2 |
| 外出 | `--out` | Aurora purple |
| 發呆（idle） | `--idle` | polar3 |

時間軸色條上的字用 `--bg`（深字疊在 Aurora／Frost 的淺色上），共同事件的白框是 `--ink-bright`。

## Brutalism 結構

- **偏移陰影**：`box-shadow: var(--offset) var(--offset) 0 var(--shadow)`（frost3 @ 50%）。按鈕用較小的 3px 實色偏移，按下時 `translate(2px, 2px)` 往陰影方向沉
- **偏移會溢出元素外框** ⚠️：放面板的 grid 要留 ≥12px 的 gap，容器右下要留出 `--offset` 的 padding（`.wall`、`.detail`、`/demo` 的 section 都有），否則陰影被相鄰元素或捲動容器截掉
- **2px 裸邊框**：面板、輸入框、按鈕、chip、分頁都是 2px `--line`；hover／focus 換成 `--accent`；選中的清單項目加 4px 左側 accent bar
- **低圓角**：`--radius` 4px；裝置畫面裡的窗、pill 用 2px；不出現 ≥8px 的圓角

## 字型

- 內文與標題：Noto Sans TC（標題 900、按鈕 600）
- 時鐘、時間、ID、狀態列、標籤：JetBrains Mono（`--font-mono`），數字一律 `tabular-nums`
- 只從 Google Fonts 載入這兩個字族；舊版的 LXGW WenKai（楷體）與 IBM Plex Mono 已移除

## 只有深色

Offbeat 是深色設計語言，**頁面固定 `color-scheme: dark`，不再跟隨系統切換淺色**。舊版的淺色／深色兩組變數已移除：
Offbeat 的禁忌清單明確排除白底，而維護兩組顏色正是讓頁面寫死色碼、兩邊漂移的原因。

## 裝置畫面

`/demo` 與監視牆裡的「窗」是在模擬 ESP32 螢幕的內容，不是介面外框，但同樣只用 token：

- 天空依時段（`night`／`dawn`／`day`／`dusk`／`evening`）設在 `.sky` 的 `data-sky`，漸層由 `offbeat.css` 的 `--sky-*` 決定
- 地板是 `.room` 的 `--k`，等於該場景類別的 token（發呆時是 `--idle`）
- 角色身體色是 `--look-<appearance key>`；沒有對應的 key 依序取 `--look-1`～`--look-6`
- 文字疊在半透明 polar0 的 `--screen-cap` 上，用 `--screen-ink`（snow2）

日後 ESP32 韌體要畫同樣的畫面時，從 `offbeat.css` 的 Nord 色票換算成裝置的色彩格式（例如 RGB565），不要另外調一組顏色。
