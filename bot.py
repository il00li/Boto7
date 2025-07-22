import telebot
from telebot import types
import requests
import threading
import time

# --------------------- إعدادات البوت ---------------------
TOKEN = "7639996535:AAH_Ppw8jeiUg4nJjjEyOXaYlip289jSAio"
ADMIN_ID = 7251748706
GEMINI_API_KEY = "AIzaSyAEULfP5zi5irv4yRhFugmdsjBoLk7kGsE"
BOT_USERNAME = "@BARM7_BOT"
MANDATORY_CHANNEL_ID = None    # يتم ضبطه من لوحة التحكم
MAX_CHANNELS_PER_USER = 2      # قابل للتعديل من لوحة التحكم
VIP_DURATION_DAYS = 7          # قابل للتعديل من لوحة التحكم

bot = telebot.TeleBot(TOKEN)

# --------------------- قواعد بيانات مؤقتة (للتجربة أو الاستبدال بـ MongoDB) ---------------------
users = {}   # user_id: {'vip': False, 'channels': [], 'invite_count': 0, 'invitees': set(), 'auto_post': {'interval': None, 'next': None}}
pending_content = {}  # user_id: {'type': '', 'text': ''}
invites = {}  # user_id: set(invited_user_ids)
notifications = []  # [{'msg_id': ..., 'text': ...}]
banned_users = set()
mandatory_channel_subs = set()
admin_settings = {
    "ban_leavers": True,
    "max_channels": MAX_CHANNELS_PER_USER,
    "vip_duration": VIP_DURATION_DAYS,
    "mandatory_channel": None
}

waiting_for_admin_notif = False

