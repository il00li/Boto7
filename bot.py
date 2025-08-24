import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from collections import defaultdict
import requests
import os
from datetime import datetime

# توكن البوت - تم توفيره (يجب استبداله بالتوكن الكامل)
API_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '8324471840:AAE5vL7o3yL8z6y1Q2ZQ3XyZ3XyZ3XyZ3Xy')
bot = telebot.TeleBot(API_TOKEN)

# إعدادات المدير
ADMIN_IDS = [int(os.environ.get('ADMIN_ID', 6689435577))]  # تم توفيره

# مفاتيح APIs
API_KEYS = {
    'pixabay': os.environ.get('PIXABAY_API_KEY', '51444506-bffefcaf12816bd85a20222d1')  # تم توفيره
}

# أنواع المحتوى المتاحة (بدون ايموجي)
content_types = {
    'photos': 'Photos',
    'illustrations': 'Illustrations',
    'videos': 'Videos'
}

# تخزين بيانات المستخدمين
user_sessions = defaultdict(dict)
user_selected_type = defaultdict(str)
bot_stats = {
    'total_users': 0,
    'active_today': set(),
    'total_searches': 0,
    'daily_reset': datetime.now().date()
}

# قناة الاشتراك الإجباري
CHANNEL_USERNAME = '@iIl337'

# قائمة المستخدمين المحظورين
banned_users = set()

# دوال APIs
def search_pixabay(query, per_page=10):
    """بحث في Pixabay API"""
    try:
        url = f"https://pixabay.com/api/?key={API_KEYS['pixabay']}&q={query}&per_page={per_page}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get('hits', [])
    except Exception as e:
        print(f"Error searching Pixabay: {e}")
        return []

def search_coverr(query, per_page=10):
    """بحث في Coverr API"""
    try:
        url = f"https://api.coverr.co/videos?query={query}&per_page={per_page}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get('videos', [])
    except Exception as e:
        print(f"Error searching Coverr: {e}")
        return []

# دالة معالجة البحث العامة
def handle_search_api(content_type, query, per_page=5):
    """توجيه البحث إلى API المناسب"""
    if content_type == 'photos':
        return search_pixabay(query, per_page)
    elif content_type == 'videos':
        return search_coverr(query, per_page)
    elif content_type == 'illustrations':
        # يمكن إضافة API للرسوم لاحقاً
        return search_pixabay(query, per_page)  # استخدام Pixabay كبديل مؤقت
    return []

# التحقق من اشتراك المستخدم في القناة
def check_channel_subscription(user_id):
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Error checking channel subscription: {e}")
        return False

# /start command - الرسالة الرئيسية الجديدة
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    
    # التحقق إذا كان المستخدم محظوراً
    if user_id in banned_users:
        bot.send_message(message.chat.id, "⛔ تم حظرك من استخدام البوت")
        return
    
    # التحقق من الاشتراك في القناة
    if not check_channel_subscription(user_id):
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("اشترك في القناة أولاً", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
        markup.add(InlineKeyboardButton("تحقق من الاشتراك", callback_data='check_subscription'))
        
        bot.send_message(
            message.chat.id,
            "⚠️ يجب الاشتراك في القناة أولاً لاستخدام البوت:\nhttps://t.me/iIl337",
            reply_markup=markup
        )
        return
    
    # تحديث الإحصائيات
    current_date = datetime.now().date()
    if bot_stats['daily_reset'] != current_date:
        bot_stats['active_today'] = set()
        bot_stats['daily_reset'] = current_date
    
    if user_id not in user_sessions:
        bot_stats['total_users'] += 1
    
    bot_stats['active_today'].add(user_id)
    
    # حفظ حالة المستخدم
    user_sessions[user_id] = {
        'current_results': [],
        'current_index': 0
    }
    
    # إرسال الرسالة الرئيسية الجديدة
    send_main_menu(message.chat.id)

def send_main_menu(chat_id):
    """إرسال القائمة الرئيسية الجديدة"""
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("بدء البحث 🌷", callback_data='start_search'))
    markup.add(InlineKeyboardButton("نوع البحث 🍇", callback_data='select_type'))
    
    # إضافة زر للإدارة إذا كان مديراً
    if chat_id in ADMIN_IDS:
        markup.add(InlineKeyboardButton("لوحة المدير", callback_data='admin_panel'))
    
    bot.send_message(
        chat_id,
        "[o_o]\n <)__)\n  ||\nاختر النوع من \"نوع البحث🍇\"\nابدء البحث عبر النوع المحدد عبر \"بدء البحث \"\n\nالمطور @OlIiIl7",
        reply_markup=markup
    )

