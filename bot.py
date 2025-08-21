import logging
import json
import os
import re
import asyncio
import random
import string
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler, ConversationHandler

# تكوين logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# بيانات البوت
TOKEN = "8324471840:AAEX2W5x02F-NKZTt7qM0NNovrrF-gFRBsU"
API_ID = 23656977
API_HASH = "49d3f43531a92b3f5bc403766313ca1e"
ADMIN_ID = 6689435577

# حالات المحادثة
(
    MAIN_MENU, USER_SETTINGS, ADMIN_PANEL, 
    GENERATE_CODE, BAN_USER, UNBAN_USER, 
    DELETE_USER, BROADCAST, VIEW_USER,
    SET_CLONE, SET_INTERVAL, CONFIRM_DELETE,
    PHONE, CODE
) = range(14)

# ملفات البيانات
USERS_FILE = "users.json"
CODES_FILE = "codes.json"
SESSIONS_DIR = "data/sessions"

# بيانات المستخدمين والأكواد
users = {}
codes = {}
banned_users = set()

# تحميل البيانات من الملفات
def load_data():
    global users, codes, banned_users
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
                banned_users = set(str(uid) for uid, data in users.items() if data.get("banned", False))
    except Exception as e:
        logger.error(f"Error loading users: {e}")
        users = {}
    
    try:
        if os.path.exists(CODES_FILE):
            with open(CODES_FILE, 'r', encoding='utf-8') as f:
                codes = json.load(f)
    except Exception as e:
        logger.error(f"Error loading codes: {e}")
        codes = {}
    
    if not os.path.exists(SESSIONS_DIR):
        os.makedirs(SESSIONS_DIR)

