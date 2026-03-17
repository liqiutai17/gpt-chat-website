from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path
import os

# 读取 .env 文件（本地开发用）
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# 创建 FastAPI 应用
app = FastAPI()

# 允许跨域（前端网页调用 API 时需要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 读取 API key
api_key = os.getenv("OPENAI_API_KEY")
print("API KEY loaded:", bool(api_key))

# 创建 OpenAI 客户端
client = OpenAI(api_key=api_key)


# ===== 根路径 =====
@app.get("/")
async def root():
    return {"message": "GPT backend is running"}


# ===== 请求数据结构 =====
class ChatRequest(BaseModel):
    message: str


# ===== 聊天接口 =====
@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        response = client.responses.create(
            model="gpt-5.4",
            input=req.message
        )

        return {
            "reply": response.output_text
        }

    except Exception as e:
        print("ERROR:", e)
        return {
            "error": str(e)
        }
    from fastapi import Request

    VERIFY_TOKEN = "emoji_chat_verify"

    @app.get("/whatsapp/webhook")
    async def verify(request: Request):
        params = request.query_params
        if params.get("hub.verify_token") == VERIFY_TOKEN:
            return int(params.get("hub.challenge"))
        return {"error": "Invalid verification token"}

    @app.post("/whatsapp/webhook")
    async def receive_message(request: Request):
        data = await request.json()
        print("收到消息:", data)

        try:
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]["text"]["body"]
            from_number = data["entry"][0]["changes"][0]["value"]["messages"][0]["from"]

            # 调用 GPT
            response = client.responses.create(
                model="gpt-5.4",
                input=message
            )

            reply = response.output_text

            # 回消息给 WhatsApp
            import requests

            url = f"https://graph.facebook.com/v18.0/{os.getenv('WHATSAPP_PHONE_NUMBER_ID')}/messages"

            headers = {
                "Authorization": f"Bearer {os.getenv('WHATSAPP_ACCESS_TOKEN')}",
                "Content-Type": "application/json"
            }

            payload = {
                "messaging_product": "whatsapp",
                "to": from_number,
                "type": "text",
                "text": {"body": reply}
            }

            requests.post(url, headers=headers, json=payload)

        except Exception as e:
            print("ERROR:", e)

        return {"status": "ok"}
