import logging
import asyncio
import time
import os
from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage

import requests

# --------- الإعدادات ---------
API_TOKEN = "7639996535:AAH_Ppw8jeiUg4nJjjEyOXaYlip289jSAio"
ADMIN_IDS = [7251748706]
CHANNEL_REQUIRED = "@crazys7"  # غيّرها لاحقاً
GEMINI_API_KEY = "AIzaSyAEULfP5zi5irv4yRhFugmdsjBoLk7kGsE"
VIP_VALIDITY_DAYS = 30
MAX_USER_CHANNELS = 2

# قواعد بيانات مصغرة (يمكنك استبدالها بـ SQLite لاحقاً)
USERS = {}  # user_id: { 'vip': bool, 'ref': str, 'invites': set, 'channels': set, 'posts': int, ... }
REF_LINKS = {}  # ref_code: inviter_id
CHANNELS = {}  # channel_username: owner_id
NOTIFICATIONS = []  # [text, ...]
BANNED_USERS = set()
GLOBAL_NOTIF = None

# --------- Gemini AI ---------
def gemini_generate(text):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    payload = {"contents":[{"parts":[{"text": text}]}]}
    try:
        r = requests.post(url, json=payload, timeout=20)
        out = r.json()
        answer = out.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        return answer.strip() if answer else "حدث خطأ في توليد المحتوى."
    except Exception as e:
        return "خطأ في الاتصال بخدمة Gemini."

def generate_content(content_type):
    prompts = {
        "sod_masri": "اكتب لي عبارة سوداوية باللهجة المصرية.",
        "motiv_short": "اكتب لي عبارة تحفيزية قصيرة.",
        "dark_joke": "اكتب لي نكتة سوداوية ولكن مضحكة.",
        "philosophy": "اكتب لي جملة فلسفية عن الحياة.",
        "symbolic": "اكتب لي عبارة غامضة ورمزية.",
        "sad_quote": "اكتب لي اقتباسًا حزينًا من الأدب أو الشعر."
    }
    prompt = prompts.get(content_type, "اكتب لي عبارة مناسبة.")
    return gemini_generate(prompt)

# --------- أدوات ---------
def get_main_menu(is_admin=False):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🧠 توليد محتوى", callback_data="generate_content"),
        types.InlineKeyboardButton("📅 جدولة النشر", callback_data="schedule_post"),
        types.InlineKeyboardButton("➕ إدارة القنوات", callback_data="manage_channels"),
        types.InlineKeyboardButton("⭐ العضوية VIP", callback_data="vip_status"),
        types.InlineKeyboardButton("📢 إشعار المدير", callback_data="manager_notice"),
        types.InlineKeyboardButton("🔒 إدارة المغادرين", callback_data="manage_leavers"),
        types.InlineKeyboardButton("⚙️ إعداداتي", callback_data="my_settings")
    )
    if is_admin:
        kb.add(types.InlineKeyboardButton("👨‍💼 مدير النظام", callback_data="admin_panel"))
    return kb

def get_content_menu():
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("عبارة سوداوية باللهجة المصرية", callback_data="content_sod_masri"),
        types.InlineKeyboardButton("عبارة تحفيزية قصيرة", callback_data="content_motiv_short"),
        types.InlineKeyboardButton("نكتة سوداوية لكن مضحكة", callback_data="content_dark_joke"),
        types.InlineKeyboardButton("جملة فلسفية عن الحياة", callback_data="content_philosophy"),
        types.InlineKeyboardButton("عبارة غامضة رمزية", callback_data="content_symbolic"),
        types.InlineKeyboardButton("اقتباس حزين من الأدب أو الشعر", callback_data="content_sad_quote"),
    )
    return kb

def get_admin_panel():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📢 إرسال إشعار عام", callback_data="send_global"),
        types.InlineKeyboardButton("❌ حذف الإشعار العام", callback_data="del_global"),
        types.InlineKeyboardButton("📡 تعيين قناة الاشتراك الإجباري", callback_data="set_required_channel"),
        types.InlineKeyboardButton("👤 تفعيل عضوية VIP يدويًا", callback_data="manual_vip"),
        types.InlineKeyboardButton("🔍 مراجعة حالة المستخدمين", callback_data="review_users"),
        types.InlineKeyboardButton("🧑‍💼 إدارة روابط الإحالة والدعوات", callback_data="manage_referrals"),
        types.InlineKeyboardButton("📊 تقرير عام لحالة المستخدمين", callback_data="report_users"),
        types.InlineKeyboardButton("⚙️ إعدادات متقدمة", callback_data="advanced_settings"),
    )
    return kb

# --------- البوت ---------
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