# حفظ البيانات إلى الملفات
def save_data():
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Error saving users: {e}")
    
    try:
        with open(CODES_FILE, 'w', encoding='utf-8') as f:
            json.dump(codes, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Error saving codes: {e}")

# إنشاء كود تفعيل جديد
def generate_code(duration_days=30):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    expires_at = (datetime.now() + timedelta(days=duration_days)).strftime("%Y-%m-%d %H:%M:%S")
    
    codes[code] = {
        "created_at": created_at,
        "expires_at": expires_at,
        "used": False,
        "used_by": None,
        "used_at": None
    }
    
    save_data()
    return code

# التحقق من صلاحية الاشتراك
def check_subscription(user_id):
    user_id = str(user_id)
    if user_id not in users:
        return False
    
    user_data = users[user_id]
    if not user_data.get("activated", False):
        return False
    
    expires_at = datetime.strptime(user_data["expires_at"], "%Y-%m-%d %H:%M:%S")
    if datetime.now() > expires_at:
        users[user_id]["activated"] = False
        save_data()
        return False
    
    return True

# التحقق من وجود جلسة للمستخدم
def has_session(user_id):
    user_id = str(user_id)
    session_file = os.path.join(SESSIONS_DIR, f"{user_id}.session")
    return os.path.exists(session_file)

# حذف جلسة المستخدم
def delete_session(user_id):
    user_id = str(user_id)
    session_file = os.path.join(SESSIONS_DIR, f"{user_id}.session")
    try:
        if os.path.exists(session_file):
            os.remove(session_file)
            return True
        return False
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        return False

# حظر مستخدم
def ban_user(user_id):
    user_id = str(user_id)
    if user_id in users:
        users[user_id]["banned"] = True
        banned_users.add(user_id)
        save_data()
        return True
    return False

# فك حظر مستخدم
def unban_user(user_id):
    user_id = str(user_id)
    if user_id in users:
        users[user_id]["banned"] = False
        if user_id in banned_users:
            banned_users.remove(user_id)
        save_data()
        return True
    return False

# حذف حساب مستخدم
def delete_user_account(user_id):
    user_id = str(user_id)
    delete_session(user_id)
    if user_id in users:
        del users[user_id]
        if user_id in banned_users:
            banned_users.remove(user_id)
        save_data()
        return True
    return False

# التحقق من أن النص لا يحتوي على روابط
def contains_links(text):
    url_pattern = re.compile(
        r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    )
    return bool(url_pattern.search(text))

# القائمة الرئيسية
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user = query.from_user
    else:
        user = update.effective_user
    
    # التحقق إذا كان المستخدم محظوراً
    if str(user.id) in banned_users:
        if query:
            await query.edit_message_text("⛔ تم حظرك من استخدام البوت.")
        else:
            await update.message.reply_text("⛔ تم حظرك من استخدام البوت.")
        return
    
    # التحقق من وجود المستخدم في النظام
    if str(user.id) not in users:
        users[str(user.id)] = {
            "activated": False,
            "activation_code": None,
            "activated_at": None,
            "expires_at": None,
            "banned": False,
            "settings": {
                "clone": "مرحباً! هذا منشور تجريبي.",
                "interval": 300
            }
        }
        save_data()
    
    # التحقق من صلاحية الاشتراك
    has_active_subscription = check_subscription(user.id)
    
    if user.id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("👤 إدارة المستخدم", callback_data="user_panel")],
            [InlineKeyboardButton("👑 لوحة المدير", callback_data="admin_panel")]
        ]
    else:
        if has_active_subscription:
            expires_at = datetime.strptime(users[str(user.id)]["expires_at"], "%Y-%m-%d %H:%M:%S")
            remaining_days = (expires_at - datetime.now()).days
            
            has_active_session = has_session(user.id)
            
            if has_active_session:
                keyboard = [
                    [InlineKeyboardButton("🚀 بدء النشر", callback_data="start_posting")],
                    [InlineKeyboardButton("⏹ إيقاف النشر", callback_data="stop_posting")],
                    [InlineKeyboardButton("📊 الإحصائيات", callback_data="user_stats")],
                    [InlineKeyboardButton("⚙️ إعدادات الحساب", callback_data="account_settings")]
                ]
            else:
                keyboard = [
                    [InlineKeyboardButton("🔐 تسجيل الدخول", callback_data="login")],
                    [InlineKeyboardButton("📊 الإحصائيات", callback_data="user_stats")],
                    [InlineKeyboardButton("⚙️ إعدادات الحساب", callback_data="account_settings")]
                ]
        else:
            keyboard = [
                [InlineKeyboardButton("🔓 تفعيل الاشتراك", callback_data="activate_subscription")]
            ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if has_active_subscription:
        expires_at = datetime.strptime(users[str(user.id)]["expires_at"], "%Y-%m-%d %H:%M:%S")
        remaining_days = (expires_at - datetime.now()).days
        message_text = f"مرحباً {user.first_name}! 👋\n\nاشتراكك نشط لمدة {remaining_days} يوم"
    else:
        message_text = f"مرحباً {user.first_name}! 👋\n\nليس لديك اشتراك نشط في البوت."
    
    if query:
        await query.edit_message_text(message_text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(message_text, reply_markup=reply_markup)
    
    return MAIN_MENU

# معالجة الأزرار الرئيسية
async def handle_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "user_panel":
        return await user_panel(update, context)
    elif data == "admin_panel":
        return await admin_panel(update, context)
    elif data == "start_posting":
        return await start_posting(update, context)
    elif data == "stop_posting":
        return await stop_posting(update, context)
    elif data == "user_stats":
        return await user_statistics(update, context)
    elif data == "account_settings":
        return await account_settings(update, context)
    elif data == "login":
        return await start_login(update, context)
    elif data == "activate_subscription":
        await query.edit_message_text(
            "لتفعيل الاشتراك، يرجى إدخال كود التفعيل باستخدام الأمر:\n/activate كود_التفعيل"
        )
        return MAIN_MENU

# لوحة المستخدم
async def user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="user_stats")],
        [InlineKeyboardButton("⚙️ إعدادات الحساب", callback_data="account_settings")],
        [InlineKeyboardButton("🔐 تسجيل الدخول", callback_data="login")],
        [InlineKeyboardButton("🔓 تفعيل الاشتراك", callback_data="activate_subscription")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "👤 لوحة المستخدم\n\nاختر الخدمة التي تريدها:",
        reply_markup=reply_markup
    )
    
    return USER_SETTINGS