# معالجة زر نوع البحث
@bot.callback_query_handler(func=lambda call: call.data == 'select_type')
def handle_select_type(call):
    user_id = call.from_user.id
    
    # التحقق إذا كان المستخدم محظوراً
    if user_id in banned_users:
        bot.answer_callback_query(call.id, "⛔ تم حظرك من استخدام البوت")
        return
    
    # إنشاء لوحة أنواع البحث (بدون ايموجي)
    markup = InlineKeyboardMarkup(row_width=1)
    
    for key, value in content_types.items():
        # وضع 🪐 بجانب النوع المحدد
        emoji = " 🪐" if user_selected_type.get(user_id) == key else ""
        markup.add(InlineKeyboardButton(f"{value}{emoji}", callback_data=f"set_type_{key}"))
    
    # زر الرجوع
    markup.add(InlineKeyboardButton("رجوع", callback_data='back_to_main'))
    
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="اختر نوع البحث:",
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error editing message: {e}")

# معالجة اختيار نوع البحث
@bot.callback_query_handler(func=lambda call: call.data.startswith('set_type_'))
def handle_set_type(call):
    user_id = call.from_user.id
    
    # التحقق إذا كان المستخدم محظوراً
    if user_id in banned_users:
        bot.answer_callback_query(call.id, "⛔ تم حظرك من استخدام البوت")
        return
    
    content_type = call.data.split('_')[2]
    
    # حفظ النوع المحدد
    user_selected_type[user_id] = content_type
    
    # العودة إلى القائمة الرئيسية
    send_main_menu(call.message.chat.id)
    bot.answer_callback_query(call.id, f"تم اختيار: {content_types[content_type]}")

# معالجة زر بدء البحث
@bot.callback_query_handler(func=lambda call: call.data == 'start_search')
def handle_start_search(call):
    user_id = call.from_user.id
    
    # التحقق إذا كان المستخدم محظوراً
    if user_id in banned_users:
        bot.answer_callback_query(call.id, "⛔ تم حظرك من استخدام البوت")
        return
    
    # التحقق من اختيار نوع البحث أولاً
    if user_id not in user_selected_type or not user_selected_type[user_id]:
        bot.answer_callback_query(call.id, "⚠️ يرجى اختيار نوع البحث أولاً")
        handle_select_type(call)
        return
    
    # طلب كلمة البحث
    msg = bot.send_message(call.message.chat.id, "أرسل كلمة البحث الآن:")
    bot.register_next_step_handler(msg, process_search_query, user_selected_type[user_id])

def process_search_query(message, content_type):
    user_id = message.from_user.id
    
    # التحقق إذا كان المستخدم محظوراً
    if user_id in banned_users:
        bot.send_message(message.chat.id, "⛔ تم حظرك من استخدام البوت")
        return
    
    search_query = message.text
    
    # تحديث الإحصائيات
    bot_stats['total_searches'] += 1
    
    # إرسال رسالة الانتظار
    waiting_msg = bot.send_message(
        message.chat.id,
        f"🔍 جاري البحث عن: {search_query}"
    )
    
    # استدعاء API المناسب
    results = handle_search_api(content_type, search_query, per_page=10)
    
    # حذف رسالة الانتظار
    try:
        bot.delete_message(message.chat.id, waiting_msg.message_id)
    except:
        pass
    
    # معالجة النتائج
    if not results:
        bot.send_message(
            message.chat.id,
            f"❌ لم يتم العثور على نتائج لـ '{search_query}'"
        )
        send_main_menu(message.chat.id)
        return
    
    # حفظ النتائج في حالة المستخدم
    user_sessions[user_id]['current_results'] = results
    user_sessions[user_id]['current_index'] = 0
    user_sessions[user_id]['current_query'] = search_query
    user_sessions[user_id]['current_type'] = content_type
    
    # إرسال أول نتيجة
    send_single_result(message.chat.id, user_id, 0)

