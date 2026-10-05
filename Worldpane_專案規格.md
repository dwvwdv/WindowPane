# Worldpane（窗間）— 多人放置型生活模擬器專案規格

> 正式名稱：**Worldpane / 窗間**  
> 狀態：V1 架構與核心規則定稿  
> 更新日期：2026-10-05  
> 目標硬體：ESP32-S3（目前開發主線為 ESP-IDF + C/C++）


## 版本進展

### 2026-10-05 — Phase 1–2 Backend 實作完成

- `worldpane-core`（Simulation Core）、`worldpane-server`（FastAPI Display API）、`supabase/`（schema）已合併。
- §34 TBD 數值與所有事件定義存在 DB，可直接調整，新增事件只需新增資料。
- Docker 一鍵部署（預設接 Supabase）與瀏覽器 Demo（`/demo`）。
- 實作狀態與尚未完成的項目見 repo 根目錄 `README.md`。

### 2026-10-05 — Worldpane 命名與多人化

- 正式命名：**窗間 / Worldpane**。
- 產品從「雙角色放置型生活模擬器」提升為「多人微型生活世界」。
- `World → Character` 正式定義為 `1:N`。
- 同一 World 可容納 2 人、3 人、5 人或更多 Character。
- Shared Event 正式支援 `2..N Participant`。
- 增加 `CharacterRelationship`，避免以 `partner_id` 綁死情侶模型。
- 情侶雙裝置共享 World 保留為核心使用情境之一，但不再是 Domain 限制。
- 多台 Device 仍可綁定同一 World，且各自保有 Local Asset / Display Preference。

---

## 1. 專案定位

這不是把完整遊戲邏輯塞進 ESP32 的單機電子寵物，而是：

> **Backend 維護一個持續存在的多人微型生活世界；ESP32 是觀看這個世界的實體窗口。**

產品名稱 **Worldpane** 來自 `World + Window Pane`：每一台裝置都是通往同一個持續世界的一扇窗。

核心特性：

- 一個 `World` 代表一組獨立運行的生活世界。
- 每個 World 可以存在 **1..N 個 Character**，核心架構不綁死兩人、情侶或固定角色數。
- 同一個 World 可以綁定多台 ESP32。
- 多台裝置看到的是同一條世界時間線、同一批事件與同一份歷史。
- 每台 ESP32 可以有自己的顯示偏好與本地角色外觀。
- 角色的作息、事件機率、請假規則等全部由 Backend 管理。
- ESP32 不負責推演角色生活，只負責：
  - 連網
  - 取得目前狀態
  - 渲染畫面
  - 顯示歷史
  - 接收本地按鍵輸入
  - 管理本地角色素材

---

## 2. 整體架構

```text
                         Backend
                    ┌──────────────┐
                    │    World     │
                    └──────┬───────┘
                           │
                   ┌───────▼────────┐
                   │ Characters 1..N │
                   │                 │
                   │ Profile         │
                   │ Schedule        │
                   │ Event Rules     │
                   │ Meal Rules      │
                   └───────┬─────────┘
                           │
                   ┌───────▼─────────┐
                   │ Relationship    │
                   │ / Group Rules   │
                   └───────┬─────────┘
                           │
                   Shared Event Rules
                           │
                           ▼
                   Simulation Engine
                           │
                   Event / History DB
                           │
                      Display API
                           │
            ┌──────────────┼──────────────┐
            │              │              │
            ▼              ▼              ▼
       ESP32 A         ESP32 B        ESP32 ...
       ┌──────────┐    ┌──────────┐
       │Asset     │    │Asset     │
       │Renderer  │    │Renderer  │
       │HTTP      │    │HTTP      │
       └────┬─────┘    └────┬─────┘
            │               │
          Display         Display
```

### 核心關係

```text
World 1 ─── N Character
World 1 ─── N Device
Character 1 ─── 1 Profile
World 1 ─── N Event
Event N ─── N Character
Character N ─── N CharacterRelationship
```

