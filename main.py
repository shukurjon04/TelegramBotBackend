import asyncio
import logging
from datetime import datetime
from typing import Optional, List
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager

# Logging sozlamalari
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# KONFIGURATSIYA
# ============================================
BOT_TOKEN = "8479466867:AAFa9DFzBh9XlsejIFm9yOLodPNBcuNLS0Y"  # @BotFather dan olingan token
API_KEY = "your-secret-api-key-12345"  # Flutter bilan bog'lanish uchun

# ============================================
# BOT VA DISPATCHER
# ============================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# ============================================
# MA'LUMOTLAR MODELLARI
# ============================================

class PostRequest(BaseModel):
    """Post yuborish uchun model"""
    chat_id: str  # Guruh/kanal ID (@username yoki -100...)
    text: str
    photo_url: Optional[str] = None
    video_url: Optional[str] = None
    parse_mode: str = "HTML"
    disable_notification: bool = False


class EditMessageRequest(BaseModel):
    """Xabarni tahrirlash uchun model"""
    chat_id: str
    message_id: int
    text: str
    parse_mode: str = "HTML"


class DeleteMessageRequest(BaseModel):
    """Xabarni o'chirish uchun model"""
    chat_id: str
    message_id: int


class ChannelInfo(BaseModel):
    """Kanal ma'lumotlari"""
    id: int
    title: str
    username: Optional[str] = None
    type: str


class BotInfo(BaseModel):
    """Bot ma'lumotlari"""
    id: int
    username: str
    first_name: str
    can_join_groups: bool
    can_read_all_group_messages: bool


# ============================================
# MA'LUMOTLAR BAZASI (SODDA VERSIYA)
# ============================================
# Real loyihada PostgreSQL/MongoDB ishlatish kerak
sent_messages = []  # Yuborilgan xabarlar tarixi
admin_users = [6862317597]  # Admin foydalanuvchilar ID


# ============================================
# API AUTHENTICATION
# ============================================
def verify_api_key(api_key: str = None):
    """API kalitni tekshirish"""
    if api_key != API_KEY:
        return True
    raise HTTPException(status_code=403, detail="Invalid API key")



# ============================================
# BOT HANDLERS
# ============================================

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Start komandasi"""
    await message.answer(
        f"👋 Salom, {message.from_user.first_name}!\n\n"
        "Men kanallar va guruhlarga xabar yuborish botiman.\n"
        "Meni guruhingizga qo'shing va admin qiling.\n\n"
        "Komandalar:\n"
        "/help - Yordam\n"
        "/info - Bot haqida ma'lumot"
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    """Yordam komandasi"""
    help_text = """
📖 <b>Bot Qo'llanmasi</b>

<b>Asosiy funksiyalar:</b>
✅ Kanal/guruhga post yuborish
✅ Xabarlarni tahrirlash
✅ Xabarlarni o'chirish
✅ Rasm va video yuborish
✅ Admin panel orqali boshqarish

<b>Botni qo'shish:</b>
1. Guruh/kanalga botni qo'shing
2. Botni admin qiling
3. Flutter ilovasidan boshqaring

<b>Savol bo'lsa:</b>
@your_support_username
    """
    await message.answer(help_text, parse_mode="HTML")


@dp.message(Command("info"))
async def cmd_info(message: types.Message):
    """Bot ma'lumotlari"""
    me = await bot.get_me()
    info_text = f"""
🤖 <b>Bot Ma'lumotlari</b>

<b>Bot nomi:</b> {me.first_name}
<b>Username:</b> @{me.username}
<b>ID:</b> <code>{me.id}</code>

<b>Statistika:</b>
📤 Yuborilgan xabarlar: {len(sent_messages)}
👥 Adminlar soni: {len(admin_users)}

<b>Status:</b> ✅ Aktiv
    """
    await message.answer(info_text, parse_mode="HTML")


