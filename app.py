"""
兆豐當舖 LINE Bot Webhook 服務 (深度實務優化版)
==============================
優化內容：
1. 全分類（汽機車/房屋/精品/黃金/3C）導入「規格化報價引導」，對話簡單直接。
2. 擴充「精品名牌包」意圖，並精準引導提供晶片/保卡資訊。
3. 新增「圖片處理 (ImageMessage)」功能，客人傳照片也能無縫引導。
4. 加入「轉人工」意圖，對接特殊狀況。
"""

import os
import opencc
from datetime import datetime, timedelta, timezone, time
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent,
    TextMessage,
    ImageMessage,       # 新增處理照片
    TextSendMessage,
    QuickReply,
    QuickReplyButton,
    MessageAction,
    LocationMessage,
    LocationSendMessage
)

# =============================================================================
# 初始化 Flask App 與 LINE SDK
# =============================================================================

app = Flask(__name__)

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")

if not LINE_CHANNEL_ACCESS_TOKEN or not LINE_CHANNEL_SECRET:
    print("⚠️ 警告：未設定 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_CHANNEL_SECRET 環境變數")

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

_s2t_converter = opencc.OpenCC('s2t')

def to_traditional(text: str) -> str:
    return _s2t_converter.convert(text)

# =============================================================================
# 當舖資訊常數
# =============================================================================

SHOP_NAME = "兆豐當舖"
SHOP_ADDRESS = "台南市永康區中正北路23號"
MONTHLY_RATE = "月息 2.5%"
LOAN_SPEED = "當天放款"

# =============================================================================
# 紀錄客人目前的對話狀態 (記憶體)
# key: user_id, value: "bot" (機器人模式) 或 "human" (人工模式)
# =============================================================================
USER_STATES = {}

# =============================================================================
# 營業時間判斷邏輯
# =============================================================================
def is_business_hours() -> bool:
    """判斷當下是否為台灣時間的營業時間 (週一至週五 08:30~19:30)"""
    # 取得台灣時間 (UTC+8)
    tw_tz = timezone(timedelta(hours=8))
    tw_now = datetime.now(tw_tz)

    # 判斷是否為週末 (0=週一, 1=週二, ... 4=週五, 5=週六, 6=週日)
    if tw_now.weekday() > 4:
        return False

    # 判斷時間是否在 08:30 ~ 19:30 之間
    current_time = tw_now.time()
    open_time = time(8, 30)
    close_time = time(19, 30)

    if open_time <= current_time <= close_time:
        return True
        
    return False

# =============================================================================
# 關鍵字意圖辨識 (擴充精品包與人工客服)
# =============================================================================

KEYWORD_INTENTS = {
    "human": ["轉人工", "客服", "專人", "真人", "接通", "人工", "專員", "專員服務"],
    "borrow": ["借款", "借錢", "貸款", "借", "週轉", "缺錢", "急用", "需要錢"],
    "gold": ["黃金", "金飾", "金子", "金條", "金項鍊", "金戒指", "鑽石", "鑽戒"],
    "luxury": ["手錶", "名錶", "勞力士", "rolex", "歐米茄", "包包", "名牌包", "精品", "香奈兒", "chanel", "lv", "愛馬仕", "hermes"],
    "vehicle": ["車", "汽車", "機車", "機車借款", "汽車借款", "重機", "貸款車"],
    "realestate": ["房子", "房屋", "土地", "房地產", "房貸", "房屋借款", "不動產", "一胎", "二胎"],
    "3c": ["手機", "電腦", "3c", "平板", "ipad", "iphone", "macbook", "筆電"],
    "rate": ["利率", "利息", "多少錢", "息", "費用", "月息", "年息"],
    "speed": ["多久", "放款", "速度", "快", "馬上"],
    "document": ["證件", "要帶什麼", "帶什麼", "準備什麼", "需要什麼"],
    "location": ["地址", "在哪", "怎麼去", "位置", "在哪裡", "店在哪", "怎麼走"],
    "greeting": ["你好", "嗨", "在嗎", "哈囉", "hi", "hello", "安安", "您好"],
}

def detect_intent(text: str) -> list[str]:
    text_traditional = to_traditional(text)
    text_lower_original = text.lower().strip()
    text_lower_traditional = text_traditional.lower().strip()
    detected = []

    for intent, keywords in KEYWORD_INTENTS.items():
        for kw in keywords:
            if kw.lower() in text_lower_original or kw.lower() in text_lower_traditional:
                detected.append(intent)
                break
    return detected

