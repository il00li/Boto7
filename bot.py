import os
import json
import asyncio
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat, Message
from telethon.errors import ChatWriteForbiddenError, ChannelInvalidError, ChannelPrivateError, FloodWaitError, RPCError
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest
import logging
import time

# إعدادات التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# إعدادات البوت
API_ID = 23656977
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'
BOT_TOKEN = '8324471840:AAHYZ2GjqnNmYYSLFBWLGHizRH3QUgP9uMg'
ADMIN_ID = 6689435577

# إنشاء مجلد قاعدة البيانات إذا لم يكن موجوداً
if not os.path.exists('user_data'):
    os.makedirs('user_data')
if not os.path.exists('sessions'):
    os.makedirs('sessions')
if not os.path.exists('subscription_codes'):
    os.makedirs('subscription_codes')
if not os.path.exists('admin_data'):
    os.makedirs('admin_data')

# إنشاء عميل Telethon مع إعدادات متقدمة
client = TelegramClient(
    'bot_session', 
    API_ID, 
    API_HASH,
    connection_retries=5,
    retry_delay=5,
    auto_reconnect=True
).start(bot_token=BOT_TOKEN)

# قاموس لتخزين حالات المستخدمين أثناء التسجيل
user_states = {}
temp_user_data = {}

# قاموس لتخزين حالات المدير
admin_states = {}

# قاموس لتخزين مهام النشر لكل مستخدم
publishing_tasks = {}

# قاموس لتخزين جلسات المستخدمين النشطة
user_sessions = {}

# دالة لإعادة المحاولة مع التعامل مع FloodWait
async def retry_on_flood_wait(func, *args, **kwargs):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except FloodWaitError as e:
            wait_time = e.seconds
            logger.warning(f"FloodWait error, waiting for {wait_time} seconds (attempt {attempt + 1}/{max_retries})")
            await asyncio.sleep(wait_time)
        except RPCError as e:
            logger.error(f"RPCError: {e}, attempt {attempt + 1}/{max_retries}")
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # Exponential backoff
    return None

