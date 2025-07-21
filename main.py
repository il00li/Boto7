import os
import time
import random
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters, JobQueue
)
import google.generativeai as genai
from apscheduler.schedulers.background import BackgroundScheduler

TELEGRAM_TOKEN = "7639996535:AAH_Ppw8jeiUg4nJjjEyOXaYlip289jSAio"
ADMIN_ID = 7251748706
GEMINI_API_KEY = "AIzaSyAEULfP5zi5irv4yRhFugmdsjBoLk7kGsE"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

# بيانات المستخدمين
users_db = {}
vip_users = {}

def get_user(user_id):
    if user_id not in users_db:
        users_db[user_id] = {"channels": [], "vip": False, "invite_count": 0, "invite_link": None}
    return users_db[user_id]

# رسالة الترحيب مع لوحة التحكم
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    get_user(user.id)
    keyboard = [
        [InlineKeyboardButton("➕ أضف البوت إلى قناتك", url=f"https://t.me/Boto7Bot?startchannel=start")],
        [InlineKeyboardButton("🚀 نشر مباشر", callback_data="post_now")],
        [InlineKeyboardButton("🕒 نشر مجدول (VIP)", callback_data="schedule_menu")],
        [InlineKeyboardButton("🖤 عبارات سوداء", callback_data="type_black")],
        [InlineKeyboardButton("🕌 خواطر إسلامية", callback_data="type_islamic")],
        [InlineKeyboardButton("💬 شعر عربي أصيل", callback_data="type_poetry")],
    ]
    text = (
        "👋 أهلاً بك في بوت النشر التلقائي للقنوات!\n\n"
        "يمكنك إضافة البوت لقناتك، ثم نشر محتوى فوري أو جدولة النشر حسب رغبتك.\n"
        "قسم الجدولة متاح فقط لمشتركي VIP.\n"
        "لمعرفة المزيد، تواصل مع المدير."
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# توليد المحتوى عبر Gemini
async def generate_content(content_type):
    if content_type == "type_black":
        prompt = "اكتب لي عبارة سودا بسطر واحد بدون اي تعليق او شرح"
    elif content_type == "type_islamic":
        prompt = "اكتب لي خاطرة اسلامية بدون تعليق او شرح"
    elif content_type == "type_poetry":
        prompt = (
            "أعطني بيتين من الشعر العربي من شاعر معروف، على أن تكون من دواوينه الموثقة، ومرتبة في سطرين متصلين، بدون أي شروحات أو تعليقات أو مصدر أو اسم كتاب أو رقم صفحة. أذكر فقط اسم الشاعر بعد البيتين، بدون رموز أو زخارف أو إيموجي."
        )
    else:
        prompt = "اكتب لي عبارة عشوائية قصيرة"
    response = model.generate_content(prompt)
    return response.text.strip()

# نشر مباشر في القناة
async def post_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if not user_data["channels"]:
        await update.callback_query.answer("أضف البوت إلى قناتك أولاً.", show_alert=True)
        return
    # اختر نوع المحتوى افتراضي أو اسأل المستخدم
    keyboard = [
        [InlineKeyboardButton("🖤 عبارات سوداء", callback_data="post_type_black")],
        [InlineKeyboardButton("🕌 خواطر إسلامية", callback_data="post_type_islamic")],
        [InlineKeyboardButton("💬 شعر عربي أصيل", callback_data="post_type_poetry")],
    ]
    await update.callback_query.message.reply_text(
        "اختر نوع المحتوى الذي تريد نشره الآن:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# تنفيذ نشر مباشر بعد اختيار نوع المحتوى
async def post_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    content_type = update.callback_query.data.replace("post_type_", "")
    content = await generate_content(content_type)
    for channel in user_data["channels"]:
        await context.bot.send_message(chat_id=channel, text=content)
    await update.callback_query.answer("تم النشر بنجاح في قنواتك!")

# قائمة جدولة النشر
async def schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if not user_data["vip"]:
        await update.callback_query.answer(
            "قسم الجدولة متاح فقط لمشتركي VIP.\nللحصول على VIP شارك رابط دعوتك مع 10 أشخاص أو تواصل مع المدير.",
            show_alert=True
        )
        return
    keyboard = [
        [InlineKeyboardButton("كل 6 ساعات", callback_data="schedule_6h")],
        [InlineKeyboardButton("كل 12 ساعة", callback_data="schedule_12h")],
        [InlineKeyboardButton("كل 24 ساعة", callback_data="schedule_24h")],
    ]
    await update.callback_query.message.reply_text(
        "اختر توقيت النشر المجدول:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# تفعيل الجدولة
def schedule_job(context, user_id, interval_hours, content_type):
    scheduler = BackgroundScheduler()
    user_data = get_user(user_id)

    def job():
        content = context.run_coroutine(generate_content(content_type))
        for channel in user_data["channels"]:
            context.bot.send_message(chat_id=channel, text=content)
    scheduler.add_job(job, 'interval', hours=interval_hours)
    scheduler.start()

async def handle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    interval_map = {"schedule_6h": 6, "schedule_12h": 12, "schedule_24h": 24}
    interval_hours = interval_map.get(update.callback_query.data)
    keyboard = [
        [InlineKeyboardButton("🖤 عبارات سوداء", callback_data=f"scheduled_black_{interval_hours}")],
        [InlineKeyboardButton("🕌 خواطر إسلامية", callback_data=f"scheduled_islamic_{interval_hours}")],
        [InlineKeyboardButton("💬 شعر عربي أصيل", callback_data=f"scheduled_poetry_{interval_hours}")],
    ]
    await update.callback_query.message.reply_text(
        f"اختر نوع المحتوى المجدول للنشر كل {interval_hours} ساعة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_content_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    data = update.callback_query.data
    parts = data.split("_")
    content_type = f"type_{parts[1]}"
    interval_hours = int(parts[2])
    schedule_job(context, user_id, interval_hours, content_type)
    await update.callback_query.answer(f"تم تفعيل النشر المجدول كل {interval_hours} ساعة!", show_alert=True)

# إضافة قناة المستخدم (يتم عبر event في Telegram بعد إضافة البوت كـ admin في القناة)
async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    channel_id = update.message.chat_id
    if update.message.chat.type == "channel":
        user_data = get_user(user_id)
        if channel_id not in user_data["channels"]:
            user_data["channels"].append(channel_id)
        await context.bot.send_message(channel_id, "✅ تم تفعيل البوت في هذه القناة!")

# زر العبارات السوداء
async def type_black(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = await generate_content("type_black")
    await update.callback_query.message.reply_text(content)

async def type_islamic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = await generate_content("type_islamic")
    await update.callback_query.message.reply_text(content)

async def type_poetry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = await generate_content("type_poetry")
    await update.callback_query.message.reply_text(content)

# VIP عبر رابط الدعوة
async def get_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    if not user_data["invite_link"]:
        # توليد رابط دعوة خاص بالمستخدم
        link = f"https://t.me/Boto7Bot?start=invite_{user_id}_{random.randint(1000,9999)}"
        user_data["invite_link"] = link
    await update.message.reply_text(
        f"للحصول على VIP شارك هذا الرابط مع 10 أشخاص:\n{user_data['invite_link']}\n"
        "بعد وصول 10 أشخاص ستتفعل ميزة الجدولة لمدة شهر."
    )

# إدارة الدعوات
async def handle_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    ref = update.message.text.split("invite_")[1].split("_")[0]
    ref_id = int(ref)
    ref_user = get_user(ref_id)
    ref_user["invite_count"] += 1
    if ref_user["invite_count"] >= 10:
        ref_user["vip"] = True
        await context.bot.send_message(ref_id, "🎉 تم تفعيل عضوية VIP لمدة شهر! يمكنك الآن استخدام الجدولة.")
    await update.message.reply_text("شكراً لانضمامك عبر رابط الدعوة!")

# تفعيل VIP عبر المدير
async def activate_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(update.message.text.split()[1])
        user_data = get_user(target_id)
        user_data["vip"] = True
        await update.message.reply_text(f"تم تفعيل VIP للمستخدم {target_id}")
    except Exception:
        await update.message.reply_text("صيغة الأمر: /vip user_id")

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vip", activate_vip))
    app.add_handler(CommandHandler("getvip", get_vip))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, add_channel))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("invite_"), handle_invite))
    app.add_handler(CallbackQueryHandler(post_now, pattern="post_now"))
    app.add_handler(CallbackQueryHandler(post_type, pattern="post_type_"))
    app.add_handler(CallbackQueryHandler(type_black, pattern="type_black"))
    app.add_handler(CallbackQueryHandler(type_islamic, pattern="type_islamic"))
    app.add_handler(CallbackQueryHandler(type_poetry, pattern="type_poetry"))
    app.add_handler(CallbackQueryHandler(schedule_menu, pattern="schedule_menu"))
    app.add_handler(CallbackQueryHandler(handle_schedule, pattern="schedule_"))
    app.add_handler(CallbackQueryHandler(handle_content_schedule, pattern="scheduled_"))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