# =============================================================================
# 共用快速選單
# =============================================================================
def get_default_quick_reply():
    return QuickReply(items=[
        QuickReplyButton(action=MessageAction(label="黃金/鑽石", text="黃金估價")),
        QuickReplyButton(action=MessageAction(label="汽機車", text="汽機車估價")),
        QuickReplyButton(action=MessageAction(label="精品/名錶", text="精品估價")),
        QuickReplyButton(action=MessageAction(label="房屋/土地", text="房屋估價")),
        QuickReplyButton(action=MessageAction(label="3C 產品", text="3C估價")),
    ])

# =============================================================================
# 回覆訊息模板 (深度優化報價引導)
# =============================================================================

def get_greeting_message() -> list:
    return [
        TextSendMessage(
            text=(
                f"您好！感謝您聯繫{SHOP_NAME} 🙏\n\n"
                f"急需資金週轉嗎？我們提供合法、快速的現金救援！{MONTHLY_RATE}，{LOAN_SPEED}。\n\n"
                "請問您今天想諮詢哪一類的抵押估價呢？請直接點選下方按鈕，或留言告訴我們："
            ),
            quick_reply=get_default_quick_reply()
        )
    ]

def get_human_message() -> list:
    """處理轉人工客服需求 (區分營業時間)"""
    if not is_business_hours():
        return [
            TextSendMessage(
                text=(
                    "已為您切換至「專員留言模式」！📝\n\n"
                    f"目前為非營業時間（{SHOP_NAME}營業時間：週一至週五 08:30~19:30）。\n\n"
                    "機器人已暫停回覆，請您直接留下您的問題、或上傳估價物品的照片與細節。\n"
                    "專員會在上班後第一時間親自為您服務！\n\n"
                    "（若想繼續使用機器人查詢其他方案，請輸入「取消人工」）"
                )
            )
        ]
    else:
        return [
            TextSendMessage(
                text=(
                    "已收到您的需求！✅\n\n"
                    "機器人已暫停自動回覆，並為您通知專員。\n"
                    "請稍候，專員會盡快親自為您服務！\n\n"
                    "（若需重新啟用機器人自動導覽，請輸入「取消人工」）"
                )
            )
        ]
      
def get_borrow_message() -> list:
    return [
        TextSendMessage(
            text=(
                f"了解！{SHOP_NAME}提供各類抵押借款服務 💰\n\n"
                "請問您想抵押什麼物品呢？請點選下方選項，我們馬上為您做線上初步估價 👇"
            ),
            quick_reply=get_default_quick_reply()
        )
    ]

def get_gold_message() -> list:
    return [
        TextSendMessage(
            text=(
                "🏆 黃金/鑽石 估價服務\n\n"
                "💡 為了能快速為您線上初步估價，麻煩直接回覆以下資訊：\n\n"
                "1. 物品類型（例：金條、金項鍊、鑽戒）\n"
                "2. 大約重量（如知道幾兩或幾錢佳）\n"
                "3. 是否有原本的銀樓保單或證書\n\n"
                "留下資訊或直接傳送照片，專員會盡快依當日盤價為您報價！😊"
            )
        )
    ]

def get_luxury_message() -> list:
    return [
        TextSendMessage(
            text=(
                "👜 精品/名錶 估價服務\n\n"
                "💡 為了能快速為您線上初步估價，麻煩直接回覆以下資訊：\n\n"
                "1. 品牌與詳細型號（例：勞力士水鬼、香奈兒CF25）\n"
                "2. 外觀保存狀況（是否有明顯刮痕或磨損）\n"
                "3. 盒裝、保證書、購證是否齊全\n"
                "4. （包款專用）是否有原廠晶片卡/NFC標籤或雷射標\n\n"
                "留下資訊或直接傳送實體照片，專員會盡快為您評估最高額度！😊"
            )
        )
    ]

def get_vehicle_message() -> list:
    return [
        TextSendMessage(
            text=(
                "🚗 汽機車 估價服務 (免留車可)\n\n"
                "💡 為了能快速為您線上初步估價，麻煩直接回覆以下資訊：\n\n"
                "1. 廠牌、車型與出廠年份（例：2017年E300-銀色）\n"
                "2. 目前大約里程數\n"
                "3. 目前是否還有銀行或融資貸款（有無分期）\n\n"
                "留下資訊或傳送行照照片，專員會盡快為您評估最高額度！😊"
            )
        )
    ]