V1 中：

- 一個 Device 同一時間只綁定一個 World。
- 一個 World 可以綁定多個 Device。
- World 與 Device 的關係不能寫死成一對一。

---

## 3. V1 不做 User 帳號系統

V1 不需要：

```text
User
  ↓
World
```

直接以：

```text
Device
  ↓
World
```

運作即可。

原因：

- 核心玩法不依賴帳號。
- 可先避免登入、OAuth、忘記密碼、權限等無關複雜度。
- 情侶共享 World 可以透過配對碼完成。

未來需要 App / Web 帳號、多 World 管理或跨裝置帳戶同步時，再補：

```text
User
  ↓
World
  ↓
Device
```

不會影響 Simulation Core。

---

## 4. World

`World` 是整個系統最重要的 Aggregate Root。

World 擁有：

```text
World
├─ Characters 1..N
├─ Character Profiles
├─ Character Relationships
├─ Individual Event Rules
├─ Shared / Group Event Rules
├─ Events
├─ History
└─ Devices
```

角色數量不是 Domain Constant。V1 的官方預設內容仍可先提供「小白 + 小雞毛」兩人世界，但 Simulation Core、資料表與 API 不得假設固定為 2 人。

建議欄位：

```text
World
-----
id
name
timezone
simulation_version
created_at
simulation_start_date
```

### Timezone

每個 World 必須有自己的時區。

V1 預設：

```text
Asia/Taipei
```

所有：

- 上班時間
- 上學時間
- 用餐時段
- 月份
- 星期
- 歷史日期

都以 World timezone 計算。

---

## 5. Character 是可擴充的 World 成員

Backend 不應寫：

```cpp
if (character == XIAOBAI) {
    ...
}
```

正確模型是：

```text
CharacterInstance
+
CharacterProfile
```

例如：

```text
World A
├─ Character 1
│  ├─ appearance_type = xiaobai
│  └─ profile = student_profile
├─ Character 2
│  ├─ appearance_type = xiaojimao
│  └─ profile = office_worker_profile
└─ Character 3
   ├─ appearance_type = custom_character
   └─ profile = freelancer_profile
```

另一個世界可以完全不同：

```text
World B
├─ 小白 B
│  └─ 12:00 ~ 21:00 工作
├─ 小雞毛 B
│  └─ 每週一到四上課
├─ Character C
│  └─ 夜班工作
├─ Character D
│  └─ 自由作息
└─ Character E
   └─ 學生
```

即使外觀都叫「小白 / 小雞毛」，也必須是完全不同的 Character Instance。

---

## 6. Appearance 與 Profile 完全分離

## CharacterAppearance

控制：

- 顯示名稱
- Sprite / 動畫
- 外觀
- 本地素材 mapping

不包含生活規則。

## CharacterProfile

控制：

- 工作 / 上學
- Weekly Schedule
- Meal Rules
- Leave Rules
- 個人事件
- 個性傾向
- 事件權重
- 休閒偏好

因此：

```text
同一個「小白」外觀
```

可以套：

```text
學生 Profile
工程師 Profile
自由工作者 Profile
```

Simulation Engine 不需要知道角色原始 IP 身份。

---

## 7. 初始官方角色／Profile 範例

## 官方預設角色：小白

### 平日

```text
週一 ~ 週五
08:30 ~ 17:30 上學
```

### 上學途中可能發生

- 睡覺
- 玩遊戲
- 其他未來新增的校園事件

這些屬於：

```text
temporary event
```

例如：

```text
SCHOOL
  ↓
SLEEPING_IN_CLASS
  ↓
SCHOOL
```

不是把整個上學 Schedule 移除。

### 請假

規則：

```text
每個 Calendar Month 最多請一天假
```

請假不是必然發生。

V1 將「本月是否請假」設成 Profile 可配置概率。

若本月判定請假：

