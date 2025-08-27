import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import time
import logging
import urllib.parse
import json
import random
from flask import Flask, request, abort
from datetime import datetime, timedelta
import threading
import schedule

# تهيئة نظام التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = '8324471840:AAHJrXuoAKmb0wmWMle3AnqbPt7Hj6zNQVI'
PIXABAY_API_KEY = '51444506-bffefcaf12816bd85a20222d1'
ADMIN_ID = 6689435577  # معرف المدير
WEBHOOK_URL = 'https://boto7-0c3p.onrender.com/webhook'  # تأكد من تطابق هذا مع عنوان URL الخاص بك

app = Flask(__name__)
bot = telebot.TeleBot(TOKEN)

# قنوات الاشتراك الإجباري
REQUIRED_CHANNELS = ['@iIl337']

# قناة التحميل
UPLOAD_CHANNEL = '@GRABOT7'

# ذاكرة مؤقتة لتخزين نتائج البحث لكل مستخدم
user_data = {}
new_users = set()  # لتتبع المستخدمين الجدد
banned_users = set()  # المستخدمون المحظورون
premium_users = set()  # المستخدمون المميزون
user_referrals = {}  # نظام الدعوة: {user_id: {'invites': count, 'referrer': referrer_id}}
user_channels = {}  # القنوات الخاصة بالمستخدمين: {user_id: channel_username}
bot_stats = {  # إحصائيات البوت
    'total_users': 0,
    'total_searches': 0,
    'total_downloads': 0,
    'start_time': datetime.now()
}

# إعدادات قنوات النشر التلقائي
auto_publish_channels = {}  # {channel_id: {'channel': '@channel', 'types': ['photo', 'illustration', 'video'], 'interval': 1, 'mention_bot': True, 'last_publish': datetime}}

# تاريخ عمليات البحث الأخيرة لكل نوع
recent_searches = {
    'photo': [],
    'illustration': [],
    'video': []
}

# رموز تعبيرية جديدة
NEW_EMOJIS = ['🏖️', '🍓', '🍇', '🍈', '🐢', '🪲', '🍍', '🧃', '🎋', '🧩', '🪖', '🌺', '🪷', '🏵️', '🐌', '🐝', '🦚', '🐦']

# وظيفة لتشغيل المهام المجدولة في خيط منفصل
def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(60)  # التحقق كل دقيقة

# بدء تشغيل المجدول في خيط منفصل
scheduler_thread = threading.Thread(target=run_scheduler)
scheduler_thread.daemon = True
scheduler_thread.start()

# جدولة المهام اليومية
schedule.every().day.at("00:00").do(publish_scheduled_content)  # النشر يومياً في منتصف الليل

def is_valid_url(url):
    """التحقق من صحة عنوان URL"""
    try:
        result = urllib.parse.urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def set_webhook():
    """تعيين ويب هوك للبوت"""
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=WEBHOOK_URL)
        logger.info("تم تعيين ويب هوك بنجاح")
    except Exception as e:
        logger.error(f"خطأ في تعيين ويب هوك: {e}")