def send_single_result(chat_id, user_id, index):
    """إرسال نتيجة واحدة مع أزرار التنقل"""
    if user_id not in user_sessions or not user_sessions[user_id]['current_results']:
        return
    
    results = user_sessions[user_id]['current_results']
    content_type = user_sessions[user_id]['current_type']
    
    if index < 0 or index >= len(results):
        return
    
    result = results[index]
    search_query = user_sessions[user_id]['current_query']
    
    # إنشاء أزرار التنقل
    markup = InlineKeyboardMarkup(row_width=3)
    
    # أزرار السابق والتالي
    nav_buttons = []
    if index > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"nav_{index-1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"{index+1}/{len(results)}", callback_data="count"))
    
    if index < len(results) - 1:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"nav_{index+1}"))
    
    markup.add(*nav_buttons)
    
    # زر العودة
    markup.add(InlineKeyboardButton("↩️ العودة", callback_data='back_to_main'))
    
    # إرسال المحتوى حسب النوع
    try:
        if content_type in ['photos', 'illustrations'] and ('webformatURL' in result or 'url' in result):
            image_url = result.get('webformatURL', result.get('url', ''))
            caption = f"📸 نتيجة {index+1} من {len(results)}\n🔍 للبحث: '{search_query}'"
            
            # إرسال الصورة مع التعديل إذا كانت رسالة موجودة
            if 'current_message_id' in user_sessions[user_id]:
                try:
                    bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=user_sessions[user_id]['current_message_id'],
                        media=telebot.types.InputMediaPhoto(image_url, caption=caption),
                        reply_markup=markup
                    )
                    return
                except:
                    pass
            
            # إذا لم تكن هناك رسالة سابقة، إرسال رسالة جديدة
            sent_msg = bot.send_photo(chat_id, image_url, caption=caption, reply_markup=markup)
            user_sessions[user_id]['current_message_id'] = sent_msg.message_id
        
        elif content_type == 'videos' and ('video_url' in result or 'url' in result):
            video_url = result.get('video_url', result.get('url', ''))
            caption = f"🎥 نتيجة {index+1} من {len(results)}\n🔍 للبحث: '{search_query}'"
            
            # إرسال الفيديو مع التعديل إذا كانت رسالة موجودة
            if 'current_message_id' in user_sessions[user_id]:
                try:
                    bot.edit_message_media(
                        chat_id=chat_id,
                        message_id=user_sessions[user_id]['current_message_id'],
                        media=telebot.types.InputMediaVideo(video_url, caption=caption),
                        reply_markup=markup
                    )
                    return
                except:
                    pass
            
            # إذا لم تكن هناك رسالة سابقة، إرسال رسالة جديدة
            sent_msg = bot.send_video(chat_id, video_url, caption=caption, reply_markup=markup)
            user_sessions[user_id]['current_message_id'] = sent_msg.message_id
        
        else:
            caption = f"📄 نتيجة {index+1} من {len(results)}\n🔍 للبحث: '{search_query}'"
            
            # إرسال رسالة نصية مع التعديل إذا كانت رسالة موجودة
            if 'current_message_id' in user_sessions[user_id]:
                try:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=user_sessions[user_id]['current_message_id'],
                        text=caption,
                        reply_markup=markup
                    )
                    return
                except:
                    pass
            
            # إذا لم تكن هناك رسالة سابقة، إرسال رسالة جديدة
            sent_msg = bot.send_message(chat_id, caption, reply_markup=markup)
            user_sessions[user_id]['current_message_id'] = sent_msg.message_id
    except Exception as e:
        print(f"Error sending result: {e}")
        bot.send_message(chat_id, "❌ حدث خطأ أثناء عرض النتائج")

# معالجة أزرار التنقل
@bot.callback_query_handler(func=lambda call: call.data.startswith('nav_'))
def handle_navigation(call):
    user_id = call.from_user.id
    
    # التحقق إذا كان المستخدم محظوراً
    if user_id in banned_users:
        bot.answer_callback_query(call.id, "⛔ تم حظرك من استخدام البوت")
        return
    
    if user_id not in user_sessions or not user_sessions[user_id]['current_results']:
        bot.answer_callback_query(call.id, "❌ لا توجد نتائج للتنقل")
        return
    
    index = int(call.data.split('_')[1])
    
    # تحديث الفهرس الحالي
    user_sessions[user_id]['current_index'] = index
    
    # إرسال النتيجة الجديدة (سيتم تعديل الرسالة الحالية)
    send_single_result(call.message.chat.id, user_id, index)
    bot.answer_callback_query(call.id)

# معالجة زر الرجوع
@bot.callback_query_handler(func=lambda call: call.data == 'back_to_main')
def handle_back(call):
    user_id = call.from_user.id
    
    # التحقق إذا كان المستخدم محظوراً
    if user_id in banned_users:
        bot.answer_callback_query(call.id, "⛔ تم حظرك من استخدام البوت")
        return
    
    send_main_menu(call.message.chat.id)

