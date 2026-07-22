"""
兆豐當舖 LINE Bot Webhook 服務
==============================
使用 Python + Flask + LINE Messaging API SDK 實現自動回覆功能，
根據客人訊息中的關鍵字判斷意圖，逐步引導客人到店諮詢。

環境變數：
  - LINE_CHANNEL_ACCESS_TOKEN: LINE Messaging API Channel Access Token
  - LINE_CHANNEL_SECRET: LINE Messaging API Channel Secret
  - PORT: 服務監聽埠（預設 5000）
"""

import os
import datetime  # 新增這行：用來處理時間
import time
from google import genai
from google.genai import types
import re
import opencc
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    TextSendMessage,
    QuickReply,
    QuickReplyButton,
    MessageAction,
    LocationMessage,
    LocationSendMessage,
    FlexSendMessage,
    BubbleContainer,
    BoxComponent,
    TextComponent,
    SeparatorComponent,
    ButtonComponent,
    Action,
    IconComponent,
)

# ==========================================
# 🌟 請把字典和 Gemini 設定加在這裡！
# ==========================================

# 新增這個用來記憶客人狀態的字典
user_status = {} 
user_chats = {}

# 設定 Gemini API 金鑰
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# 設定 Gemini 模型與人設
SYSTEM_INSTRUCTION = """你是「台南」兆豐當舖的專屬客服。請用親切專業的語氣回答客人的問題。我們主要是為了約束客人還款與說明方案，所以回覆請保持直接、簡潔扼要，不用這麼詳細或長篇大論。

【重要回覆規範】
1. 「只有」當客人明確詢問「地址、在哪裡、電話、營業時間」時，才提供下方的營業資訊。
2. 如果客人「沒有」主動問，請絕對不要在對話中夾帶地址或電話，保持對話自然。
3. 若被問到地址，我們只有台南這一家店，嚴禁回答台中或其他縣市的分店。

* 店名：兆豐當舖
* 電話：06-243-3838
* 地址：台南市永康區中正北路23號
* 營業時間：週一到週五 早上 08:30 ～ 晚上 19:30 (線上客服24H)
"""

# =============================================================================
# 初始化 Flask App 與 LINE SDK
# =============================================================================

app = Flask(__name__)

# 從環境變數讀取 LINE 憑證
LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    print("⚠️ 警告：未設定 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_CHANNEL_SECRET 環境變數")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# =============================================================================
# 簡繁中文轉換器
# =============================================================================

# 初始化簡體→繁體轉換器（用於將使用者輸入統一轉為繁體再做關鍵字匹配）
_s2t_converter = opencc.OpenCC('s2t')


def to_traditional(text: str) -> str:
    """
    將簡體中文轉換為繁體中文。
    若輸入本身已是繁體則原樣回傳，不影響非中文字元。

    Args:
        text: 原始文字

    Returns:
        繁體中文文字
    """
    return _s2t_converter.convert(text)


# =============================================================================
# 當舖資訊常數
# =============================================================================

SHOP_NAME = "兆豐當舖"
SHOP_ADDRESS = "台南市永康區中正北路23號"
SHOP_GOOGLE_MAPS_URL = "https://maps.google.com/?q=台南市永康區中正北路23號"
MONTHLY_RATE = "月息 2.5%"
LOAN_SPEED = "當天放款"

# =============================================================================
# 關鍵字意圖辨識
# =============================================================================