1. 找出當月可請假的工作日（Mon-Fri）。
2. 隨機選一天。
3. 本月不再產生第二次請假。

概率數值目前尚未定案，必須留在設定中，不 hard-code 到 Simulation Engine。

---

## 官方預設角色：小雞毛

### 平日

```text
週一 ~ 週五
08:30 ~ 17:30 工作
```

### 工作途中可能發生

- 摸魚
- 其他未來新增的工作事件

事件形式：

```text
WORK
  ↓
SLACKING
  ↓
WORK
```

### 請假

以固定 14 天 Cycle 運作。

```text
Cycle 1：Day 1 ~ Day 14
Cycle 2：Day 15 ~ Day 28
Cycle 3：Day 29 ~ Day 42
...
```

Cycle 必須使用固定 Anchor Date 計算，不能因為實際請假而重置。

例如：

```text
Day 8 請假

Day 9 ~ Day 14
不重新開始計算

Day 15
才進入下一個 14-day cycle
```

每個 Cycle：

1. 判定這一輪是否產生請假。
2. 若有請假：
   - 從 Cycle 內符合條件的工作日挑一天。
   - 最多一天。
3. Cycle Anchor 不因請假日改變。

建議欄位：

```text
leave_cycle_anchor_date
leave_cycle_days = 14
leave_max_per_cycle = 1
leave_probability = configurable
```

請假概率目前尚未定案。

---

## 8. Meal Rules

官方預設的小白與小雞毛每天都有三個用餐時段。Meal Rule 本身屬於 Character Profile，因此未來其他 Character 可以有完全不同的餐次、時段與跳過概率。

| 餐別 | 可開始時段 | 用餐時間 |
|---|---|---:|
| 早餐 | 08:00 ~ 11:00 | 15 ~ 20 分鐘 |
| 午餐 | 11:00 ~ 14:00 | 15 ~ 20 分鐘 |
| 晚餐 | 17:00 ~ 20:00 | 15 ~ 20 分鐘 |

每個 Character Instance 獨立生成自己的用餐事件。

## Meal Start

餐點的 `start_at` 必須落在該餐允許時段內。

例如：

```text
早餐開始：
08:00 <= start <= 11:00
```

結束時間可以超出 Window 尾端。

---

## Meal Duration

```text
15 ~ 20 分鐘
```

由 RNG 產生。

---

## Meal Skip

每餐都有：

```text
skip_probability
```

例如：

```text
早餐判定跳過
→ 今天沒有 BREAKFAST event
```

每個角色、每一餐未來都可以有不同概率。

概率數值目前不 hard-code。

---

## 餐與餐最小間隔

吃完上一餐後：

```text
下一餐開始時間 >= 上一餐結束時間 + 90 分鐘
```

例如：

```text
早餐
10:53 ~ 11:11

午餐 earliest:
12:41
```

則：

```text
lunch_start = random(12:41, 14:00)
```

如果上一餐跳過：

```text
不套用上一餐 + 90 分鐘 constraint
```

---

## 9. Base Schedule 與 Temporary Event

角色目前狀態必須至少拆成：

```text
location
activity
```

例如小雞毛：

```text
location = OFFICE
activity = SLACKING
```

小白：

```text
location = SCHOOL
activity = SLEEPING
```

不要把：

```text
WORK
SCHOOL
```

直接當成角色唯一狀態。

這樣吃飯、摸魚、睡覺等 Temporary Event 才能自然覆蓋 Base Schedule。

---

## 10. 17:30 後的生活事件

平日 17:30 後進入生活事件池。

## Individual Events

初始包含：

- 洗澡
- 滑手機
- 看小說
- 玩遊戲
- 其他後續事件

每個 Event Definition 至少具有：

```text
type
weight
min_duration
max_duration
allowed_time
allowed_context
cooldown
```

例如：

