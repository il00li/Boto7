import telebot
from telebot import types
import json
import os
import random
import string
from datetime import datetime, timedelta

# إعدادات البوت
BOT_TOKEN = os.getenv('BOT_TOKEN', '8324471840:AAFqTHWy4-FZFIHGusm5RWk1Y240cV32SCw')
ADMIN_ID = int(os.getenv('ADMIN_ID', 6689435577))
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '@iIl337')
MAIN_CHANNEL = os.getenv('MAIN_CHANNEL', '@GRABOT7')
DEVELOPER_USERNAME = os.getenv('DEVELOPER_USERNAME', '@OlIiIl7')

# مسارات ملفات التخزين
USERS_FILE = "users.json"
SEARCH_TYPES_FILE = "search_types.json"
INVITES_FILE = "invites.json"

# وظائف التخزين
def ensure_file_exists(file_path):
    """تأكد من وجود الملف، وإنشائه إذا لم يكن موجوداً"""
    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=4)

def read_json(file_path):
    """قراءة ملف JSON"""
    ensure_file_exists(file_path)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def write_json(file_path, data):
    """كتابة بيانات إلى ملف JSON"""
    ensure_file_exists(file_path)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# دوال لإدارة المستخدمين
def get_user(user_id):
    """الحصول على بيانات مستخدم"""
    users = read_json(USERS_FILE)
    user_id_str = str(user_id)
    return users.get(user_id_str, {})

def save_user(user_id, user_data):
    """حفظ بيانات مستخدم"""
    users = read_json(USERS_FILE)
    user_id_str = str(user_id)
    users[user_id_str] = user_data
    write_json(USERS_FILE, users)

def get_all_users():
    """الحصول على جميع المستخدمين"""
    return read_json(USERS_FILE)

def update_user_subscription(user_id, days=30):
    """تحديث اشتراك المستخدم"""
    user = get_user(user_id)
    if not user:
        user = {}
    
    subscription_end = datetime.now() + timedelta(days=days)
    user['subscription_end'] = subscription_end.isoformat()
    user['is_banned'] = False
    
    save_user(user_id, user)

def check_subscription(user_id):
    """التحقق من صلاحية اشتراك المستخدم"""
    user = get_user(user_id)
    if not user or user.get('is_banned', False):
        return False
    
    subscription_end = user.get('subscription_end')
    if not subscription_end:
        return False
    
    try:
        end_date = datetime.fromisoformat(subscription_end)
        return end_date > datetime.now()
    except (ValueError, TypeError):
        return False

# دوال لأنواع البحث
def get_search_type(user_id):
    """الحصول على نوع البحث للمستخدم"""
    search_types = read_json(SEARCH_TYPES_FILE)
    user_id_str = str(user_id)
    return search_types.get(user_id_str, 'illustration')

def set_search_type(user_id, search_type):
    """تعيين نوع البحث للمستخدم"""
    search_types = read_json(SEARCH_TYPES_FILE)
    user_id_str = str(user_id)
    search_types[user_id_str] = search_type
    write_json(SEARCH_TYPES_FILE, search_types)

# دوال لإدارة الدعوات
def get_invite_code(user_id):
    """الحصول على كود الدعوة للمستخدم"""
    user = get_user(user_id)
    return user.get('invite_code')

def set_invite_code(user_id, invite_code):
    """تعيين كود الدعوة للمستخدم"""
    user = get_user(user_id)
    if not user:
        user = {}
    
    user['invite_code'] = invite_code
    save_user(user_id, user)

def increment_invite_count(user_id):
    """زيادة عداد الدعوات للمستخدم"""
    user = get_user(user_id)
    if not user:
        user = {}
    
    current_count = user.get('invited_count', 0)
    user['invited_count'] = current_count + 1
    save_user(user_id, user)
    
    # إذا وصل عدد الدعوات إلى 10، تفعيل الاشتراك
    if user['invited_count'] >= 10:
        update_user_subscription(user_id, 30)
    
    return user['invited_count']

def add_invite_record(invite_code, owner_id, used_by):
    """إضافة سجل دعوة"""
    invites = read_json(INVITES_FILE)
    invite_id = str(len(invites) + 1)
    invites[invite_id] = {
        'invite_code': invite_code,
        'owner_id': owner_id,
        'used_by': used_by,
        'created_at': datetime.now().isoformat()
    }
    write_json(INVITES_FILE, invites)

def find_user_by_invite_code(invite_code):
    """البحث عن مستخدم بواسطة كود الدعوة"""
    users = get_all_users()
    for user_id, user_data in users.items():
        if user_data.get('invite_code') == invite_code:
            return int(user_id)
    return None

# وظائف الأدوات المساعدة
def is_subscribed(bot, user_id, channel_username):
    try:
        chat_member = bot.get_chat_member(channel_username.replace('@', ''), user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except:
        return False

def generate_invite_code(length=10):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

# وظائف لوحة المفاتيح
def main_menu_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    keyboard.add(
        types.InlineKeyboardButton("بدء البحث 🫐", callback_data="start_search"),
        types.InlineKeyboardButton("نوع البحث 🍇", callback_data="search_type"),
        types.InlineKeyboardButton("معلومات 🪻", callback_data="info"),
        types.InlineKeyboardButton("اشتراك مجاني 🏖️", callback_data="free_subscription")
    )
    
    return keyboard

def search_type_keyboard(selected_type=None):
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    
    types_list = [
        ("Illustration | رسومات", "illustration"),
        ("Photo | صور", "photo"),
        ("Video | فيديو", "video")
    ]
    
    for name, callback in types_list:
        if selected_type == callback:
            name = f"🪐 {name}"
        keyboard.add(types.InlineKeyboardButton(name, callback_data=f"set_type_{callback}"))
    
    keyboard.add(types.InlineKeyboardButton("رجوع", callback_data="back_to_main"))
    
    return keyboard

def subscription_keyboard(user_id):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    keyboard.add(
        types.InlineKeyboardButton("طلب الاشتراك من المطور", url=f"tg://user?id={DEVELOPER_USERNAME.replace('@', '')}"),
        types.InlineKeyboardButton("اشتراك مجاني 🏖️", callback_data="free_subscription"),
        types.InlineKeyboardButton("تحقق 👀", callback_data="check_subscription")
    )
    
    return keyboard

def force_subscribe_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    
    keyboard.add(
        types.InlineKeyboardButton("اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"),
        types.InlineKeyboardButton("تحقق 👀", callback_data="check_subscription")
    )
    
    return keyboard

def admin_keyboard():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    
    keyboard.add(
        types.InlineKeyboardButton("إرسال إشعار للجميع", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("عرض المستخدمين", callback_data="admin_list_users"),
        types.InlineKeyboardButton("حظر مستخدم", callback_data="admin_ban_user"),
        types.InlineKeyboardButton("رفع حظر مستخدم", callback_data="admin_unban_user")
    )
    
    return keyboard

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