# 定義關鍵字群組與對應意圖
KEYWORD_INTENTS = {
    # 借款意圖（繁體 + 簡體補充）
    "borrow": ["借款", "借錢", "貸款", "借", "週轉", "缺錢", "急用", "需要錢",
               "借钱", "贷款", "周转", "缺钱", "需要钱"],
    # 黃金抵押（繁體 + 簡體補充）
    "gold": ["黃金", "金飾", "金子", "金條", "金項鍊", "金戒指", "金手鐲",
             "黄金", "金饰", "金条", "金项链", "金手镯"],
    # 名錶抵押（繁體 + 簡體補充）
    "watch": ["手錶", "名錶", "勞力士", "rolex", "歐米茄", "omega", "手环", "錶",
              "手表", "名表", "表"],
    # 車輛抵押（繁體 + 簡體補充）
    "vehicle": ["車", "汽車", "機車", "機車借款", "汽車借款", "重機", "機車貸款", "汽車貸款",
                "车", "汽车", "机车", "机车借款", "汽车借款", "重机", "机车贷款", "汽车贷款"],
    # 房產抵押（繁體 + 簡體補充）
    "realestate": ["房子", "房屋", "土地", "房地產", "房貸", "房屋借款", "不動產",
                   "房地产", "房贷", "不动产"],
    # 3C 產品抵押（繁體 + 簡體補充）
    "3c": ["手機", "電腦", "3c", "平板", "ipad", "iphone", "macbook", "筆電", "3C",
           "手机", "电脑", "笔电"],
    # 利率詢問（繁體 + 簡體補充）
    "rate": ["利率", "利息", "多少錢", "息", "費用", "月息", "年息",
             "多少钱", "费用"],
    # 放款速度（繁體 + 簡體補充）
    "speed": ["多久", "放款", "速度", "快", "馬上", "即時", "何時",
              "即时"],
    # 證件詢問（繁體 + 簡體補充）
    "document": ["證件", "要帶什麼", "帶什麼", "準備什麼", "需要什麼", "證件", "文件",
                 "证件", "要带什么", "带什么", "准备什么", "需要什么"],
    # 地址詢問（繁體 + 簡體補充）
    "location": ["地址", "在哪", "怎麼去", "位置", "在哪裡", "店在哪", "怎麼走", "導航",
                 "怎么去", "在哪里", "怎么走"],
    # 打招呼（繁體 + 簡體補充）
    "greeting": ["你好", "嗨", "在嗎", "哈囉", "hi", "hello", "安安", "您好",
                 "在吗", "哈喽"],
}


def detect_intent(text: str) -> list[str]:
    """
    根據訊息文字偵測使用者意圖，回傳意圖清單（可多個）。
    先將簡體中文轉為繁體，再做關鍵字匹配，確保簡體輸入也能正確辨識。
    同時對原始文字與轉換後文字做匹配，避免繁體異體字（如「裏」vs「裡」）漏配。

    Args:
        text: 使用者傳入的文字訊息

    Returns:
        偵測到的意圖清單，例如 ["gold", "rate"]
    """
    # 簡體→繁體轉換，統一用繁體做關鍵字匹配
    text_traditional = to_traditional(text)
    # 同時用原始文字與轉換後文字匹配，確保簡體關鍵字與繁體異體字都能命中
    text_lower_original = text.lower().strip()
    text_lower_traditional = text_traditional.lower().strip()
    detected = []

    for intent, keywords in KEYWORD_INTENTS.items():
        for kw in keywords:
            if kw.lower() in text_lower_original or kw.lower() in text_lower_traditional:
                detected.append(intent)
                break  # 同一意圖命中一次即可，避免重複

    return detected


# =============================================================================
# 回覆訊息模板
# =============================================================================

def get_greeting_message() -> list:
    """
    Step 1：打招呼 + 快速響應
    首次對話時介紹業務並詢問需求。
    """
    messages = [
        TextSendMessage(
            text=(
                f"您好！感謝您聯繫{SHOP_NAME}🙏\n\n"
                "請問您目前需要借款服務嗎？\n"
                "方便告訴我您想抵押的物品類型嗎？\n\n"
                "黃金、名錶、汽機車、房屋、3C 產品我們都收！"
            ),
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="黃金借款", text="黃金借款")),
                QuickReplyButton(action=MessageAction(label="名錶借款", text="名錶借款")),
                QuickReplyButton(action=MessageAction(label="汽機車借款", text="汽機車借款")),
                QuickReplyButton(action=MessageAction(label="房屋借款", text="房屋借款")),
                QuickReplyButton(action=MessageAction(label="3C 產品借款", text="3C 產品借款")),
            ])
        )
    ]
    return messages


def get_borrow_message() -> list:
    """
    Step 2：了解需求 — 借款諮詢流程
    """
    messages = [
        TextSendMessage(
            text=(
                f"了解！{SHOP_NAME}提供各類抵押借款服務 💰\n\n"
                f"✅ {MONTHLY_RATE}，合法合規\n"
                f"✅ {LOAN_SPEED}，免聯徵\n"
                f"✅ 全程透明，絕無隱藏費用\n\n"
                "請問您想抵押什麼物品呢？\n"
                "我來為您說明詳細方案 👇"
            ),
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="黃金", text="黃金借款")),
                QuickReplyButton(action=MessageAction(label="名錶", text="名錶借款")),
                QuickReplyButton(action=MessageAction(label="汽機車", text="汽機車借款")),
                QuickReplyButton(action=MessageAction(label="房屋", text="房屋借款")),
                QuickReplyButton(action=MessageAction(label="3C 產品", text="3C 產品借款")),
            ])
        )
    ]
    return messages