# معالجة لوحة المستخدم
async def handle_user_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "user_stats":
        return await user_statistics(update, context)
    elif data == "account_settings":
        return await account_settings(update, context)
    elif data == "login":
        return await start_login(update, context)
    elif data == "activate_subscription":
        await query.edit_message_text(
            "لتفعيل الاشتراك، يرجى إدخال كود التفعيل باستخدام الأمر:\n/activate كود_التفعيل"
        )
        return USER_SETTINGS
    elif data == "back_main":
        return await main_menu(update, context)

# لوحة المدير
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🔑 إنشاء كود تفعيل", callback_data="generate_code")],
        [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="ban_user")],
        [InlineKeyboardButton("✅ فك حظر مستخدم", callback_data="unban_user")],
        [InlineKeyboardButton("🗑️ حذف حساب مستخدم", callback_data="delete_user")],
        [InlineKeyboardButton("📢 إرسال إشعار عام", callback_data="broadcast")],
        [InlineKeyboardButton("👀 عرض رسائل مستخدم", callback_data="view_user")],
        [InlineKeyboardButton("📈 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_main")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "👑 لوحة المدير\n\nاختر الإجراء الذي تريد تنفيذه:",
        reply_markup=reply_markup
    )
    
    return ADMIN_PANEL

# معالجة لوحة المدير
async def handle_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "generate_code":
        await query.edit_message_text(
            "الرجاء إرسال عدد الأيام لصلاحية الكود (افتراضي 30 يوم):"
        )
        return GENERATE_CODE
    elif data == "ban_user":
        await query.edit_message_text(
            "الرجاء إرسال معرف المستخدم الذي تريد حظره:"
        )
        return BAN_USER
    elif data == "unban_user":
        await query.edit_message_text(
            "الرجاء إرسال معرف المستخدم الذي تريد فك حظره:"
        )
        return UNBAN_USER
    elif data == "delete_user":
        await query.edit_message_text(
            "الرجاء إرسال معرف المستخدم الذي تريد حذف حسابه:"
        )
        return DELETE_USER
    elif data == "broadcast":
        await query.edit_message_text(
            "الرجاء إرسال الرسالة التي تريد إرسالها لجميع المستخدمين:"
        )
        return BROADCAST
    elif data == "view_user":
        await query.edit_message_text(
            "الرجاء إرسال معرف المستخدم الذي تريد عرض رسائله:"
        )
        return VIEW_USER
    elif data == "admin_stats":
        return await admin_statistics(update, context)
    elif data == "back_main":
        return await main_menu(update, context)

# معالجة إنشاء كود التفعيل
async def handle_generate_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return ConversationHandler.END
    
    duration_input = update.message.text
    try:
        duration_days = int(duration_input) if duration_input.isdigit() else 30
        if duration_days < 1:
            await update.message.reply_text("❌ عدد الأيام يجب أن يكون أكبر من الصفر.")
            return GENERATE_CODE
        
        code = generate_code(duration_days)
        await update.message.reply_text(
            f"✅ تم إنشاء كود جديد:\n\nالكود: `{code}`\nالصالح لمدة: {duration_days} يوم"
        )
        return await admin_panel(update, context)
    except ValueError:
        await update.message.reply_text("❌ المدخل غير صحيح! يرجى إدخال رقم صحيح.")
        return GENERATE_CODE

# معالجة حظر مستخدم
async def handle_ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return ConversationHandler.END
    
    user_id_input = update.message.text
    try:
        user_id = int(user_id_input)
        if ban_user(user_id):
            await update.message.reply_text(f"✅ تم حظر المستخدم {user_id} بنجاح.")
        else:
            await update.message.reply_text(f"❌ لم يتم العثور على المستخدم {user_id}.")
        return await admin_panel(update, context)
    except ValueError:
        await update.message.reply_text("❌ المدخل غير صحيح! يرجى إدخال معرف مستخدم صحيح.")
        return BAN_USER

