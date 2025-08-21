import os
import json
import asyncio
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.types import Channel, Chat
from telethon.errors import ChatWriteForbiddenError, ChannelInvalidError, ChannelPrivateError
import logging

# إعدادات التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# إعدادات البوت
API_ID = int(os.environ.get('API_ID', 23656977))
API_HASH = os.environ.get('API_HASH', '49d3f43531a92b3f5bc403766313ca1e')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8324471840:AAHYZ2GjqnNmYYSLFBWLGHizRH3QUgP9uMg')
ADMIN_ID = int(os.environ.get('ADMIN_ID', 6689435577))  # معرّف المدير

# إنشاء مجلد قاعدة البيانات إذا لم يكن موجوداً
if not os.path.exists('user_data'):
    os.makedirs('user_data')
if not os.path.exists('sessions'):
    os.makedirs('sessions')

# إنشاء عميل Telethon
client = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# قاموس لتخزين حالات المستخدمين أثناء التسجيل
user_states = {}
temp_user_data = {}

# قاموس لتخزين مهام النشر لكل مستخدم
publishing_tasks = {}

# قاموس لتخزين جلسات المستخدمين النشطة
user_sessions = {}

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

# دالة للتحقق من صلاحية الاشتراك
def is_subscription_valid(user_data):
    if not user_data:
        return False
    
    subscription_date = datetime.strptime(user_data['subscription_date'], '%Y-%m-%d')
    validity_days = user_data['validity_days']
    expiry_date = subscription_date + timedelta(days=validity_days)
    
    return datetime.now() < expiry_date

# دالة لإرسال رسالة إلى المدير
async def notify_admin(message):
    try:
        await client.send_message(ADMIN_ID, message)
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
            groups = await get_user_groups(user_session)
            successful_posts = 0
            failed_posts = 0
            
            for group in groups:
                try:
                    await user_session.send_message(group.id, cliche)
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
            await publishing_tasks[user_id]
        except asyncio.CancelledError:
            logger.info(f"Publishing task for user {user_id} was cancelled")
        del publishing_tasks[user_id]
    
    # فصل جلسة المستخدم إذا كانت متصلة
    if user_id in user_sessions:
        try:
            await user_sessions[user_id].disconnect()
            logger.info(f"Disconnected session for user {user_id}")
        except Exception as e:
            logger.error(f"Error disconnecting session for user {user_id}: {e}")
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
        del user_sessions[user_id]
    
    # تحديث حالة الجلسة في ملف المستخدم
    if user_data:
        user_data['session_active'] = False
        save_user_data(user_id, user_data)
        logger.info(f"User {user_id} logged out successfully")
    
    return True

# معالجة الأمر /start
@client.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    user_data = load_user_data(user_id)
    
    if not user_data or not is_subscription_valid(user_data):
        await event.respond('مرحباً! يبدو أنك غير مسجل أو أن اشتراكك قد انتهى. يرجى التسجيل أولاً.')
        return
    
    buttons = [
        [Button.inline("تسجيل", data="register")],
        [Button.inline("تعيين الكليشة", data="set_cliche")],
        [Button.inline("تعيين الفاصل", data="set_interval")],
        [Button.inline("تشغيل", data="start_publishing"), Button.inline("إيقاف", data="stop_publishing")],
        [Button.inline("إعداد الحساب", data="setup_account")],
        [Button.inline("تسجيل الخروج", data="logout")],
        [Button.inline("إحصائيات", data="statistics")]
    ]
    
    await event.respond('مرحباً! اختر أحد الخيارات:', buttons=buttons)