def get_gold_message() -> list:
    """Step 2：黃金抵押借款方案"""
    messages = [
        TextSendMessage(
            text=(
                "🏆 黃金抵押借款方案\n\n"
                "我們接受各類黃金飾品抵押：\n"
                "• 金條、金飾、金項鍊、金戒指等\n"
                "• 依當日國際金價計算，估價公道\n"
                f"• {MONTHLY_RATE}，{LOAN_SPEED}\n"
                "• 免聯徵，不影響信用評分\n\n"
                "黃金抵押是最受歡迎的借款方式，\n"
                "金價高，可借金額也相對較高哦！\n\n"
                "歡迎攜帶黃金到店免費估價 😊"
            )
        )
    ]
    return messages


def get_watch_message() -> list:
    """Step 2：名錶抵押借款方案"""
    messages = [
        TextSendMessage(
            text=(
                "⌚ 名錶抵押借款方案\n\n"
                "我們接受各類名錶抵押：\n"
                "• 勞力士、歐米茄、百達翡麗等\n"
                "• 專業鑑定，估價實在\n"
                f"• {MONTHLY_RATE}，{LOAN_SPEED}\n"
                "• 免聯徵，不影響信用評分\n\n"
                "名錶保值性高，借款額度優！\n"
                "歡迎攜帶名錶到店免費鑑定估價 😊"
            )
        )
    ]
    return messages


def get_vehicle_message() -> list:
    """Step 2：汽機車抵押借款方案"""
    messages = [
        TextSendMessage(
            text=(
                "🚗 汽機車抵押借款方案\n\n"
                "我們接受各類車輛抵押：\n"
                "• 汽車、機車、重機均可\n"
                "• 免留車，車照開照用\n"
                f"• {MONTHLY_RATE}，{LOAN_SPEED}\n"
                "• 免聯徵，不影響信用評分\n\n"
                "汽機車借款流程簡便，\n"
                "帶雙證件 + 行照 + 牌照登記書即可辦理！\n\n"
                "歡迎到店諮詢 😊"
            )
        )
    ]
    return messages


def get_realestate_message() -> list:
    """Step 2：房屋抵押借款方案"""
    messages = [
        TextSendMessage(
            text=(
                "🏠 房屋抵押借款方案\n\n"
                "我們提供房屋/不動產抵押借款：\n"
                "• 房屋、土地、不動產均可\n"
                "• 額度高，利率優\n"
                f"• {MONTHLY_RATE}，{LOAN_SPEED}\n"
                "• 免聯徵，不影響信用評分\n\n"
                "房屋借款需準備：\n"
                "雙證件 + 建物/土地權狀 + 印章\n\n"
                "歡迎到店諮詢，我們為您量身規劃 😊"
            )
        )
    ]
    return messages


def get_3c_message() -> list:
    """Step 2：3C 產品抵押借款方案"""
    messages = [
        TextSendMessage(
            text=(
                "📱 3C 產品抵押借款方案\n\n"
                "我們接受各類 3C 產品抵押：\n"
                "• iPhone、iPad、MacBook\n"
                "• 筆電、桌電、相機等\n"
                f"• {MONTHLY_RATE}，{LOAN_SPEED}\n"
                "• 免聯徵，不影響信用評分\n\n"
                "歡迎攜帶 3C 產品到店估價 😊"
            )
        )
    ]
    return messages


def get_rate_message() -> list:
    """Step 3：利率說明"""
    messages = [
        TextSendMessage(
            text=(
                f"💰 利率說明\n\n"
                f"{SHOP_NAME}的借款利率為 {MONTHLY_RATE}\n\n"
                "📌 重點提醒：\n"
                "• 月息 2.5%，合法合規\n"
                "• 無手續費、無隱藏費用\n"
                "• 利息按月計算，提前還款不違約\n"
                "• 全程透明，依法開立當票\n\n"
                "有任何疑問，歡迎直接到店諮詢！\n"
                "我們會詳細為您說明 😊"
            )
        )
    ]
    return messages


