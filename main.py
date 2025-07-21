from fastapi import FastAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

# 🔐 رمز البوت المباشر (يرجى استبداله عند النشر العام)
TOKEN = "7639996535:AAH_Ppw8jeiUg4nJjjEyOXaYlip289jSAio"

app = FastAPI()

# 🧠 دالة توليد رابط البحث في Freepik
def generate_freepik_link(query: str) -> str:
    base_url = "https://www.freepik.com/search"
    return f"{base_url}?format=search&query={query.replace(' ', '+')}"

# 🟢 أمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 مرحباً بك في بوت البحث عن الملفات من Freepik!\n"
        "📌 فقط أرسل كلمة البحث مثل: *شعار ذهبي* وسأرسل لك رابط النتائج 🔍",
        parse_mode="Markdown"
    )

# 🔍 معالج البحث بالنص
async def search_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    link = generate_freepik_link(query)

    keyboard = [
        [InlineKeyboardButton("🔗 فتح النتائج في Freepik", url=link)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🔍 نتائج البحث عن: *{query}*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# 🚀 تشغيل البوت عند بدء التطبيق
@app.on_event("startup")
async def on_startup():
    bot_app = ApplicationBuilder().token(TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), search_handler))

    bot_app.run_polling()