async def check_subscription(user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_REQUIRED, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

@dp.message(commands=["start"])
async def start_msg(message: types.Message):
    uid = message.from_user.id
    if uid not in USERS:
        USERS[uid] = {"vip": False, "ref": "", "invites": set(), "channels": set(), "posts": 0, "last_vip": 0}
    if not await check_subscription(uid):
        kb = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("✅ اشتركت", callback_data="subscribed"))
        await message.answer(f"يرجى الاشتراك في القناة {CHANNEL_REQUIRED} أولاً.", reply_markup=kb)
    else:
        is_admin = uid in ADMIN_IDS
        await message.answer("مرحبًا! اختر من القائمة:", reply_markup=get_main_menu(is_admin))

@dp.callback_query(lambda c: c.data == "subscribed")
async def after_subscribed(call: types.CallbackQuery):
    uid = call.from_user.id
    if await check_subscription(uid):
        is_admin = uid in ADMIN_IDS
        await call.message.edit_text("تم التحقق من الاشتراك! اختر من القائمة:", reply_markup=get_main_menu(is_admin))
    else:
        await call.answer("لم يتم العثور على اشتراكك بعد. يرجى الاشتراك أولاً.", show_alert=True)

# --------- توليد المحتوى ---------
@dp.callback_query(lambda c: c.data == "generate_content")
async def content_menu(call: types.CallbackQuery):
    await call.message.edit_text("اختر نوع المحتوى:", reply_markup=get_content_menu())

@dp.callback_query(lambda c: c.data.startswith("content_"))
async def handle_content_generation(call: types.CallbackQuery):
    content_type = call.data.replace("content_", "")
    text = generate_content(content_type)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("✅ نشر المحتوى", callback_data=f"publish_{content_type}"),
        types.InlineKeyboardButton("❌ تجاهل المحتوى", callback_data="ignore_content")
    )
    await call.message.edit_text(f"المحتوى:\n\n{text}", reply_markup=kb)
    USERS[call.from_user.id]["last_content"] = text

@dp.callback_query(lambda c: c.data.startswith("publish_") or c.data == "ignore_content")
async def publish_or_ignore(call: types.CallbackQuery):
    uid = call.from_user.id
    if call.data == "ignore_content":
        await call.message.edit_text("تم تجاهل المحتوى.")
    else:
        text = USERS[uid].get("last_content", "")
        USERS[uid]["posts"] += 1
        await call.message.edit_text(f"تم نشر المحتوى:\n\n{text}")
        # VIP عبر الدعوات بعد 5 منشورات
        if USERS[uid]["posts"] >= 5 and not USERS[uid]["vip"]:
            ref_code = f"ref{uid}"
            REF_LINKS[ref_code] = uid
            USERS[uid]["ref"] = ref_code
            await bot.send_message(uid, f"للحصول على VIP ادعُ 10 أشخاص للاشتراك في القناة عبر رابطك:\nhttps://t.me/your_bot?start={ref_code}")

# --------- جدولة النشر ---------
@dp.callback_query(lambda c: c.data == "schedule_post")
async def schedule_menu(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("كل 6 ساعات", callback_data="sched_6"),
        types.InlineKeyboardButton("كل 12 ساعة", callback_data="sched_12"),
        types.InlineKeyboardButton("كل 24 ساعة", callback_data="sched_24"),
    )
    await call.message.edit_text("اختر توقيت النشر التلقائي:", reply_markup=kb)

@dp.callback_query(lambda c: c.data.startswith("sched_"))
async def set_schedule(call: types.CallbackQuery):
    hours = int(call.data.split("_")[1])
    USERS[call.from_user.id]["schedule"] = hours
    await call.message.edit_text(f"تم ضبط النشر التلقائي كل {hours} ساعة.")
    # يمكنك هنا تفعيل جدولة فعلية باستخدام asyncio أو APScheduler لاحقاً.