def get_speed_message() -> list:
    """Step 3：放款速度說明"""
    messages = [
        TextSendMessage(
            text=(
                f"⚡ 放款速度\n\n"
                f"{SHOP_NAME}承諾 {LOAN_SPEED}！\n\n"
                "📋 辦理流程：\n"
                "1️⃣ 到店出示證件與抵押物品\n"
                "2️⃣ 現場專業估價\n"
                "3️⃣ 雙方確認金額與條件\n"
                "4️⃣ 簽約開立當票\n"
                "5️⃣ 現場撥款，馬上拿現金 💵\n\n"
                "全程約 30 分鐘即可完成！\n"
                "歡迎到店辦理 😊"
            )
        )
    ]
    return messages


def get_document_message() -> list:
    """Step 3：證件說明 — 提供安心感"""
    messages = [
        TextSendMessage(
            text=(
                "📋 需攜帶證件說明\n\n"
                "基本證件（必備）：\n"
                "• 身份證 正本\n"
                "• 第二證件（駕照 或 健保卡）\n\n"
                "依抵押物品不同，另需準備：\n"
                "🏆 黃金 → 黃金相關證明（如有）\n"
                "⌚ 名錶 → 錶盒、保證書（如有）\n"
                "🚗 汽機車 → 行照 + 牌照登記書\n"
                "🏠 房屋 → 建物/土地權狀\n"
                "📱 3C → 原廠包裝、發票（如有）\n\n"
                "另外建議攜帶：\n"
                "• 印章（或可用簽名）\n"
                "• 存摺（如需匯款）\n\n"
                "⚠️ 全程透明、合法合規，依法開立當票，請放心！"
            )
        )
    ]
    return messages


def get_location_message() -> list:
    """Step 4：引導到店 — 發送地址與地圖"""
    messages = [
        TextSendMessage(
            text=(
                f"📍 {SHOP_NAME} 店址\n\n"
                f"🏠 {SHOP_ADDRESS}\n\n"
                "營業時間：請來電確認\n"
                "歡迎直接來店諮詢，不用預約！\n\n"
                "請問您預計什麼時候過來呢？\n"
                "我們好為您安排接待 😊"
            ),
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="今天過去", text="今天過去")),
                QuickReplyButton(action=MessageAction(label="明天過去", text="明天過去")),
                QuickReplyButton(action=MessageAction(label="先詢問利率", text="利率多少")),
                QuickReplyButton(action=MessageAction(label="要帶什麼證件", text="要帶什麼證件")),
            ])
        ),
        LocationSendMessage(
            title=f"{SHOP_NAME}",
            address=SHOP_ADDRESS,
            latitude=23.0410,   # 台南市永康區中正北路23號 約略座標
            longitude=120.2340,
        ),
    ]
    return messages


def get_visit_confirmation_message(text: str) -> list:
    """Step 4：確認到店時間"""
    messages = [
        TextSendMessage(
            text=(
                f"太好了！期待您的到來 🎉\n\n"
                f"📍 {SHOP_ADDRESS}\n\n"
                "到店前提醒：\n"
                "✅ 攜帶雙證件（身份證 + 駕照/健保卡）\n"
                "✅ 攜帶抵押物品\n"
                "✅ 攜帶印章及存摺（如需匯款）\n\n"
                "如有任何問題，歡迎隨時發訊息詢問！\n"
                "我們到店見 😊"
            )
        )
    ]
    return messages


def get_fallback_message() -> list:
    """預設回覆：當無法辨識意圖時"""
    messages = [
        TextSendMessage(
            text=(
                f"感謝您的訊息！😊\n\n"
                f"{SHOP_NAME}提供各類抵押借款服務，\n"
                "黃金、名錶、汽機車、房屋、3C 產品我們都收！\n\n"
                "請問您想了解哪方面呢？\n"
                "您可以直接輸入關鍵字，例如：\n"
                "「黃金借款」「利率多少」「地址在哪」\n\n"
                "或到店直接諮詢最快速 🙏"
            ),
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="借款諮詢", text="借款諮詢")),
                QuickReplyButton(action=MessageAction(label="利率多少", text="利率多少")),
                QuickReplyButton(action=MessageAction(label="要帶什麼證件", text="要帶什麼證件")),
                QuickReplyButton(action=MessageAction(label="店址在哪", text="地址在哪")),
            ])
        )
    ]
    return messages


