import asyncio
import logging
import json
import os
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, FloodWaitError
from telethon.tl.types import Message
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

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

# handler لبدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    # التحقق من وجود اشتراك فعال
    if not is_subscription_active(user_id):
        await update.message.reply_text(
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
            await client.connect()
            if await client.is_user_authorized():
                user_sessions[user_id] = {
                    "client": client,
                    "session_string": session_string
                }
        except Exception as e:
            logger.error(f"Error loading session for user {user_id}: {e}")
    
    # عرض لوحة التحكم الرئيسية
    keyboard = []
    
    if user_id in user_sessions:
        if user_settings[user_id].get("active", False):
            keyboard.append([InlineKeyboardButton("⏹ إيقاف النشر", callback_data='stop_posting')])
            # حساب الوقت المتبقي للنشر القادم
            interval = user_settings[user_id].get("interval", 5)
            next_post = "قريباً"  # يمكن تحسين هذا بحساب الوقت الفعلي
            status_text = f"🟢 النشر نشط - التالي: {next_post}"
        else:
            keyboard.append([InlineKeyboardButton("▶️ تشغيل النشر", callback_data='start_posting')])
            status_text = "🔴 النشر متوقف"
        
        keyboard.extend([
            [InlineKeyboardButton("📝 تعيين الكليشة", callback_data='set_message')],
            [InlineKeyboardButton("⏱ تعيين الفاصل", callback_data='set_interval')],
            [InlineKeyboardButton("⚙️ إعداد الحساب", callback_data='account_settings')],
            [InlineKeyboardButton("📊 الإحصائيات", callback_data='stats')],
            [InlineKeyboardButton("🚪 تسجيل الخروج", callback_data='logout')]
        ])
    else:
        keyboard.append([InlineKeyboardButton("🔐 تسجيل الدخول", callback_data='login')])
        status_text = "❌ لا توجد جلسة نشطة"
    
    # إضافة أزرار المدير إذا كان المستخدم مديراً
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 لوحة المدير", callback_data='admin_panel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = f"""
🤖 بوت النشر التلقائي

{status_text}

⚙️ الإعدادات الحالية:
- الكليشة: {user_settings[user_id].get('message', 'غير معينة')[:30] + '...' if user_settings[user_id].get('message') else 'غير معينة'}
- الفاصل الزمني: {user_settings[user_id].get('interval', 5)} دقائق

📅 انتهاء الاشتراك: {USER_SUBSCRIPTIONS[user_id].strftime('%Y-%m-%d') if user_id in USER_SUBSCRIPTIONS else 'غير معروف'}
"""
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

# handler لأزرار Inline
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    
    # التحقق من صلاحية الاشتراك
    if not is_subscription_active(user_id) and query.data != 'login':
        await query.edit_message_text("انتهت صلاحية اشتراكك. يرجى التواصل مع المدير لتجديده.")
        return
    
    if query.data == 'login':
        user_sessions[user_id] = {'step': 'phone'}
        await query.edit_message_text(
            "📱 يرجى إرسال رقم هاتفك مع رمز الدولة:\n"
            "مثال: +201234567890"
        )
    
    elif query.data == 'set_message':
        user_sessions[user_id] = {'step': 'set_message'}
        await query.edit_message_text(
            "📝 يرجى إرسال الكليشة التي تريد نشرها:\n\n"
            "ملاحظة: لا يسمح بالوسائط (صور، فيديو، روابط)"
        )
    
    elif query.data == 'set_interval':
        user_sessions[user_id] = {'step': 'set_interval'}
        await query.edit_message_text(
            "⏱ يرجى إرسال الفاصل الزمني بين النشرات (بالدقائق):\n\n"
            "الحد الأدنى: 5 دقائق"
        )
    
    elif query.data == 'start_posting':
        if user_id not in user_sessions:
            await query.edit_message_text("❌ يجب تسجيل الدخول أولاً!")
            return
        
        user_settings[user_id]["active"] = True
        save_user_settings(user_id, user_settings[user_id])
        
        # بدء مهمة النشر التلقائي
        auto_posting_tasks[user_id] = asyncio.create_task(auto_posting_task(user_id))
        
        await query.edit_message_text(
            "✅ تم بدء النشر التلقائي بنجاح!\n\n"
            "سيتم الآن نشر كليشتك في جميع مجموعاتك تلقائياً."
        )
    
    elif query.data == 'stop_posting':
        user_settings[user_id]["active"] = False
        save_user_settings(user_id, user_settings[user_id])
        
        # إيقاف مهمة النشر إذا كانت نشطة
        if user_id in auto_posting_tasks:
            auto_posting_tasks[user_id].cancel()
            del auto_posting_tasks[user_id]
        
        await query.edit_message_text("⏹ تم إيقاف النشر التلقائي.")
    
    elif query.data == 'account_settings':
        keyboard = [
            [InlineKeyboardButton("📝 تغيير الكليشة", callback_data='set_message')],
            [InlineKeyboardButton("⏱ تغيير الفاصل", callback_data='set_interval')],
            [InlineKeyboardButton("🗑 حذف الحساب", callback_data='delete_account')],
            [InlineKeyboardButton("↩️ رجوع", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚙️ إعدادات الحساب:\n\n"
            "يمكنك من هنا تعديل إعدادات حسابك أو حذفه بالكامل.",
            reply_markup=reply_markup
        )
    
    elif query.data == 'stats':
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
        
        await query.edit_message_text(stats_text)
    
    elif query.data == 'logout':
        if user_id in user_sessions:
            # إيقاف النشر أولاً
            if user_settings[user_id].get("active", False):
                user_settings[user_id]["active"] = False
                save_user_settings(user_id, user_settings[user_id])
                
                if user_id in auto_posting_tasks:
                    auto_posting_tasks[user_id].cancel()
                    del auto_posting_tasks[user_id]
            
            # قطع الاتصال بحساب Telegram
            await user_sessions[user_id]["client"].disconnect()
            del user_sessions[user_id]
            
            await query.edit_message_text(
                "✅ تم تسجيل الخروج بنجاح!\n\n"
                "للعودة مرة أخرى، ستحتاج إلى إدخال كود التفعيل من المدير."
            )
        else:
            await query.edit_message_text("❌ لا توجد جلسة نشطة لتسجيل الخروج منها.")
    
    elif query.data == 'delete_account':
        keyboard = [
            [InlineKeyboardButton("✅ نعم، احذف حسابي", callback_data='confirm_delete')],
            [InlineKeyboardButton("❌ لا، إلغاء", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚠️ تأكيد حذف الحساب\n\n"
            "هل أنت متأكد من أنك تريد حذف حسابك بالكامل؟\n"
            "هذا الإجراء لا يمكن التراجع عنه وسيتم حذف جميع بياناتك.",
            reply_markup=reply_markup
        )
    
    elif query.data == 'confirm_delete':
        delete_user_account(user_id)
        await query.edit_message_text(
            "🗑 تم حذف حسابك بنجاح.\n\n"
            "شكراً لك على استخدام البوت."
        )
    
    elif query.data == 'back_to_main':
        await start(update, context)
    
    elif query.data == 'admin_panel' and is_admin(user_id):
        keyboard = [
            [InlineKeyboardButton("🎟 إنشاء كود تفعيل", callback_data='generate_code')],
            [InlineKeyboardButton("👥 إدارة المستخدمين", callback_data='manage_users')],
            [InlineKeyboardButton("📊 إحصائيات عامة", callback_data='admin_stats')],
            [InlineKeyboardButton("📣 إشعار عام", callback_data='broadcast')],
            [InlineKeyboardButton("↩️ رجوع", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "👑 لوحة تحكم المدير\n\n"
            "من هنا يمكنك إدارة البوت والمستخدمين.",
            reply_markup=reply_markup
        )
    
    elif query.data == 'generate_code' and is_admin(user_id):
        # إنشاء كود تفعيل جديد
        import random
        import string
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        expiry_date = datetime.now() + timedelta(days=30)
        ACTIVATION_CODES[code] = {
            "created_by": user_id,
            "expiry_date": expiry_date,
            "used": False
        }
        await query.edit_message_text(
            f"🎟 تم إنشاء كود التفعيل:\n\n"
            f"الكود: `{code}`\n"
            f"صالح حتى: {expiry_date.strftime('%Y-%m-%d')}\n\n"
            "يمكن للمستخدم استخدام هذا الكود للتفعيل.",
            parse_mode='Markdown'
        )
    
    elif query.data == 'manage_users' and is_admin(user_id):
        keyboard = [
            [InlineKeyboardButton("🚫 حظر مستخدم", callback_data='ban_user')],
            [InlineKeyboardButton("📞 سحب أرقام", callback_data='withdraw_numbers')],
            [InlineKeyboardButton("↩️ رجوع", callback_data='admin_panel')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "👥 إدارة المستخدمين\n\n"
            "من هنا يمكنك حظر المستخدمين أو سحب أرقامهم.",
            reply_markup=reply_markup
        )
    
    elif query.data == 'admin_stats' and is_admin(user_id):
        stats_text = "📊 الإحصائيات العامة:\n\n"
        stats_text += f"👥 عدد المستخدمين: {len(user_settings)}\n"
        stats_text += f"🔢 عدد الجلسات النشطة: {len(user_sessions)}\n"
        stats_text += f"📨 إجمالي المنشورات: {sum(s.get('posts', 0) for s in user_stats.values())}\n"
        
        # عدد الأكواد المنتهية الصلاحية
        expired_codes = sum(1 for code in ACTIVATION_CODES.values() 
                           if code['expiry_date'] < datetime.now() or code['used'])
        stats_text += f"🎟 الأكواد المنتهية: {expired_codes}\n"
        
        await query.edit_message_text(stats_text)
    
    elif query.data == 'broadcast' and is_admin(user_id):
        user_sessions[user_id] = {'step': 'broadcast_message'}
        await query.edit_message_text(
            "📣 إشعار عام\n\n"
            "أرسل الرسالة التي تريد إرسالها لجميع المستخدمين:"
        )

# handler لمعالجة الرسائل النصية
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text
    
    if user_id not in user_sessions or 'step' not in user_sessions[user_id]:
        return
    
    step = user_sessions[user_id]['step']
    
    if step == 'phone':
        # التحقق من صحة رقم الهاتف
        if not re.match(r'^\+\d{8,15}$', text):
            await update.message.reply_text("❌ رقم الهاتف غير صحيح. يرجى إرسال رقم صحيح مع رمز الدولة.")
            return
        
        user_sessions[user_id]['phone'] = text
        user_sessions[user_id]['step'] = 'code'
        
        # إنشاء جلسة Telethon جديدة
        session = StringSession()
        client = TelegramClient(session, API_ID, API_HASH)
        await client.connect()
        
        # إرسال طلب الكود
        try:
            await client.send_code_request(text)
            user_sessions[user_id]['client'] = client
            await update.message.reply_text("📨 تم إرسال كود التحقق إلى حسابك. يرجى إرسال الكود:")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ في إرسال الكود: {str(e)}")
            del user_sessions[user_id]
    
    elif step == 'code':
        # محاولة تسجيل الدخول بالكود
        try:
            client = user_sessions[user_id]['client']
            await client.sign_in(user_sessions[user_id]['phone'], text)
            
            # حفظ الجلسة
            session_string = client.session.save()
            save_user_session(user_id, session_string)
            user_sessions[user_id]['session_string'] = session_string
            
            await update.message.reply_text("✅ تم تسجيل الدخول بنجاح!")
            
            # العودة إلى القائمة الرئيسية
            del user_sessions[user_id]['step']
            await start(update, context)
            
        except SessionPasswordNeededError:
            user_sessions[user_id]['step'] = 'password'
            await update.message.reply_text("🔐 حسابك محمي بكلمة مرور ثنائية. يرجى إرسال كلمة المرور:")
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ في تسجيل الدخول: {str(e)}")
            del user_sessions[user_id]
    
    elif step == 'password':
        # معالجة كلمة المرور الثنائية
        try:
            client = user_sessions[user_id]['client']
            await client.sign_in(password=text)
            
            # حفظ الجلسة
            session_string = client.session.save()
            save_user_session(user_id, session_string)
            user_sessions[user_id]['session_string'] = session_string
            
            await update.message.reply_text("✅ تم تسجيل الدخول بنجاح!")
            
            # العودة إلى القائمة الرئيسية
            del user_sessions[user_id]['step']
            await start(update, context)
            
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ في تسجيل الدخول: {str(e)}")
            del user_sessions[user_id]
    
    elif step == 'set_message':
        # حفظ الكليشة
        user_settings[user_id]['message'] = text
        save_user_settings(user_id, user_settings[user_id])
        
        await update.message.reply_text("✅ تم حفظ الكليشة بنجاح!")
        del user_sessions[user_id]['step']
        await start(update, context)
    
    elif step == 'set_interval':
        # التحقق من الفاصل الزمني
        try:
            interval