# معالجة زر التحقق من الاشتراك
@bot.callback_query_handler(func=lambda call: call.data == 'check_subscription')
def handle_check_subscription(call):
    user_id = call.from_user.id
    
    # التحقق إذا كان المستخدم محظوراً
    if user_id in banned_users:
        bot.answer_callback_query(call.id, "⛔ تم حظرك من استخدام البوت")
        return
    
    if check_channel_subscription(user_id):
        send_main_menu(call.message.chat.id)
    else:
        bot.answer_callback_query(call.id, "⚠️ لم تشترك بعد في القناة")

# أمر حظر المستخدم للمدير
@bot.message_handler(commands=['ban'])
def handle_ban_command(message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "⛔ ليس لديك صلاحية استخدام هذا الأمر")
        return
    
    # التحقق من وجود معرف المستخدم في الأمر
    if len(message.text.split()) < 2:
        bot.send_message(message.chat.id, "⚠️ يرجى تحديد معرف المستخدم\nمثال: /ban 123456789")
        return
    
    try:
        target_id = int(message.text.split()[1])
        
        # حظر المستخدم
        banned_users.add(target_id)
        
        bot.send_message(
            message.chat.id,
            f"✅ تم حظر المستخدم {target_id} بنجاح"
        )
        
        # إرسال رسالة للمستخدم المحظور
        try:
            bot.send_message(
                target_id,
                "⛔ تم حظرك من استخدام البوت"
            )
        except Exception as e:
            print(f"Error sending ban message: {e}")
            
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ معرف المستخدم غير صحيح")

# أمر إلغاء حظر المستخدم للمدير
@bot.message_handler(commands=['unban'])
def handle_unban_command(message):
    user_id = message.from_user.id
    
    if user_id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "⛔ ليس لديك صلاحية استخدام هذا الأمر")
        return
    
    # التحقق من وجود معرف المستخدم في الأمر
    if len(message.text.split()) < 2:
        bot.send_message(message.chat.id, "⚠️ يرجى تحديد معرف المستخدم\nمثال: /unban 123456789")
        return
    
    try:
        target_id = int(message.text.split()[1])
        
        # إلغاء حظر المستخدم
        if target_id in banned_users:
            banned_users.remove(target_id)
        
        bot.send_message(
            message.chat.id,
            f"✅ تم إلغاء حظر المستخدم {target_id} بنجاح"
        )
        
        # إرسال رسالة للمستخدم
        try:
            bot.send_message(
                target_id,
                "✅ تم إلغاء حظرك من البوت"
            )
        except Exception as e:
            print(f"Error sending unban message: {e}")
            
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ معرف المستخدم غير صحيح")

# معالجة الأخطاء العامة
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    try:
        if call.data == 'admin_panel':
            if call.from_user.id in ADMIN_IDS:
                handle_admin_panel(call)
            else:
                bot.answer_callback_query(call.id, "⛔ ليس لديك صلاحية الوصول")
        elif call.data == 'count':
            bot.answer_callback_query(call.id)
    except Exception as e:
        print(f"Error handling callback: {e}")

def handle_admin_panel(call):
    """لوحة تحكم المدير"""
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📊 الإحصائيات", callback_data='admin_stats'))
    markup.add(InlineKeyboardButton("📣 إرسال إشعار", callback_data='admin_broadcast'))
    markup.add(InlineKeyboardButton("⬅️ العودة", callback_data='back_to_main'))
    
    try:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="🛠️ لوحة تحكم المدير:",
            reply_markup=markup
        )
    except Exception as e:
        print(f"Error editing admin panel: {e}")

# تشغيل البوت
if __name__ == '__main__':
    print("✅ البوت يعمل...")
    print(f"📊 المدير: {ADMIN_IDS}")
    
    # إزالة تخزين الويبhook القديم إذا كان موجوداً
    bot.remove_webhook()
    
    # على Render، استخدم webhook بدلاً من polling
    if os.environ.get('RENDER'):
        webhook_url = os.environ.get('WEBHOOK_URL')
        if webhook_url:
            bot.set_webhook(url=webhook_url)
            print("🌐 Webhook mode activated")
        else:
            print("❌ WEBHOOK_URL not set, using polling")
            bot.infinity_polling()
    else:
        # التشغيل المحلي باستخدام polling
        print("🖥️ Local mode activated")
        bot.infinity_polling()