```json
{
  "type": "reading",
  "weight": 20,
  "min_duration_min": 15,
  "max_duration_min": 60,
  "allowed_time": ["17:30", "23:30"]
}
```

---

## 11. Shared / Group Events

共同事件必須從一開始就支援 **2..N 個 Participant**。

例如：

- 兩人一起看電影
- 三人一起打遊戲
- 四人打球
- 五人一起出去吃飯
- 未來其他團體事件

Shared Event 是一筆真正的共同 Event：

```text
Event
├─ participant: Character A
├─ participant: Character B
├─ participant: Character C
└─ ...
```

禁止每個角色各自 RNG 後碰巧得到同一事件。

否則容易出現：

```text
小白：和小雞毛看電影
小雞毛：正在洗澡
```

Shared Event Scheduler 必須先檢查：

- 所有候選 Participant 都可用
- Participant 人數符合 Event Rule 的 `min_participants / max_participants`
- 時段沒有不可覆蓋事件
- 滿足 Relationship / Group constraint（若該 Event 有要求）
- 滿足 Event Rule
- 滿足 cooldown
- 滿足活動可用時段

成功後一次鎖定所有 Participant 的時段。

---

## 12. Character Relationship

角色之間的關係不能寫死成：

```text
character.partner_id
```

因為一個 World 未來可能是：

```text
2 人情侶
3 人好友
5 人小團體
室友
家人
混合關係
```

採用獨立關係模型：

```text
CharacterRelationship
---------------------
id
world_id
character_a_id
character_b_id
relationship_type
affinity
metadata
```

例如：

```text
小白 ↔ 小雞毛
relationship_type = couple

小白 ↔ 阿毛
relationship_type = friend

小雞毛 ↔ 阿毛
relationship_type = roommate
```

Relationship 可以作為事件生成條件，但不是 Character 的固定屬性。

例如：

```text
date
min_participants = 2
max_participants = 2
relationship_required = couple

basketball
min_participants = 2
max_participants = 5

group_dinner
min_participants = 2
max_participants = 8
```

V1 可以只保留最基本的 `relationship_type`，`affinity` 等數值型社交系統暫不實作。

---

## 13. 假日事件

假日不建立另一套 Simulation Engine。

只改變 Event Context：

```text
weekday = false
holiday = true
```

假日可以額外開放：

- 打球
- 出門逛街
- 長時間遊戲
- 看電影
- 其他休閒事件

Profile 的 Event Rules 可以根據 Context 改：

```text
enabled
weight
duration
```

因此未來可以自然擴充：

```text
下雨
冬天
連假
生日
特殊節日
```

而不用修改 Scheduler 核心。

---

## 14. Event Priority / Conflict Resolution

V1 固定以下優先級：

```text
1. Fixed / mandatory event
2. Meal
3. Shared event
4. Work / School temporary event
5. Individual leisure event
6. Idle
```

Simulation Engine 產生事件時必須避免 overlap。

若較低優先事件已存在，而高優先事件取得同一時間：

- 嘗試移動低優先事件。
- 無法移動則取消低優先事件。
- 不允許產生互相矛盾的 Current State。

---

## 15. Simulation Strategy

V1 採：

> **Server-authoritative + deterministic daily planning**

不採用大量即時 Cron Job。

---

## Daily Plan

Backend 針對：

```text
World
Character
Date
Simulation Version
```

生成當日事件。

推薦 Seed 分兩層：

Character-local event：

```text
hash(
  world_id
  + character_id
  + local_date
  + simulation_version
)
```

World-level shared/group event：

```text
hash(
  world_id
  + local_date
  + "shared"
  + simulation_version
)
```

如此多人共同事件不會依賴某一個 Character 成為主角。

好處：

- Server reboot 不改變結果。
- 可以重現 Bug。
- 容易寫 unit test。
- 同一天不會因多次 API 呼叫得到不同生活。
- 修改 Simulation Algorithm 時可透過 `simulation_version` 明確產生新版本。