# --------------------- الدوال المساعدة ---------------------
def check_subscription(user_id):
    """
    تحقق من اشتراك المستخدم في القناة الإلزامية باستخدام Telegram API.
    """
    if not admin_settings["mandatory_channel"]:
        return True
    try:
        chat_member = bot.get_chat_member(admin_settings["mandatory_channel"], user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception:
        return False

def get_gemini_content(content_type):
    """
    توليد محتوى بواسطة Gemini API حسب نوع المحتوى.
    """
    prompts = {
        "egyptian_dark_phrase": "اكتب عبارة سوداوية باللهجة المصرية.",
        "motivational": "اكتب عبارة تحفيزية قصيرة.",
        "dark_joke": "اكتب نكتة سوداوية لكنها مضحكة باللهجة المصرية.",
        "philosophy": "اكتب جملة فلسفية عن الحياة.",
        "mysterious": "اكتب عبارة غامضة رمزية.",
        "sad_quote": "اعطني اقتباسًا حزينًا من الأدب أو الشعر."
    }
    prompt = prompts.get(content_type, "اكتب عبارة عشوائية.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    res = requests.post(url, json=payload)
    try:
        return res.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        return "حدث خطأ أثناء توليد المحتوى. حاول مرة أخرى لاحقًا."

def is_admin(user_id):
    return user_id == ADMIN_ID

def is_vip(user_id):
    return users.get(user_id, {}).get("vip", False)

def get_user_channels(user_id):
    return users.get(user_id, {}).get("channels", [])

def add_user_channel(user_id, channel_id):
    if user_id not in users:
        users[user_id] = {"vip": False, "channels": [], "invite_count": 0, "invitees": set(), "auto_post": {"interval": None, "next": None}}
    if channel_id not in users[user_id]["channels"] and len(users[user_id]["channels"]) < admin_settings["max_channels"]:
        users[user_id]["channels"].append(channel_id)

def remove_user_channel(user_id, channel_id):
    if user_id in users and channel_id in users[user_id]["channels"]:
        users[user_id]["channels"].remove(channel_id)

def vip_invite_check(user_id):
    invitees = users[user_id]["invitees"]
    for invited_id in invitees:
        if not check_subscription(invited_id):
            return False
    return len(invitees) >= 10

def schedule_autopost():
    while True:
        now = time.time()
        for user_id, u in users.items():
            auto = u.get("auto_post", {})
            if auto.get("interval") and auto.get("next") and now >= auto["next"]:
                if get_user_channels(user_id):
                    text = get_gemini_content("egyptian_dark_phrase")
                    for ch in get_user_channels(user_id):
                        try:
                            bot.send_message(ch, text)
                        except Exception: pass
                users[user_id]["auto_post"]["next"] = now + auto["interval"]
        time.sleep(30)

threading.Thread(target=schedule_autopost, daemon=True).start()

# --------------------- الأزرار الرئيسية ---------------------
def main_menu(user_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🧠 توليد محتوى", callback_data="generate_content"),
        types.InlineKeyboardButton("📅 جدولة النشر", callback_data="schedule_post"),
        types.InlineKeyboardButton("➕ إدارة القنوات", callback_data="manage_channels"),
        types.InlineKeyboardButton("⭐ العضوية VIP", callback_data="vip_info"),
        types.InlineKeyboardButton("📢 إشعار المدير", callback_data="notification"),
        types.InlineKeyboardButton("🔒 إدارة المغادرين", callback_data="ban_leavers"),
        types.InlineKeyboardButton("⚙️ إعداداتي", callback_data="settings")
    )
    if is_admin(user_id):
        kb.add(types.InlineKeyboardButton("👨‍💼 مدير النظام", callback_data="admin_panel"))
    return kb

# --------------------- بدء البوت ---------------------
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    if user_id in banned_users:
        return
    if admin_settings["mandatory_channel"] and not check_subscription(user_id):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✅ اشتركت", callback_data="check_sub"))
        bot.send_message(user_id, f"يرجى الاشتراك في القناة أولاً:\nhttps://t.me/{admin_settings['mandatory_channel']}", reply_markup=kb)
        return
    bot.send_message(user_id, "مرحبًا بك في بوت الذكاء الاصطناعي!\nاختر من القائمة:", reply_markup=main_menu(user_id))

# --------------------- تحقق الاشتراك الإجباري ---------------------
@bot.callback_query_handler(func=lambda call: call.data == "check_sub")
def check_sub(call):
    user_id = call.from_user.id
    if check_subscription(user_id):
        bot.send_message(user_id, "تم التحقق من الاشتراك! يمكنك الآن استخدام البوت.", reply_markup=main_menu(user_id))
    else:
        bot.answer_callback_query(call.id, "يرجى الاشتراك أولاً.")

# --------------------- قائمة توليد المحتوى ---------------------
@bot.callback_query_handler(func=lambda call: call.data == "generate_content")
def generate_content_menu(call):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("سوداوية باللهجة المصرية", callback_data="gen_egyptian_dark_phrase"),
        types.InlineKeyboardButton("تحفيزية قصيرة", callback_data="gen_motivational"),
        types.InlineKeyboardButton("نكتة سوداوية مضحكة", callback_data="gen_dark_joke"),
        types.InlineKeyboardButton("فلسفية عن الحياة", callback_data="gen_philosophy"),
        types.InlineKeyboardButton("غامضة رمزية", callback_data="gen_mysterious"),
        types.InlineKeyboardButton("اقتباس حزين", callback_data="gen_sad_quote"),
    )
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu"))
    bot.edit_message_text("اختر نوع المحتوى:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("gen_"))
def generate_content_type(call):
    user_id = call.from_user.id
    content_type = call.data.replace("gen_", "")
    text = get_gemini_content(content_type)
    pending_content[user_id] = {'type': content_type, 'text': text}
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ نشر المحتوى", callback_data="publish_content"))
    kb.add(types.InlineKeyboardButton("❌ تجاهل المحتوى", callback_data="ignore_content"))
    bot.edit_message_text(f"المحتوى المُولد:\n\n{text}", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == "publish_content")
def publish_content(call):
    user_id = call.from_user.id
    data = pending_content.get(user_id)
    if not data:
        return
    channels = get_user_channels(user_id)
    if not channels:
        bot.send_message(user_id, "لم تقم بإضافة قنوات للنشر!")
        return
    for ch in channels:
        try:
            bot.send_message(ch, data['text'])
        except Exception: pass
    bot.send_message(user_id, "تم نشر المحتوى بنجاح!")
    pending_content.pop(user_id, None)
    if user_id not in users:
        users[user_id] = {"vip": False, "channels": [], "invite_count": 1, "invitees": set(), "auto_post": {"interval": None, "next": None}}
    else:
        users[user_id]["invite_count"] = users[user_id].get("invite_count", 0) + 1
    if users[user_id]["invite_count"] == 5 and not is_vip(user_id):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("رابط الإحالة", url=f"https://t.me/{BOT_USERNAME}?start={user_id}"))
        bot.send_message(user_id, "لقد وصلت إلى الحد الأقصى للنشر المجاني.\nادعُ 10 أشخاص واشترط اشتراكهم في القناة الإلزامية للحصول على VIP.", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == "ignore_content")
def ignore_content(call):
    user_id = call.from_user.id
    pending_content.pop(user_id, None)
    bot.send_message(user_id, "تم تجاهل المحتوى.", reply_markup=main_menu(user_id))

# --------------------- جدولة النشر ---------------------
@bot.callback_query_handler(func=lambda call: call.data == "schedule_post")
def schedule_post_menu(call):
    kb = types.InlineKeyboardMarkup(row_width=3)
    kb.add(
        types.InlineKeyboardButton("كل 6 ساعات", callback_data="schedule_6"),
        types.InlineKeyboardButton("كل 12 ساعة", callback_data="schedule_12"),
        types.InlineKeyboardButton("كل 24 ساعة", callback_data="schedule_24"),
        types.InlineKeyboardButton("إيقاف الجدولة", callback_data="schedule_off"),
        types.InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu"),
    )
    bot.edit_message_text("اختر توقيت النشر التلقائي:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("schedule_"))
def set_schedule(call):
    user_id = call.from_user.id
    interval_map = {'6': 6*3600, '12': 12*3600, '24': 24*3600}
    opt = call.data.replace("schedule_", "")
    if opt == "off":
        users[user_id]["auto_post"] = {"interval": None, "next": None}
        bot.send_message(user_id, "تم إيقاف النشر التلقائي.")
    else:
        users.setdefault(user_id, {}).setdefault("auto_post", {})
        users[user_id]["auto_post"]["interval"] = interval_map[opt]
        users[user_id]["auto_post"]["next"] = time.time() + interval_map[opt]
        bot.send_message(user_id, f"تم جدولة النشر كل {opt} ساعة.")

# --------------------- إدارة القنوات ---------------------
@bot.callback_query_handler(func=lambda call: call.data == "manage_channels")
def manage_channels_menu(call):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("➕ إضافة قناة", callback_data="add_channel"),
        types.InlineKeyboardButton("➖ حذف قناة", callback_data="remove_channel"),
        types.InlineKeyboardButton("📋 عرض القنوات", callback_data="show_channels"),
        types.InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu"),
    )
    bot.edit_message_text("إدارة قنواتك:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == "add_channel")
def add_channel_step1(call):
    bot.send_message(call.message.chat.id, "أرسل معرف القناة (@channel أو ID) التي تريد إضافتها.")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("@"))
def add_channel_step2(message):
    user_id = message.from_user.id
    ch = message.text
    try:
        admins = bot.get_chat_administrators(ch)
        if any(a.user.id == user_id for a in admins):
            add_user_channel(user_id, ch)
            bot.send_message(user_id, f"تمت إضافة القناة: {ch}")
        else:
            bot.send_message(user_id, "يجب أن تكون مديرًا في القناة.")
    except Exception:
        bot.send_message(user_id, "تأكد أنك أضفت البوت كمدير في القناة.")

@bot.callback_query_handler(func=lambda call: call.data == "remove_channel")
def remove_channel_step1(call):
    user_id = call.from_user.id
    channels = get_user_channels(user_id)
    if not channels:
        bot.send_message(user_id, "لا توجد قنوات مرتبطة بك.")
        return
    kb = types.InlineKeyboardMarkup(row_width=1)
    for ch in channels:
        kb.add(types.InlineKeyboardButton(ch, callback_data=f"delch_{ch}"))
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data="manage_channels"))
    bot.send_message(user_id, "اختر القناة لحذفها:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data.startswith("delch_"))
def remove_channel_step2(call):
    user_id = call.from_user.id
    ch = call.data.replace("delch_", "")
    remove_user_channel(user_id, ch)
    bot.send_message(user_id, f"تم حذف القناة: {ch}")

@bot.callback_query_handler(func=lambda call: call.data == "show_channels")
def show_channels(call):
    user_id = call.from_user.id
    channels = get_user_channels(user_id)
    if channels:
        bot.send_message(user_id, "قنواتك المرتبطة:\n" + "\n".join(channels))
    else:
        bot.send_message(user_id, "لا توجد قنوات مرتبطة بك.")

# --------------------- العضوية VIP ---------------------
@bot.callback_query_handler(func=lambda call: call.data == "vip_info")
def vip_info(call):
    user_id = call.from_user.id
    if is_vip(user_id):
        bot.send_message(user_id, "عضويتك VIP ✅")
    else:
        bot.send_message(user_id, "للحصول على VIP:\nانشر 5 مرات وادعُ 10 أشخاص للاشتراك في القناة الإلزامية.")

@bot.message_handler(func=lambda m: m.text and m.text.startswith("/start "))
def referral_link(message):
    referrer_id = int(message.text.split()[1])
    user_id = message.from_user.id
    if user_id == referrer_id: return
    if referrer_id in users:
        users[referrer_id]["invitees"].add(user_id)
        if vip_invite_check(referrer_id):
            users[referrer_id]["vip"] = True
            bot.send_message(referrer_id, "تم تفعيل VIP تلقائيًا!")
        else:
            bot.send_message(referrer_id, f"عدد المدعوين الحالي: {len(users[referrer_id]['invitees'])}/10")
    bot.send_message(user_id, "شكرًا على الانضمام!")

# --------------------- إشعار المدير ---------------------
@bot.callback_query_handler(func=lambda call: call.data == "notification")
def notification(call):
    user_id = call.from_user.id
    latest = notifications[-1] if notifications else None
    if latest:
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("✔️ تم نشر الإشعار", callback_data="notif_ack"))
        bot.send_message(user_id, latest["text"], reply_markup=kb)
    else:
        bot.send_message(user_id, "لا يوجد إشعار عام حالي.")