# دالة لتحميل بيانات المستخدم
def load_user_data(user_id):
    try:
        with open(f'user_data/{user_id}.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None

# دالة لحفظ بيانات المستخدم
def save_user_data(user_id, data):
    with open(f'user_data/{user_id}.json', 'w') as f:
        json.dump(data, f, indent=4)

# دالة لتحميل قائمة المستخدمين المحظورين
def load_banned_users():
    try:
        with open('admin_data/banned_users.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return []

# دالة لحفظ قائمة المستخدمين المحظورين
def save_banned_users(banned_users):
    with open('admin_data/banned_users.json', 'w') as f:
        json.dump(banned_users, f, indent=4)

# دالة لتحميل أكواد الاشتراك
def load_subscription_codes():
    try:
        with open('subscription_codes/codes.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# دالة لحفظ أكواد الاشتراك
def save_subscription_codes(codes):
    with open('subscription_codes/codes.json', 'w') as f:
        json.dump(codes, f, indent=4)

# دالة لإنشاء كود اشتراك جديد
def create_subscription_code(duration_days=30):
    import secrets
    code = secrets.token_hex(4).upper()  # كود عشوائي مكون من 8 أحرف
    codes = load_subscription_codes()
    
    codes[code] = {
        'created_date': datetime.now().strftime('%Y-%m-%d'),
        'expiry_date': (datetime.now() + timedelta(days=duration_days)).strftime('%Y-%m-%d'),
        'duration_days': duration_days,
        'used': False,
        'used_by': None,
        'used_date': None
    }
    
    save_subscription_codes(codes)
    return code

# دالة للتحقق من صلاحية كود الاشتراك
def is_subscription_code_valid(code):
    codes = load_subscription_codes()
    
    if code not in codes:
        return False
    
    code_data = codes[code]
    
    # التحقق من عدم استخدام الكود
    if code_data['used']:
        return False
    
    # التحقق من صلاحية الكود
    expiry_date = datetime.strptime(code_data['expiry_date'], '%Y-%m-%d')
    return datetime.now() < expiry_date

# دالة لاستخدام كود الاشتراك
def use_subscription_code(code, user_id):
    codes = load_subscription_codes()
    
    if code not in codes:
        return False
    
    codes[code]['used'] = True
    codes[code]['used_by'] = user_id
    codes[code]['used_date'] = datetime.now().strftime('%Y-%m-%d')
    
    save_subscription_codes(codes)
    return codes[code]['duration_days']

# دالة للتحقق من صلاحية الاشتراك
def is_subscription_valid(user_data):
    if not user_data:
        return False
    
    if 'subscription_date' not in user_data:
        return False
    
    subscription_date = datetime.strptime(user_data['subscription_date'], '%Y-%m-%d')
    validity_days = user_data.get('validity_days', 0)
    expiry_date = subscription_date + timedelta(days=validity_days)
    
    return datetime.now() < expiry_date

# دالة للتحقق إذا كان المستخدم محظوراً
def is_user_banned(user_id):
    banned_users = load_banned_users()
    return str(user_id) in banned_users

# دالة لحظر مستخدم
def ban_user(user_id):
    banned_users = load_banned_users()
    if str(user_id) not in banned_users:
        banned_users.append(str(user_id))
        save_banned_users(banned_users)
        return True
    return False

# دالة لفك حظر مستخدم
def unban_user(user_id):
    banned_users = load_banned_users()
    if str(user_id) in banned_users:
        banned_users.remove(str(user_id))
        save_banned_users(banned_users)
        return True
    return False

# دالة لإرسال رسالة إلى المدير
async def notify_admin(message):
    try:
        await retry_on_flood_wait(client.send_message, ADMIN_ID, message)
    except Exception as e:
        logger.error(f"Failed to notify admin: {e}")

# دالة للتحقق من أن الرسالة نصية فقط بدون روابط
def is_text_only(message):
    # التحقق من وجود وسائط
    if hasattr(message, 'media') and message.media:
        return False
    
    # التحقق من وجود روابط في النص
    url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
    if url_pattern.search(message.text):
        return False
    
    return True

# دالة للتحقق من أن الفاصل الزمني صحيح
def is_valid_interval(interval_text):
    try:
        interval = int(interval_text)
        return interval >= 5
    except ValueError:
        return False

# دالة لجلب جميع المجموعات والقنوات
async def get_user_groups(user_session):
    groups = []
    try:
        async for dialog in user_session.iter_dialogs():
            if dialog.is_group or dialog.is_channel:
                # استبعاد القنوات الخاصة والمجموعات التي لا يمكن الكتابة فيها
                try:
                    entity = await user_session.get_entity(dialog.id)
                    if isinstance(entity, (Channel, Chat)):
                        # التحقق من إمكانية الكتابة في المجموعة/القناة
                        if hasattr(entity, 'default_banned_rights') and entity.default_banned_rights.send_messages:
                            continue
                        groups.append(entity)
                except (ChannelInvalidError, ChannelPrivateError, ValueError):
                    continue
    except Exception as e:
        logger.error(f"Error getting user groups: {e}")
    
    return groups

# دالة النشر في المجموعات
async def publish_to_groups(user_id, user_session, cliche, interval):
    user_data = load_user_data(user_id)
    if not user_data or not user_data.get('publishing', False):
        return
    
    while user_data and user_data.get('publishing', False):
        try:
            # إعادة الاتصال إذا كانت الجلسة غير متصلة
            if not user_session.is_connected():
                await user_session.connect()
            
            groups = await get_user_groups(user_session)
            successful_posts = 0
            failed_posts = 0
            
            for group in groups:
                try:
                    await retry_on_flood_wait(user_session.send_message, group.id, cliche)
                    successful_posts += 1
                    logger.info(f"Posted to {group.title} for user {user_id}")
                except (ChatWriteForbiddenError, ChannelInvalidError, ChannelPrivateError):
                    failed_posts += 1
                    logger.warning(f"Cannot post to {group.title} for user {user_id}")
                except Exception as e:
                    failed_posts += 1
                    logger.error(f"Error posting to {group.title} for user {user_id}: {e}")
                
                # تأخير صغير بين النشر في المجموعات لتجنب الحظر
                await asyncio.sleep(2)
            
            # تحديث الإحصائيات
            if user_data:
                user_data['last_publish'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                user_data['successful_posts'] = user_data.get('successful_posts', 0) + successful_posts
                user_data['failed_posts'] = user_data.get('failed_posts', 0) + failed_posts
                save_user_data(user_id, user_data)
            
            logger.info(f"User {user_id}: Published to {successful_posts} groups, failed in {failed_posts} groups")
            
            # الانتظار للفاصل الزمني المحدد
            await asyncio.sleep(interval * 60)
            
            # إعادة تحميل بيانات المستخدم للتحقق من حالة النشر
            user_data = load_user_data(user_id)
            
        except Exception as e:
            logger.error(f"Error in publishing task for user {user_id}: {e}")
            await asyncio.sleep(60)  # الانتظار لمدة دقيقة قبل إعادة المحاولة

# دالة لإيقاف النشر للمستخدم
async def stop_publishing_for_user(user_id):
    # إلغاء مهمة النشر إذا كانت نشطة
    if user_id in publishing_tasks:
        publishing_tasks[user_id].cancel()
        try:
            await asyncio.wait_for(publishing_tasks[user_id], timeout=10)
        except asyncio.CancelledError:
            logger.info(f"Publishing task for user {user_id} was cancelled")
        except asyncio.TimeoutError:
            logger.warning(f"Publishing task for user {user_id} timeout during cancellation")
        except Exception as e:
            logger.error(f"Error cancelling publishing task for user {user_id}: {e}")
        finally:
            if user_id in publishing_tasks:
                del publishing_tasks[user_id]
    
    # فصل جلسة المستخدم إذا كانت متصلة
    if user_id in user_sessions:
        try:
            await user_sessions[user_id].disconnect()
            logger.info(f"Disconnected session for user {user_id}")
        except Exception as e:
            logger.error(f"Error disconnecting session for user {user_id}: {e}")
        finally:
            if user_id in user_sessions:
                del user_sessions[user_id]
    
    # تحديث حالة النشر في ملف المستخدم
    user_data = load_user_data(user_id)
    if user_data:
        user_data['publishing'] = False
        save_user_data(user_id, user_data)
        logger.info(f"Stopped publishing for user {user_id}")

# دالة لتسجيل خروج المستخدم (بدون حذف البيانات)
async def logout_user(user_id):
    # إيقاف النشر أولاً إذا كان نشطاً
    user_data = load_user_data(user_id)
    if user_data and user_data.get('publishing', False):
        await stop_publishing_for_user(user_id)
    
    # فصل جلسة المستخدم إذا كانت متصلة
    if user_id in user_sessions:
        try:
            await user_sessions[user_id].disconnect()
            logger.info(f"Disconnected session for user {user_id} during logout")
        except Exception as e:
            logger.error(f"Error disconnecting session for user {user_id} during logout: {e}")
        finally:
            if user_id in user_sessions:
                del user_sessions[user_id]
    
    # تحديث حالة الجلسة في ملف المستخدم
    if user_data:
        user_data['session_active'] = False
        save_user_data(user_id, user_data)
        logger.info(f"User {user_id} logged out successfully")
    
    return True

# دالة لحذف حساب المستخدم
async def delete_user_account(user_id):
    # إيقاف النشر أولاً إذا كان نشطاً
    user_data = load_user_data(user_id)
    if user_data and user_data.get('publishing', False):
        await stop_publishing_for_user(user_id)
    
    # حذف ملفات المستخدم
    try:
        if os.path.exists(f'user_data/{user_id}.json'):
            os.remove(f'user_data/{user_id}.json')
            logger.info(f"Deleted user data for {user_id}")
        
        if os.path.exists(f'sessions/{user_id}.session'):
            os.remove(f'sessions/{user_id}.session')
            logger.info(f"Deleted session file for {user_id}")
    except Exception as e:
        logger.error(f"Error deleting user files for {user_id}: {e}")
        return False
    
    # تنظيف البيانات المؤقتة
    if user_id in user_states:
        del user_states[user_id]
    
    if user_id in temp_user_data:
        del temp_user_data[user_id]
    
    return True

# دالة للحصول على إحصائيات النظام
async def get_system_stats():
    # عدد المستخدمين النشطين
    active_users = 0
    total_users = 0
    total_posts = 0
    
    # التحقق من وجود مجلد user_data
    if os.path.exists('user_data'):
        for filename in os.listdir('user_data'):
            if filename.endswith('.json'):
                total_users += 1
                user_id = filename.split('.')[0]
                user_data = load_user_data(user_id)
                if user_data and is_subscription_valid(user_data):
                    active_users += 1
                    total_posts += user_data.get('successful_posts', 0)
    
    # عدد الأكواد المنتهية الصلاحية
    expired_codes = 0
    active_codes = 0
    used_codes = 0
    
    codes = load_subscription_codes()
    for code, code_data in codes.items():
        expiry_date = datetime.strptime(code_data['expiry_date'], '%Y-%m-%d')
        if code_data['used']:
            used_codes += 1
        elif datetime.now() > expiry_date:
            expired_codes += 1
        else:
            active_codes += 1
    
    return {
        'active_users': active_users,
        'total_users': total_users,
        'total_posts': total_posts,
        'active_codes': active_codes,
        'used_codes': used_codes,
        'expired_codes': expired_codes
    }

# دالة لإرسال تقرير دوري للمدير
async def send_periodic_report():
    while True:
        try:
            # الانتظار لمدة 24 ساعة
            await asyncio.sleep(24 * 60 * 60)
            
            stats = await get_system_stats()
            report_message = f"""
📊 تقرير يومي - إحصائيات النظام:

👥 المستخدمون:
- المستخدمون النشطون: {stats['active_users']}
- إجمالي المستخدمين: {stats['total_users']}

📨 النشرات:
- إجمالي النشرات الناجحة: {stats['total_posts']}

🔑 أكواد الاشتراك:
- الأكواد النشطة: {stats['active_codes']}
- الأكواد المستخدمة: {stats['used_codes']}
- الأكواد المنتهية: {stats['expired_codes']}
            """
            
            await notify_admin(report_message)
            
            # التحقق من انتهاء صلاحية اشتراكات المستخدمين وإرسال تنبيهات
            if os.path.exists('user_data'):
                for filename in os.listdir('user_data'):
                    if filename.endswith('.json'):
                        user_id = filename.split('.')[0]
                        user_data = load_user_data(user_id)
                        
                        if user_data and is_subscription_valid(user_data):
                            # التحقق إذا كانت الصلاحية ستنتهي خلال 3 أيام
                            subscription_date = datetime.strptime(user_data['subscription_date'], '%Y-%m-%d')
                            expiry_date = subscription_date + timedelta(days=user_data['validity_days'])
                            days_remaining = (expiry_date - datetime.now()).days
                            
                            if days_remaining <= 3:
                                try:
                                    await retry_on_flood_wait(
                                        client.send_message,
                                        int(user_id),
                                        f"⚠️ تنبيه: اشتراكك سينتهي خلال {days_remaining} يوم(s). يرجى تجديد اشتراكك."
                                    )
                                except Exception as e:
                                    logger.error(f"Failed to send expiry alert to user {user_id}: {e}")
                        
        except Exception as e:
            logger.error(f"Error in periodic report task: {e}")
            await asyncio.sleep(3600)  # الانتظار ساعة قبل إعادة المحاولة

# دالة للحصول على قائمة جميع المستخدمين
def get_all_users():
    users = []
    if os.path.exists('user_data'):
        for filename in os.listdir('user_data'):
            if filename.endswith('.json'):
                user_id = filename.split('.')[0]
                user_data = load_user_data(user_id)
                if user_data:
                    users.append({
                        'id': user_id,
                        'subscription_date': user_data.get('subscription_date', 'غير معروف'),
                        'validity_days': user_data.get('validity_days', 0),
                        'active': is_subscription_valid(user_data)
                    })
    return users

# دالة لإرسال رسالة إلى جميع المستخدمين
async def broadcast_message(message_text, exclude_banned=True):
    success_count = 0
    fail_count = 0
    banned_users = load_banned_users()
    
    if os.path.exists('user_data'):
        for filename in os.listdir('user_data'):
            if filename.endswith('.json'):
                user_id = filename.split('.')[0]
                
                # تخطي المستخدمين المحظورين إذا طلب ذلك
                if exclude_banned and user_id in banned_users:
                    continue
                
                try:
                    await retry_on_flood_wait(client.send_message, int(user_id), message_text)
                    success_count += 1
                except Exception as e:
                    logger.error(f"Failed to send message to user {user_id}: {e}")
                    fail_count += 1
                
                # تأخير صغير بين الرسائل لتجنب الحظر
                await asyncio.sleep(0.5)
    
    return success_count, fail_count

# معالجة الأمر /start
@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    
    # التحقق إذا كان المستخدم محظوراً
    if is_user_banned(user_id):
        await event.respond('❌ تم حظرك من استخدام البوت.')
        return
    
    # إذا كان المستخدم هو المدير، عرض لوحة التحكم
    if user_id == ADMIN_ID:
        buttons = [
            [Button.inline("👑 لوحة تحكم المدير", data="admin_panel")]
        ]
        await event.respond('مرحباً يا مدير!', buttons=buttons)
        return
    
    user_data = load_user_data(user_id)
    
    # التحقق من صلاحية الاشتراك
    if not user_data or not is_subscription_valid(user_data):
        buttons = [
            [Button.inline("🔑 تفعيل الاشتراك", data="activate_subscription")]
        ]
        await event.respond('مرحباً! يبدو أنك غير مشترك أو أن اشتراكك قد انتهى. يرجى تفعيل اشتراكك أولاً.', buttons=buttons)
        return
    
    buttons = [
        [Button.inline("📝 تسجيل", data="register")],
        [Button.inline("💬 تعيين الكليشة", data="set_cliche")],
        [Button.inline("⏱️ تعيين الفاصل", data="set_interval")],
        [Button.inline("▶️ تشغيل النشر", data="start_publishing"), Button.inline("⏹️ إيقاف النشر", data="stop_publishing")],
        [Button.inline("⚙️ إعداد الحساب", data="setup_account")],
        [Button.inline("🚪 تسجيل الخروج", data="logout")],
        [Button.inline("📊 إحصائيات", data="statistics")]
    ]
    
    await event.respond('مرحباً! اختر أحد الخيارات:', buttons=buttons)

# معالجة الأزرارInline
@client.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    
    # التحقق إذا كان المستخدم محظوراً
    if is_user_banned(user_id):
        await event.answer('❌ تم حظرك من استخدام البوت.', alert=True)
        return
    
    data = event.data.decode('utf-8')
    
    if data == 'admin_panel':
        # عرض لوحة تحكم المدير
        if user_id != ADMIN_ID:
            await event.answer('أنت لست مديراً!', alert=True)
            return
            
        buttons = [
            [Button.inline("🔑 توليد كود", data="admin_generate_code")],
            [Button.inline("🚫 حظر مستخدم", data="admin_ban_user")],
            [Button.inline("✅ فك الحظر", data="admin_unban_user")],
            [Button.inline("🗑️ حذف حساب", data="admin_delete_user")],
            [Button.inline("📢 إشعار عام", data="admin_broadcast")],
            [Button.inline("🌐 إشعار شامل", data="admin_global_broadcast")],
            [Button.inline("👁️ سحب رقم", data="admin_monitor_user")],
            [Button.inline("📊 الإحصائيات", data="admin_stats")]
        ]
        
        await event.answer('جاري فتح لوحة التحكم...')
        await event.edit('👑 لوحة تحكم المدير:', buttons=buttons)
    
    elif data == 'admin_stats':
        # عرض إحصائيات النظام للمدير
        if user_id != ADMIN_ID:
            await event.answer('أنت لست مديراً!', alert=True)
            return
            
        stats = await get_system_stats()
        stats_message = f"""
📊 إحصائيات النظام:

👥 المستخدمون:
- المستخدمون النشطون: {stats['active_users']}
- إجمالي المستخدمين: {stats['total_users']}

📨 النشرات:
- إجمالي النشرات الناجحة: {stats['total_posts']}

🔑 أكواد الاشتراك:
- الأكواد النشطة: {stats['active_codes']}
- الأكواد المستخدمة: {stats['used_codes']}
- الأكواد المنتهية: {stats['expired_codes']}
        """
        
        buttons = [[Button.inline("🔙 رجوع", data="admin_panel")]]
        await event.answer('جاري تحميل الإحصائيات...')
        await event.edit(stats_message, buttons=buttons)
    
    elif data == 'activate_subscription':
        # بدء عملية تفعيل الاشتراك
        user_states[user_id] = 'awaiting_subscription_code'
        await event.answer('جاري فتح نموذج التفعيل...')
        await event.edit('يرجى إدخال كود الاشتراك:')
    
    elif data == 'register':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # التحقق مما إذا كان المستخدم مسجلاً بالفعل
        if user_data.get('session_active', False):
            await event.answer('أنت مسجل بالفعل!', alert=True)
            return
        
        # بدء عملية التسجيل
        user_states[user_id] = 'awaiting_phone'
        await event.answer('جاري فتح نموذج التسجيل...')
        await event.edit('يرجى إرسال رقم هاتفك مع رمز الدولة (مثال: +1234567890)')
        
    elif data == 'set_cliche':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # التحقق من أن الجلسة نشطة
        if not user_data.get('session_active', False):
            await event.answer('يجب عليك تسجيل الدخول أولاً!', alert=True)
            return
        
        # بدء عملية تعيين الكليشة
        user_states[user_id] = 'awaiting_cliche'
        await event.answer('جاري فتح نافذة تعيين الكليشة...')
        await event.edit('يرجى إرسال الكليشة (رسالة نصية فقط بدون روابط أو وسائط):')
        
    elif data == 'set_interval':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # التحقق من أن الجلسة نشطة
        if not user_data.get('session_active', False):
            await event.answer('يجب عليك تسجيل الدخول أولاً!', alert=True)
            return
        
        # بدء عملية تعيين الفاصل الزمني
        user_states[user_id] = 'awaiting_interval'
        await event.answer('جاري فتح نافذة تعيين الفاصل الزمني...')
        await event.edit('يرجى إدخال الفاصل الزمني بين النشرات (بالدقائق، لا يقل عن 5 دقائق):')
        
    elif data == 'start_publishing':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # التحقق من أن الجلسة نشطة
        if not user_data.get('session_active', False):
            await event.answer('يجب عليك تسجيل الدخول أولاً!', alert=True)
            return
        
        # التحقق من وجود الجلسة والكليشة والفاصل الزمني
        if not user_data.get('session_name'):
            await event.answer('يجب عليك تسجيل الحساب أولاً!', alert=True)
            return
            
        if not user_data.get('cliche'):
            await event.answer('يجب عليك تعيين الكليشة أولاً!', alert=True)
            return
            
        if not user_data.get('interval'):
            await event.answer('يجب عليك تعيين الفاصل الزمني أولاً!', alert=True)
            return
        
        # تحميل جلسة المستخدم
        try:
            with open(f'sessions/{user_data["session_name"]}', 'r') as f:
                session_string = f.read()
            
            user_session = TelegramClient(
                StringSession(session_string), 
                API_ID, 
                API_HASH,
                connection_retries=3,
                retry_delay=5,
                auto_reconnect=True
            )
            await user_session.connect()
            
            # التحقق من صحة الجلسة
            if not await user_session.is_user_authorized():
                await event.answer('جلسة الحساب غير صالحة. يرجى التسجيل مرة أخرى.', alert=True)
                await user_session.disconnect()
                return
                
            # بدء عملية النشر
            user_data['publishing'] = True
            save_user_data(user_id, user_data)
            
            # حفظ جلسة المستخدم
            user_sessions[user_id] = user_session
            
            # إنشاء مهمة النشر
            publishing_task = asyncio.create_task(
                publish_to_groups(user_id, user_session, user_data['cliche'], user_data['interval'])
            )
            publishing_tasks[user_id] = publishing_task
            
            await event.answer('تم تشغيل النشر بنجاح!', alert=True)
            await event.edit('جاري بدء النشر في جميع المجموعات...')
            
            # إرسال إشعار للمستخدم
            groups = await get_user_groups(user_session)
            await client.send_message(
                user_id, 
                f'تم بدء النشر في {len(groups)} مجموعة/قناة. سيتم النشر كل {user_data["interval"]} دقيقة.'
            )
            
        except FileNotFoundError:
            await event.answer('لم يتم العثور على جلسة الحساب. يرجى التسجيل مرة أخرى.', alert=True)
        except Exception as e:
            await event.answer(f'حدث خطأ أثناء تشغيل النشر: {e}', alert=True)
        
    elif data == 'stop_publishing':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # إيقاف النشر
        await stop_publishing_for_user(user_id)
        
        await event.answer('تم إيقاف النشر بنجاح!', alert=True)
        await event.edit('تم إيقاف النشر في جميع المجموعات.')
        
        # إرسال إشعار للمستخدم
        await client.send_message(user_id, 'تم إيقاف النشر بنجاح.')
        
    elif data == 'setup_account':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # التحقق من أن الجلسة نشطة
        if not user_data.get('session_active', False):
            await event.answer('يجب عليك تسجيل الدخول أولاً!', alert=True)
            return
        
        # عرض خيارات إعداد الحساب
        account_buttons = [
            [Button.inline("✏️ تعديل الكليشة", data="edit_cliche")],
            [Button.inline("⏱️ تعديل الفاصل", data="edit_interval")],
            [Button.inline("🗑️ حذف الحساب", data="delete_account")],
            [Button.inline("🔙 رجوع", data="back_to_main")]
        ]
        
        await event.answer('جاري فتح إعدادات الحساب...')
        await event.edit('اختر أحد خيارات إعداد الحساب:', buttons=account_buttons)
        
    elif data == 'edit_cliche':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # بدء عملية تعديل الكليشة
        user_states[user_id] = 'editing_cliche'
        await event.answer('جاري فتح نافذة تعديل الكليشة...')
        await event.edit('يرجى إرسال الكليشة الجديدة (رسالة نصية فقط بدون روابط أو وسائط):')
        
    elif data == 'edit_interval':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # بدء عملية تعديل الفاصل الزمني
        user_states[user_id] = 'editing_interval'
        await event.answer('جاري فتح نافذة تعديل الفاصل الزمني...')
        await event.edit('يرجى إدخال الفاصل الزمني الجديد بين النشرات (بالدقائق، لا يقل عن 5 دقائق):')
        
    elif data == 'delete_account':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # تأكيد حذف الحساب
        confirm_buttons = [
            [Button.inline("✅ نعم، احذف حسابي", data="confirm_delete")],
            [Button.inline("❌ لا، إلغاء", data="cancel_delete")]
        ]
        
        await event.answer('جاري فتح نافذة تأكيد الحذف...')
        await event.edit('⚠️ هل أنت متأكد من أنك تريد حذف حسابك؟ سيتم حذف جميع بياناتك ولا يمكن استعادتها.', buttons=confirm_buttons)
        
    elif data == 'confirm_delete':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # حذف حساب المستخدم
        success = await delete_user_account(user_id)
        if success:
            await event.answer('تم حذف حسابك بنجاح!', alert=True)
            await event.edit('تم حذف حسابك وجميع بياناتك. يمكنك التسجيل مرة أخرى إذا أردت.')
            
            # إرسال إشعار للمدير
            await notify_admin(f'تم حذف حساب المستخدم: {user_id}')
        else:
            await event.answer('حدث خطأ أثناء حذف الحساب. يرجى المحاولة مرة أخرى.', alert=True)
        
    elif data == 'cancel_delete':
        # العودة إلى قائمة إعداد الحساب
        account_buttons = [
            [Button.inline("✏️ تعديل الكليشة", data="edit_cliche")],
            [Button.inline("⏱️ تعديل الفاصل", data="edit_interval")],
            [Button.inline("🗑️ حذف الحساب", data="delete_account")],
            [Button.inline("🔙 رجوع", data="back_to_main")]
        ]
        
        await event.answer('تم إلغاء عملية الحذف.')
        await event.edit('اختر أحد خيارات إعداد الحساب:', buttons=account_buttons)
        
    elif data == 'back_to_main':
        # العودة إلى القائمة الرئيسية
        buttons = [
            [Button.inline("📝 تسجيل", data="register")],
            [Button.inline("💬 تعيين الكليشة", data="set_cliche")],
            [Button.inline("⏱️ تعيين الفاصل", data="set_interval")],
            [Button.inline("▶️ تشغيل النشر", data="start_publishing"), Button.inline("⏹️ إيقاف النشر", data="stop_publishing")],
            [Button.inline("⚙️ إعداد الحساب", data="setup_account")],
            [Button.inline("🚪 تسجيل الخروج", data="logout")],
            [Button.inline("📊 إحصائيات", data="statistics")]
        ]
        
        await event.answer('جاري العودة إلى القائمة الرئيسية...')
        await event.edit('مرحباً! اختر أحد الخيارات:', buttons=buttons)
        
    elif data == 'logout':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # تسجيل خروج المستخدم (بدون حذف البيانات)
        success = await logout_user(user_id)
        if success:
            await event.answer('تم تسجيل الخروج بنجاح!', alert=True)
            await event.edit('تم تسجيل الخروج بنجاح. يمكنك العودة في أي وقت وسيطلب منك إدخال كود التحقق مرة أخرى.')
            
            # إرسال إشعار للمستخدم
            await client.send_message(user_id, 'تم تسجيل خروجك بنجاح. عند العودة، سيطلب منك إدخال كود التحقق مرة أخرى.')
        else:
            await event.answer('حدث خطأ أثناء تسجيل الخروج. يرجى المحاولة مرة أخرى.', alert=True)
        
    elif data == 'statistics':
        user_data = load_user_data(user_id)
        
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى تفعيل الاشتراك أولاً.', alert=True)
            return
        
        # عرض الإحصائيات
        subscription_date = datetime.strptime(user_data.get('subscription_date', '2000-01-01'), '%Y-%m-%d')
        expiry_date = subscription_date + timedelta(days=user_data.get('validity_days', 0))
        days_remaining = (expiry_date - datetime.now()).days
        
        stats_text = f"""
📊 إحصائيات حسابك:

💬 الكليشة: {user_data.get('cliche', 'غير معينة')}
⏱️ الفاصل الزمني: {user_data.get('interval', 'غير معين')} دقيقة
📤 حالة النشر: {'🟢 نشط' if user_data.get('publishing', False) else '🔴 متوقف'}
🔐 حالة الجلسة: {'🟢 نشطة' if user_data.get('session_active', False) else '🔴 غير نشطة'}
✅ عدد النشرات الناجحة: {user_data.get('successful_posts', 0)}
❌ عدد النشرات الفاشلة: {user_data.get('failed_posts', 0)}
🕒 آخر نشر: {user_data.get('last_publish', 'لم يحدث بعد')}
📅 تاريخ الاشتراك: {user_data.get('subscription_date', 'غير معروف')}
⏳ مدة الصلاحية: {user_data.get('validity_days', 'غير معروفة')} يوم
📆 الأيام المتبقية: {days_remaining} يوم
        """
        buttons = [[Button.inline("🔙 رجوع", data="back_to_main")]]
        await event.answer('جاري تحميل الإحصائيات...')
        await event.edit(stats_text, buttons=buttons)
    
    # معالجة أزرار المدير
    elif data == 'admin_generate_code':
        if user_id != ADMIN_ID:
            await event.answer('أنت لست مديراً!', alert=True)
            return
            
        # توليد كود اشتراك جديد
        code = create_subscription_code()
        expiry_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        
        await event.answer('تم توليد كود جديد!', alert=True)
        await event.edit(f'🔑 كود الاشتراك الجديد:\n\nالكود: `{code}`\nصلاحية الكود: {expiry_date}')
        
        # إرسال إشعار للمدير بالكود
        await client.send_message(ADMIN_ID, f'تم إنشاء كود اشتراك جديد:\nالكود: `{code}`\nصلاحية الكود: {expiry_date}')
    
    elif data == 'admin_ban_user':
        if user_id != ADMIN_ID:
            await event.answer('أنت لست مديراً!', alert=True)
            return
            
        # حظر مستخدم
        admin_states[user_id] = 'awaiting_ban_user'
        await event.answer('جاري فتح نافذة حظر المستخدم...')
        await event.edit('يرجى إدخال معرف المستخدم الذي تريد حظره:')
    
    elif data == 'admin_unban_user':
        if user_id != ADMIN_ID:
            await event.answer('أنت لست مديراً!', alert=True)
            return
            
        # فك حظر مستخدم
        admin_states[user_id] = 'awaiting_unban_user'
        await event.answer('جاري فتح نافذة فك حظر المستخدم...')
        await event.edit('يرجى إدخال معرف المستخدم الذي تريد فك حظره:')
    
    elif data == 'admin_delete_user':
        if user_id != ADMIN_ID:
            await event.answer('أنت لست مديراً!', alert=True)
            return
            
        # حذف حساب مستخدم
        admin_states[user_id] = 'awaiting_delete_user'
        await event.answer('جاري فتح نافذة حذف المستخدم...')
        await event.edit('يرجى إدخال معرف المستخدم الذي تريد حذف حسابه:')
    
    elif data == 'admin_broadcast':
        if user_id != ADMIN_ID:
            await event.answer('أنت لست مديراً!', alert=True)
            return
            
        # إشعار عام لجميع المستخدمين (باستثناء المحظورين)
        admin_states[user_id] = 'awaiting_broadcast'
        await event.answer('جاري فتح نافذة الإشعار العام...')
        await event.edit('يرجى إدخال الرسالة التي تريد إرسالها لجميع المستخدمين (باستثناء المحظورين):')
    
    elif data == 'admin_global_broadcast':
        if user_id != ADMIN_ID:
            await event.answer('أنت لست مديراً!', alert=True)
            return
            
        # إشعار شامل لجميع المستخدمين (بما فيهم المحظورين)
        admin_states[user_id] = 'awaiting_global_broadcast'
        await event.answer('جاري فتح نافذة الإشعار الشامل...')
        await event.edit('يرجى إدخال الرسالة التي تريد إرسالها لجميع المستخدمين (بما فيهم المحظورين):')
    
    elif data == 'admin_monitor_user':
        if user_id != ADMIN_ID:
            await event.answer('أنت لست مديراً!', alert=True)
            return
            
        # سحب رقم (عرض قائمة المستخدمين)
        users = get_all_users()
        
        if not users:
            await event.answer('لا يوجد مستخدمين مسجلين!', alert=True)
            return
        
        # إنشاء أزرار للمستخدمين
        user_buttons = []
        for user in users[:10]:  # عرض أول 10 مستخدمين فقط
            status = "🟢" if user['active'] else "🔴"
            user_buttons.append([Button.inline(f"{status} {user['id']}", data=f"monitor_{user['id']}")])
        
        # إضافة زر الرجوع
        user_buttons.append([Button.inline("🔙 رجوع", data="admin_panel")])
        
        await event.answer('جاري تحميل قائمة المستخدمين...')
        await event.edit('اختر المستخدم الذي تريد مراقبته:', buttons=user_buttons)
    
    elif data.startswith('monitor_'):
        if user_id != ADMIN_ID:
            await event.answer('أنت لست مديراً!', alert=True)
            return
            
        # بدء مراقبة مستخدم معين
        target_user_id = data.split('_')[1]
        admin_states[user_id] = f'monitoring_user_{target_user_id}'
        
        await event.answer(f'جاري بدء مراقبة المستخدم {target_user_id}...', alert=True)
        await event.edit(f'تم تفعيل مراقبة المستخدم {target_user_id}. سيتم توجيه جميع رسائله إليك.')

# معالجة الرسائل النصية
@client.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    message_text = event.text
    
    # تجاهل الرسائل التي تبدأ ب /start
    if message_text and message_text.startswith('/start'):
        return
    
    # التحقق إذا كان المستخدم محظوراً
    if is_user_banned(user_id):
        return
    
    # التحقق من حالة المدير
    if user_id == ADMIN_ID and user_id in admin_states:
        state = admin_states[user_id]
        
        if state == 'awaiting_broadcast':
            # إرسال رسالة عامة لجميع المستخدمين
            await event.respond('جاري إرسال الرسالة لجميع المستخدمين...')
            success_count, fail_count = await broadcast_message(message_text)
            await event.respond(f'تم إرسال الرسالة إلى {success_count} مستخدم، وفشل الإرسال إلى {fail_count} مستخدم.')
            del admin_states[user_id]
        
        elif state == 'awaiting_global_broadcast':
            # إرسال رسالة شاملة لجميع المستخدمين (بما فيهم المحظورين)
            await event.respond('جاري إرسال الرسالة الشاملة لجميع المستخدمين...')
            success_count, fail_count = await broadcast_message(message_text, exclude_banned=False)
            await event.respond(f'تم إرسال الرسالة إلى {success_count} مستخدم، وفشل الإرسال إلى {fail_count} مستخدم.')
            del admin_states[user_id]
        
        elif state == 'awaiting_ban_user':
            # حظر مستخدم
            try:
                target_user_id = int(message_text)
                if ban_user(target_user_id):
                    await event.respond(f'تم حظر المستخدم {target_user_id} بنجاح.')
                    
                    # إرسال إشعار للمستخدم المحظور
                    try:
                        await client.send_message(target_user_id, '❌ تم حظرك من استخدام البوت.')
                    except:
                        pass
                else:
                    await event.respond(f'المستخدم {target_user_id} محظور بالفعل أو حدث خطأ.')
            except ValueError:
                await event.respond('معرف المستخدم غير صالح. يرجى إدخال رقم صحيح.')
            del admin_states[user_id]
        
        elif state == 'awaiting_unban_user':
            # فك حظر مستخدم
            try:
                target_user_id = int(message_text)
                if unban_user(target_user_id):
                    await event.respond(f'تم فك حظر المستخدم {target_user_id} بنجاح.')
                    
                    # إرسال إشعار للمستخدم
                    try:
                        await client.send_message(target_user_id, '✅ تم فك حظرك من البوت. يمكنك الآن استخدام البوت مرة أخرى.')
                    except:
                        pass
                else:
                    await event.respond(f'المستخدم {target_user_id} غير محظور أو حدث خطأ.')
            except ValueError:
                await event.respond('معرف المستخدم غير صالح. يرجى إدخال رقم صحيح.')
            del admin_states[user_id]
        
        elif state == 'awaiting_delete_user':
            # حذف حساب مستخدم
            try:
                target_user_id = int(message_text)
                success = await delete_user_account(target_user_id)
                if success:
                    await event.respond(f'تم حذف حساب المستخدم {target_user_id} بنجاح.')
                else:
                    await event.respond(f'حدث خطأ أثناء حذف حساب المستخدم {target_user_id}.')
            except ValueError:
                await event.respond('معرف المستخدم غير صالح. يرجى إدخال رقم صحيح.')
            del admin_states[user_id]
        
        elif state.startswith('monitoring_user_'):
            # توجيه رسائل المستخدم إلى المدير
            monitored_user_id = int(state.split('_')[2])
            if monitored_user_id:
                # توجيه الرسالة إلى المدير
                try:
                    await event.forward_to(ADMIN_ID)
                except Exception as e:
                    await event.respond(f'فشل في توجيه الرسالة: {e}')
    
    # التحقق من حالة المستخدم في عملية التسجيل
    elif user_id in user_states:
        state = user_states[user_id]
        
        if state == 'awaiting_subscription_code':
            # التحقق من كود الاشتراك
            code = message_text.strip().upper()
            
            if is_subscription_code_valid(code):
                # استخدام الكود
                duration_days = use_subscription_code(code, user_id)
                
                # إنشاء أو تحديث بيانات المستخدم
                user_data = load_user_data(user_id) or {}
                user_data.update({
                    'subscription_date': datetime.now().strftime('%Y-%m-%d'),
                    'validity_days': duration_days,
                    'subscription_code': code
                })
                
                save_user_data(user_id, user_data)
                
                # إرسال إشعار للمدير
                await notify_admin(f'تم تفعيل اشتراك جديد:\nالمستخدم: {user_id}\nالكود: {code}\nالمدة: {duration_days} يوم')
                
                await event.respond(f'تم تفعيل اشتراكك بنجاح! مدة الاشتراك: {duration_days} يوم.')
                
                # تنظيف حالة المستخدم
                del user_states[user_id]
                
                # عرض القائمة الرئيسية
                buttons = [
                    [Button.inline("📝 تسجيل", data="register")],
                    [Button.inline("💬 تعيين الكليشة", data="set_cliche")],
                    [Button.inline("⏱️ تعيين الفاصل", data="set_interval")],
                    [Button.inline("▶️ تشغيل النشر", data="start_publishing"), Button.inline("⏹️ إيقاف النشر", data="stop_publishing")],
                    [Button.inline("⚙️ إعداد الحساب", data="setup_account")],
                    [Button.inline("🚪 تسجيل الخروج", data="logout")],
                    [Button.inline("📊 إحصائيات", data="statistics")]
                ]
                
                await event.respond('مرحباً! اختر أحد الخيارات:', buttons=buttons)
            else:
                await event.respond('كود الاشتراك غير صالح أو منتهي الصلاحية. يرجى المحاولة مرة أخرى:')
        
        elif state == 'awaiting_phone':
            # حفظ رقم الهاتف مؤقتاً
            temp_user_data[user_id] = {'phone': message_text}
            user_states[user_id] = 'awaiting_code'
            
            # إنشاء عميل جديد للتسجيل
            session_name = f"sessions/{user_id}"
            temp_client = TelegramClient(session_name, API_ID, API_HASH)
            
            try:
                await temp_client.connect()
                # إرسال رمز التحقق
                sent_code = await temp_client.send_code_request(message_text)
                temp_user_data[user_id]['client'] = temp_client
                temp_user_data[user_id]['phone_code_hash'] = sent_code.phone_code_hash
                
                await event.respond('تم إرسال رمز التحقق إلى هاتفك. يرجى إدخال الرمز:')
            except Exception as e:
                await event.respond(f'حدث خطأ: {e}. يرجى المحاولة مرة أخرى.')
                del user_states[user_id]
                if user_id in temp_user_data:
                    del temp_user_data[user_id]
        
        elif state == 'awaiting_code':
            # التحقق من وجود بيانات مؤقتة
            if user_id not in temp_user_data:
                await event.respond('حدث خطأ. يرجى البدء من جديد باستخدام /start')
                del user_states[user_id]
                return
            
            try:
                code = message_text.strip()
                client_data = temp_user_data[user_id]
                temp_client = client_data['client']
                phone = client_data['phone']
                phone_code_hash = client_data['phone_code_hash']
                
                # تسجيل الدخول باستخدام الرمز
                await temp_client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
                
                # حفظ الجلسة
                session_string = temp_client.session.save()
                with open(f'sessions/{user_id}.session', 'w') as f:
                    f.write(session_string)
                
                # تحديث بيانات المستخدم
                user_data = load_user_data(user_id)
                if user_data:
                    user_data.update({
                        'session_name': f'{user_id}.session',
                        'cliche': '',
                        'interval': 60,
                        'publishing': False,
                        'session_active': True,
                        'successful_posts': 0,
                        'failed_posts': 0
                    })
                else:
                    # إذا لم يكن هناك بيانات مستخدم (يجب ألا يحدث هذا مع نظام الكود)
                    user_data = {
                        'session_name': f'{user_id}.session',
                        'cliche': '',
                        'interval': 60,
                        'publishing': False,
                        'session_active': True,
                        'subscription_date': datetime.now().strftime('%Y-%m-%d'),
                        'validity_days': 30,
                        'successful_posts': 0,
                        'failed_posts': 0
                    }
                
                save_user_data(user_id, user_data)
                
                await event.respond('تم تسجيلك بنجاح! يمكنك الآن استخدام البوت.')
                
                # تنظيف البيانات المؤقتة
                del user_states[user_id]
                del temp_user_data[user_id]
                
            except Exception as e:
                await event.respond(f'حدث خطأ أثناء التسجيل: {e}. يرجى المحاولة مرة أخرى.')
                # تنظيف البيانات المؤقتة في حالة الخطأ
                if user_id in user_states:
                    del user_states[user_id]
                if user_id in temp_user_data:
                    if 'client' in temp_user_data[user_id]:
                        await temp_user_data[user_id]['client'].disconnect()
                    del temp_user_data[user_id]
        
        elif state == 'awaiting_cliche' or state == 'editing_cliche':
            # التحقق من أن الرسالة نصية فقط بدون روابط أو وسائط
            if not is_text_only(event):
                await event.respond('الرجاء إرسال رسالة نصية فقط بدون روابط أو وسائط. يرجى المحاولة مرة أخرى:')
                return
            
            # حفظ الكليشة في ملف المستخدم
            user_data = load_user_data(user_id)
            if user_data:
                user_data['cliche'] = message_text
                save_user_data(user_id, user_data)
                await event.respond('تم حفظ الكليشة بنجاح!')
            else:
                await event.respond('حدث خطأ في حفظ الكليشة. يرجى المحاولة مرة أخرى.')
            
            # تنظيف حالة المستخدم
            del user_states[user_id]
        
        elif state == 'awaiting_interval' or state == 'editing_interval':
            # التحقق من أن الفاصل الزمني صحيح
            if not is_valid_interval(message_text):
                await event.respond('الفاصل الزمني غير صحيح. يجب أن يكون رقم صحيح ولا يقل عن 5 دقائق. يرجى المحاولة مرة أخرى:')
                return
            
            # حفظ الفاصل الزمني في ملف المستخدم
            user_data = load_user_data(user_id)
            if user_data:
                user_data['interval'] = int(message_text)
                save_user_data(user_id, user_data)
                await event.respond(f'تم تعيين الفاصل الزمني إلى {message_text} دقيقة بنجاح!')
            else:
                await event.respond('حدث خطأ في حفظ الفاصل الزمني. يرجى المحاولة مرة أخرى.')
            
            # تنظيف حالة المستخدم
            del user_states[user_id]

# معالجة الأخطاء العامة
@client.on(events.NewMessage)
async def error_handler(event):
    try:
        # تجاهل الرسائل التي تمت معالجتها بالفعل
        if event.message.text and event.message.text.startswith('/'):
            return
            
        # تجاهل الرسائل التي تمت معالجتها بواسطة معالجات أخرى
        if event.chat_id in user_states or event.chat_id in admin_states:
            return
            
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

# تشغيل البوت والمهام الدورية
async def main():
    try:
        await client.start()
        logger.info('Bot started successfully!')
        
        # بدء مهمة التقارير الدورية
        asyncio.create_task(send_periodic_report())
        
        await client.run_until_disconnected()
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
    finally:
        # تنظيف جميع الجلسات عند إيقاف البوت
        for user_id in list(user_sessions.keys()):
            try:
                await user_sessions[user_id].disconnect()
            except:
                pass
        await client.disconnect()

if __name__ == '__main__':
    # تشغيل البوت مع التعامل مع الاستثناءات
    while True:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}, restarting in 10 seconds...")
            time.sleep(10)