---

## 建議生成順序

```text
1. Resolve Calendar Context
2. Resolve Leave
3. Build Base Schedule
4. Generate Meals
5. Generate Work / School temporary events
6. Generate Evening / Holiday individual events
7. Generate Shared Events
8. Resolve Conflicts
9. Persist Events
```

Shared Event 必須在同一個 World 層級生成。

---

## 16. World 在 ESP32 離線時仍持續運作

ESP32 不擁有 Simulation State。

例如：

```text
ESP32 10/01 關機
ESP32 10/05 開機
```

Backend 的 World 仍然持續。

ESP32 開機後只需要：

```text
GET current display state
```

即可直接看到 10/05 現在角色在做什麼。

10/01 ~ 10/05 的 History 由 Backend 保存。

因此不需要：

- ESP32 replay 四天事件
- ESP32 保存完整 Event Log
- ESP32 自己判斷漏掉哪些事件

---

## 17. History

歷史紀錄由 Backend 永久保存。

不要每分鐘 snapshot。

採 Event Log：

```text
Event
-----
id
world_id
type
scene
start_at
end_at
status
metadata
```

搭配：

```text
EventParticipant
----------------
event_id
character_id
```

例如：

```text
2026/10/05

小白
08:30 上學
10:14 睡覺
10:28 繼續上課
12:37 午餐
15:02 玩遊戲
17:30 放學
18:31 看小說
20:05 和小雞毛看電影

小雞毛
08:30 上班
09:42 摸魚
10:03 繼續工作
13:06 午餐
17:30 下班
18:12 洗澡
20:05 和小白看電影
```

ESP32 歷史畫面只從 API 讀取。

---

## 18. ESP32 的責任

ESP32 是 Thin Client。

Firmware 大致拆成：

```text
WiFiManager
ApiClient
GameState
AssetManager
Renderer
DisplayDriver
InputManager
LocalWebServer
```

ESP32 不知道：

- 小雞毛每 14 天可能請假。
- 小白每月最多請一天。
- 晚上看電影的權重。
- 早餐什麼時候生成。
- Shared Event 如何排程。

它只知道：

```text
現在角色在哪裡
現在角色正在做什麼
應該使用哪個 scene / animation
```

---

## 19. Display API

Backend 回傳 Semantic State，不傳每一幀圖像。

例如：

```json
{
  "server_time": "2026-10-05T18:42:10+08:00",
  "revision": 18291,
  "world_id": "world_abc",
  "characters": [
    {
      "id": "char_a",
      "appearance": "xiaobai",
      "scene": "home_living_room",
      "activity": "reading",
      "started_at": "2026-10-05T18:31:00+08:00",
      "ends_at": "2026-10-05T19:03:00+08:00"
    },
    {
      "id": "char_b",
      "appearance": "xiaojimao",
      "scene": "home_bathroom",
      "activity": "shower",
      "started_at": "2026-10-05T18:38:00+08:00",
      "ends_at": "2026-10-05T18:51:00+08:00"
    }
  ]
}
```

ESP32：

```text
scene + activity
       ↓
AssetManager
       ↓
Renderer
```

---

## 20. Backend 通訊方式

V1 使用：

```text
HTTPS REST + Polling
```

暫時不用：

- WebSocket
- SSE
- MQTT

理由：

- 事件時間尺度為分鐘。
- 沒有亞秒級同步需求。
- REST reconnect 最簡單。
- ESP32 firmware 較容易維護。

建議：

```text
poll interval = 15 秒
```

API 使用：

```text
revision
ETag / If-None-Match
```

避免沒有變更時重送完整 payload。

---

## 21. Backend API V1

核心 API：

```http
GET /api/v1/world/state
```

取得此 Device 所綁 World 的 Current State。

---

```http
GET /api/v1/world/history?date=2026-10-05
```

取得指定日期歷史。

---

```http
POST /api/v1/device/input
```