@dp.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """Statistika"""
    if message.from_user.id not in admin_users:
        await message.answer("⛔️ Bu komanda faqat adminlar uchun!")
        return

    stats_text = f"""
📊 <b>Bot Statistikasi</b>

📤 Jami yuborilgan xabarlar: {len(sent_messages)}
🕐 Oxirgi xabar: {sent_messages[-1]['time'] if sent_messages else 'Hali yo\'q'}
👥 Adminlar soni: {len(admin_users)}

<b>So'nggi 5 ta xabar:</b>
    """

    for msg in sent_messages[-5:]:
        stats_text += f"\n• {msg['time']} - {msg['chat_id']}"

    await message.answer(stats_text, parse_mode="HTML")


# ============================================
# FASTAPI ILOVA
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifecycle"""
    # Bot polling ni alohida task'da ishga tushirish
    asyncio.create_task(dp.start_polling(bot))
    logger.info("Bot started polling")
    yield
    # Shutdown
    await bot.session.close()


app = FastAPI(
    title="Telegram Bot API",
    description="Admin panel uchun backend API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS sozlamalari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production'da faqat Flutter app URL'ini qo'ying
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================
# API ENDPOINTS
# ============================================

@app.get("/")
async def root():
    """API asosiy sahifasi"""
    return {
        "message": "Telegram Bot API",
        "version": "1.0.0",
        "status": "active",
        "endpoints": {
            "bot_info": "/api/bot/info",
            "send_message": "/api/messages/send",
            "edit_message": "/api/messages/edit",
            "delete_message": "/api/messages/delete",
            "get_history": "/api/messages/history"
        }
    }


@app.get("/api/bot/info")
async def get_bot_info(auth: bool = Depends(verify_api_key)):
    """Bot haqida ma'lumot olish"""
    try:
        me = await bot.get_me()
        return {
            "success": True,
            "data": {
                "id": me.id,
                "username": me.username,
                "first_name": me.first_name,
                "can_join_groups": me.can_join_groups,
                "can_read_all_group_messages": me.can_read_all_group_messages,
                "supports_inline_queries": me.supports_inline_queries
            }
        }
    except Exception as e:
        logger.error(f"Error getting bot info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/{chat_id}")
async def get_chat_info(chat_id: str, auth: bool = Depends(verify_api_key)):
    """Kanal/guruh haqida ma'lumot"""
    try:
        chat = await bot.get_chat(chat_id)
        return {
            "success": True,
            "data": {
                "id": chat.id,
                "title": chat.title,
                "username": chat.username,
                "type": chat.type,
                "description": chat.description,
                "member_count": await bot.get_chat_member_count(chat_id) if chat.type in ["group",
                                                                                          "supergroup"] else None
            }
        }
    except Exception as e:
        logger.error(f"Error getting chat info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/messages/send")
async def send_message(request: PostRequest, auth: bool = Depends(verify_api_key)):
    """Xabar yuborish"""
    try:
        sent_message = None

        # Rasm bilan xabar
        if request.photo_url:
            sent_message = await bot.send_photo(
                chat_id=request.chat_id,
                photo=request.photo_url,
                caption=request.text,
                parse_mode=request.parse_mode,
                disable_notification=request.disable_notification
            )

        # Video bilan xabar
        elif request.video_url:
            sent_message = await bot.send_video(
                chat_id=request.chat_id,
                video=request.video_url,
                caption=request.text,
                parse_mode=request.parse_mode,
                disable_notification=request.disable_notification
            )

        # Oddiy matn xabar
        else:
            sent_message = await bot.send_message(
                chat_id=request.chat_id,
                text=request.text,
                parse_mode=request.parse_mode,
                disable_notification=request.disable_notification
            )

        # Tarixga saqlash
        sent_messages.append({
            "message_id": sent_message.message_id,
            "chat_id": request.chat_id,
            "text": request.text,
            "time": datetime.now().isoformat(),
            "type": "photo" if request.photo_url else "video" if request.video_url else "text"
        })

        logger.info(f"Message sent to {request.chat_id}: {sent_message.message_id}")

        return {
            "success": True,
            "message": "Xabar muvaffaqiyatli yuborildi",
            "data": {
                "message_id": sent_message.message_id,
                "chat_id": sent_message.chat.id,
                "date": sent_message.date.isoformat()
            }
        }

    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=f"Xabar yuborishda xatolik: {str(e)}")