@bot.callback_query_handler(func=lambda call: call.data == "notif_ack")
def notif_ack(call):
    bot.answer_callback_query(call.id, "تم تأكيد النشر.")

# --------------------- إدارة المغادرين ---------------------
@bot.callback_query_handler(func=lambda call: call.data == "ban_leavers")
def ban_leavers(call):
    status = "مفعل ✅" if admin_settings["ban_leavers"] else "متوقف ❌"
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("تشغيل", callback_data="ban_on"))
    kb.add(types.InlineKeyboardButton("إيقاف", callback_data="ban_off"))
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu"))
    bot.edit_message_text(f"حظر المغادرين: {status}", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == "ban_on")
def ban_on(call):
    admin_settings["ban_leavers"] = True
    bot.send_message(call.message.chat.id, "تم تشغيل الحظر.")

@bot.callback_query_handler(func=lambda call: call.data == "ban_off")
def ban_off(call):
    admin_settings["ban_leavers"] = False
    bot.send_message(call.message.chat.id, "تم إيقاف الحظر.")

# --------------------- قائمة الإعدادات الشخصية ---------------------
@bot.callback_query_handler(func=lambda call: call.data == "settings")
def settings(call):
    user_id = call.from_user.id
    txt = "إعداداتك:\n"
    txt += f"- VIP: {'✅' if is_vip(user_id) else '❌'}\n"
    txt += f"- عدد القنوات: {len(get_user_channels(user_id))}/{admin_settings['max_channels']}\n"
    txt += f"- النشر التلقائي: {'مفعل' if users.get(user_id, {}).get('auto_post', {}).get('interval') else 'غير مفعل'}"
    bot.send_message(user_id, txt)

