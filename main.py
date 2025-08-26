import telebot
from telebot import types
import config
import database
import requests

bot = telebot.TeleBot(config.TOKEN)

# تهيئة قاعدة البيانات
database.init_db()

# دالة التحقق من الاشتراك
def is_subscribed(user_id):
    try:
        member = bot.get_chat_member(config.CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except:
        return False

# دالة إرسال رسالة الاشتراك الإجباري
def send_subscription_message(chat_id):
    markup = types.InlineKeyboardMarkup()
    btn_channel = types.InlineKeyboardButton("اشترك في القناة 🌐", url=config.CHANNEL_URL)
    btn_check = types.InlineKeyboardButton("تحقق 👀", callback_data="check_subscription")
    markup.add(btn_channel)
    markup.add(btn_check)
    bot.send_message(chat_id, "(／。＼)ノ\nاشتراك في القناة عبر الزر بالأسفل ثم اضغط على \"تحقق 👀\"", reply_markup=markup)

# الدالة الرئيسية — عرض القائمة
def main_menu():
    markup = types.InlineKeyboardMarkup()
    btn_search = types.InlineKeyboardButton("بدء البحث 🫐", callback_data="start_search")
    btn_type = types.InlineKeyboardButton("نوع البحث 🍇", callback_data="select_type")
    btn_info = types.InlineKeyboardButton("معلومات 🪻", callback_data="info")
    markup.row(btn_type)
    markup.row(btn_search)
    markup.row(btn_info)
    return markup

# أمر /start
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    username = message.from_user.username or "unknown"
    referrer_id = None

    # معالجة رابط الدعوة
    if len(message.text.split()) > 1:
        ref_code = message.text.split()[1]
        if ref_code.startswith("ref") and ref_code[3:].isdigit():
            referrer_id = int(ref_code[3:])
            if referrer_id != user_id:
                database.add_user(referrer_id, "", ref_code)  # تأكد من وجود المرجع

    database.add_user(user_id, username, database.generate_referral_code(user_id))
    user = database.get_user(user_id)

    if user[8] == 1:  # إذا كان محظورًا
        bot.send_message(user_id, "🚫 تم حظرك من استخدام هذا البوت.")
        return

    bot.send_message(user_id, 
        "(＾▽＾)／ \n"
        "اختر نوع البحث من \"نوع البحث 🍇\" وابدء البحث عبر \"بدء البحث 🫐\"", 
        reply_markup=main_menu())

# الكولباكات
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    user_id = call.from_user.id
    user = database.get_user(user_id)

    if user and user[8] == 1:  # محظور
        bot.answer_callback_query(call.id, "🚫 أنت محظور من استخدام هذا البوت.")
        return

    if call.data == "info":
        referral_link = f"https://t.me/{config.BOT_USERNAME}?start={user[3]}"
        info_msg = (
            "💛 | البوت مدفوع ، يمكنك طلب الاشتراك من المطور @OlIiIl7\n"
            "🧡 | يمكن الحصول على الاشتراك عن طريق رابط الدعوة ، قم بدعوة 10 اشخاص للحصول عليها\n"
            "❤️ | او يمكنك الحصول على الملحقات التي تم البحث عنها في القناة @GRABOT7\n"
            "🤍 | ترقبو التحديثات القادمة \n"
            "https://t.me/iIl337  \n\n"
            f"🔗 رابط الدعوة الخاص بك:\n{referral_link}\n"
            "عدد من دعوتهم: " + str(user[6]) + "/10"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("رجوع 🏡", callback_data="back_main"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text=info_msg, reply_markup=markup)

    elif call.data == "select_type":
        markup = types.InlineKeyboardMarkup()
        current_type = user[2] if user[2] else None

        # أزرار الأنواع
        types_btns = [
            ("Illustration | رسومات", "type_illustration"),
            ("Photo | صور", "type_photo"),
            ("Video | فيديو", "type_video")
        ]

        for text, cb_data in types_btns:
            mark = " 🪐" if current_type and cb_data == f"type_{current_type.lower()}" else ""
            markup.add(types.InlineKeyboardButton(text + mark, callback_data=cb_data))

        markup.add(types.InlineKeyboardButton("رجوع 🏡", callback_data="back_main"))
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text="اختر نوع البحث:", reply_markup=markup)

    elif call.data.startswith("type_"):
        search_type = call.data.split("_")[1].capitalize()
        database.update_search_type(user_id, search_type)
        bot.answer_callback_query(call.id, f"✅ تم تعيين نوع البحث إلى: {search_type}")
        bot.edit_message_reply_markup(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                      reply_markup=main_menu())

    elif call.data == "start_search":
        if not is_subscribed(user_id):
            send_subscription_message(user_id)
            return

        if user[4] == 0:  # غير مشترك في العضوية
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("طلب الاشتراك 💬", url=f"tg://user?id={config.OWNER_ID}"))
            markup.add(types.InlineKeyboardButton("اشتراك مجاني 🏖️", callback_data="referral"))
            bot.send_message(user_id, 
                "(ง'‌-'‌)ง\n"
                "ليس لديك صلاحية البحث، انقر على الزر أدناه لطلب الاشتراك", 
                reply_markup=markup)
        else:
            bot.send_message(user_id, f"🔎 جاري البحث عن {user[2]}... (مُزيف للتجربة)")

    elif call.data == "referral":
        referral_link = f"https://t.me/{config.BOT_USERNAME}?start={user[3]}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("رجوع 🏡", callback_data="back_main"))
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"🔗 شارك هذا الرابط مع أصدقائك:\n\n{referral_link}\n\nعدد من دعوتهم: {user[6]}/10",
            reply_markup=markup
        )

    elif call.data == "check_subscription":
        if is_subscribed(user_id):
            database.set_subscription(user_id, 1)
            bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                  text="✅ تم التحقق! يمكنك الآن استخدام البوت.", reply_markup=main_menu())
        else:
            bot.answer_callback_query(call.id, "❌ لم تُشترك بعد!")

    elif call.data == "back_main":
        bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                              text="(＾▽＾)／ \nاختر نوع البحث من \"نوع البحث 🍇\" وابدء البحث عبر \"بدء البحث 🫐\"",
                              reply_markup=main_menu())

