from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import os
import requests

# ===== 加载 .env =====
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ===== 创建 FastAPI =====
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 环境变量 =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "emoji_chat_verify")

print("OPENAI:", bool(OPENAI_API_KEY))
print("WA TOKEN:", bool(WHATSAPP_ACCESS_TOKEN))
print("WA ID:", bool(WHATSAPP_PHONE_NUMBER_ID))

# ===== OpenAI 客户端 =====
client = OpenAI(api_key=OPENAI_API_KEY)

# ===== 记录每个用户当前模式 =====
user_modes = {}

# ===== 数据模型 =====
class ChatRequest(BaseModel):
    message: str

# ===== 根路由 =====
@app.get("/")
async def root():
    return {"message": "GPT backend is running"}

# ===== baseline GPT =====
def ask_baseline_gpt(message: str) -> str:
    response = client.responses.create(
        model="gpt-5.4",
        input=message
    )
    return response.output_text

# ===== customized GPT =====
def ask_custom_gpt(message: str) -> str:
    response = client.responses.create(
        model="gpt-5.4",
        input=[
            {
                "role": "system",
                "content": (
                    "You are a friendly WhatsApp chat partner. "
                    "Reply naturally, briefly, and conversationally. "
                    "Use emojis selectively when they help express warmth, stance, alignment, or emotion. "
                    "Do not overuse emojis. "
                    "Sound human-like and natural in WhatsApp-style interaction."
                )
            },
            {
                "role": "user",
                "content": message
            }
        ]
    )
    return response.output_text

# ===== 网页接口（默认 baseline）=====
@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        reply = ask_baseline_gpt(req.message)
        return {"reply": reply}
    except Exception as e:
        print("CHAT ERROR:", e)
        return {"error": str(e)}

# ===== WhatsApp webhook 验证 =====
@app.get("/whatsapp/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    print("VERIFY:", mode, token, challenge)

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(challenge)

    return PlainTextResponse("Verification failed", status_code=403)

# ===== 发送 WhatsApp 消息 =====
def send_whatsapp_text(to_number: str, text: str):
    url = f"https://graph.facebook.com/v23.0/{WHATSAPP_PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": text},
    }

    res = requests.post(url, headers=headers, json=payload, timeout=30)
    print("SEND:", res.status_code, res.text)

# ===== 接收 WhatsApp 消息 =====
@app.post("/whatsapp/webhook")
async def receive_webhook(request: Request):
    data = await request.json()
    print("INCOMING:", data)

    try:
        value = data["entry"][0]["changes"][0]["value"]

        if "messages" not in value:
            return {"status": "no message"}

        msg = value["messages"][0]
        from_number = msg["from"]

        if msg["type"] != "text":
            send_whatsapp_text(from_number, "目前只支持文字消息 😊")
            return {"status": "unsupported"}

        user_text = msg["text"]["body"].strip()

        # ===== 切换到 baseline =====
        if user_text.lower() == "/baseline":
            user_modes[from_number] = "baseline"
            send_whatsapp_text(
                from_number,
                "已切换到 baseline 模式。现在你发来的消息都会进入 baseline 路线。"
            )
            return {"status": "mode set"}

        # ===== 切换到 custom =====
        if user_text.lower() == "/custom":
            user_modes[from_number] = "custom"
            send_whatsapp_text(
                from_number,
                "已切换到 customized 模式。现在你发来的消息都会进入 customized 路线。"
            )
            return {"status": "mode set"}

        # ===== 查看当前模式 =====
        if user_text.lower() == "/mode":
            current_mode = user_modes.get(from_number, "baseline")
            send_whatsapp_text(
                from_number,
                f"你当前的模式是：{current_mode}"
            )
            return {"status": "mode shown"}

        # ===== 帮助指令 =====
        if user_text.lower() == "/help":
            help_text = (
                "可用指令：\n"
                "/baseline 切换到 baseline 路线\n"
                "/custom 切换到 customized 路线\n"
                "/mode 查看当前模式\n"
                "/help 查看帮助"
            )
            send_whatsapp_text(from_number, help_text)
            return {"status": "help shown"}

        # ===== 默认模式：baseline =====
        if from_number not in user_modes:
            user_modes[from_number] = "baseline"

        current_mode = user_modes[from_number]
        print("CURRENT MODE:", from_number, current_mode)

        # ===== 按模式调用不同 GPT =====
        if current_mode == "baseline":
            reply = ask_baseline_gpt(user_text)
        else:
            reply = ask_custom_gpt(user_text)

        send_whatsapp_text(from_number, reply)
        return {"status": "ok"}

    except Exception as e:
        print("ERROR:", e)
        return {"error": str(e)}