# --------------------- لوحة المدير ---------------------
@bot.callback_query_handler(func=lambda call: call.data == "admin_panel")
def admin_panel(call):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("📢 إرسال إشعار عام", callback_data="admin_send_notif"),
        types.InlineKeyboardButton("❌ حذف الإشعار العام", callback_data="admin_delete_notif"),
        types.InlineKeyboardButton("📡 تعيين قناة الاشتراك الإجباري", callback_data="admin_set_mandatory"),
        types.InlineKeyboardButton("👤 تفعيل عضوية VIP يدويًا", callback_data="admin_vip_manual"),
        types.InlineKeyboardButton("🔍 مراجعة حالة المستخدمين", callback_data="admin_review_users"),
        types.InlineKeyboardButton("🧑‍💼 إدارة روابط الإحالة", callback_data="admin_manage_invites"),
        types.InlineKeyboardButton("📊 تقرير عام للمستخدمين", callback_data="admin_report"),
        types.InlineKeyboardButton("⚙️ إعدادات متقدمة", callback_data="admin_advanced")
    )
    kb.add(types.InlineKeyboardButton("⬅️ رجوع", callback_data="main_menu"))
    bot.edit_message_text("لوحة المدير:", call.message.chat.id, call.message.message_id, reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == "admin_send_notif")
def admin_send_notif(call):
    global waiting_for_admin_notif
    waiting_for_admin_notif = True
    bot.send_message(ADMIN_ID, "أرسل النص للإشعار العام.")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and waiting_for_admin_notif)
def admin_notif_text(message):
    global waiting_for_admin_notif
    notifications.append({"msg_id": message.message_id, "text": message.text})
    for uid in users:
        try:
            bot.send_message(uid, message.text)
            for ch in get_user_channels(uid):
                bot.send_message(ch, message.text)
        except Exception: pass
    waiting_for_admin_notif = False