ESP32 按鍵 / 本地操作送往 Backend。

例如：

```json
{
  "type": "button_press",
  "button": "A"
}
```

---

```http
POST /api/v1/device/pair
```

使用 Pairing Code 綁定 World。

---

```http
POST /api/v1/world
POST /api/v1/world/pairing-codes
```

第一台裝置建立 World（回傳該裝置的 token 與給其他裝置用的 Pairing Code）；已綁定的裝置可再發一組 Pairing Code 邀請其他裝置（見 §22）。

---

## 22. Device Pairing

多個使用者可以各自擁有裝置，但加入同一個 World。情侶雙裝置是其中一個主要使用情境。

```text
                 World ABC
            小白 A + 小雞毛 A
                   │
          ┌────────┴────────┐
          │                 │
      Device A          Device B
      男方桌上          女方桌上
```

兩台裝置：

```text
Device A → World ABC
Device B → World ABC
```

它們不是互相 P2P 通訊。

而是：

```text
Device A ─┐
          ├── Backend ── World ABC
Device B ─┘
```

---

## Pairing Flow

第一台裝置：

```text
Create World
↓
Backend 建立 World ABC
↓
產生短期 Pairing Code
824917
```

第二台裝置：

```text
Join Existing World
↓
輸入 824917
↓
Backend 驗證
↓
Device B → World ABC
```

Pairing Code 必須：

- 有效期限
- 使用後失效或受次數限制
- 不直接暴露 World ID

---

## 23. Device Preference

同一 World 的兩台裝置可以有不同顯示方式。

例如：

```text
Device A
primary_character = 小白

Device B
primary_character = 小雞毛

Device C
layout = group_overview
```

建議模型：

```text
DevicePreference
----------------
device_id
primary_character_id
layout
brightness
history_display_mode
```

因此：

```text
World State = 共享
Display Preference = 每台 Device 獨立
```

---

## 24. 自定義角色素材

角色行為在 Backend。

角色「長什麼樣」可以存在 ESP32 本地。

使用者連上裝置所在 Wi-Fi 後，可以打開 ESP32 本地管理頁：

```text
http://device.local
```

管理：

- 小白外觀
- 小雞毛外觀
- 上傳角色素材
- 預覽
- 刪除
- 恢復預設素材

---

## Local Asset Bundle

素材採：

```text
manifest
+
animation assets
```

概念：

```text
characters/
├─ char_a/
│  ├─ manifest.json
│  ├─ idle/
│  ├─ eating/
│  ├─ sleeping/
│  └─ reading/
│
└─ char_b/
```

Manifest：

```json
{
  "version": 1,
  "animations": {
    "idle": {
      "frames": ["idle_0", "idle_1"],
      "frame_ms": 500
    },
    "eating": {
      "frames": ["eat_0", "eat_1"],
      "frame_ms": 300
    }
  }
}
```

---

## Animation Fallback

自定義角色不必畫完所有事件。

例如 Backend：

```text
activity = shower
```

但使用者沒有提供：

```text
shower animation
```

Renderer：

```text
shower
  ↓ missing
idle animation
  +
activity overlay/icon
```

如此才能讓自定義角色的製作門檻合理。

---

## Display-Specific Asset Spec

目前顯示器解析度尚未在本規格中定案，因此不固定：

- Sprite resolution
- Canvas resolution
- 單張 frame bytes
- 最大 frame 數

但介面契約先固定：

```text
manifest
animation key
frame duration
fallback
asset size validation
```

選定實際螢幕後再建立：

```text
DeviceDisplayProfile
```

由 Profile 決定素材尺寸與容量限制。

---

## 25. 本地素材不等於 World 資料

自定義角色外觀 V1 預設：

```text
存在 Device 本地
```

因此同一 World 的兩台裝置可以：

```text
Device A
→ 自己的小白外觀

Device B
→ 另一套小白外觀
```

兩者仍然觀看完全相同的：