# معالجة فك حظر مستخدم
async def handle_unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return ConversationHandler.END
    
    user_id_input = update.message.text
    try:
        user_id = int(user_id_input)
        if unban_user(user_id):
            await update.message.reply_text(f"✅ تم فك حظر المستخدم {user_id} بنجاح.")
        else:
            await update.message.reply_text(f"❌ لم يتم العثور على المستخدم {user_id} أو لم يكن محظوراً.")
        return await admin_panel(update, context)
    except ValueError:
        await update.message.reply_text("❌ المدخل غير صحيح! يرجى إدخال معرف مستخدم صحيح.")
        return UNBAN_USER

# معالجة حذف حساب مستخدم
async def handle_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return ConversationHandler.END
    
    user_id_input = update.message.text
    try:
        user_id = int(user_id_input)
        if delete_user_account(user_id):
            await update.message.reply_text(f"✅ تم حذف حساب المستخدم {user_id} بنجاح.")
        else:
            await update.message.reply_text(f"❌ لم يتم العثور على المستخدم {user_id}.")
        return await admin_panel(update, context)
    except ValueError:
        await update.message.reply_text("❌ المدخل غير صحيح! يرجى إدخال معرف مستخدم صحيح.")
        return DELETE_USER

# معالجة الإشعار العام
async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return ConversationHandler.END
    
    message = update.message.text
    sent_count = 0
    failed_count = 0
    
    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📢 إشعار عام من الإدارة:\n\n{message}"
            )
            sent_count += 1
        except Exception as e:
            logger.error(f"Error sending broadcast to {user_id}: {e}")
            failed_count += 1
    
    await update.message.reply_text(
        f"✅ تم إرسال الإشعار العام:\nالرسائل المرسلة: {sent_count}\nالرسائل الفاشلة: {failed_count}"
    )
    return await admin_panel(update, context)

# معالجة عرض رسائل مستخدم
async def handle_view_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ هذا الأمر للمدير فقط.")
        return ConversationHandler.END
    
    user_id_input = update.message.text
    try:
        user_id = int(user_id_input)
        # هذه الوظيفة تحتاج إلى تطبيق حسب احتياجك
        await update.message.reply_text(f"عرض رسائل المستخدم {user_id} - هذه الميزة تحت التطوير.")
        return await admin_panel(update, context)
    except ValueError:
        await update.message.reply_text("❌ المدخل غير صحيح! يرجى إدخال معرف مستخدم صحيح.")
        return VIEW_USER

# إحصائيات المدير
async def admin_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    total_users = len(users)
    active_users = sum(1 for u in users.values() if u.get("activated", False))
    banned_users_count = len(banned_users)
    total_posts = sum(u.get("post_stats", {}).get("total_posts", 0) for u in users.values())
    
    total_codes = len(codes)
    used_codes = sum(1 for c in codes.values() if c.get("used", False))
    available_codes = total_codes - used_codes
    
    stats_text = (
        f"📊 إحصائيات المدير:\n\n"
        f"👥 إجمالي المستخدمين: {total_users}\n"
        f"🟢 المستخدمين النشطين: {active_users}\n"
        f"🔴 المستخدمين المحظورين: {banned_users_count}\n"
        f"📤 إجمالي المنشورات: {total_posts}\n\n"
        f"🔑 إجمالي الأكواد: {total_codes}\n"
        f"🟢 الأكواد المستخدمة: {used_codes}\n"
        f"🟡 الأكواد المتاحة: {available_codes}\n\n"
        f"📅 تاريخ التقرير: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_admin")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(stats_text, reply_markup=reply_markup)
    return ADMIN_PANEL