# =============================================================================
# 意圖 → 回覆訊息 對應表
# =============================================================================

INTENT_HANDLERS = {
    "greeting": get_greeting_message,
    "borrow": get_borrow_message,
    "gold": get_gold_message,
    "watch": get_watch_message,
    "vehicle": get_vehicle_message,
    "realestate": get_realestate_message,
    "3c": get_3c_message,
    "rate": get_rate_message,
    "speed": get_speed_message,
    "document": get_document_message,
    "location": get_location_message,
}

# 意圖優先級（排在前面的優先回覆，避免一次回覆太多訊息）
INTENT_PRIORITY = ["borrow", "gold", "watch", "vehicle", "realestate", "3c",
                   "rate", "speed", "document", "location", "greeting"]

# 到店相關關鍵字（繁體 + 簡體補充）
VISIT_KEYWORDS = ["今天過去", "明天過去", "過去", "過來", "到店", "拜訪", "過去看", "過來看",
                  "今天过去", "明天过去", "过去", "过来", "到店", "拜访", "过去看", "过来看"]


# =============================================================================
# 核心回覆邏輯
# =============================================================================

def generate_reply(text: str) -> list:
    """
    根據使用者訊息生成回覆訊息清單。

    處理邏輯：
    1. 先檢查是否為到店確認訊息
    2. 進行關鍵字意圖辨識
    3. 按優先級選擇最相關的回覆
    4. 無法辨識時回傳預設訊息

    Args:
        text: 使用者傳入的文字訊息

    Returns:
        LINE Message 物件清單
    """
    # 簡體→繁體轉換，確保簡體輸入也能匹配到店關鍵字
    text_traditional = to_traditional(text)

    # 檢查是否為到店確認（同時匹配原始文字與轉換後文字）
    for kw in VISIT_KEYWORDS:
        if kw in text or kw in text_traditional:
            return get_visit_confirmation_message(text)

    # 意圖辨識
    detected_intents = detect_intent(text)

    if not detected_intents:
        return get_fallback_message()

    # 按優先級排序，取最高優先級的意圖回覆
    for intent in INTENT_PRIORITY:
        if intent in detected_intents:
            handler_func = INTENT_HANDLERS.get(intent)
            if handler_func:
                return handler_func()

    return get_fallback_message()


# =============================================================================
# Webhook 路由
# =============================================================================

@app.route("/callback", methods=["POST"])
def callback():
    """
    LINE Webhook 回調端點
    接收 LINE 平台轉發的使用者訊息，驗證簽章後交由 handler 處理。
    """
    # 取得 X-Line-Signature 標頭，用於驗證請求
    signature = request.headers.get("X-Line-Signature", "")
    if not signature:
        print("⚠️ 缺少 X-Line-Signature 標頭")
        abort(400)

    # 取得請求體
    body = request.get_data(as_text=True)

    # 記錄接收到的訊息（開發時使用，正式環境可移除）
    print(f"📨 收到 Webhook 請求：{body[:200]}")

    # 驗證簽章
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("❌ 簽章驗證失敗")
        abort(400)
    except Exception as e:
        print(f"❌ 處理 Webhook 時發生錯誤：{e}")
        abort(500)

    return "OK"


@app.route("/", methods=["GET"])
def health_check():
    """健康檢查端點"""
    return f"{SHOP_NAME} LINE Bot 運行中 ✅"


# =============================================================================
# LINE 訊息事件處理
# =============================================================================