```text
World State
Events
History
```

這是刻意保留的能力。

未來若需要「共享 Skin」，再加入 Cloud Asset Sync。

---

## 26. Wi-Fi / Local Setup

V1 建議流程：

```text
首次開機
↓
ESP32 SoftAP / Setup Portal
↓
輸入家庭 Wi-Fi
↓
ESP32 連線
↓
之後可以透過 LAN 開啟 device.local
```

本地管理頁負責：

- Wi-Fi 設定
- Backend Pairing
- World 綁定
- 角色素材上傳
- Device Preference
- Firmware / Device Info

不讓 Local Web UI 修改 Simulation Rule。

生活規則一律屬於 Backend。

---

## 27. Backend 建議技術棧

V1：

```text
FastAPI
+
Supabase PostgreSQL
```

理由：

- Rule Engine / Simulation 用 Python 開發速度快。
- 日期、隨機事件、測試容易處理。
- PostgreSQL 很適合 Event / History / JSON config。
- 日後可增加 Web 管理介面而不改硬體協定。

ESP32：

```text
ESP-IDF
C/C++
```

---

## 28. Backend 概念資料模型

```text
worlds
------
id
name
timezone
simulation_version
simulation_start_date
created_at


characters
----------
id
world_id
appearance_key
display_name
profile_id


character_profiles
------------------
id
schedule_config
meal_config
leave_config
event_config


character_relationships
-----------------------
id
world_id
character_a_id
character_b_id
relationship_type
affinity
metadata


events
------
id
world_id
type
scene
start_at
end_at
priority
metadata
simulation_version


event_participants
------------------
event_id
character_id


devices
-------
id
world_id
device_token_hash
firmware_version
last_seen_at


device_preferences
------------------
device_id
primary_character_id
layout
brightness
config


pairing_codes
-------------
id
world_id
code_hash
expires_at
max_uses
used_count
```

實際 schema 可以在 Backend 開發階段再正規化。

---

## 29. 不該存進 Backend 的東西

V1 不需要把以下內容綁死在 World：

```text
ESP32 sprite binary
每一幀動畫
螢幕 brightness
Device-specific layout
本地 Wi-Fi 密碼
```

其中：

- Sprite / animation → Device Asset Store
- Brightness / layout → Device Preference
- Wi-Fi credential → Device local secure storage

---

## 30. 不該放進 ESP32 的東西

ESP32 不保存：

```text
完整世界歷史
角色請假算法
事件權重演算法
每日排程生成算法
14-day leave cycle
Calendar month leave logic
shared-event conflict resolver
```

Firmware 不應因為：

```text
新增一個角色事件
調整某事件概率
修改工作時間
```

就必須重新燒錄。

---

## 31. V1 核心不變量

以下視為架構約束：

### 1.

```text
Backend 是 World State 的唯一真相來源。
```

### 2.

```text
ESP32 不自行推演角色生活。
```

### 3.

```text
World 與 Device 是 1:N。
```

### 4.

```text
一台 Device 同一時間只顯示一個 World。
```

### 5.

```text
Character Appearance 與 Character Behavior 必須分離。
```

### 6.

```text
不同 World 的「同名角色」仍是不同 Character Instance。
```

### 7.

```text
角色數量是 1..N，不得在 Core / Schema / API 中 hard-code 為 2。
```

### 8.

```text
Shared / Group Event 是單一 Event + 2..N Participant。
```

### 9.

```text
History 存 Event Transition，不存每分鐘 Snapshot。
```

### 10.

```text
Simulation 必須可重現。
```

### 11.

```text
角色素材缺失時必須能 fallback，不要求所有自訂角色畫完全部動作。
```

### 12.

```text
Character 關係不得用 partner_id 等單一固定關係欄位建模。
```

---

## 32. V1 Scope

## Backend

