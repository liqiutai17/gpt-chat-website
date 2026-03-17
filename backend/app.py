from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import os
import requests

# ===== 正确加载 .env（项目根目录）=====
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

# ===== 数据模型 =====
class ChatRequest(BaseModel):
    message: str

# ===== 根路由 =====
@app.get("/")
async def root():
    return {"message": "GPT backend is running"}

# ===== GPT 函数 =====
def ask_gpt(message: str) -> str:
    response = client.responses.create(
        model="gpt-5.4",
        input=message
    )
    return response.output_text

# ===== 网页接口 =====
@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        reply = ask_gpt(req.message)
        return {"reply": reply}
    except Exception as e:
        print("CHAT ERROR:", e)
        return {"error": str(e)}

# ===== WhatsApp 验证 =====
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

    res = requests.post(url, headers=headers, json=payload)
    print("SEND:", res.status_code, res.text)

# ===== 接收 WhatsApp =====
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

        if msg["type"] == "text":
            user_text = msg["text"]["body"]
            reply = ask_gpt(user_text)
            send_whatsapp_text(from_number, reply)
            return {"status": "ok"}

        send_whatsapp_text(from_number, "目前只支持文字消息 😊")
        return {"status": "unsupported"}

    except Exception as e:
        print("ERROR:", e)
        return {"error": str(e)}