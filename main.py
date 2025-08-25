import telebot
from telebot import types
import datetime
from config import *
from storage import *
from keyboards import *
from utils import is_subscribed, generate_invite_code

# تهيئة البوت
bot = telebot.TeleBot(BOT_TOKEN)

# معالجة الأمر /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name
    
    # حفظ المستخدم إذا لم يكن موجوداً
    user_data = get_user(user_id)
    if not user_data:
        user_data = {
            'username': username,
            'full_name': full_name,
            'subscription_end': None,
            'is_banned': False,
            'invite_code': None,
            'invited_count': 0
        }
        save_user(user_id, user_data)
    
    # معالجة رابط الدعوة إذا وجد
    if len(message.text.split()) > 1:
        invite_code = message.text.split()[1]
        
        # البحث عن صاحب كود الدعوة
        owner_id = find_user_by_invite_code(invite_code)
        if owner_id and owner_id != user_id:
            # زيادة عداد الدعوات لصاحب الكود
            new_count = increment_invite_count(owner_id)
            
            # إرسال إشعار لصاحب الدعوة
            try:
                bot.send_message(owner_id, f"🎉 انضم عضو جديد عبر رابط الدعوة الخاص بك! الآن لديك {new_count} دعوة.")
            except:
                pass
    
    # التحقق من الاشتراك في القناة
    if not is_subscribed(bot, user_id, CHANNEL_USERNAME):
        bot.send_message(message.chat.id, 
                        "(／。＼)ノ\nاشتراك في القناة عبر الزر بالأسفل ثم اضغط على \"تحقق 👀\"", 
                        reply_markup=force_subscribe_keyboard())
        return
    
    # إرسال رسالة الترحيب
    welcome_text = "(＾▽＾)／ \nاختر نوع البحث من\" نوع البحث 🍇\" وابدء البحث عبر \"بدء البحث 🫐\"\n\nالمطور @OlIiIl7"
    bot.send_message(message.chat.id, welcome_text, reply_markup=main_menu_keyboard())

# معالجة الأزرار الإنلاين
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    
    # التحقق من الاشتراك أولاً
    if not is_subscribed(bot, user_id, CHANNEL_USERNAME) and call.data != "check_subscription":
        bot.answer_callback_query(call.id, "يجب الاشتراك في القناة أولاً")
        return
    
    if call.data == "start_search":
        # التحقق من صلاحية البحث
        if not check_subscription(user_id):
            bot.answer_callback_query(call.id, "ليس لديك صلاحية البحث")
            bot.edit_message_text("(ง'‌-'‌)ง\nليس لديك صلاحية البحث، انقر على الزر ادناة لطلب الاشتراك", 
                                 chat_id, message_id, 
                                 reply_markup=subscription_keyboard(user_id))
            return
        
        # بدء البحث بناءً على النوع المحدد
        search_type = get_search_type(user_id)
        # هنا يمكنك إضافة منطق البحث الفعلي
        bot.answer_callback_query(call.id, f"سيتم البحث عن {search_type}")
    
    elif call.data == "search_type":
        current_type = get_search_type(user_id)
        bot.edit_message_text("اختر نوع البحث:", chat_id, message_id, 
                             reply_markup=search_type_keyboard(current_type))
    
    elif call.data.startswith("set_type_"):
        search_type = call.data.split("_")[2]
        set_search_type(user_id, search_type)
        bot.answer_callback_query(call.id, f"تم اختيار: {search_type}")
        bot.edit_message_reply_markup(chat_id, message_id, 
                                     reply_markup=search_type_keyboard(search_type))
    
    elif call.data == "back_to_main":
        welcome_text = "(＾▽＾)／ \nاختر نوع البحث من\" نوع البحث 🍇\" وابدء البحث عبر \"بدء البحث 🫐\"\n\nالمطور @OlIiIl7"
        bot.edit_message_text(welcome_text, chat_id, message_id, 
                             reply_markup=main_menu_keyboard())
    
    elif call.data == "info":
        info_text = """
💛 | البوت مدفوع ، يمكنك طلب الاشتراك من المطور @OlIiIl7
🧡 | يمكن الحصول على الاشتراك عن طريق رابط الدعوة ، قم بدعوة 10 اشخاص للحصول عليها
❤️ | او يمكنك الحصول على الملحقات التي تم البحث عنها في القناة @GRABOT7
🤍 | ترقبو التحديثات القادمة 
https://t.me/iIl337

- قناة الاشتراك الاجباري
https://t.me/iIl337
        """
        bot.edit_message_text(info_text, chat_id, message_id, 
                             reply_markup=main_menu_keyboard())
    
    elif call.data == "free_subscription":
        # إنشاء رابط دعوة فريد
        invite_code = get_invite_code(user_id)
        
        if not invite_code:
            invite_code = generate_invite_code()
            set_invite_code(user_id, invite_code)
        
        invite_link = f"https://t.me/{bot.get_me().username}?start={invite_code}"
        bot.edit_message_text(f"رابط الدعوة الخاص بك:\n{invite_link}\n\nادعُ 10 أصدقاء للحصول على اشتراك مجاني لمدة شهر!", 
                             chat_id, message_id, 
                             reply_markup=main_menu_keyboard())
    
    elif call.data == "check_subscription":
        if is_subscribed(bot, user_id, CHANNEL_USERNAME):
            welcome_text = "(＾▽＾)／ \nاختر نوع البحث من\" نوع البحث 🍇\" وابدء البحث عبر \"بدء البحث 🫐\"\n\nالمطور @OlIiIl7"
            bot.edit_message_text(welcome_text, chat_id, message_id, 
                                 reply_markup=main_menu_keyboard())
        else:
            bot.answer_callback_query(call.id, "لم تشترك في القناة بعد")
    
    # أوامر المدير
    elif call.data == "admin_panel" and user_id == ADMIN_ID:
        bot.edit_message_text("لوحة تحكم المدير", chat_id, message_id, 
                             reply_markup=admin_keyboard())
    
    elif call.data == "admin_list_users" and user_id == ADMIN_ID:
        users = get_all_users()
        users_text = "قائمة المستخدمين:\n\n"
        for uid, user_data in users.items():
            users_text += f"ID: {uid}, Name: {user_data.get('full_name', 'N/A')}, Username: @{user_data.get('username', 'N/A')}\n"
        
        bot.edit_message_text(users_text, chat_id, message_id, 
                             reply_markup=admin_keyboard())

# أوامر المدير
@bot.message_handler(commands=['admin'], func=lambda message: message.from_user.id == ADMIN_ID)
def admin_panel(message):
    bot.send_message(message.chat.id, "لوحة تحكم المدير", reply_markup=admin_keyboard())

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
