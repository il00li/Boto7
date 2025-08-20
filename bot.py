import asyncio
import logging
import json
import os
import re
import random
import string
import threading
import time
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
import telebot
from telebot import types

# تكوين logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# بيانات API
API_ID = 23656977
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'
BOT_TOKEN = '8324471840:AAEX2W5x02F-NKZTt7qM0NNovrrF-gFRBsU'

# إنشاء كائن البوت
bot = telebot.TeleBot(BOT_TOKEN)

# إعدادات المدير
ADMIN_IDS = [7251748706]  # أيدي المدير
ACTIVATION_CODES = {}  # ستخزن أكواد التفعيل {code: {user_id, expiry_date}}
USER_SUBSCRIPTIONS = {}  # ستخزن اشتراكات المستخدمين {user_id: expiry_date}

# هياكل البيانات
user_sessions = {}  # جلسات المستخدمين النشطة
user_settings = {}  # إعدادات المستخدمين
auto_posting_tasks = {}  # مهام النشر التلقائي
user_stats = {}  # إحصائيات المستخدمين

# مسارات الملفات
SESSIONS_DIR = "sessions"
SETTINGS_DIR = "settings"
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(SETTINGS_DIR, exist_ok=True)

# دالة للتحقق إذا كان المستخدم مديراً
def is_admin(user_id):
    return user_id in ADMIN_IDS

# دالة للتحقق من صلاحية الاشتراك
def is_subscription_active(user_id):
    if user_id in USER_SUBSCRIPTIONS:
        return USER_SUBSCRIPTIONS[user_id] > datetime.now()
    return False

# دالة لتحميل إعدادات المستخدم
def load_user_settings(user_id):
    settings_file = os.path.join(SETTINGS_DIR, f"{user_id}.json")
    if os.path.exists(settings_file):
        with open(settings_file, 'r') as f:
            return json.load(f)
    return {"message": "", "interval": 5, "active": False}

# دالة لحفظ إعدادات المستخدم
def save_user_settings(user_id, settings):
    settings_file = os.path.join(SETTINGS_DIR, f"{user_id}.json")
    with open(settings_file, 'w') as f:
        json.dump(settings, f)

# دالة لتحميل جلسة المستخدم
def load_user_session(user_id):
    session_file = os.path.join(SESSIONS_DIR, f"{user_id}.session")
    if os.path.exists(session_file):
        with open(session_file, 'r') as f:
            return f.read().strip()
    return None

# دالة لحفظ جلسة المستخدم
def save_user_session(user_id, session_string):
    session_file = os.path.join(SESSIONS_DIR, f"{user_id}.session")
    with open(session_file, 'w') as f:
        f.write(session_string)

# دالة لحذف حساب المستخدم
def delete_user_account(user_id):
    # حذف الجلسة
    session_file = os.path.join(SESSIONS_DIR, f"{user_id}.session")
    if os.path.exists(session_file):
        os.remove(session_file)
    
    # حذف الإعدادات
    settings_file = os.path.join(SETTINGS_DIR, f"{user_id}.json")
    if os.path.exists(settings_file):
        os.remove(settings_file)
    
    # إيقاف النشر إذا كان نشطاً
    if user_id in auto_posting_tasks:
        auto_posting_tasks[user_id].cancel()
        del auto_posting_tasks[user_id]
    
    # حذف من الذاكرة
    if user_id in user_sessions:
        del user_sessions[user_id]
    if user_id in user_settings:
        del user_settings[user_id]
    if user_id in user_stats:
        del user_stats[user_id]

# دالة النشر التلقائي
async def auto_posting_task(user_id):
    while user_id in user_settings and user_settings[user_id].get("active", False):
        try:
            client = user_sessions[user_id]["client"]
            settings = user_settings[user_id]
            message = settings["message"]
            
            # الحصول على جميع الدردشات والمجموعات
            dialogs = await client.get_dialogs()
            
            # النشر في المجموعات والقنوات فقط (لا الدردشات الخاصة)
            for dialog in dialogs:
                if dialog.is_group or dialog.is_channel:
                    try:
                        await client.send_message(dialog.id, message)
                        
                        # تحديث الإحصائيات
                        if user_id not in user_stats:
                            user_stats[user_id] = {"posts": 0, "groups": set()}
                        
                        user_stats[user_id]["posts"] += 1
                        user_stats[user_id]["groups"].add(dialog.id)
                        
                        await asyncio.sleep(5)  # تأخير بين الرسائل لتجنب الحظر
                    except Exception as e:
                        logger.error(f"Error posting in {dialog.id}: {e}")
                        continue
            
            # الانتظار للفاصل الزمني المحدد
            interval = settings.get("interval", 5)
            for i in range(interval * 60):
                if not user_settings[user_id].get("active", False):
                    break
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Error in auto_posting_task for user {user_id}: {e}")
            break