def get_realestate_message() -> list:
    return [
        TextSendMessage(
            text=(
                "🏠 房屋/土地 估價服務\n\n"
                "💡 為了能快速為您線上初步估價，麻煩直接回覆以下資訊：\n\n"
                "1. 座落區域（例：台南市永康區）\n"
                "2. 房屋類型與大約坪數（例：電梯大樓 35坪）\n"
                "3. 目前房屋是否有貸款？是一胎還是二胎？\n\n"
                "留下資訊，專員會馬上接手為您做專業評估，保密辦理！😊"
            )
        )
    ]

def get_3c_message() -> list:
    return [
        TextSendMessage(
            text=(
                "📱 3C 產品 估價服務\n\n"
                "💡 為了能快速為您線上初步估價，麻煩直接回覆以下資訊：\n\n"
                "1. 產品詳細型號與容量（例：iPhone 16 Pro 256G）\n"
                "2. 外觀是否有明顯刮痕或損傷\n"
                "3. 盒裝與原廠配件是否齊全\n"
                "4. （手機專用）電池健康度百分比\n\n"
                "留下資訊，專員會盡快為您評估最高額度！😊"
            )
        )
    ]

def get_rate_message() -> list:
    return [
        TextSendMessage(
            text=(
                f"💰 利率說明\n\n"
                f"{SHOP_NAME}的借款利率為 {MONTHLY_RATE}，合法合規。\n"
                "無隱藏費用，利息按月計算，提前還款不違約。\n\n"
                "想要先知道能借多少嗎？請點選下方選項讓我們為您估價 👇"
            ),
            quick_reply=get_default_quick_reply()
        )
    ]

def get_speed_message() -> list:
    return [
        TextSendMessage(
            text=(
                f"⚡ 放款速度\n\n"
                f"{SHOP_NAME}承諾 {LOAN_SPEED}！\n"
                "現場估價簽約後，馬上現金撥款 💵\n"
                "想要先線上估價嗎？請點選下方選項 👇"
            ),
            quick_reply=get_default_quick_reply()
        )
    ]

def get_document_message() -> list:
    return [
        TextSendMessage(
            text=(
                "📋 需攜帶證件說明\n\n"
                "基本必備：身份證 正本 ＋ 第二證件（駕照/健保卡）\n\n"
                "⚠️ 視抵押物品不同，需搭配對應證明（如車輛行照、房屋權狀、手錶保卡等）。"
            )
        )
    ]

def get_location_message() -> list:
    return [
        TextSendMessage(
            text=(
                f"📍 {SHOP_NAME} 店址\n\n"
                f"🏠 {SHOP_ADDRESS}\n\n"
                "⏰ 營業時間：週一至週五 08:30 ~ 19:30\n\n"
                "歡迎在營業時間內直接來店免費估價，不用預約！"
            ),
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="今天過去", text="今天過去")),
                QuickReplyButton(action=MessageAction(label="明天過去", text="明天過去")),
                QuickReplyButton(action=MessageAction(label="轉接專員", text="轉接專員")),
            ])
        ),
        LocationSendMessage(
            title=f"{SHOP_NAME}",
            address=SHOP_ADDRESS,
            latitude=23.0410,
            longitude=120.2340,
        ),
    ]
  
def get_visit_confirmation_message(text: str) -> list:
    """處理到店確認訊息 (區分營業時間)"""
    if not is_business_hours():
        return [
            TextSendMessage(
                text=(
                    f"收到您的訊息！🙏\n\n"
                    f"提醒您，目前為非營業時間，店面尚未開放喔！\n"
                    f"（{SHOP_NAME}營業時間：週一至週五 08:30 ~ 19:30）\n\n"
                    "如果您有急需估價的需求，您可以先點選「轉接專員」留下物品資訊，\n"
                    "我們會在看到訊息時第一時間為您處理！😊"
                ),
                # 附上快速按鈕，引導客人進入留言模式或繼續用機器人查詢
                quick_reply=QuickReply(items=[
                    QuickReplyButton(action=MessageAction(label="轉接專員 (留言)", text="轉接專員")),
                    QuickReplyButton(action=MessageAction(label="查看估價項目", text="借款諮詢")),
                ])
            )
        ]
    
    # 營業時間內的正常回覆
    return [
        TextSendMessage(
            text=(
                f"太好了！期待您的到來，請問您大概幾點抵達呢? 🎉\n\n"
                f"📍 {SHOP_ADDRESS}\n\n"
                "到店前提醒：請記得攜帶雙證件與抵押物品。我們到店見 😊"
            )
        )
    ]
  