# إحصائيات المستخدم
async def user_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    if str(user.id) not in users or not users[str(user.id)].get("activated", False):
        await query.edit_message_text("ليس لديك اشتراك نشط.")
        return
    
    user_data = users[str(user.id)]
    activated_at = datetime.strptime(user_data["activated_at"], "%Y-%m-%d %H:%M:%S")
    expires_at = datetime.strptime(user_data["expires_at"], "%Y-%m-%d %H:%M:%S")
    remaining_days = (expires_at - datetime.now()).days
    
    interval_minutes = user_data["settings"]["interval"] // 60
    has_active_session = has_session(user.id)
    
    post_stats = user_data.get("post_stats", {})
    
    status_text = (
        f"📊 إحصائيات حسابك:\n\n"
        f"الحالة: {'نشط' if user_data['activated'] else 'غير نشط'}\n"
        f"كود التفعيل: {user_data['activation_code']}\n"
        f"تاريخ التفعيل: {activated_at.strftime('%Y-%m-%d')}\n"
        f"تاريخ الانتهاء: {expires_at.strftime('%Y-%m-%d')}\n"
        f"الأيام المتبقية: {remaining_days} يوم\n"
        f"الفاصل الزمني: {interval_minutes} دقيقة\n"
        f"حالة الجلسة: {'✅ نشطة' if has_active_session else '❌ غير نشطة'}\n"
    )
    
    if post_stats:
        status_text += (
            f"إجمالي المنشورات: {post_stats.get('total_posts', 0)}\n"
            f"المنشورات الناجحة: {post_stats.get('successful_posts', 0)}\n"
            f"المنشورات الفاشلة: {post_stats.get('failed_posts', 0)}\n"
        )
    
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="back_user")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(status_text, reply_markup=reply_markup)
    return USER_SETTINGS

# إعدادات الحساب
async def account_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 تعديل الكليشة", callback_data="edit_clone")],
        [InlineKeyboardButton("⏰ تعديل الفاصل الزمني", callback_data="edit_interval")],
        [InlineKeyboardButton("🚪 تسجيل الخروج", callback_data="logout")],
        [InlineKeyboardButton("🗑️ حذف الحساب", callback_data="delete_account")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="back_user")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "⚙️ إعدادات الحساب\n\nاختر الإعداد الذي تريد تعديله:",
        reply_markup=reply_markup
    )
    
    return USER_SETTINGS