# دالة للتحقق من انتهاء الاشتراكات دورياً
def check_expired_subscriptions():
    while True:
        try:
            now = datetime.now()
            expired_users = []
            
            for user_id, expiry_date in USER_SUBSCRIPTIONS.items():
                if expiry_date < now:
                    expired_users.append(user_id)
                    
                    # إرسال تنبيه للمستخدم
                    try:
                        bot.send_message(
                            user_id,
                            "⚠️ انتهت صلاحية اشتراكك!\n\n"
                            "يرجى التواصل مع المدير لتجديد الاشتراك."
                        )
                    except Exception as e:
                        logger.error(f"Error sending message to user {user_id}: {e}")
            
            # إرسال تقرير للمدير
            if expired_users and ADMIN_IDS:
                for admin_id in ADMIN_IDS:
                    try:
                        bot.send_message(
                            admin_id,
                            f"📊 تقرير الاشتراكات المنتهية:\n\n"
                            f"عدد المستخدمين المنتهية صلاحيتهم: {len(expired_users)}"
                        )
                    except Exception as e:
                        logger.error(f"Error sending report to admin {admin_id}: {e}")
            
            # الانتظار 24 ساعة قبل التحقق مرة أخرى
            time.sleep(86400)  # 24 ساعة
                
        except Exception as e:
            logger.error(f"Error in subscription check: {e}")
            time.sleep(3600)  # الانتظار ساعة واحدة قبل إعادة المحاولة

# بدء خيط للتحقق من الاشتراكات المنتهية
subscription_thread = threading.Thread(target=check_expired_subscriptions, daemon=True)
subscription_thread.start()

# handler لبدء البوت
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    
    # التحقق من وجود اشتراك فعال
    if not is_subscription_active(user_id):
        bot.send_message(
            user_id,
            "🔒 البوت مدفوع ويتطلب اشتراكاً\n\n"
            "يجب عليك الحصول على كود تفعيل من المدير لاستخدام البوت.\n"
            "يرجى التواصل مع المدير للحصول على كود التفعيل."
        )
        return
    
    # تحميل إعدادات المستخدم إذا كانت موجودة
    if user_id not in user_settings:
        user_settings[user_id] = load_user_settings(user_id)
    
    # تحميل الجلسة إذا كانت موجودة
    session_string = load_user_session(user_id)
    if session_string and user_id not in user_sessions:
        try:
            client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
            asyncio.run(client.connect())
            if asyncio.run(client.is_user_authorized()):
                user_sessions[user_id] = {
                    "client": client,
                    "session_string": session_string
                }
        except Exception as e:
            logger.error(f"Error loading session for user {user_id}: {e}")
    
    # عرض لوحة التحكم الرئيسية
    keyboard = types.InlineKeyboardMarkup()
    
    if user_id in user_sessions:
        if user_settings[user_id].get("active", False):
            keyboard.add(types.InlineKeyboardButton("⏹ إيقاف النشر", callback_data='stop_posting'))
            # حساب الوقت المتبقي للنشر القادم
            interval = user_settings[user_id].get("interval", 5)
            next_post = "قريباً"  # يمكن تحسين هذا بحساب الوقت الفعلي
            status_text = f"🟢 النشر نشط - التالي: {next_post}"
        else:
            keyboard.add(types.InlineKeyboardButton("▶️ تشغيل النشر", callback_data='start_posting'))
            status_text = "🔴 النشر متوقف"
        
        keyboard.add(
            types.InlineKeyboardButton("📝 تعيين الكليشة", callback_data='set_message'),
            types.InlineKeyboardButton("⏱ تعيين الفاصل", callback_data='set_interval')
        )
        keyboard.add(
            types.InlineKeyboardButton("⚙️ إعداد الحساب", callback_data='account_settings'),
            types.InlineKeyboardButton("📊 الإحصائيات", callback_data='stats')
        )
        keyboard.add(types.InlineKeyboardButton("🚪 تسجيل الخروج", callback_data='logout'))
    else:
        keyboard.add(types.InlineKeyboardButton("🔐 تسجيل الدخول", callback_data='login'))
        status_text = "❌ لا توجد جلسة نشطة"
    
    # إضافة أزرار المدير إذا كان المستخدم مديراً
    if is_admin(user_id):
        keyboard.add(types.InlineKeyboardButton("👑 لوحة المدير", callback_data='admin_panel'))
    
    welcome_text = f"""
🤖 بوت النشر التلقائي

{status_text}

⚙️ الإعدادات الحالية:
- الكليشة: {user_settings[user_id].get('message', 'غير معينة')[:30] + '...' if user_settings[user_id].get('message') else 'غير معينة'}
- الفاصل الزمني: {user_settings[user_id].get('interval', 5)} دقائق

📅 انتهاء الاشتراك: {USER_SUBSCRIPTIONS[user_id].strftime('%Y-%m-%d') if user_id in USER_SUBSCRIPTIONS else 'غير معروف'}
"""
    bot.send_message(user_id, welcome_text, reply_markup=keyboard)