# مراقبة روابط الدعوة
@bot.message_handler(func=lambda message: message.text.startswith("/start ref"))
def handle_referral(message):
    referrer_id = int(message.text.split("ref")[1])
    user_id = message.from_user.id
    if user_id == referrer_id:
        return
    user = database.get_user(referrer_id)
    if user:
        count = database.increment_referral(referrer_id)
        bot.send_message(referrer_id, f"🎉 شخص جديد انضم عبر رابطك! العدد: {count}/10")
        if count >= 10:
            database.set_subscription(referrer_id, 1)
            bot.send_message(referrer_id, "🎉 تم تفعيل عضويتك المدفوعة لمدة شهر! يمكنك الآن البحث.")

# أوامر المدير
@bot.message_handler(commands=['ban'])
def ban_user_cmd(message):
    if message.from_user.id != config.OWNER_ID:
        return
    try:
        user_id = int(message.text.split()[1])
        database.ban_user(user_id)
        bot.send_message(message.chat.id, f"✅ تم حظر المستخدم {user_id}")
    except:
        bot.send_message(message.chat.id, "❌ خطأ في حظر المستخدم.")

@bot.message_handler(commands=['unban'])
def unban_user_cmd(message):
    if message.from_user.id != config.OWNER_ID:
        return
    try:
        user_id = int(message.text.split()[1])
        database.unban_user(user_id)
        bot.send_message(message.chat.id, f"✅ تم فك الحظر عن المستخدم {user_id}")
    except:
        bot.send_message(message.chat.id, "❌ خطأ في فك الحظر.")

@bot.message_handler(commands=['activate'])
def activate_user(message):
    if message.from_user.id != config.OWNER_ID:
        return
    try:
        user_id = int(message.text.split()[1])
        database.set_subscription(user_id, 1)
        bot.send_message(message.chat.id, f"✅ تم تفعيل العضوية للمستخدم {user_id}")
        bot.send_message(user_id, "🎉 تم تفعيل عضويتك من قبل المدير!")
    except:
        bot.send_message(message.chat.id, "❌ خطأ في التفعيل.")

@bot.message_handler(commands=['deactivate'])
def deactivate_user(message):
    if message.from_user.id != config.OWNER_ID:
        return
    try:
        user_id = int(message.text.split()[1])
        database.set_subscription(user_id, 0)
        bot.send_message(message.chat.id, f"✅ تم إلغاء العضوية للمستخدم {user_id}")
        bot.send_message(user_id, "⚠️ تم إلغاء عضويتك.")
    except:
        bot.send_message(message.chat.id, "❌ خطأ في الإلغاء.")

@bot.message_handler(commands=['broadcast'])
def broadcast(message):
    if message.from_user.id != config.OWNER_ID:
        return
    text = message.text[len("/broadcast "):]
    if not text:
        bot.send_message(message.chat.id, "استخدم: /broadcast [الرسالة]")
        return
    user_ids = database.get_all_user_ids()
    for uid in user_ids:
        try:
            bot.send_message(uid, text)
        except Exception as e:
            print(f"فشل في إرسال للمستخدم {uid}: {e}")
    bot.send_message(message.chat.id, f"✅ تم الإرسال إلى {len(user_ids)} مستخدمًا.")

# تشغيل البوت
if __name__ == '__main__':
    print("Bot is running...")
    bot.polling(none_stop=True) 