@app.route('/webhook', methods=['POST'])
def webhook():
    """معالجة التحديثات الواردة من تلجرام"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        abort(403)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # التحقق من وجود رابط دعوة
    if len(message.text.split()) > 1:
        referral_code = message.text.split()[1]
        try:
            referrer_id = int(referral_code)
            if referrer_id != user_id and referrer_id in user_referrals:
                # زيادة عدد الدعوات للمستخدم الذي قام بالدعوة
                if 'invites' not in user_referrals[referrer_id]:
                    user_referrals[referrer_id]['invites'] = 0
                user_referrals[referrer_id]['invites'] += 1
                
                # حفظ معلومات الداعي للمستخدم الجديد
                if user_id not in user_referrals:
                    user_referrals[user_id] = {}
                user_referrals[user_id]['referrer'] = referrer_id
                
                # منح العضوية المميزة إذا وصل عدد الدعوات إلى 10
                if user_referrals[referrer_id]['invites'] >= 10 and referrer_id not in premium_users:
                    premium_users.add(referrer_id)
                    try:
                        bot.send_message(referrer_id, "🎉 مبروك! لقد وصلت إلى 10 دعوات وتم ترقيتك إلى العضوية المميزة!")
                    except:
                        pass
        except ValueError:
            pass
    
    # التحقق من الحظر
    if user_id in banned_users:
        bot.send_message(chat_id, "⛔️ حسابك محظور من استخدام البوت.")
        return
    
    # زيادة عدد المستخدمين
    if user_id not in new_users:
        new_users.add(user_id)
        bot_stats['total_users'] += 1
        notify_admin(user_id, message.from_user.username)
    
    # التحقق من الاشتراك في القنوات
    not_subscribed = check_subscription(user_id)
    
    if not_subscribed:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🏖️ تحقق من الاشتراك", callback_data="check_subscription"))
        bot.send_message(chat_id, "🍓 يجب الاشتراك في القنوات التالية اولا:\n" + "\n".join(not_subscribed), reply_markup=markup)
    else:
        # دائماً إرسال رسالة جديدة عند /start
        show_main_menu(chat_id, user_id, new_message=True)

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    """لوحة تحكم المدير"""
    if message.from_user.id != ADMIN_ID:
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🍇 إدارة المستخدمين", callback_data="admin_users"),
        InlineKeyboardButton("🍈 الإحصائيات", callback_data="admin_stats")
    )
    markup.add(
        InlineKeyboardButton("🐢 إدارة العضويات", callback_data="admin_subscriptions"),
        InlineKeyboardButton("🪲 نقل الأعضاء", callback_data="admin_transfer_members")
    )
    markup.add(
        InlineKeyboardButton("🍍 الإشعارات", callback_data="admin_notifications"),
        InlineKeyboardButton("🧃 قنوات النشر", callback_data="admin_publish_channels")
    )
    markup.add(
        InlineKeyboardButton("🧃 رجوع", callback_data="admin_back")
    )
    
    bot.send_message(ADMIN_ID, "👨‍💼 لوحة تحكم المدير:", reply_markup=markup)

# ... (بقية دوال الإدارة كما هي)

@bot.callback_query_handler(func=lambda call: call.data == "admin_publish_channels")
def admin_publish_channels(call):
    """إدارة قنوات النشر التلقائي"""
    if call.from_user.id != ADMIN_ID:
        return
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ إضافة قناة نشر", callback_data="admin_add_publish_channel"),
        InlineKeyboardButton("🗑️ إزالة قناة نشر", callback_data="admin_remove_publish_channel")
    )
    markup.add(
        InlineKeyboardButton("⚙️ تعديل إعدادات قناة", callback_data="admin_edit_publish_channel"),
        InlineKeyboardButton("📋 عرض القنوات", callback_data="admin_list_publish_channels")
    )
    markup.add(InlineKeyboardButton("🧃 رجوع", callback_data="admin_back"))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="📢 إدارة قنوات النشر التلقائي:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "admin_add_publish_channel")
def admin_add_publish_channel(call):
    """إضافة قناة نشر جديدة"""
    if call.from_user.id != ADMIN_ID:
        return
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="أرسل معرف القناة التي تريد إضافتها للنشر التلقائي (مثال: @channel_name):"
    )
    bot.register_next_step_handler(call.message, process_add_publish_channel)

def process_add_publish_channel(message):
    """معالجة إضافة قناة نشر جديدة"""
    channel_username = message.text.strip()
    if not channel_username.startswith('@'):
        bot.send_message(ADMIN_ID, "❌ يجب أن يبدأ معرف القناة بـ @")
        admin_panel(message)
        return
    
    # التحقق من أن البوت هو مدير في القناة
    try:
        chat_member = bot.get_chat_member(chat_id=channel_username, user_id=bot.get_me().id)
        if chat_member.status not in ['administrator', 'creator']:
            bot.send_message(ADMIN_ID, "❌ يجب أن أكون مسؤولاً في القناة لأتمكن من النشر فيها")
            admin_panel(message)
            return
    except Exception as e:
        logger.error(f"خطأ في التحقق من صلاحية البوت في القناة: {e}")
        bot.send_message(ADMIN_ID, "❌ لا يمكنني الوصول إلى القناة، تأكد من أني مسؤول فيها")
        admin_panel(message)
        return
    
    # إضافة القناة إلى قنوات النشر
    channel_id = len(auto_publish_channels) + 1
    auto_publish_channels[channel_id] = {
        'channel': channel_username,
        'types': ['photo', 'illustration', 'video'],
        'interval': 1,  # يومياً
        'mention_bot': True,
        'last_publish': None
    }
    
    bot.send_message(ADMIN_ID, f"✅ تم إضافة القناة {channel_username} للنشر التلقائي بنجاح")
    admin_panel(message)

@bot.callback_query_handler(func=lambda call: call.data == "admin_remove_publish_channel")
def admin_remove_publish_channel(call):
    """إزالة قناة نشر"""
    if call.from_user.id != ADMIN_ID:
        return
    
    if not auto_publish_channels:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ لا توجد قنوات نشر مضافة حالياً"
        )
        return
    
    # عرض قنوات النشر الحالية
    channels_text = "📋 قنوات النشر الحالية:\n\n"
    for channel_id, channel_data in auto_publish_channels.items():
        channels_text += f"{channel_id}. {channel_data['channel']} (كل {channel_data['interval']} أيام)\n"
    
    channels_text += "\nأرسل رقم القناة التي تريد إزالتها:"
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=channels_text
    )
    bot.register_next_step_handler(call.message, process_remove_publish_channel)

def process_remove_publish_channel(message):
    """معالجة إزالة قناة نشر"""
    try:
        channel_id = int(message.text)
        if channel_id in auto_publish_channels:
            channel_name = auto_publish_channels[channel_id]['channel']
            del auto_publish_channels[channel_id]
            bot.send_message(ADMIN_ID, f"✅ تم إزالة القناة {channel_name} من النشر التلقائي")
        else:
            bot.send_message(ADMIN_ID, "❌ رقم القناة غير صحيح")
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ يجب إدخال رقم صحيح")
    
    admin_panel(message)

@bot.callback_query_handler(func=lambda call: call.data == "admin_edit_publish_channel")
def admin_edit_publish_channel(call):
    """تعديل إعدادات قناة نشر"""
    if call.from_user.id != ADMIN_ID:
        return
    
    if not auto_publish_channels:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ لا توجد قنوات نشر مضافة حالياً"
        )
        return
    
    # عرض قنوات النشر الحالية
    channels_text = "📋 قنوات النشر الحالية:\n\n"
    for channel_id, channel_data in auto_publish_channels.items():
        channels_text += f"{channel_id}. {channel_data['channel']} (كل {channel_data['interval']} أيام)\n"
    
    channels_text += "\nأرسل رقم القناة التي تريد تعديل إعداداتها:"
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=channels_text
    )
    bot.register_next_step_handler(call.message, process_edit_publish_channel_step1)

def process_edit_publish_channel_step1(message):
    """الخطوة الأولى في تعديل إعدادات قناة نشر"""
    try:
        channel_id = int(message.text)
        if channel_id not in auto_publish_channels:
            bot.send_message(ADMIN_ID, "❌ رقم القناة غير صحيح")
            admin_panel(message)
            return
        
        # حفظ معرف القناة مؤقتاً
        user_data[ADMIN_ID] = {'edit_channel_id': channel_id}
        
        # عرض خيارات التعديل
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("📅 تغيير الفترة", callback_data="edit_channel_interval"),
            InlineKeyboardButton("🖼️ تغيير أنواع المحتوى", callback_data="edit_channel_types")
        )
        markup.add(
            InlineKeyboardButton("🔔 تغيير ذكر البوت", callback_data="edit_channel_mention"),
            InlineKeyboardButton("🧃 رجوع", callback_data="admin_back")
        )
        
        bot.send_message(ADMIN_ID, "اختر الإعداد الذي تريد تعديله:", reply_markup=markup)
    except ValueError:
        bot.send_message(ADMIN_ID, "❌ يجب إدخال رقم صحيح")
        admin_panel(message)

@bot.callback_query_handler(func=lambda call: call.data == "edit_channel_interval")
def edit_channel_interval(call):
    """تغيير فترة النشر للقناة"""
    if call.from_user.id != ADMIN_ID:
        return
    
    channel_id = user_data[ADMIN_ID].get('edit_channel_id')
    if not channel_id:
        bot.send_message(ADMIN_ID, "❌ لم يتم تحديد قناة")
        admin_panel(call.message)
        return
    
    markup = InlineKeyboardMarkup(row_width=3)
    markup.add(
        InlineKeyboardButton("يومياً", callback_data="interval_1"),
        InlineKeyboardButton("كل يومين", callback_data="interval_2"),
        InlineKeyboardButton("كل 3 أيام", callback_data="interval_3")
    )
    markup.add(InlineKeyboardButton("🧃 رجوع", callback_data="admin_back"))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="اختر الفترة الزمنية للنشر:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("interval_"))
def set_channel_interval(call):
    """تعيين الفترة الزمنية للنشر"""
    if call.from_user.id != ADMIN_ID:
        return
    
    channel_id = user_data[ADMIN_ID].get('edit_channel_id')
    if not channel_id:
        bot.send_message(ADMIN_ID, "❌ لم يتم تحديد قناة")
        admin_panel(call.message)
        return
    
    interval = int(call.data.split("_")[1])
    auto_publish_channels[channel_id]['interval'] = interval
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"✅ تم تعيين فترة النشر إلى كل {interval} أيام"
    )
    admin_panel(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "edit_channel_types")
def edit_channel_types(call):
    """تغيير أنواع المحتوى للقناة"""
    if call.from_user.id != ADMIN_ID:
        return
    
    channel_id = user_data[ADMIN_ID].get('edit_channel_id')
    if not channel_id:
        bot.send_message(ADMIN_ID, "❌ لم يتم تحديد قناة")
        admin_panel(call.message)
        return
    
    current_types = auto_publish_channels[channel_id]['types']
    
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(f"{'✅' if 'photo' in current_types else '❌'} Photos", callback_data="toggle_photo"),
        InlineKeyboardButton(f"{'✅' if 'illustration' in current_types else '❌'} Illustrations", callback_data="toggle_illustration"),
        InlineKeyboardButton(f"{'✅' if 'video' in current_types else '❌'} Videos", callback_data="toggle_video")
    )
    markup.add(InlineKeyboardButton("💾 حفظ", callback_data="save_channel_types"))
    markup.add(InlineKeyboardButton("🧃 رجوع", callback_data="admin_back"))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="اختر أنواع المحتوى التي تريد نشرها في هذه القناة:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_"))
def toggle_content_type(call):
    """تبديل نوع المحتوى"""
    if call.from_user.id != ADMIN_ID:
        return
    
    channel_id = user_data[ADMIN_ID].get('edit_channel_id')
    if not channel_id:
        bot.send_message(ADMIN_ID, "❌ لم يتم تحديد قناة")
        admin_panel(call.message)
        return
    
    content_type = call.data.split("_")[1]
    current_types = auto_publish_channels[channel_id]['types']
    
    if content_type in current_types:
        current_types.remove(content_type)
    else:
        current_types.append(content_type)
    
    # تحديث الزر
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton(f"{'✅' if 'photo' in current_types else '❌'} Photos", callback_data="toggle_photo"),
        InlineKeyboardButton(f"{'✅' if 'illustration' in current_types else '❌'} Illustrations", callback_data="toggle_illustration"),
        InlineKeyboardButton(f"{'✅' if 'video' in current_types else '❌'} Videos", callback_data="toggle_video")
    )
    markup.add(InlineKeyboardButton("💾 حفظ", callback_data="save_channel_types"))
    markup.add(InlineKeyboardButton("🧃 رجوع", callback_data="admin_back"))
    
    bot.edit_message_reply_markup(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data == "save_channel_types")
def save_channel_types(call):
    """حفظ أنواع المحتوى للقناة"""
    if call.from_user.id != ADMIN_ID:
        return
    
    channel_id = user_data[ADMIN_ID].get('edit_channel_id')
    if not channel_id:
        bot.send_message(ADMIN_ID, "❌ لم يتم تحديد قناة")
        admin_panel(call.message)
        return
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text="✅ تم حفظ أنواع المحتوى بنجاح"
    )
    admin_panel(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "edit_channel_mention")
def edit_channel_mention(call):
    """تغيير إعداد ذكر البوت للقناة"""
    if call.from_user.id != ADMIN_ID:
        return
    
    channel_id = user_data[ADMIN_ID].get('edit_channel_id')
    if not channel_id:
        bot.send_message(ADMIN_ID, "❌ لم يتم تحديد قناة")
        admin_panel(call.message)
        return
    
    current_setting = auto_publish_channels[channel_id]['mention_bot']
    
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("✅ تفعيل ذكر البوت", callback_data="set_mention_true"),
        InlineKeyboardButton("❌ إلغاء ذكر البوت", callback_data="set_mention_false")
    )
    markup.add(InlineKeyboardButton("🧃 رجوع", callback_data="admin_back"))
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"الإعداد الحالي: {'مفعل' if current_setting else 'معطل'}\n\nاختر الإعداد الجديد:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("set_mention_"))
def set_channel_mention(call):
    """تعيين إعداد ذكر البوت للقناة"""
    if call.from_user.id != ADMIN_ID:
        return
    
    channel_id = user_data[ADMIN_ID].get('edit_channel_id')
    if not channel_id:
        bot.send_message(ADMIN_ID, "❌ لم يتم تحديد قناة")
        admin_panel(call.message)
        return
    
    mention_setting = call.data.endswith("_true")
    auto_publish_channels[channel_id]['mention_bot'] = mention_setting
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"✅ تم {'تفعيل' if mention_setting else 'إلغاء'} ذكر البوت في هذه القناة"
    )
    admin_panel(call.message)

@bot.callback_query_handler(func=lambda call: call.data == "admin_list_publish_channels")
def admin_list_publish_channels(call):
    """عرض قنوات النشر الحالية"""
    if call.from_user.id != ADMIN_ID:
        return
    
    if not auto_publish_channels:
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="❌ لا توجد قنوات نشر مضافة حالياً"
        )
        return
    
    channels_text = "📋 قنوات النشر التلقائي:\n\n"
    for channel_id, channel_data in auto_publish_channels.items():
        types_text = ", ".join(channel_data['types'])
        mention_status = "✅" if channel_data['mention_bot'] else "❌"
        last_publish = channel_data['last_publish'].strftime("%Y-%m-%d %H:%M") if channel_data['last_publish'] else "لم يتم النشر بعد"
        
        channels_text += f"📢 {channel_data['channel']}\n"
        channels_text += f"   📅 النشر: كل {channel_data['interval']} أيام\n"
        channels_text += f"   🖼️ الأنواع: {types_text}\n"
        channels_text += f"   🔔 ذكر البوت: {mention_status}\n"
        channels_text += f"   ⏰ آخر نشر: {last_publish}\n\n"
    
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=channels_text,
        reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🧃 رجوع", callback_data="admin_back"))
    )

def publish_scheduled_content():
    """نشر المحتوى المجدول في القنوات"""
    logger.info("بدء عملية النشر التلقائي في القنوات")
    
    for channel_id, channel_data in auto_publish_channels.items():
        # التحقق من موعد النشر
        if channel_data['last_publish']:
            days_since_last_publish = (datetime.now() - channel_data['last_publish']).days
            if days_since_last_publish < channel_data['interval']:
                continue  # لم يحن موعد النشر بعد
        
        try:
            # نشر المحتوى في القناة
            publish_to_channel(channel_data)
            
            # تحديث وقت آخر نشر
            auto_publish_channels[channel_id]['last_publish'] = datetime.now()
            
            logger.info(f"تم النشر في القناة {channel_data['channel']} بنجاح")
        except Exception as e:
            logger.error(f"خطأ في النشر التلقائي للقناة {channel_data['channel']}: {e}")

def publish_to_channel(channel_data):
    """نشر المحتوى إلى قناة محددة"""
    channel_username = channel_data['channel']
    content_types = channel_data['types']
    mention_bot = channel_data['mention_bot']
    
    # جمع المحتوى من عمليات البحث الأخيرة
    media_group = []
    
    for content_type in content_types:
        if content_type in recent_searches and recent_searches[content_type]:
            # أخذ آخر 5 عمليات بحث لهذا النوع (أو أقل)
            for i, search_item in enumerate(recent_searches[content_type][:5]):
                if content_type == 'video':
                    # إضافة فيديو
                    media_group.append(telebot.types.InputMediaVideo(
                        media=search_item['url'],
                        caption=f"🎥 {search_item['search_term']}\n\n@PIXA7_BOT" if mention_bot and i == 0 else None
                    ))
                else:
                    # إضافة صورة
                    media_group.append(telebot.types.InputMediaPhoto(
                        media=search_item['url'],
                        caption=f"🖼️ {search_item['search_term']}\n\n@PIXA7_BOT" if mention_bot and i == 0 else None
                    ))
    
    if media_group:
        # إرسال المجموعة الوسائط
        bot.send_media_group(channel_username, media_group)
        
        # إرسال رسالة منفصلة إذا كان ذكر البوت معطلًا
        if not mention_bot:
            bot.send_message(channel_username, "🖼️ مجموعة من الصور والفيديوهات عالية الجودة\n\n@PIXA7_BOT")

# تحديث وظيفة process_search_term لتخزين عمليات البحث الأخيرة
def process_search_term(message, user_id):
    chat_id = message.chat.id
    search_term = message.text
    
    # زيادة عداد عمليات البحث
    bot_stats['total_searches'] += 1
    
    # حذف رسالة إدخال المستخدم
    try:
        bot.delete_message(chat_id, message.message_id)
    except Exception as e:
        logger.error(f"خطأ في حذف رسالة المستخدم: {e}")
    
    # استرجاع نوع المحتوى
    if user_id not in user_data or 'content_type' not in user_data[user_id]:
        show_main_menu(chat_id, user_id, new_message=True)
        return
    
    content_type = user_data[user_id]['content_type']
    
    # تحديث الرسالة السابقة لإظهار حالة التحميل
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=user_data[user_id]['search_message_id'],
            text="⏳ جاري البحث في قاعدة البيانات...",
            reply_markup=None
        )
    except Exception as e:
        logger.error(f"خطأ في عرض رسالة التحميل: {e}")
    
    # البحث في Pixabay
    results = search_pixabay(search_term, content_type)
    
    if not results or len(results) == 0:
        # عرض خيارات عند عدم وجود نتائج
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(f"{random.choice(NEW_EMOJIS)} بحث جديد", callback_data="search"))
        markup.add(InlineKeyboardButton(f"{random.choice(NEW_EMOJIS)} الرئيسية", callback_data="back_to_main"))
        
        try:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=user_data[user_id]['search_message_id'],
                text=f"❌ لم يتم العثور على نتائج لكلمة: {search_term}\nيرجى المحاولة بكلمات أخرى",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"خطأ في عرض رسالة عدم وجود نتائج: {e}")
        return
    
    # حفظ النتائج
    user_data[user_id]['search_term'] = search_term
    user_data[user_id]['search_results'] = results
    user_data[user_id]['current_index'] = 0
    
    # تخزين عملية البحث الأخيرة
    if results and content_type in ['photo', 'illustration', 'video']:
        # أخذ أول نتيجة
        first_result = results[0]
        if content_type == 'video' and 'videos' in first_result:
            url = first_result['videos']['medium']['url']
        else:
            url = first_result.get('largeImageURL', first_result.get('webformatURL', ''))
        
        # إضافة إلى عمليات البحث الأخيرة
        if content_type in recent_searches:
            recent_searches[content_type].insert(0, {
                'search_term': search_term,
                'url': url,
                'timestamp': datetime.now()
            })
            # الاحتفاظ بآخر 50 عملية بحث فقط
            recent_searches[content_type] = recent_searches[content_type][:50]
    
    # عرض النتيجة الأولى في نفس رسالة "جاري البحث"
    show_result(chat_id, user_id, message_id=user_data[user_id]['search_message_id'])

# ... (بقية الدوال تبقى كما هي)

if __name__ == '__main__':
    logger.info("بدء تشغيل البوت...")
    set_webhook()
    app.run(host='0.0.0.0', port=10000)