# handler لأزرار Inline
@bot.callback_query_handler(func=lambda call: True)
def button_handler(call):
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)
    
    # التحقق من صلاحية الاشتراك
    if not is_subscription_active(user_id) and call.data != 'login':
        bot.edit_message_text(
            "انتهت صلاحية اشتراكك. يرجى التواصل مع المدير لتجديده.",
            user_id,
            call.message.message_id
        )
        return
    
    if call.data == 'login':
        user_sessions[user_id] = {'step': 'phone'}
        bot.edit_message_text(
            "📱 يرجى إرسال رقم هاتفك مع رمز الدولة:\n"
            "مثال: +201234567890",
            user_id,
            call.message.message_id
        )
    
    elif call.data == 'set_message':
        user_sessions[user_id] = {'step': 'set_message'}
        bot.edit_message_text(
            "📝 يرجى إرسال الكليشة التي تريد نشرها:\n\n"
            "ملاحظة: لا يسمح بالوسائط (صور، فيديو، روابط)",
            user_id,
            call.message.message_id
        )
    
    elif call.data == 'set_interval':
        user_sessions[user_id] = {'step': 'set_interval'}
        bot.edit_message_text(
            "⏱ يرجى إرسال الفاصل الزمني بين النشرات (بالدقائق):\n\n"
            "الحد الأدنى: 5 دقائق",
            user_id,
            call.message.message_id
        )
    
    elif call.data == 'start_posting':
        if user_id not in user_sessions:
            bot.edit_message_text(
                "❌ يجب تسجيل الدخول أولاً!",
                user_id,
                call.message.message_id
            )
            return
        
        user_settings[user_id]["active"] = True
        save_user_settings(user_id, user_settings[user_id])
        
        # بدء مهمة النشر التلقائي
        auto_posting_tasks[user_id] = asyncio.create_task(auto_posting_task(user_id))
        
        bot.edit_message_text(
            "✅ تم بدء النشر التلقائي بنجاح!\n\n"
            "سيتم الآن نشر كليشتك في جميع مجموعاتك تلقائياً.",
            user_id,
            call.message.message_id
        )
    
    elif call.data == 'stop_posting':
        user_settings[user_id]["active"] = False
        save_user_settings(user_id, user_settings[user_id])
        
        # إيقاف مهمة النشر إذا كانت نشطة
        if user_id in auto_posting_tasks:
            auto_posting_tasks[user_id].cancel()
            del auto_posting_tasks[user_id]
        
        bot.edit_message_text(
            "⏹ تم إيقاف النشر التلقائي.",
            user_id,
            call.message.message_id
        )
    
    elif call.data == 'account_settings':
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("📝 تغيير الكليشة", callback_data='set_message'),
            types.InlineKeyboardButton("⏱ تغيير الفاصل", callback_data='set_interval')
        )
        keyboard.add(types.InlineKeyboardButton("🗑 حذف الحساب", callback_data='delete_account'))
        keyboard.add(types.InlineKeyboardButton("↩️ رجوع", callback_data='back_to_main'))
        
        bot.edit_message_text(
            "⚙️ إعدادات الحساب:\n\n"
            "يمكنك من هنا تعديل إعدادات حسابك أو حذفه بالكامل.",
            user_id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    elif call.data == 'stats':
        stats_text = "📊 الإحصائيات:\n\n"
        
        if user_id in user_stats:
            stats = user_stats[user_id]
            stats_text += f"عدد المنشورات: {stats.get('posts', 0)}\n"
            stats_text += f"عدد المجموعات: {len(stats.get('groups', set()))}\n"
        else:
            stats_text += "لا توجد إحصائيات حتى الآن.\n"
        
        # إحصائيات عامة (للمدير فقط)
        if is_admin(user_id):
            stats_text += f"\n👥 المستخدمون النشطون: {len(user_sessions)}\n"
            stats_text += f"📨 إجمالي المنشورات: {sum(s.get('posts', 0) for s in user_stats.values())}\n"
        
        bot.edit_message_text(
            stats_text,
            user_id,
            call.message.message_id
        )
    
    elif call.data == 'logout':
        if user_id in user_sessions:
            # إيقاف النشر أولاً
            if user_settings[user_id].get("active", False):
                user_settings[user_id]["active"] = False
                save_user_settings(user_id, user_settings[user_id])
                
                if user_id in auto_posting_tasks:
                    auto_posting_tasks[user_id].cancel()
                    del auto_posting_tasks[user_id]
            
            # قطع الاتصال بحساب Telegram
            asyncio.run(user_sessions[user_id]["client"].disconnect())
            del user_sessions[user_id]
            
            bot.edit_message_text(
                "✅ تم تسجيل الخروج بنجاح!\n\n"
                "للعودة مرة أخرى، ستحتاج إلى إدخال كود التفعيل من المدير.",
                user_id,
                call.message.message_id
            )
        else:
            bot.edit_message_text(
                "❌ لا توجد جلسة نشطة لتسجيل الخروج منها.",
                user_id,
                call.message.message_id
            )
    
    elif call.data == 'delete_account':
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(
            types.InlineKeyboardButton("✅ نعم، احذف حسابي", callback_data='confirm_delete'),
            types.InlineKeyboardButton("❌ لا، إلغاء", callback_data='back_to_main')
        )
        
        bot.edit_message_text(
            "⚠️ تأكيد حذف الحساب\n\n"
            "هل أنت متأكد من أنك تريد حذف حسابك بالكامل؟\n"
            "هذا الإجراء لا يمكن التراجع عنه وسيتم حذف جميع بياناتك.",
            user_id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    elif call.data == 'confirm_delete':
        delete_user_account(user_id)
        bot.edit_message_text(
            "🗑 تم حذف حسابك بنجاح.\n\n"
            "شكراً لك على استخدام البوت.",
            user_id,
            call.message.message_id
        )
    
    elif call.data == 'back_to_main':
        start(call.message)
    
    elif call.data == 'admin_panel' and is_admin(user_id):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🎟 إنشاء كود تفعيل", callback_data='generate_code'))
        keyboard.add(types.InlineKeyboardButton("👥 إدارة المستخدمين", callback_data='manage_users'))
        keyboard.add(types.InlineKeyboardButton("📊 إحصائيات عامة", callback_data='admin_stats'))
        keyboard.add(types.InlineKeyboardButton("📣 إشعار عام", callback_data='broadcast'))
        keyboard.add(types.InlineKeyboardButton("↩️ رجوع", callback_data='back_to_main'))
        
        bot.edit_message_text(
            "👑 لوحة تحكم المدير\n\n"
            "من هنا يمكنك إدارة البوت والمستخدمين.",
            user_id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    elif call.data == 'generate_code' and is_admin(user_id):
        # إنشاء كود تفعيل جديد
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        expiry_date = datetime.now() + timedelta(days=30)
        ACTIVATION_CODES[code] = {
            "created_by": user_id,
            "expiry_date": expiry_date,
            "used": False
        }
        bot.edit_message_text(
            f"🎟 تم إنشاء كود التفعيل:\n\n"
            f"الكود: `{code}`\n"
            f"صالح حتى: {expiry_date.strftime('%Y-%m-%d')}\n\n"
            "يمكن للمستخدم استخدام هذا الكود للتفعيل.",
            user_id,
            call.message.message_id,
            parse_mode='Markdown'
        )
    
    elif call.data == 'manage_users' and is_admin(user_id):
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("🚫 حظر مستخدم", callback_data='ban_user'))
        keyboard.add(types.InlineKeyboardButton("📞 سحب أرقام", callback_data='withdraw_numbers'))
        keyboard.add(types.InlineKeyboardButton("↩️ رجوع", callback_data='admin_panel'))
        
        bot.edit_message_text(
            "👥 إدارة المستخدمين\n\n"
            "من هنا يمكنك حظر المستخدمين أو سحب أرقامهم.",
            user_id,
            call.message.message_id,
            reply_markup=keyboard
        )
    
    elif call.data == 'admin_stats' and is_admin(user_id):
        stats_text = "📊 الإحصائيات العامة:\n\n"
        stats_text += f"👥 عدد المستخدمين: {len(user_settings)}\n"
        stats_text += f"🔢 عدد الجلسات النشطة: {len(user_sessions)}\n"
        stats_text += f"📨 إجمالي المنشورات: {sum(s.get('posts', 0) for s in user_stats.values())}\n"
        
        # عدد الأكواد المنتهية الصلاحية
        expired_codes = sum(1 for code in ACTIVATION_CODES.values() 
                           if code['expiry_date'] < datetime.now() or code['used'])
        stats_text += f"🎟 الأكواد المنتهية: {expired_codes}\n"
        
        bot.edit_message_text(
            stats_text,
            user_id,
            call.message.message_id
        )
    
    elif call.data == 'broadcast' and is_admin(user_id):
        user_sessions[user_id] = {'step': 'broadcast_message'}
        bot.edit_message_text(
            "📣 إشعار عام\n\n"
            "أرسل الرسالة التي تريد إرسالها لجميع المستخدمين:",
            user_id,
            call.message.message_id
        )

# handler لمعالجة الرسائل النصية
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    text = message.text
    
    if user_id not in user_sessions or 'step' not in user_sessions[user_id]:
        return
    
    step = user_sessions[user_id]['step']
    
    if step == 'phone':
        # التحقق من صحة رقم الهاتف
        if not re.match(r'^\+\d{8,15}$', text):
            bot.send_message(user_id, "❌ رقم الهاتف غير صحيح. يرجى إرسال رقم صحيح مع رمز الدولة.")
            return
        
        user_sessions[user_id]['phone'] = text
        user_sessions[user_id]['step'] = 'code'
        
        # إنشاء جلسة Telethon جديدة
        session = StringSession()
        client = TelegramClient(session, API_ID, API_HASH)
        asyncio.run(client.connect())
        
        # إرسال طلب الكود
        try:
            asyncio.run(client.send_code_request(text))
            user_sessions[user_id]['client'] = client
            bot.send_message(user_id, "📨 تم إرسال كود التحقق إلى حسابك. يرجى إرسال الكود:")
        except Exception as e:
            bot.send_message(user_id, f"❌ خطأ في إرسال الكود: {str(e)}")
            del user_sessions[user_id]
    
    elif step == 'code':
        # محاولة تسجيل الدخول بالكود
        try:
            client = user_sessions[user_id]['client']
            asyncio.run(client.sign_in(user_sessions[user_id]['phone'], text))
            
            # حفظ الجلسة
            session_string = client.session.save()
            save_user_session(user_id, session_string)
            user_sessions[user_id]['session_string'] = session_string
            
            bot.send_message(user_id, "✅ تم تسجيل الدخول بنجاح!")
            
            # العودة إلى القائمة الرئيسية
            del user_sessions[user_id]['step']
            start(message)
            
        except SessionPasswordNeededError:
            user_sessions[user_id]['step'] = 'password'
            bot.send_message(user_id, "🔐 حسابك محمي بكلمة مرور ثنائية. يرجى إرسال كلمة المرور:")
        except Exception as e:
            bot.send_message(user_id, f"❌ خطأ في تسجيل الدخول: {str(e)}")
            del user_sessions[user_id]
    
    elif step == 'password':
        # معالجة كلمة المرور الثنائية
        try:
            client = user_sessions[user_id]['client']
            asyncio.run(client.sign_in(password=text))
            
            # حفظ الجلسة
            session_string = client.session.save()
            save_user_session(user_id, session_string)
            user_sessions[user_id]['session_string'] = session_string
            
            bot.send_message(user_id, "✅ تم تسجيل الدخول بنجاح!")
            
            # العودة إلى القائمة الرئيسية
            del user_sessions[user_id]['step']
            start(message)
            
        except Exception as e:
            bot.send_message(user_id, f"❌ خطأ في تسجيل الدخول: {str(e)}")
            del user_sessions[user_id]
    
    elif step == 'set_message':
        # حفظ الكليشة
        user_settings[user_id]['message'] = text
        save_user_settings(user_id, user_settings[user_id])
        
        bot.send_message(user_id, "✅ تم حفظ الكليشة بنجاح!")
        del user_sessions[user_id]['step']
        start(message)
    
    elif step == 'set_interval':
        # التحقق من الفاصل الزمني
        try:
            interval = int(text)
            if interval < 5:
                bot.send_message(user_id, "❌ الفاصل الزمني يجب أن يكون 5 دقائق على الأقل.")
                return
            
            user_settings[user_id]['interval'] = interval
            save_user_settings(user_id, user_settings[user_id])
            
            bot.send_message(user_id, f"✅ تم تعيين الفاصل الزمني إلى {interval} دقائق.")
            del user_sessions[user_id]['step']
            start(message)
            
        except ValueError:
            bot.send_message(user_id, "❌ يرجى إدخال رقم صحيح للفاصل الزمني.")
    
    elif step == 'activation_code':
        # التحقق من كود التفعيل
        if text in ACTIVATION_CODES:
            code_data = ACTIVATION_CODES[text]
            
            if code_data['expiry_date'] < datetime.now() or code_data['used']:
                bot.send_message(user_id, "❌ كود التفعيل منتهي الصلاحية أو مستخدم مسبقاً.")
            else:
                # تفعيل الاشتراك
                expiry_date = datetime.now() + timedelta(days=30)
                USER_SUBSCRIPTIONS[user_id] = expiry_date
                ACTIVATION_CODES[text]['used'] = True
                ACTIVATION_CODES[text]['used_by'] = user_id
                
                bot.send_message(
                    user_id,
                    f"✅ تم تفعيل الاشتراك بنجاح!\n\n"
                    f"صالح حتى: {expiry_date.strftime('%Y-%m-%d')}"
                )
                
                # إرسال إشعار للمدير
                for admin_id in ADMIN_IDS:
                    try:
                        bot.send_message(
                            admin_id,
                            f"🎉 تم تفعيل اشتراك جديد\n\n"
                            f"المستخدم: {user_id}\n"
                            f"الكود: {text}\n"
                            f"الصلاحية: {expiry_date.strftime('%Y-%m-%d')}"
                        )
                    except:
                        pass
                
                del user_sessions[user_id]['step']
                start(message)
        else:
            bot.send_message(user_id, "❌ كود التفعيل غير صحيح.")
    
    elif step == 'broadcast_message' and is_admin(user_id):
        # إرسال إشعار عام لجميع المستخدمين
        sent = 0
        failed = 0
        
        for uid in user_settings:
            try:
                bot.send_message(uid, f"📣 إشعار من المدير:\n\n{text}")
                sent += 1
            except:
                failed += 1
        
        bot.send_message(
            user_id,
            f"✅ تم إرسال الإشعار:\n\n"
            f"تم بنجاح: {sent}\n"
            f"فشل: {failed}"
        )
        del user_sessions[user_id]['step']

# تشغيل البوت
if __name__ == '__main__':
    print("🤖 بوت النشر التلقائي يعمل الآن...")
    bot.infinity_polling()
