from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import os
import requests

# ===== Load .env from project root =====
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ===== Create FastAPI app =====
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== Environment variables =====
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "emoji_chat_verify")

print("OPENAI:", bool(OPENAI_API_KEY))
print("WA TOKEN:", bool(WHATSAPP_ACCESS_TOKEN))
print("WA ID:", bool(WHATSAPP_PHONE_NUMBER_ID))

# ===== OpenAI client =====
client = OpenAI(api_key=OPENAI_API_KEY)

# ===== Store each user's current mode =====
user_modes = {}

# ===== Request model for web chat =====
class ChatRequest(BaseModel):
    message: str

# ===== Root route =====
@app.get("/")
async def root():
    return {"message": "GPT backend is running"}

# ===== Baseline GPT =====
def ask_baseline_gpt(message: str) -> str:
    response = client.responses.create(
        model="gpt-5.4",
        input=message
    )
    return response.output_text

# ===== Customized GPT =====
def ask_custom_gpt(message: str) -> str:
    response = client.responses.create(
        model="gpt-5.4",
        input=[
            {
                "role": "system",
                "content": (
                    "You are a friendly WhatsApp chat partner. "
                    "Reply naturally, briefly, and conversationally in English. "
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

# ===== Web route (defaults to baseline) =====
@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        reply = ask_baseline_gpt(req.message)
        return {"reply": reply}
    except Exception as e:
        print("CHAT ERROR:", e)
        return {"error": str(e)}

# ===== WhatsApp webhook verification =====
@app.get("/whatsapp/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    print("VERIFY:", mode, token, challenge)

    if mode == "subscribe" and token == WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(challenge)

    return PlainTextResponse("Verification failed", status_code=403)

# ===== Send WhatsApp text message =====
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

# ===== Receive WhatsApp messages =====
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
            send_whatsapp_text(from_number, "Currently, only text messages are supported 😊")
            return {"status": "unsupported"}

        user_text = msg["text"]["body"].strip()

        # ===== Switch to baseline =====
        if user_text.lower() == "/baseline":
            user_modes[from_number] = "baseline"
            send_whatsapp_text(
                from_number,
                "Switched to baseline mode. Your messages will now be handled by the baseline system."
            )
            return {"status": "mode set"}

        # ===== Switch to custom =====
        if user_text.lower() == "/custom":
            user_modes[from_number] = "custom"
            send_whatsapp_text(
                from_number,
                "Switched to customized mode. Your messages will now be handled by the customized system."
            )
            return {"status": "mode set"}

        # ===== Show current mode =====
        if user_text.lower() == "/mode":
            current_mode = user_modes.get(from_number, "baseline")
            send_whatsapp_text(
                from_number,
                f"Your current mode is: {current_mode}"
            )
            return {"status": "mode shown"}

        # ===== Help =====
        if user_text.lower() == "/help":
            help_text = (
                "Available commands:\n"
                "/baseline - switch to baseline mode\n"
                "/custom - switch to customized mode\n"
                "/mode - check current mode\n"
                "/help - show this help message"
            )
            send_whatsapp_text(from_number, help_text)
            return {"status": "help shown"}

        # ===== Default mode =====
        if from_number not in user_modes:
            user_modes[from_number] = "baseline"

        current_mode = user_modes[from_number]
        print("CURRENT MODE:", from_number, current_mode)

        # ===== Route message =====
        if current_mode == "baseline":
            reply = ask_baseline_gpt(user_text)
        else:
            reply = ask_custom_gpt(user_text)

        send_whatsapp_text(from_number, reply)
        return {"status": "ok"}

    except Exception as e:
        print("ERROR:", e)
        return {"error": str(e)}