def get_fallback_message() -> list:
    return [
        TextSendMessage(
            text=(
                f"收到您的訊息！😊\n\n"
                f"如果您需要估價，請直接點選下方對應的按鈕，或是點擊「轉人工客服」由專員親自為您服務 🙏"
            ),
            quick_reply=QuickReply(items=[
                QuickReplyButton(action=MessageAction(label="汽機車估價", text="汽機車估價")),
                QuickReplyButton(action=MessageAction(label="黃金精品估價", text="黃金估價")),
                QuickReplyButton(action=MessageAction(label="店址在哪", text="地址在哪")),
                QuickReplyButton(action=MessageAction(label="轉人工客服", text="轉接客服")),
            ])
        )
    ]

# =============================================================================
# 意圖 → 回覆訊息 對應表與優先級
# =============================================================================

INTENT_HANDLERS = {
    "human": get_human_message,
    "greeting": get_greeting_message,
    "borrow": get_borrow_message,
    "gold": get_gold_message,
    "luxury": get_luxury_message,
    "vehicle": get_vehicle_message,
    "realestate": get_realestate_message,
    "3c": get_3c_message,
    "rate": get_rate_message,
    "speed": get_speed_message,
    "document": get_document_message,
    "location": get_location_message,
}

# 具體分類優先於一般借款
INTENT_PRIORITY = [
    "human", "gold", "luxury", "vehicle", "realestate", "3c",
    "rate", "speed", "document", "location", "borrow", "greeting"
]

VISIT_KEYWORDS = ["今天過去", "明天過去", "過去", "過來", "到店", "拜訪", "過去看", "過來看"]

# =============================================================================
# 核心回覆邏輯
# =============================================================================

def generate_reply(text: str) -> list:
    text_traditional = to_traditional(text)

    for kw in VISIT_KEYWORDS:
        if kw in text or kw in text_traditional:
            return get_visit_confirmation_message(text)

    detected_intents = detect_intent(text)

    if not detected_intents:
        return get_fallback_message()

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
    signature = request.headers.get("X-Line-Signature", "")
    if not signature:
        abort(400)
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    except Exception as e:
        print(f"❌ 處理 Webhook 時發生錯誤：{e}")
        abort(500)
    return "OK"

@app.route("/", methods=["GET"])
def health_check():
    return f"{SHOP_NAME} LINE Bot 運行中 ✅"

# =============================================================================
# LINE 訊息事件處理
# =============================================================================

@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_text = event.message.text
    user_id = event.source.user_id

    # 1. 檢查客人是否想要主動「切回機器人」
    if user_text.strip() == "取消人工":
        USER_STATES[user_id] = "bot"
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="已為您切換回機器人自動回覆模式！🤖\n請問有什麼我可以幫忙的嗎？")
        )
        return

    # 2. 檢查客人目前是否處於「人工模式」
    if USER_STATES.get(user_id) == "human":
        # 如果是人工模式，機器人直接閉嘴，不執行任何回覆
        return 

    # 3. 偵測客人是否觸發了「轉人工」關鍵字
    detected_intents = detect_intent(user_text)
    if "human" in detected_intents:
        USER_STATES[user_id] = "human"  # 將該客人的狀態標記為人工模式

    # 4. 正常機器人回覆邏輯
    try:
        reply_messages = generate_reply(user_text)
        line_bot_api.reply_message(event.reply_token, reply_messages)
    except Exception as e:
        print(f"❌ 回覆文字訊息時發生錯誤：{e}")


@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    user_id = event.source.user_id

    # 如果已經是人工模式，客人傳照片時機器人也要閉嘴
    if USER_STATES.get(user_id) == "human":
        return

    # 如果是機器人模式，則引導客人補充資訊
    try:
        reply_messages = [
            TextSendMessage(
                text=(
                    "收到您的圖片囉！📸\n\n"
                    "為了加快報價速度，請幫我們文字補充一下這個物品的相關資訊（如型號、出廠年份、盒卡是否齊全等）。\n\n"
                    "若需專員直接評估，請輸入「轉人工」。"
                )
            )
        ]
        line_bot_api.reply_message(event.reply_token, reply_messages)
    except Exception as e:
        print(f"❌ 回覆圖片訊息時發生錯誤：{e}")

# =============================================================================
# 應用程式啟動
# =============================================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