@app.put("/api/messages/edit")
async def edit_message(request: EditMessageRequest, auth: bool = Depends(verify_api_key)):
    """Xabarni tahrirlash"""
    try:
        await bot.edit_message_text(
            chat_id=request.chat_id,
            message_id=request.message_id,
            text=request.text,
            parse_mode=request.parse_mode
        )

        logger.info(f"Message edited in {request.chat_id}: {request.message_id}")

        return {
            "success": True,
            "message": "Xabar muvaffaqiyatli tahrirlandi",
            "data": {
                "message_id": request.message_id,
                "chat_id": request.chat_id
            }
        }

    except Exception as e:
        logger.error(f"Error editing message: {e}")
        raise HTTPException(status_code=500, detail=f"Xabarni tahrirlashda xatolik: {str(e)}")


@app.delete("/api/messages/delete")
async def delete_message(request: DeleteMessageRequest, auth: bool = Depends(verify_api_key)):
    """Xabarni o'chirish"""
    try:
        await bot.delete_message(
            chat_id=request.chat_id,
            message_id=request.message_id
        )

        logger.info(f"Message deleted from {request.chat_id}: {request.message_id}")

        return {
            "success": True,
            "message": "Xabar muvaffaqiyatli o'chirildi",
            "data": {
                "message_id": request.message_id,
                "chat_id": request.chat_id
            }
        }

    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        raise HTTPException(status_code=500, detail=f"Xabarni o'chirishda xatolik: {str(e)}")


@app.get("/api/messages/history")
async def get_message_history(
        limit: int = 50,
        auth: bool = Depends(verify_api_key)
):
    """Yuborilgan xabarlar tarixi"""
    try:
        return {
            "success": True,
            "data": {
                "total": len(sent_messages),
                "messages": sent_messages[-limit:]
            }
        }
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/messages/send-bulk")
async def send_bulk_messages(
        requests: List[PostRequest],
        auth: bool = Depends(verify_api_key)
):
    """Ko'plab kanallarga bir vaqtda yuborish"""
    results = []

    for req in requests:
        try:
            result = await send_message(req, auth=True)
            results.append({
                "chat_id": req.chat_id,
                "success": True,
                "data": result["data"]
            })
        except Exception as e:
            results.append({
                "chat_id": req.chat_id,
                "success": False,
                "error": str(e)
            })

    success_count = sum(1 for r in results if r["success"])

    return {
        "success": True,
        "message": f"{success_count}/{len(requests)} xabar yuborildi",
        "results": results
    }


@app.get("/api/health")
async def health_check():
    """Server holati"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "bot_active": True,
        "messages_sent": len(sent_messages)
    }


# ============================================
# ISHGA TUSHIRISH
# ============================================

if __name__ == "__main__":
    print("=" * 60)
    print("🤖 TELEGRAM BOT BACKEND")
    print("=" * 60)
    print(f"📡 API Server: http://localhost:8000")
    print(f"📚 API Docs: http://localhost:8000/docs")
    print(f"🔑 API Key: {API_KEY}")
    print("=" * 60)
    print("\n⚠️  MUHIM:")
    print("1. BOT_TOKEN ni @BotFather dan olingan token bilan almashtiring")
    print("2. API_KEY ni xavfsiz kalit bilan almashtiring")
    print("3. Production'da CORS sozlamalarini to'g'rilang")
    print("\n🚀 Server ishga tushmoqda...\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )