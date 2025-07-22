import os
import time
import random
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
import google.generativeai as genai
from apscheduler.schedulers.background import BackgroundScheduler

# إعدادات عامة وقيم أساسية
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
ADMIN_ID = 123456789
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
FORCE_SUB_CHANNEL = "@YourForceSubChannel"

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

users_db = {}
channels_db = {}
notifications_db = {}

def get_user(user_id):
    if user_id not in users_db:
        users_db[user_id] = {
            "channels": [],
            "vip": False,
            "invite_count": 0,
            "invite_link": None,
            "vip_expiry": None,
            "invitees": set(),
            "publish_count": 0,
            "force_sub_ok": False,
            "blocked": False,
        }
    return users_db[user_id]

def get_channel(channel_id):
    if channel_id not in channels_db:
        channels_db[channel_id] = {
            "owner": None,
            "block_leavers": False,
        }
    return channels_db[channel_id]

# تحقق الاشتراك الإجباري عبر زر
async def check_force_sub(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = get_user(update.effective_user.id)
    if user["force_sub_ok"]:
        return True
    # تحقق فعلي من اشتراك المستخدم في القناة
    chat_member = await context.bot.get_chat_member(FORCE_SUB_CHANNEL, update.effective_user.id)
    if chat_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
        user["force_sub_ok"] = True
        return True
    keyboard = [
        [InlineKeyboardButton("✅ اشتركت", callback_data="force_sub_check")]
    ]
    await update.message.reply_text(
        f"يرجى الاشتراك أولًا في القناة: {FORCE_SUB_CHANNEL}\nثم اضغط '✅ اشتركت' لتفعيل الميزات.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return False

# رسالة البداية ولوحة التحكم الأساسية
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not await check_force_sub(update, context):
        return
    keyboard = [
        [InlineKeyboardButton("🧠 توليد محتوى", callback_data="generate_menu")],
        [InlineKeyboardButton("➕ إضافة قناة", callback_data="add_channel")],
        [InlineKeyboardButton("📣 إشعار عام", callback_data="notifications")],
        [InlineKeyboardButton("⚙️ لوحة المدير", callback_data="admin_panel") if user_id == ADMIN_ID else None],
    ]
    keyboard = [row for row in keyboard if row]  # إزالة None
    await update.message.reply_text(
        "👋 مرحبًا بك في بوت الذكاء الاصطناعي!\nاستخدم الأزرار أدناه:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# قائمة أنواع المحتوى
async def generate_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not await check_force_sub(update, context):
        return
    keyboard = [
        [InlineKeyboardButton("عبارة سوداوية باللهجة المصرية", callback_data="gen_egypt_black")],
        [InlineKeyboardButton("عبارة تحفيزية قصيرة", callback_data="gen_motivation")],
        [InlineKeyboardButton("نكتة سوداوية لكن مضحكة", callback_data="gen_dark_joke")],
        [InlineKeyboardButton("جملة فلسفية عن الحياة", callback_data="gen_philosophy")],
        [InlineKeyboardButton("عبارة غامضة فيها رمزية", callback_data="gen_symbolic")],
        [InlineKeyboardButton("اقتباس حزين من الأدب أو الشعر", callback_data="gen_sad_quote")],
    ]
    await update.callback_query.message.reply_text(
        "اختر نوع المحتوى الذي ترغب في توليده:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# توليد المحتوى بالذكاء الاصطناعي حسب النوع
async def generate_content(content_type):
    prompts = {
        "gen_egypt_black": "اكتب لي عبارة سوداوية باللهجة المصرية في سطر واحد فقط.",
        "gen_motivation": "اكتب لي عبارة تحفيزية قصيرة جدًا.",
        "gen_dark_joke": "اكتب لي نكتة سوداوية لكن مضحكة وغير جارحة.",
        "gen_philosophy": "اكتب لي جملة فلسفية عميقة عن الحياة.",
        "gen_symbolic": "اكتب لي عبارة غامضة فيها رمزية.",
        "gen_sad_quote": "اعطني اقتباسًا حزينًا من الأدب العربي أو الشعر.",
    }
    prompt = prompts.get(content_type, "اكتب لي عبارة عشوائية قصيرة.")
    response = model.generate_content(prompt)
    return response.text.strip()

# بعد توليد المحتوى: زر نشر وزر تجاهل
async def handle_content_generation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    content_type = update.callback_query.data
    content = await generate_content(content_type)
    user["last_content"] = content
    keyboard = [
        [InlineKeyboardButton("✅ نشر المحتوى", callback_data="publish_content")],
        [InlineKeyboardButton("❌ تجاهل", callback_data="ignore_content")],
    ]
    await update.callback_query.message.reply_text(content, reply_markup=InlineKeyboardMarkup(keyboard))

async def publish_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    user["publish_count"] += 1
    content = user.get("last_content", "لا يوجد محتوى.")
    for channel in user["channels"]:
        await context.bot.send_message(chat_id=channel, text=content)
    await update.callback_query.answer("✅ تم النشر بنجاح!")
    # ميزة VIP الذكية: بعد 5 نشرات
    if user["publish_count"] == 5 and not user["vip"]:
        if not user["invite_link"]:
            link = f"https://t.me/YourBot?start=invite_{user_id}_{random.randint(1000,9999)}"
            user["invite_link"] = link
        await context.bot.send_message(
            user_id,
            f"للحصول على VIP، ادعُ 10 أشخاص عبر هذا الرابط واشتركوا في قناة الاشتراك:\n{user['invite_link']}"
        )

async def ignore_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer("❌ تم تجاهل المحتوى.")

# جدولة النشر التلقائي
def schedule_job(context, user_id, interval_hours, content_type):
    scheduler = BackgroundScheduler()
    user = get_user(user_id)
    async def job():
        if not user["channels"]:
            return
        content = await generate_content(content_type)
        for channel in user["channels"]:
            await context.bot.send_message(chat_id=channel, text=content)
    scheduler.add_job(lambda: context.application.create_task(job()), 'interval', hours=interval_hours)
    scheduler.start()

async def schedule_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if not user["vip"] or (user["vip_expiry"] and time.time() > user["vip_expiry"]):
        await update.callback_query.answer(
            "ميزة الجدولة متاحة فقط لمشتركي VIP.",
            show_alert=True
        )
        return
    keyboard = [
        [InlineKeyboardButton("كل 6 ساعات", callback_data="schedule_6")],
        [InlineKeyboardButton("كل 12 ساعة", callback_data="schedule_12")],
        [InlineKeyboardButton("كل 24 ساعة", callback_data="schedule_24")],
    ]
    await update.callback_query.message.reply_text(
        "اختر توقيت النشر التلقائي:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    interval_map = {"schedule_6": 6, "schedule_12": 12, "schedule_24": 24}
    interval_hours = interval_map.get(update.callback_query.data)
    # قائمة أنواع المحتوى للجدولة
    keyboard = [
        [InlineKeyboardButton("عبارة سوداوية باللهجة المصرية", callback_data=f"auto_gen_egypt_black_{interval_hours}")],
        [InlineKeyboardButton("عبارة تحفيزية قصيرة", callback_data=f"auto_gen_motivation_{interval_hours}")],
        [InlineKeyboardButton("نكتة سوداوية لكن مضحكة", callback_data=f"auto_gen_dark_joke_{interval_hours}")],
        [InlineKeyboardButton("جملة فلسفية عن الحياة", callback_data=f"auto_gen_philosophy_{interval_hours}")],
        [InlineKeyboardButton("عبارة غامضة فيها رمزية", callback_data=f"auto_gen_symbolic_{interval_hours}")],
        [InlineKeyboardButton("اقتباس حزين من الأدب أو الشعر", callback_data=f"auto_gen_sad_quote_{interval_hours}")],
    ]
    await update.callback_query.message.reply_text(
        f"اختر نوع المحتوى الذي سيتم نشره تلقائيًا كل {interval_hours} ساعة:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_content_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    data = update.callback_query.data
    parts = data.split("_")
    content_type = "_".join(parts[2:-1])
    interval_hours = int(parts[-1])
    schedule_job(context, user_id, interval_hours, content_type)
    await update.callback_query.answer(f"تم تفعيل النشر التلقائي كل {interval_hours} ساعة!", show_alert=True)

# زر إضافة قناة (حتى قناتين فقط)
async def add_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if len(user["channels"]) >= 2:
        await update.callback_query.answer("يمكنك إضافة حتى قناتين فقط.", show_alert=True)
        return
    await update.callback_query.message.reply_text(
        "أرسل الآن معرف القناة التي تريد إضافتها (مثال: @channelname)، ويجب أن تكون مديرًا فيها."
    )

async def handle_channel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    channel_username = update.message.text.strip()
    # تحقق من الصلاحية (مبدئيًا فقط تحقق من الاسم)
    if channel_username.startswith("@"):
        # هنا يمكن إضافة تحقق فعلي من إدارة المستخدم للقناة باستخدام get_chat_member
        user["channels"].append(channel_username)
        get_channel(channel_username)["owner"] = user_id
        await update.message.reply_text(f"✅ تم إضافة القناة: {channel_username}")
    else:
        await update.message.reply_text("يرجى إرسال معرف القناة بشكل صحيح يبدأ بـ @.")

# نظام الإحالة والـ VIP الذكية
async def handle_invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        ref = update.message.text.split("invite_")[1].split("_")[0]
        ref_id = int(ref)
    except Exception:
        return
    ref_user = get_user(ref_id)
    # تحقق من اشتراك المدعو في قناة الاشتراك
    chat_member = await context.bot.get_chat_member(FORCE_SUB_CHANNEL, user_id)
    if chat_member.status in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
        ref_user["invitees"].add(user_id)
        ref_user["invite_count"] = len(ref_user["invitees"])
        if ref_user["invite_count"] >= 10 and not ref_user["vip"]:
            ref_user["vip"] = True
            ref_user["vip_expiry"] = time.time() + 30*24*60*60
            await context.bot.send_message(ref_id, "🎉 تم تفعيل عضوية VIP لمدة شهر! يمكنك الآن استخدام الجدولة.")
        await update.message.reply_text("شكراً لانضمامك عبر رابط الدعوة!")
    else:
        await update.message.reply_text(f"يجب عليك الاشتراك في قناة: {FORCE_SUB_CHANNEL} أولاً.")

# مراقبة مغادرة المدعوين وإلغاء VIP تلقائيًا
async def monitor_leavers(context: ContextTypes.DEFAULT_TYPE):
    # يفترض هنا وجود آلية دورية لمراجعة اشتراك المدعوين وإلغاء VIP عند مغادرة أحدهم
    for user_id, user in users_db.items():
        if user["vip"]:
            for invitee_id in user["invitees"]:
                chat_member = await context.bot.get_chat_member(FORCE_SUB_CHANNEL, invitee_id)
                if chat_member.status not in [ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER]:
                    user["vip"] = False
                    await context.bot.send_message(user_id, "تم إلغاء عضوية VIP: أحد المدعوين غادر القناة.")

# تفعيل VIP يدويًا من المدير
async def activate_vip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        target_id = int(update.message.text.split()[1])
        user = get_user(target_id)
        user["vip"] = True
        user["vip_expiry"] = time.time() + 30*24*60*60
        await update.message.reply_text(f"تم تفعيل VIP للمستخدم {target_id} لمدة شهر")
    except Exception:
        await update.message.reply_text("صيغة الأمر: /vip user_id")

# ميزة حظر مغادري القناة (تفعيل/إيقاف لكل قناة)
async def toggle_block_leavers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        channel_username = update.message.text.split()[1]
        channel = get_channel(channel_username)
        channel["block_leavers"] = not channel["block_leavers"]
        status = "مفعّل" if channel["block_leavers"] else "متوقف"
        await update.message.reply_text(f"حظر المغادرين في {channel_username}: {status}")
    except Exception:
        await update.message.reply_text("صيغة الأمر: /blockleavers @channelusername")

# ميزة "الإشعار العام"
async def notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)
    if user_id != ADMIN_ID:
        await update.callback_query.answer("هذه الميزة للمدير فقط.", show_alert=True)
        return
    await update.callback_query.message.reply_text(
        "أرسل نص الإشعار ليتم نشره على جميع المستخدمين وقنواتهم."
    )

async def handle_notification_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    notif_id = str(random.randint(100000,999999))
    notifications_db[notif_id] = update.message.text
    # إرسال الإشعار لجميع المستخدمين وقنواتهم
    for user_id, user in users_db.items():
        try:
            await context.bot.send_message(user_id, f"إشعار عام:\n{update.message.text}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✔️ تم نشر الإشعار", callback_data=f"notif_done_{notif_id}"),
                                                    InlineKeyboardButton("❌ حذف الإشعار", callback_data=f"notif_del_{notif_id}")]]))
            for channel in user["channels"]:
                await context.bot.send_message(channel, f"إشعار عام:\n{update.message.text}")
        except Exception: pass

async def handle_notification_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.callback_query.data
    notif_id = data.split("_")[-1]
    if data.startswith("notif_del_"):
        # حذف من جميع المستخدمين وقنواتهم
        for user_id, user in users_db.items():
            try:
                await context.bot.send_message(user_id, f"❌ تم حذف الإشعار العام رقم {notif_id}.")
                for channel in user["channels"]:
                    await context.bot.send_message(channel, f"❌ تم حذف الإشعار العام رقم {notif_id}.")
            except Exception: pass
        notifications_db.pop(notif_id, None)
        await update.callback_query.answer("❌ تم حذف الإشعار.")
    elif data.startswith("notif_done_"):
        await update.callback_query.answer("✔️ تم نشر الإشعار.")

# لوحة تحكم المدير
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("هذه الميزة للمدير فقط.", show_alert=True)
        return
    keyboard = [
        [InlineKeyboardButton("تفعيل/إيقاف ميزات مستخدم", callback_data="admin_toggle_user")],
        [InlineKeyboardButton("تعيين قناة الاشتراك الإجباري", callback_data="admin_set_forcesub")],
        [InlineKeyboardButton("إدارة عضويات VIP", callback_data="admin_vip")],
        [InlineKeyboardButton("مراقبة القنوات المرتبطة", callback_data="admin_monitor_channels")],
        [InlineKeyboardButton("إشعار عام", callback_data="notifications")],
    ]
    await update.callback_query.message.reply_text(
        "لوحة تحكم المدير:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# نقاط الإدخال الرئيسية
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("vip", activate_vip))
    app.add_handler(CommandHandler("blockleavers", toggle_block_leavers))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, add_channel))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("invite_"), handle_invite))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("@"), handle_channel_add))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^(?!invite_).*"), handle_notification_text))
    app.add_handler(CallbackQueryHandler(generate_menu, pattern="generate_menu"))
    app.add_handler(CallbackQueryHandler(handle_content_generation, pattern="gen_"))
    app.add_handler(CallbackQueryHandler(publish_content, pattern="publish_content"))
    app.add_handler(CallbackQueryHandler(ignore_content, pattern="ignore_content"))
    app.add_handler(CallbackQueryHandler(schedule_menu, pattern="schedule_menu"))
    app.add_handler(CallbackQueryHandler(handle_schedule, pattern="schedule_"))
    app.add_handler(CallbackQueryHandler(handle_content_schedule, pattern="auto_gen_"))
    app.add_handler(CallbackQueryHandler(add_channel, pattern="add_channel"))
    app.add_handler(CallbackQueryHandler(notifications, pattern="notifications"))
    app.add_handler(CallbackQueryHandler(handle_notification_action, pattern="notif_"))
    app.add_handler(CallbackQueryHandler(admin_panel, pattern="admin_panel"))
    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()