# معالجة إعدادات الحساب
async def handle_account_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "edit_clone":
        await query.edit_message_text("الرجاء إرسال الكليشة النصية الجديدة:")
        return SET_CLONE
    elif data == "edit_interval":
        await query.edit_message_text("الرجاء إرسال الفاصل الزمني الجديد (بالدقائق):")
        return SET_INTERVAL
    elif data == "logout":
        if delete_session(query.from_user.id):
            await query.edit_message_text("✅ تم تسجيل الخروج بنجاح!")
        else:
            await query.edit_message_text("❌ لم يتم العثور على جلسة نشطة.")
        return await user_panel(update, context)
    elif data == "delete_account":
        keyboard = [
            [InlineKeyboardButton("✅ نعم، احذف حسابي", callback_data="confirm_delete")],
            [InlineKeyboardButton("❌ لا، إلغاء", callback_data="cancel_delete")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "⚠️ هل أنت متأكد من أنك تريد حذف حسابك بالكامل؟ هذا الإجراء لا يمكن التراجع عنه!",
            reply_markup=reply_markup
        )
        return CONFIRM_DELETE
    elif data == "back_user":
        return await user_panel(update, context)

# معالجة تأكيد حذف الحساب
async def handle_confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    
    if data == "confirm_delete":
        if delete_user_account(query.from_user.id):
            await query.edit_message_text("✅ تم حذف حسابك بنجاح.")
        else:
            await query.edit_message_text("❌ حدث خطأ أثناء حذف الحساب.")
        return ConversationHandler.END
    elif data == "cancel_delete":
        return await account_settings(update, context)

# بدء النشر
async def start_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # هذه الوظيفة تحتاج إلى تطبيق حسب احتياجك
    await query.edit_message_text("🚀 بدء النشر - هذه الميزة تحت التطوير.")
    return MAIN_MENU

# إيقاف النشر
async def stop_posting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # هذه الوظيفة تحتاج إلى تطبيق حسب احتياجك
    await query.edit_message_text("⏹ إيقاف النشر - هذه الميزة تحت التطوير.")
    return MAIN_MENU

# بدء تسجيل الدخول
async def start_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("الرجاء إرسال رقم هاتفك مع رمز الدولة (مثال: +1234567890):")
    return PHONE

# معالجة رقم الهاتف
async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone_number = update.message.text
    
    if not phone_number.startswith('+'):
        await update.message.reply_text("❌ رقم الهاتف غير صحيح. يجب أن يبدأ بـ '+'.")
        return PHONE
    
    context.user_data['phone'] = phone_number
    await update.message.reply_text("✅ تم إرسال رمز التحقق إلى حسابك. الرجاء إدخال الرمز:")
    return CODE

# معالجة رمز التحقق
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    
    if not code.isdigit() or len(code) != 5:
        await update.message.reply_text("❌ رمز التحقق غير صحيح. يجب أن يكون 5 أرقام.")
        return CODE
    
    # هذه الوظيفة تحتاج إلى تطبيق كامل باستخدام Telethon
    await update.message.reply_text("✅ تم تسجيل الدخول بنجاح!")
    return await main_menu(update, context)

# معالجة الكليشة الجديدة
async def handle_set_clone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    new_clone = update.message.text
    user_id = str(user.id)
    
    if len(new_clone) > 1000:
        await update.message.reply_text("❌ النص طويل جداً! الحد الأقصى 1000 حرف.")
        return SET_CLONE
    
    if contains_links(new_clone):
        await update.message.reply_text("❌ لا يسمح باستخدام الروابط في الكليشة!")
        return SET_CLONE
    
    users[user_id]["settings"]["clone"] = new_clone
    save_data()
    await update.message.reply_text("✅ تم تحديث الكليشة بنجاح!")
    return await account_settings(update, context)

# معالجة الفاصل الزمني الجديد
async def handle_set_interval(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    interval_input = update.message.text
    user_id = str(user.id)
    
    try:
        interval_minutes = int(interval_input)
        if interval_minutes < 5:
            await update.message.reply_text("❌ الفاصل الزمني أقل من المسموح! الحد الأدنى 5 دقائق.")
            return SET_INTERVAL
        
        if interval_minutes > 1440:
            await update.message.reply_text("❌ الفاصل الزمني أكبر من المسموح! الحد الأقصى 1440 دقيقة.")
            return SET_INTERVAL
        
        users[user_id]["settings"]["interval"] = interval_minutes * 60
        save_data()
        await update.message.reply_text(f"✅ تم تحديث الفاصل الزمني إلى {interval_minutes} دقيقة بنجاح!")
        return await account_settings(update, context)
    except ValueError:
        await update.message.reply_text("❌ المدخل غير صحيح! يرجى إدخال رقم صحيح.")
        return SET_INTERVAL

# الأمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await main_menu(update, context)

# الأمر /activate
async def activate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("يرجى إدخال كود التفعيل بعد الأمر: /activate كود_التفعيل")
        return
    
    code = context.args[0].upper()
    # هنا يجب إضافة منطق التحقق من الكود وتفعيل الاشتراك
    await update.message.reply_text(f"✅ تم تفعيل الاشتراك بالكود: {code}")
    return await main_menu(update, context)

# إلغاء المحادثة
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم إلغاء العملية.")
    return ConversationHandler.END

# معالجة الأخطاء
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(msg="Exception occurred:", exc_info=context.error)

def main():
    # تحميل البيانات
    load_data()
    
    # إنشاء التطبيق
    application = Application.builder().token(TOKEN).build()
    
    # إضافة معالجات الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("activate", activate))
    
    # إضافة معالجات المحادثة
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [CallbackQueryHandler(handle_main_menu)],
            USER_SETTINGS: [CallbackQueryHandler(handle_user_panel)],
            ADMIN_PANEL: [CallbackQueryHandler(handle_admin_panel)],
            GENERATE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_generate_code)],
            BAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ban_user)],
            UNBAN_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_unban_user)],
            DELETE_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_delete_user)],
            BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast)],
            VIEW_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_view_user)],
            SET_CLONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_clone)],
            SET_INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_set_interval)],
            CONFIRM_DELETE: [CallbackQueryHandler(handle_confirm_delete)],
            PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    # بدء البوت
    print("البوت يعمل...")
    application.run_polling()

if __name__ == "__main__":
    main()