# 建立新版 Gemini 客戶端與人設
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
SYSTEM_INSTRUCTION = """你是「台南」兆豐當舖的專屬客服。請用親切專業的語氣回答客人的問題。我們主要是為了約束客人還款與說明方案，所以回覆請保持直接、簡潔扼要，不用這麼詳細或長篇大論。

【重要回覆規範】
1. 「只有」當客人明確詢問「地址、在哪裡、電話、營業時間」時，才提供下方的營業資訊。
2. 如果客人「沒有」主動問，請絕對不要在對話中夾帶地址或電話，保持對話自然。
3. 若被問到地址，我們只有台南這一家店，嚴禁回答台中或其他縣市的分店。

* 店名：兆豐當舖
* 電話：06-243-3838
* 地址：台南市永康區中正北路23號
* 營業時間：週一到週五 早上 08:30 ～ 晚上 19:30 (線上客服24H)
"""

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id         
    user_message = event.message.text.strip() 
    
    # 取得當下時間的秒數
    current_time = time.time()
    
    # ==========================================
    # 狀況 1：客人主動喚醒 AI
    # ==========================================
    if user_message == "智能客服" or user_message == "切換AI":
        user_status[user_id] = {"mode": "ai", "time": current_time}
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="智能客服已重新上線！請問還有什麼我可以幫忙的嗎？")
        )
        return

    # ==========================================
    # 狀況 2：客人要求轉人工 (多重關鍵字版)
    # ==========================================
    human_keywords = ["轉人工", "呼叫人工", "找客服", "真人", "專員"]
    
    if any(keyword in user_message for keyword in human_keywords):
        tz = datetime.timezone(datetime.timedelta(hours=8))
        now = datetime.datetime.now(tz)
        current_hour = now.hour

        if 0 <= current_hour < 9:
            reply_text = "現在是休息時間，目前無人工客服在線。請您留下聯絡方式或問題，我們會在上班後第一時間回覆您！"
        else:
            reply_text = "請稍後，已為您通知專員，約 5 分鐘內將有專員為您服務！\n(若專員服務完畢，需重新喚醒智能客服，請輸入「智能客服」)"
        
        user_status[user_id] = {
            "mode": "human",
            "time": current_time
        } 
        
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
        return

    # ==========================================
    # 狀況 3：檢查是否在人工模式，以及是否超過 30 分鐘 (1800秒)
    # ==========================================
    user_info = user_status.get(user_id)
    if user_info and user_info.get("mode") == "human":
        last_time = user_info.get("time", 0)
        
        if (current_time - last_time) > 1800:
            user_status[user_id] = {"mode": "ai", "time": current_time}
        else:
            return

# ==========================================
    # 狀況 4：交給 Gemini AI 處理 (三天自動失憶完整版)
    # ==========================================
    try:
        # 取得當下時間
        current_time = time.time()
        
        # 檢查客人是不是已經有聊天室了
        if user_id in user_chats:
            # 拿出上次講話的時間
            last_active_time = user_chats[user_id]['last_time']
            
            # 3天 = 3天 * 24小時 * 60分 * 60秒 = 259200 秒
            # 如果距離上次講話超過 3 天，就把舊記憶刪掉
            if current_time - last_active_time > 259200:
                del user_chats[user_id]
        
        # 如果這個客人還沒有聊天室，或是剛剛(因為超過三天)被刪除了，就建一個新的
        if user_id not in user_chats:
            user_chats[user_id] = {
                'chat': client.chats.create(
                    model='gemini-3.6-flash',
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION
                    )
                ),
                'last_time': current_time # 記錄這次建立的時間
            }
        
        # 更新最後講話的時間，並拿出專屬聊天室
        user_chats[user_id]['last_time'] = current_time
        chat_session = user_chats[user_id]['chat']
        
        # 把客人的新訊息傳進聊天室
        response = chat_session.send_message(user_message)
        reply_text = response.text

    # 👇 就是漏了下面這段，它是用來接住當機並回覆客人的防護網！
    except Exception as e:
        print(f"Error: {e}")
        reply_text = "不好意思，客服系統忙碌中，請稍後再試。"

    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text))

@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    """
    處理位置訊息事件
    當使用者傳送位置時，引導到店。
    """
    print(f"📍 使用者傳送了位置訊息")

    try:
        reply_messages = [
            TextSendMessage(
                text=(
                    f"感謝您傳送位置！📍\n\n"
                    f"{SHOP_NAME}位於：\n{SHOP_ADDRESS}\n\n"
                    "歡迎直接來店諮詢，\n"
                    "我們提供免費估價服務！😊"
                )
            )
        ]
        line_bot_api.reply_message(
            event.reply_token,
            reply_messages
        )
    except Exception as e:
        print(f"❌ 回覆位置訊息時發生錯誤：{e}")


# =============================================================================
# 應用程式啟動
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 {SHOP_NAME} LINE Bot 啟動中...")
    print(f"📡 監聽埠：{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
