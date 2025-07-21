from fastapi import FastAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import os

# إعدادات
TOKEN = os.getenv("BOT_TOKEN")  # ضعه في بيئة Render
app = FastAPI()

# دالة توليد رابط البحث
def generate_freepik_link(query: str) -> str:
    base_url = "https://www.freepik.com/search"
    return f"{base_url}?format=search&query={query.replace(' ', '+')}"

# أمر البداية
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحباً بك!\nأرسل كلمة البحث مثل 'أيقونة ذهب' وسأجلب لك نتائج Freepik 🔍"
    )

# عند استقبال رسالة
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    link = generate_freepik_link(query)

    keyboard = [
        [InlineKeyboardButton("🔗 فتح Freepik", url=link)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🔍 نتائج البحث عن: *{query}*\nاضغط الزر أدناه:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# بدء البوت
@app.on_event("startup")
async def on_startup():
    bot_app = ApplicationBuilder().token(TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), search_handler))

    bot_app.run_polling()
