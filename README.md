---
AIGC:
    Label: "1"
    ContentProducer: 001191110102MACQD9K64018705
    ProduceID: 4016952425064233_0-data_volume/7663408774010634531-files/所有对话/主对话/line_bot/README.md
    ReservedCode1: ""
    ContentPropagator: 001191110102MACQD9K64028705
    PropagateID: 4016952425064233#1784280653256
    ReservedCode2: ""
---
# 兆豐當舖 LINE Bot 自動回覆系統

> 透過 LINE Messaging API 自動回覆客人訊息，逐步引導到店諮詢的 Webhook 服務。

---

## 📋 專案簡介

兆豐當舖 LINE Bot 提供 24 小時自動回覆服務，根據客人訊息中的關鍵字辨識意圖，按照 SOP 四步驟引導：

1. **打招呼 + 快速響應** — 介紹業務，詢問需求
2. **了解需求** — 依物品類型介紹借款方案
3. **提供安心感** — 告知利率、放款速度、證件要求
4. **引導到店** — 發送地址，安排接待

---

## 📁 專案結構

```
line_bot/
├── app.py              # 主程式（Flask + LINE Webhook + 回覆邏輯）
├── requirements.txt    # Python 依賴清單
└── README.md           # 部署指南（本檔案）
```

---

## 🔧 本地開發設定

### 1. 安裝依賴

```bash
cd line_bot
pip install -r requirements.txt
```

### 2. 設定環境變數

```bash
export LINE_CHANNEL_ACCESS_TOKEN="你的_Channel_Access_Token"
export LINE_CHANNEL_SECRET="你的_Channel_Secret"
export PORT=5000
```

### 3. 啟動本地伺服器

```bash
python app.py
```

伺服器將在 `http://localhost:5000` 啟動。

### 4. 使用 ngrok 測試 Webhook

開發時需使用 ngrok 將本地伺服器暴露到公網：

```bash
ngrok http 5000
```

將 ngrok 產生的 URL 填入 LINE Developers Console 的 Webhook URL：

```
https://<your-ngrok-id>.ngrok-free.app/callback
```

---

## 🚀 部署指南

### 方案一：Railway 部署

[Railway](https://railway.app/) 提供簡單快速的雲端部署，免費方案即可使用。

#### 步驟：

1. **建立 Railway 帳號**
   - 前往 [railway.app](https://railway.app/) 註冊並登入

2. **建立新專案**
   - 點擊「New Project」→「Deploy from GitHub」或「Empty Project」

3. **上傳程式碼**
   - 如果使用 GitHub：將本專案推到 GitHub Repository，然後連接
   - 如果手動上傳：使用 Railway CLI
     ```bash
     npm install -g @railway/cli
     railway login
     railway init
     railway up
     ```

4. **設定環境變數**
   - 在 Railway Dashboard → 你的服務 → Variables 中新增：
     - `LINE_CHANNEL_ACCESS_TOKEN` = 你的 Channel Access Token
     - `LINE_CHANNEL_SECRET` = 你的 Channel Secret

5. **取得公網 URL**
   - Railway 會自動分配一個 `xxx.up.railway.app` 的網域
   - 在 Settings → Networking 中確認

6. **設定 LINE Webhook**
   - 前往 [LINE Developers Console](https://developers.line.biz/)
   - 選擇你的 Messaging API Channel
   - 在 Messaging API 頁籤設定 Webhook URL：
     ```
     https://<your-railway-app>.up.railway.app/callback
     ```
   - 開啟「Use webhook」選項

7. **驗證部署**
   - 在 LINE 上傳送訊息給你的官方帳號，確認有收到自動回覆

---

### 方案二：Render 部署

[Render](https://render.com/) 提供免費的 Web Service 部署方案。

#### 步驟：

1. **建立 Render 帳號**
   - 前往 [render.com](https://render.com/) 註冊並登入

2. **推送程式碼到 GitHub**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/<your-username>/<your-repo>.git
   git push -u origin main
   ```

3. **建立 Render Web Service**
   - 點擊「New」→「Web Service」
   - 連接你的 GitHub Repository

4. **設定建構與啟動命令**
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`

5. **設定環境變數**
   - 在 Environment 中新增：
     - `LINE_CHANNEL_ACCESS_TOKEN` = 你的 Channel Access Token
     - `LINE_CHANNEL_SECRET` = 你的 Channel Secret

6. **選擇免費方案**
   - Instance Type 選擇「Free」

7. **部署並取得 URL**
   - 點擊「Create Web Service」開始部署
   - 部署完成後會得到 `https://<your-app>.onrender.com` 的 URL

8. **設定 LINE Webhook**
   - 前往 [LINE Developers Console](https://developers.line.biz/)
   - 選擇你的 Messaging API Channel
   - 設定 Webhook URL：
     ```
     https://<your-app>.onrender.com/callback
     ```
   - 開啟「Use webhook」選項

9. **驗證部署**
   - 在 LINE 上傳送訊息給你的官方帳號，確認自動回覆正常

---

## ⚠️ 注意事項

1. **免費方案限制**
   - Railway 免費方案有每月用量限制，適合測試與低流量使用
   - Render 免費方案會在 15 分鐘無流量後休眠，首次請求需等待約 30 秒冷啟動

2. **安全性**
   - 請勿將 Channel Access Token 和 Channel Secret 硬編碼在程式中
   - 務必透過環境變數設定敏感資訊
   - LINE 會透過 X-Line-Signature 標頭驗證請求真偽

3. **LINE 官方帳號設定**
   - 需在 LINE Developers Console 建立 Provider 和 Messaging API Channel
   - 開啟「Use webhook」功能
   - 關閉自動回覆訊息（避免與本 Bot 衝突）

4. **座標精度**
   - `app.py` 中的經緯度座標為約略值，建議使用 Google Maps 取得精確座標後更新

---

## 🔑 LINE 官方帳號設定步驟

1. 前往 [LINE Developers Console](https://developers.line.biz/)
2. 建立 Provider（或選擇已有的）
3. 建立 Messaging API Channel
4. 在 Channel 設定頁面取得：
   - Channel Secret（基本設定頁籤）
   - Channel Access Token（Messaging API 頁籤，點擊 Issue）
5. 設定 Webhook URL 為你的伺服器位址 + `/callback`
6. 開啟「Use webhook」
7. 在「LINE Official Account Manager」中關閉自動回覆與全域問候訊息

---

## 📊 關鍵字辨識清單

| 意圖 | 觸發關鍵字 |
|------|-----------|
| 借款諮詢 | 借款、借錢、貸款、週轉、缺錢、急用 |
| 黃金抵押 | 黃金、金飾、金子、金條、金項鍊 |
| 名錶抵押 | 手錶、名錶、勞力士、rolex、歐米茄 |
| 車輛抵押 | 車、汽車、機車、重機 |
| 房屋抵押 | 房子、房屋、土地、房地產、不動產 |
| 3C 產品 | 手機、電腦、3C、平板、iPhone |
| 利率詢問 | 利率、利息、多少錢、月息 |
| 放款速度 | 多久、放款、速度、馬上 |
| 證件詢問 | 證件、要帶什麼、準備什麼 |
| 地址詢問 | 地址、在哪、怎麼去、導航 |
| 打招呼 | 你好、嗨、在嗎、哈囉、hi |

---

## 🛠 擴展建議

- **加入對話狀態追蹤**：使用 Redis 或資料庫記錄每個使用者的對話進度，實現更精準的多輪對話
- **串接 LLM**：整合 OpenAI / Claude 等 LLM 處理更複雜的對話場景
- **加入圖片辨識**：允許客人上傳物品照片，自動辨識類型並給出估價範圍
- **加入預約功能**：讓客人可直接透過 LINE 預約到店時間
- **資料分析**：記錄常見詢問類型，優化回覆策略

---

## 📄 授權

本專案為兆豐當舖內部使用，未經授權不得外流。

---

> 本内容由 Coze AI 生成，请遵循相关法律法规及《人工智能生成合成内容标识办法》使用与传播。