# معالجة الأزرارInline
@client.on(events.CallbackQuery)
async def callback_handler(event):
    user_id = event.sender_id
    user_data = load_user_data(user_id)
    
    data = event.data.decode('utf-8')
    
    if data == 'register':
        # التحقق مما إذا كان المستخدم مسجلاً بالفعل
        if user_data and is_subscription_valid(user_data) and user_data.get('session_active', False):
            await event.answer('أنت مسجل بالفعل!', alert=True)
            return
        
        # بدء عملية التسجيل
        user_states[user_id] = 'awaiting_phone'
        await event.answer('جاري فتح نموذج التسجيل...')
        await event.edit('يرجى إرسال رقم هاتفك مع رمز الدولة (مثال: +1234567890)')
        
    elif data == 'set_cliche':
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى التسجيل أولاً.', alert=True)
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
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى التسجيل أولاً.', alert=True)
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
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى التسجيل أولاً.', alert=True)
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
            
            user_session = TelegramClient(StringSession(session_string), API_ID, API_HASH)
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
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى التسجيل أولاً.', alert=True)
            return
        
        # إيقاف النشر
        await stop_publishing_for_user(user_id)
        
        await event.answer('تم إيقاف النشر بنجاح!', alert=True)
        await event.edit('تم إيقاف النشر في جميع المجموعات.')
        
        # إرسال إشعار للمستخدم
        await client.send_message(user_id, 'تم إيقاف النشر بنجاح.')
        
    elif data == 'setup_account':
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى التسجيل أولاً.', alert=True)
            return
        
        # التحقق من أن الجلسة نشطة
        if not user_data.get('session_active', False):
            await event.answer('يجب عليك تسجيل الدخول أولاً!', alert=True)
            return
        
        # عرض خيارات إعداد الحساب
        account_buttons = [
            [Button.inline("تعديل الكليشة", data="edit_cliche")],
            [Button.inline("تعديل الفاصل", data="edit_interval")],
            [Button.inline("حذف الحساب", data="delete_account")],
            [Button.inline("رجوع", data="back_to_main")]
        ]
        
        await event.answer('جاري فتح إعدادات الحساب...')
        await event.edit('اختر أحد خيارات إعداد الحساب:', buttons=account_buttons)
        
    elif data == 'edit_cliche':
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشترак غير فعال أو منتهي الصلاحية. يرجى التسجيل أولاً.', alert=True)
            return
        
        # بدء عملية تعديل الكليشة
        user_states[user_id] = 'editing_cliche'
        await event.answer('جاري فتح نافذة تعديل الكليشة...')
        await event.edit('يرجى إرسال الكليشة الجديدة (رسالة نصية فقط بدون روابط أو وسائط):')
        
    elif data == 'edit_interval':
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى التسجيل أولاً.', alert=True)
            return
        
        # بدء عملية تعديل الفاصل الزمني
        user_states[user_id] = 'editing_interval'
        await event.answer('جاري فتح نافذة تعديل الفاصل الزمني...')
        await event.edit('يرجى إدخال الفاصل الزمني الجديد بين النشرات (بالدقائق، لا يقل عن 5 دقائق):')
        
    elif data == 'delete_account':
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى التسجيل أولاً.', alert=True)
            return
        
        # تأكيد حذف الحساب
        confirm_buttons = [
            [Button.inline("نعم، احذف حسابي", data="confirm_delete")],
            [Button.inline("لا، إلغاء", data="cancel_delete")]
        ]
        
        await event.answer('جاري فتح نافذة تأكيد الحذف...')
        await event.edit('⚠️ هل أنت متأكد من أنك تريد حذف حسابك؟ سيتم حذف جميع بياناتك ولا يمكن استعادتها.', buttons=confirm_buttons)
        
    elif data == 'confirm_delete':
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى التسجيل أولاً.', alert=True)
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
            [Button.inline("تعديل الكليشة", data="edit_cliche")],
            [Button.inline("تعديل الفاصل", data="edit_interval")],
            [Button.inline("حذف الحساب", data="delete_account")],
            [Button.inline("رجوع", data="back_to_main")]
        ]
        
        await event.answer('تم إلغاء عملية الحذف.')
        await event.edit('اختر أحد خيارات إعداد الحساب:', buttons=account_buttons)
        
    elif data == 'back_to_main':
        # العودة إلى القائمة الرئيسية
        buttons = [
            [Button.inline("تسجيل", data="register")],
            [Button.inline("تعيين الكليشة", data="set_cliche")],
            [Button.inline("تعيين الفاصل", data="set_interval")],
            [Button.inline("تشغيل", data="start_publishing"), Button.inline("إيقاف", data="stop_publishing")],
            [Button.inline("إعداد الحساب", data="setup_account")],
            [Button.inline("تسجيل الخروج", data="logout")],
            [Button.inline("إحصائيات", data="statistics")]
        ]
        
        await event.answer('جاري العودة إلى القائمة الرئيسية...')
        await event.edit('مرحباً! اختر أحد الخيارات:', buttons=buttons)
        
    elif data == 'logout':
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى التسجيل أولاً.', alert=True)
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
        # التحقق من صلاحية الاشتراك
        if not user_data or not is_subscription_valid(user_data):
            await event.answer('اشتراكك غير فعال أو منتهي الصلاحية. يرجى التسجيل أولاً.', alert=True)
            return
        
        # عرض الإحصائيات
        stats_text = f"""
إحصائيات حسابك:
- الكليشة: {user_data.get('cliche', 'غير معينة')}
- الفاصل الزمني: {user_data.get('interval', 'غير معين')} دقيقة
- حالة النشر: {'نشط' if user_data.get('publishing', False) else 'متوقف'}
- حالة الجلسة: {'نشطة' if user_data.get('session_active', False) else 'غير نشطة'}
- عدد النشرات الناجحة: {user_data.get('successful_posts', 0)}
- عدد النشرات الفاشلة: {user_data.get('failed_posts', 0)}
- آخر نشر: {user_data.get('last_publish', 'لم يحدث بعد')}
- تاريخ الاشتراك: {user_data.get('subscription_date', 'غير معروف')}
- مدة الصلاحية: {user_data.get('validity_days', 'غير معروفة')} يوم
        """
        await event.answer('جاري تحميل الإحصائيات...')
        await event.edit(stats_text)

# معالجة الرسائل النصية
@client.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    message_text = event.text
    
    # تجاهل الرسائل التي تبدأ ب /start
    if message_text and message_text.startswith('/start'):
        return
    
    # التحقق من حالة المستخدم في عملية التسجيل
    if user_id in user_states:
        state = user_states[user_id]
        
        if state == 'awaiting_phone':
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
                
                # إنشاء بيانات المستخدم
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
                
                # إرسال إشعار للمدير
                await notify_admin(f'مستخدم جديد سجّل في البوت:\nالمعرف: {user_id}\nالتاريخ: {user_data["subscription_date"]}')
                
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

# تشغيل البوت
if __name__ == '__main__':
    logger.info('Starting bot...')
    client.run_until_disconnected()