# --------- إدارة القنوات ---------
@dp.callback_query(lambda c: c.data == "manage_channels")
async def channel_menu(call: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(
        types.InlineKeyboardButton("➕ إضافة قناة", callback_data="add_channel"),
        types.InlineKeyboardButton("🗑 حذف قناة", callback_data="del_channel"),
        types.InlineKeyboardButton("📑 عرض القنوات المرتبطة", callback_data="list_channels"),
    )
    await call.message.edit_text("إدارة القنوات:", reply_markup=kb)

@dp.callback_query(lambda c: c.data == "add_channel")
async def ask_channel(call: types.CallbackQuery):
    await call.message.edit_text("أرسل اسم القناة (مثال: @mychannel).")

@dp.message(lambda message: message.text.startswith("@"))
async def add_channel_step(message: types.Message):
    uid = message.from_user.id
    ch = message.text.strip()
    if len(USERS[uid]["channels"]) >= MAX_USER_CHANNELS:
        await message.answer(f"لا يمكنك إضافة أكثر من {MAX_USER_CHANNELS} قناة.")
        return
    try:
        member = await bot.get_chat_member(ch, uid)
        if member.status not in ["administrator", "creator"]:
            await message.answer("يجب أن تكون مديرًا في القناة.")
            return
        USERS[uid]["channels"].add(ch)
        CHANNELS[ch] = uid
        await message.answer(f"تمت إضافة القناة {ch} للنشر التلقائي.")
    except Exception:
        await message.answer("تعذر العثور على القناة أو صلاحياتك غير كافية.")

@dp.callback_query(lambda c: c.data == "del_channel")
async def ask_del_channel(call: types.CallbackQuery):
    uid = call.from_user.id
    if USERS[uid]["channels"]:
        kb = types.InlineKeyboardMarkup()
        for ch in USERS[uid]["channels"]:
            kb.add(types.InlineKeyboardButton(f"حذف {ch}", callback_data=f"remove_{ch}"))
        await call.message.edit_text("اختر قناة للحذف:", reply_markup=kb)
    else:
        await call.message.edit_text("لا توجد قنوات مرتبطة.")

@dp.callback_query(lambda c: c.data.startswith("remove_"))
async def remove_channel(call: types.CallbackQuery):
    uid = call.from_user.id
    ch = call.data.replace("remove_", "")
    if ch in USERS[uid]["channels"]:
        USERS[uid]["channels"].remove(ch)
        CHANNELS.pop(ch, None)
        await call.message.edit_text(f"تم حذف القناة {ch}.")

@dp.callback_query(lambda c: c.data == "list_channels")
async def list_channels(call: types.CallbackQuery):
    uid = call.from_user.id
    if USERS[uid]["channels"]:
        txt = "\n".join(list(USERS[uid]["channels"]))
        await call.message.edit_text(f"قنواتك المرتبطة:\n{txt}")
    else:
        await call.message.edit_text("لا توجد قنوات مرتبطة.")

# --------- VIP ---------
@dp.callback_query(lambda c: c.data == "vip_status")
async def vip_status(call: types.CallbackQuery):
    uid = call.from_user.id
    if USERS[uid]["vip"]:
        await call.message.edit_text("عضويتك VIP ✅")
    else:
        invites = len(USERS[uid]["invites"])
        await call.message.edit_text(f"لست VIP بعد.\nدعوتك الحالية: {invites}/10\nرابط الإحالة: https://t.me/your_bot?start={USERS[uid]['ref']}")

@dp.message(commands=["start"])
async def referral_handler(message: types.Message):
    # معالجة رابط الإحالة عبر /start ref_code
    args = message.text.split(" ", 1)
    uid = message.from_user.id
    if len(args) > 1 and args[1].startswith("ref"):
        ref_code = args[1]
        inviter = REF_LINKS.get(ref_code)
        if inviter and inviter != uid:
            USERS.setdefault(uid, {"vip": False, "ref": "", "invites": set(), "channels": set(), "posts": 0, "last_vip": 0})
            USERS[inviter]["invites"].add(uid)
            # تحقق من الاشتراك الإجباري
            if await check_subscription(uid):
                if len(USERS[inviter]["invites"]) >= 10:
                    USERS[inviter]["vip"] = True
                    USERS[inviter]["last_vip"] = int(time.time())
                    await bot.send_message(inviter, "مبروك! تم تفعيل VIP تلقائيًا.")
            else:
                await message.answer("يرجى الاشتراك في القناة الإلزامية أولاً.")
        await start_msg(message)

# --------- إشعار المدير ---------
@dp.callback_query(lambda c: c.data == "manager_notice")
async def manager_notice(call: types.CallbackQuery):
    if GLOBAL_NOTIF:
        kb = types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("✔️ تم نشر الإشعار", callback_data="notif_done"),
            types.InlineKeyboardButton("❌ حذف الإشعار", callback_data="notif_del"),
        )
        await call.message.edit_text(f"إشعار المدير:\n{GLOBAL_NOTIF}", reply_markup=kb)
    else:
        await call.message.edit_text("لا يوجد إشعار حالياً.")

@dp.callback_query(lambda c: c.data == "notif_done")
async def notif_done(call: types.CallbackQuery):
    await call.message.edit_text("تمت قراءة الإشعار.")

@dp.callback_query(lambda c: c.data == "notif_del")
async def notif_del(call: types.CallbackQuery):
    global GLOBAL_NOTIF
    GLOBAL_NOTIF = None
    await call.message.edit_text("تم حذف الإشعار.")

# --------- إدارة المغادرين ---------
@dp.callback_query(lambda c: c.data == "manage_leavers")
async def manage_leavers(call: types.CallbackQuery):
    await call.message.edit_text("ميزة الحظر التلقائي للمغادرين غير مفعلة بالكود التجريبي.")