- World
- 1..N Character Instance
- 官方預設先提供小白 / 小雞毛 Profile
- Character Profile
- Character Relationship 基礎模型
- 平日 Schedule
- 三餐
- Meal Skip
- Meal minimum interval
- 小白月請假
- 小雞毛 14-day leave cycle
- 工作 / 上學 temporary events
- 平日晚間 individual events
- Shared / Group events（2..N participants）
- Weekend leisure events
- Deterministic daily plan
- Event conflict resolution
- History
- Device pairing
- Display State API

## ESP32

- Wi-Fi onboarding
- HTTPS Client
- State polling
- JSON parsing
- Display rendering
- Local asset store
- Character asset upload
- Animation fallback
- History screen
- Device preference
- Pairing code flow

---

## 33. V1 明確不做

先不做：

- User account
- Social system
- 好感度
- 飢餓值 / 血量 / 數值養成
- P2P 裝置同步
- WebSocket / MQTT
- Cloud Skin Sync
- 任意腳本上傳
- 使用者自訂 Backend code
- AI 角色行為
- 天氣 API
- 真實 GPS / Location
- Push notification

避免第一版膨脹。

---

## 34. 尚未決定但不阻塞架構的設定

以下不能替需求方自行假定數值，因此保留為 Config：

### Meal

```text
breakfast_skip_probability = TBD
lunch_skip_probability = TBD
dinner_skip_probability = TBD
```

### 小雞毛

```text
leave_probability_per_14_day_cycle = TBD
```

### 小白

```text
leave_probability_per_month = TBD
```

### Temporary Events

```text
摸魚 weight / frequency = TBD
上課睡覺 weight / frequency = TBD
上課玩遊戲 weight / frequency = TBD
```

### Leisure Events

所有：

```text
weight
duration
cooldown
allowed_time
```

先做成 Profile Config，不寫死 Simulation Core。

---

## 35. 後續開發順序

## Phase 1 — Backend Simulation Prototype

先不碰硬體 UI。

完成：

```text
World
Character
Profile
Daily Plan Generator
Meal Generator
Leave Generator
Individual Event Generator
Shared Event Generator
Conflict Resolver
History
```

目標：

```text
給定 World + Date
→ 可以輸出完整兩人一天 Timeline
```

並且相同 Seed 必須得到相同 Timeline。

---

## Phase 2 — Display API

完成：

```text
GET current state
GET history
Device registration
World pairing
revision / ETag
```

---

## Phase 3 — ESP32 Thin Client

完成：

```text
Wi-Fi
HTTP
JSON
Renderer
Polling
```

先用官方 placeholder sprite。

---

## Phase 4 — Local Asset System

完成：

```text
device.local
asset upload
manifest validation
asset fallback
custom character rendering
```

---

## Phase 5 — Multi Device / Shared World

完成：

```text
Device A → World X
Device B → World X
```

验证：

- 兩台看到相同 Event。
- 兩台 History 一致。
- Display Preference 可以不同。
- 本地角色素材可以不同。
- 任一台離線不影響 World。

---

## 36. 最終產品概念

這個產品不是：

> 「兩台彼此同步的 ESP32 電子寵物。」

而是：

> **Worldpane 是一個持續存在於 Backend 的多人微型生活世界；一台或多台實體裝置，是觀看同一個世界的不同窗口。**

它不是以「一對角色」或「一對情侶」為架構前提。

```text
World = 共享真實
Characters = 世界裡的居民（1..N）
Character Profile = 個別人生規則
Character Relationship = 居民之間的關係
Shared / Group Event = 多人共同生活事件
Simulation Engine = 世界運行方式
Event History = 世界記憶
Device = 顯示窗口
Local Assets = 每個窗口自己的視覺呈現
```

產品命名：

```text
中文：窗間
英文：Worldpane
Repository：worldpane
Firmware：worldpane-firmware
Backend：worldpane-server
Simulation Core：worldpane-core
```

這是後續所有功能設計應維持的邊界。