@bot.callback_query_handler(func=lambda call: call.data == "admin_delete_notif")
def admin_delete_notif(call):
    notifications.clear()
    bot.send_message(ADMIN_ID, "تم حذف جميع الإشعارات.")

@bot.callback_query_handler(func=lambda call: call.data == "admin_set_mandatory")
def admin_set_mandatory(call):
    bot.send_message(ADMIN_ID, "أرسل معرف القناة الإلزامية (@channel أو ID).")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text.startswith("@"))
def set_mandatory_channel(message):
    admin_settings["mandatory_channel"] = message.text.replace("@", "")
    bot.send_message(ADMIN_ID, f"تم تعيين القناة الإلزامية: {admin_settings['mandatory_channel']}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_vip_manual")
def admin_vip_manual(call):
    bot.send_message(ADMIN_ID, "أرسل رقم المستخدم (ID) لتفعيل VIP يدويًا.")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text.isdigit())
def admin_vip_manual_id(message):
    uid = int(message.text)
    if uid in users:
        users[uid]["vip"] = True
        bot.send_message(ADMIN_ID, f"تم تفعيل VIP للمستخدم {uid}")
        bot.send_message(uid, "تم تفعيل عضوية VIP يدويًا من المدير.")
    else:
        bot.send_message(ADMIN_ID, "المستخدم غير موجود.")

@bot.callback_query_handler(func=lambda call: call.data == "admin_review_users")
def admin_review_users(call):
    txt = ""
    for uid, u in users.items():
        txt += f"ID: {uid}, VIP: {'✅' if u.get('vip') else '❌'}, دعوات: {len(u.get('invitees', []))}, اشتراك: {check_subscription(uid)}\n"
    bot.send_message(ADMIN_ID, txt or "لا يوجد مستخدمون.")

@bot.callback_query_handler(func=lambda call: call.data == "admin_manage_invites")
def admin_manage_invites(call):
    txt = ""
    for uid, u in users.items():
        txt += f"ID: {uid}, دعوات: {len(u.get('invitees', []))}\n"
    bot.send_message(ADMIN_ID, txt or "لا يوجد بيانات دعوات.")

@bot.callback_query_handler(func=lambda call: call.data == "admin_report")
def admin_report(call):
    total = len(users)
    vips = sum(1 for u in users.values() if u.get("vip"))
    bot.send_message(ADMIN_ID, f"تقرير المستخدمين:\nإجمالي: {total}\nVIP: {vips}")

@bot.callback_query_handler(func=lambda call: call.data == "admin_advanced")
def admin_advanced(call):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("تشغيل حظر المغادرين", callback_data="ban_on"),
        types.InlineKeyboardButton("إيقاف حظر المغادرين", callback_data="ban_off"),
        types.InlineKeyboardButton("ضبط الحد الأقصى للقنوات", callback_data="set_max_channels"),
        types.InlineKeyboardButton("ضبط مدة VIP", callback_data="set_vip_duration"),
        types.InlineKeyboardButton("⬅️ رجوع", callback_data="admin_panel"),
    )
    bot.send_message(ADMIN_ID, "إعدادات متقدمة:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: call.data == "set_max_channels")
def set_max_channels(call):
    bot.send_message(ADMIN_ID, "أرسل رقم الحد الأقصى للقنوات لكل مستخدم.")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text.isdigit())
def set_max_channels_value(message):
    admin_settings["max_channels"] = int(message.text)
    bot.send_message(ADMIN_ID, f"تم ضبط الحد الأقصى للقنوات: {admin_settings['max_channels']}")

@bot.callback_query_handler(func=lambda call: call.data == "set_vip_duration")
def set_vip_duration(call):
    bot.send_message(ADMIN_ID, "أرسل مدة صلاحية VIP بالأيام.")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text.isdigit())
def set_vip_duration_value(message):
    admin_settings["vip_duration"] = int(message.text)
    bot.send_message(ADMIN_ID, f"تم ضبط مدة VIP: {admin_settings['vip_duration']} يوم")

@bot.callback_query_handler(func=lambda call: call.data == "main_menu")
def return_main_menu(call):
    bot.edit_message_text("القائمة الرئيسية:", call.message.chat.id, call.message.message_id, reply_markup=main_menu(call.from_user.id))

# --------------------- تشغيل البوت ---------------------
if __name__ == "__main__":
    print("Bot started...")
    bot.infinity_polling()