# --------- إعداداتي ---------
@dp.callback_query(lambda c: c.data == "my_settings")
async def my_settings(call: types.CallbackQuery):
    uid = call.from_user.id
    txt = f"عدد المنشورات: {USERS[uid]['posts']}\nVIP: {'✅' if USERS[uid]['vip'] else '❌'}\nقنوات مرتبطة: {len(USERS[uid]['channels'])}"
    await call.message.edit_text(txt)

# --------- لوحة المدير ---------
@dp.callback_query(lambda c: c.data == "admin_panel")
async def admin_panel(call: types.CallbackQuery):
    if call.from_user.id in ADMIN_IDS:
        await call.message.edit_text("قائمة المدير:", reply_markup=get_admin_panel())
    else:
        await call.answer("هذه القائمة للمدير فقط.", show_alert=True)

@dp.callback_query(lambda c: c.data == "send_global")
async def ask_global_notif(call: types.CallbackQuery):
    await call.message.edit_text("أرسل نص الإشعار المراد نشره للجميع.")

@dp.message(lambda message: message.text.startswith("إشعار:") and message.from_user.id in ADMIN_IDS)
async def set_global_notif(message: types.Message):
    global GLOBAL_NOTIF
    GLOBAL_NOTIF = message.text[7:]
    for uid in USERS:
        try:
            await bot.send_message(uid, f"إشعار المدير:\n{GLOBAL_NOTIF}")
        except: pass
    await message.answer("تم إرسال الإشعار للجميع.")

@dp.callback_query(lambda c: c.data == "del_global")
async def del_global(call: types.CallbackQuery):
    global GLOBAL_NOTIF
    GLOBAL_NOTIF = None
    await call.message.edit_text("تم حذف الإشعار العام.")

@dp.callback_query(lambda c: c.data == "manual_vip")
async def manual_vip(call: types.CallbackQuery):
    await call.message.edit_text("أرسل رقم المستخدم لتفعيل VIP يدويًا.")

@dp.message(lambda message: message.text.isdigit() and message.from_user.id in ADMIN_IDS)
async def activate_vip_manually(message: types.Message):
    uid = int(message.text)
    if uid in USERS:
        USERS[uid]["vip"] = True
        USERS[uid]["last_vip"] = int(time.time())
        await message.answer(f"تم تفعيل VIP للمستخدم {uid}.")
    else:
        await message.answer("المستخدم غير موجود.")

@dp.callback_query(lambda c: c.data == "review_users")
async def review_users(call: types.CallbackQuery):
    txt = ""
    for uid, data in USERS.items():
        txt += f"{uid}: VIP={'✅' if data['vip'] else '❌'} - دعوات: {len(data['invites'])}\n"
    await call.message.edit_text(txt if txt else "لا يوجد مستخدمين.")

@dp.callback_query(lambda c: c.data == "report_users")
async def report_users(call: types.CallbackQuery):
    total = len(USERS)
    vips = sum(1 for u in USERS.values() if u["vip"])
    await call.message.edit_text(f"عدد المستخدمين: {total}\nVIP: {vips}")

@dp.callback_query(lambda c: c.data == "manage_referrals")
async def manage_referrals(call: types.CallbackQuery):
    txt = ""
    for uid, data in USERS.items():
        if data["ref"]:
            txt += f"{uid}: {data['ref']} -> {len(data['invites'])} دعوة\n"
    await call.message.edit_text(txt if txt else "لا يوجد روابط إحالة.")

@dp.callback_query(lambda c: c.data == "set_required_channel")
async def set_required_channel(call: types.CallbackQuery):
    await call.message.edit_text("أرسل اسم القناة الإلزامية الجديد (مثال: @new_channel).")

@dp.message(lambda message: message.text.startswith("@") and message.from_user.id in ADMIN_IDS)
async def change_required_channel(message: types.Message):
    global CHANNEL_REQUIRED
    CHANNEL_REQUIRED = message.text.strip()
    await message.answer(f"تم تغيير القناة الإلزامية إلى: {CHANNEL_REQUIRED}")

@dp.callback_query(lambda c: c.data == "advanced_settings")
async def advanced_settings(call: types.CallbackQuery):
    await call.message.edit_text(
        f"الحد الأقصى للقنوات لكل مستخدم: {MAX_USER_CHANNELS}\nمدة VIP: {VIP_VALIDITY_DAYS} يوم\nميزة الحظر التلقائي: غير مفعلة بالكود التجريبي."
    )

# --------- تشغيل البوت على Render ---------
WEBHOOK_HOST = "https://boto7-r0c1.onrender.com"
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
PORT = int(os.environ.get("PORT", 8443))  # Render يحدد هذا تلقائياً

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(dp):
    await bot.delete_webhook()

if __name__ == "__main__":
    from aiogram import executor
    executor.start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="0.0.0.0",
        port=PORT,
    )