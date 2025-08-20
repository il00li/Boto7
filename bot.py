import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, events, Button
from telethon.errors import SessionPasswordNeededError, ChannelInvalidError, ChatWriteForbiddenError
from telethon.tl.types import Message, User, Channel, Chat
import logging

# تكوين logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# إعدادات البوت
API_ID = 23656977
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'
BOT_TOKEN = '8324471840:AAEX2W5x02F-NKZTt7qM0NNovrrF-gFRBsU'
ADMIN_ID = 6689435577  # معرف المدير

# مجلدات البيانات
SESSIONS_DIR = 'sessions'
DATA_DIR = 'data'
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ملفات البيانات
USERS_FILE = os.path.join(DATA_DIR, 'users.json')
CODES_FILE = os.path.join(DATA_DIR, 'codes.json')

# نحمل بيانات المستخدمين والأكواد
def load_data(filename):
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_data(data, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

users_data = load_data(USERS_FILE)
codes_data = load_data(CODES_FILE)

# نحتاج لتخزين المهام النشطة للنشر التلقائي لكل مستخدم
active_tasks = {}
user_clients = {}  # لتخزين عملاء Telethon للمستخدمين
user_states = {}  # لتخزين حالة المستخدم أثناء التفاعل

# إنشاء عميل البوت
bot = TelegramClient('bot', API_ID, API_HASH)

# وظائف المساعدة
def get_user_data(user_id):
    return users_data.get(str(user_id), {})

def save_user_data(user_id, data):
    users_data[str(user_id)] = data
    save_data(users_data, USERS_FILE)

def get_code_data(code):
    return codes_data.get(code, {})

def save_code_data(code, data):
    codes_data[code] = data
    save_data(codes_data, CODES_FILE)

# نتحقق من صلاحية اشتراك المستخدم
def is_subscription_active(user_data):
    sub = user_data.get('subscription', {})
    if sub.get('active') and 'expiry_date' in sub:
        expiry = datetime.strptime(sub['expiry_date'], '%Y-%m-%d')
        return expiry > datetime.now()
    return False

# نتحقق من صلاحية الكود
def is_code_valid(code):
    code_data = get_code_data(code)
    if not code_data:
        return False
    
    if not code_data.get('used', False) and 'expiry_date' in code_data:
        expiry = datetime.strptime(code_data['expiry_date'], '%Y-%m-%d')
        return expiry > datetime.now()
    
    return False

# توليد كود تفعيل جديد
def generate_activation_code(duration_days=30):
    import random
    import string
    
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    expiry_date = (datetime.now() + timedelta(days=duration_days)).strftime('%Y-%m-%d')
    
    code_data = {
        'created_at': datetime.now().strftime('%Y-%m-%d'),
        'expiry_date': expiry_date,
        'used': False,
        'used_by': None,
        'used_at': None
    }
    
    save_code_data(code, code_data)
    return code

# وظائف للنشر التلقائي
async def publish_message(client, user_id, message_text):
    user_data = get_user_data(user_id)
    if not user_data or not is_subscription_active(user_data):
        return 0, 0
    
    dialogs = await client.get_dialogs()
    successful_posts = 0
    total_groups = 0
    
    for dialog in dialogs:
        if dialog.is_group or dialog.is_channel:
            total_groups += 1
            try:
                await client.send_message(dialog.id, message_text)
                successful_posts += 1
                await asyncio.sleep(1)  # تجنب القيود
            except (ChannelInvalidError, ChatWriteForbiddenError, ValueError) as e:
                logger.warning(f"Cannot post in {dialog.id}: {str(e)}")
            except Exception as e:
                logger.error(f"Error posting in {dialog.id}: {str(e)}")
    
    # تحديث الإحصائيات
    user_data = get_user_data(user_id)
    stats = user_data.get('statistics', {})
    stats['total_posts'] = stats.get('total_posts', 0) + successful_posts
    stats['successful_groups'] = stats.get('successful_groups', 0) + successful_posts
    stats['total_groups'] = total_groups
    user_data['statistics'] = stats
    save_user_data(user_id, user_data)
    
    return successful_posts, total_groups

async def start_publishing(user_id):
    user_data = get_user_data(user_id)
    if not user_data or not is_subscription_active(user_data):
        await bot.send_message(user_id, "❌ ليس لديك اشتراك فعال أو انتهت صلاحيته.")
        return
    
    session_name = user_data.get('session_file')
    if not session_name or not os.path.exists(session_name):
        await bot.send_message(user_id, "❌ لم تقم بتسجيل جلسة بعد. استخدم زر 'تسجيل' أولاً.")
        return
    
    # إيقاف المهمة الحالية إذا كانت تعمل
    if user_id in active_tasks:
        active_tasks[user_id].cancel()
        if user_id in user_clients:
            await user_clients[user_id].disconnect()
            del user_clients[user_id]
    
    # إنشاء عميل للمستخدم
    try:
        client = TelegramClient(session_name, API_ID, API_HASH)
        await client.start()
        user_clients[user_id] = client
    except Exception as e:
        await bot.send_message(user_id, f"❌ فشل في بدء الجلسة: {str(e)}")
        return
    
    message_text = user_data.get('settings', {}).get('message', '')
    interval = user_data.get('settings', {}).get('interval', 300)  # 5 دقائق افتراضيًا
    
    if not message_text:
        await bot.send_message(user_id, "⚠️ لم تقم بتعيين كليشة النشر بعد!")
        return
    
    # تحديث حالة النشر
    user_data['is_publishing'] = True
    save_user_data(user_id, user_data)
    
    async def publishing_loop():
        next_publish_time = datetime.now()
        while user_data.get('is_publishing', False) and is_subscription_active(user_data):
            try:
                # حساب الوقت المتبقي للنشر القادم
                remaining_time = (next_publish_time - datetime.now()).total_seconds()
                if remaining_time > 0:
                    await asyncio.sleep(remaining_time)
                
                # النشر
                successful_posts, total_groups = await publish_message(client, user_id, message_text)
                
                # تحديث وقت النشر التالي
                next_publish_time = datetime.now() + timedelta(seconds=interval)
                
                # إرسال تقرير عن النشر
                await bot.send_message(
                    user_id, 
                    f"✅ تم النشر في {successful_posts} من أصل {total_groups} مجموعة.\n"
                    f"⏰ النشر القادم: {next_publish_time.strftime('%H:%M:%S')}"
                )
                
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in publishing loop: {str(e)}")
                await asyncio.sleep(60)  # الانتظار لمدة دقيقة قبل إعادة المحاولة
    
    task = asyncio.create_task(publishing_loop())
    active_tasks[user_id] = task
    
    next_publish = datetime.now() + timedelta(seconds=interval)
    await bot.send_message(
        user_id, 
        f"✅ بدأ النشر التلقائي.\n"
        f"⏰ الفاصل الزمني: {interval//60} دقائق\n"
        f"📝 الكليشة: {message_text[:50]}...\n"
        f"⏳ النشر القادم: {next_publish.strftime('%H:%M:%S')}"
    )

async def stop_publishing(user_id):
    if user_id in active_tasks:
        active_tasks[user_id].cancel()
        del active_tasks[user_id]
    
    if user_id in user_clients:
        await user_clients[user_id].disconnect()
        del user_clients[user_id]
    
    user_data = get_user_data(user_id)
    if user_data:
        user_data['is_publishing'] = False
        save_user_data(user_id, user_data)
    
    await bot.send_message(user_id, "⏹️ توقف النشر التلقائي.")

# أحداث البوت
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    user_data = get_user_data(user_id)
    
    # التحقق من صلاحية الاشتراك
    if not user_data or not is_subscription_active(user_data):
        buttons = [
            [Button.inline('تسجيل', 'register')],
            [Button.inline('إدخال كود التفعيل', 'enter_code')]
        ]
        await event.reply('مرحبًا! يبدو أنك لم تسجل بعد أو أن اشتراكك منتهي. اختر أحد الخيارات:', buttons=buttons)
    else:
        await show_main_menu(event)

@bot.on(events.CallbackQuery)
async def callback_handler(event):
    data = event.data.decode('utf-8')
    user_id = event.sender_id
    
    if data == 'register':
        await start_registration(event)
    elif data == 'enter_code':
        user_states[user_id] = 'waiting_for_code'
        await event.edit('أرسل كود التفعيل الذي حصلت عليه من المدير:')
    elif data == 'set_message':
        user_states[user_id] = 'waiting_for_message'
        await event.edit('أرسل الكليشة التي تريد نشرها:')
    elif data == 'set_interval':
        user_states[user_id] = 'waiting_for_interval'
        await event.edit('أرسل الفاصل الزمني بين النشرات بالدقائق (الحد الأدنى 5 دقائق):')
    elif data == 'start_publishing':
        await start_publishing(user_id)
    elif data == 'stop_publishing':
        await stop_publishing(user_id)
    elif data == 'account_settings':
        await show_account_settings(event)
    elif data == 'statistics':
        await show_statistics(event)
    elif data == 'logout':
        await logout_user(event)
    elif data == 'back':
        await show_main_menu(event)
    elif data == 'delete_account':
        await delete_account(event)
    elif data == 'admin_panel' and user_id == ADMIN_ID:
        await show_admin_panel(event)
    elif data.startswith('admin_'):
        await handle_admin_actions(event, data)

async def show_main_menu(event):
    user_id = event.sender_id
    user_data = get_user_data(user_id)
    
    buttons = [
        [Button.inline('تعيين الكليشة', 'set_message'), Button.inline('تعيين الفاصل', 'set_interval')],
        [Button.inline('تشغيل النشر', 'start_publishing'), Button.inline('إيقاف النشر', 'stop_publishing')],
        [Button.inline('إعداد الحساب', 'account_settings'), Button.inline('إحصائيات', 'statistics')],
        [Button.inline('تسجيل الخروج', 'logout')]
    ]
    
    # إذا كان المدير، نضيف زر المدير
    if user_id == ADMIN_ID:
        buttons.append([Button.inline('لوحة المدير', 'admin_panel')])
    
    # عرض الوقت المتبقي للنشر القادم إذا كان النشر نشطًا
    message = "📋 القائمة الرئيسية:"
    if user_data.get('is_publishing', False):
        interval = user_data.get('settings', {}).get('interval', 300)
        message += f"\n\nالنشر نشط ✅\nالفاصل الزمني: {interval//60} دقائق"
    
    await event.edit(message, buttons=buttons) if hasattr(event, 'edit') else await event.reply(message, buttons=buttons)

async def show_account_settings(event):
    user_id = event.sender_id
    user_data = get_user_data(user_id)
    
    message_text = user_data.get('settings', {}).get('message', 'لم يتم تعيين كليشة بعد')
    interval = user_data.get('settings', {}).get('interval', 300) // 60  # التحويل إلى دقائق
    
    buttons = [
        [Button.inline('تغيير الكليشة', 'set_message')],
        [Button.inline('تغيير الفاصل الزمني', 'set_interval')],
        [Button.inline('حذف الحساب', 'delete_account')],
        [Button.inline('رجوع', 'back')]
    ]
    
    await event.edit(
        f"⚙️ إعدادات الحساب:\n\n📝 الكليشة: {message_text[:100]}{'...' if len(message_text) > 100 else ''}\n⏰ الفاصل الزمني: {interval} دقائق", 
        buttons=buttons
    )

async def show_statistics(event):
    user_id = event.sender_id
    user_data = get_user_data(user_id)
    stats = user_data.get('statistics', {})
    
    total_posts = stats.get('total_posts', 0)
    successful_groups = stats.get('successful_groups', 0)
    total_groups = stats.get('total_groups', 0)
    
    message = f"📊 إحصائياتك:\n\n- إجمالي المنشورات: {total_posts}\n- المجموعات الناجحة: {successful_groups}\n- إجمالي المجموعات: {total_groups}"
    
    if user_id == ADMIN_ID:
        # إحصائيات المدير
        active_users = sum(1 for uid, data in users_data.items() if is_subscription_active(data))
        total_users = len(users_data)
        total_codes = len(codes_data)
        expired_codes = sum(1 for code, data in codes_data.items() 
                           if 'expiry_date' in data and datetime.strptime(data['expiry_date'], '%Y-%m-%d') < datetime.now())
        
        message += f"\n\n👑 إحصائيات المدير:\n- المستخدمون النشطون: {active_users}\n- إجمالي المستخدمين: {total_users}\n- إجمالي الأكواد: {total_codes}\n- الأكواد المنتهية: {expired_codes}"
    
    await event.edit(message, buttons=[[Button.inline('رجوع', 'back')]])

async def show_admin_panel(event):
    buttons = [
        [Button.inline('توليد كود تفعيل', 'admin_generate_code')],
        [Button.inline('حظر مستخدم', 'admin_ban_user')],
        [Button.inline('فك حظر مستخدم', 'admin_unban_user')],
        [Button.inline('حذف مستخدم', 'admin_delete_user')],
        [Button.inline('إشعار عام', 'admin_broadcast')],
        [Button.inline('سحب رقم', 'admin_pull_number')],
        [Button.inline('رجوع', 'back')]
    ]
    
    await event.edit("👑 لوحة تحكم المدير:", buttons=buttons)

async def handle_admin_actions(event, action):
    user_id = event.sender_id
    
    if action == 'admin_generate_code':
        code = generate_activation_code()
        await event.edit(f"✅ تم توليد كود التفعيل:\n\n`{code}`\n\nصالح لمدة 30 يومًا")
    
    elif action == 'admin_ban_user':
        user_states[user_id] = 'admin_waiting_ban_user'
        await event.edit("أرسل معرف المستخدم الذي تريد حظره:")
    
    elif action == 'admin_unban_user':
        user_states[user_id] = 'admin_waiting_unban_user'
        await event.edit("أرسل معرف المستخدم الذي تريد فك حظره:")
    
    elif action == 'admin_delete_user':
        user_states[user_id] = 'admin_waiting_delete_user'
        await event.edit("أرسل معرف المستخدم الذي تريد حذفه:")
    
    elif action == 'admin_broadcast':
        user_states[user_id] = 'admin_waiting_broadcast'
        await event.edit("أرسل الرسالة التي تريد بثها لجميع المستخدمين:")
    
    elif action == 'admin_pull_number':
        await show_user_list(event)

async def show_user_list(event):
    user_list = []
    for uid, data in users_data.items():
        status = "نشط" if is_subscription_active(data) else "غير نشط"
        user_list.append(f"👤 {uid} - {status}")
    
    if not user_list:
        await event.edit("لا يوجد مستخدمين مسجلين بعد.")
        return
    
    # تقسيم القائمة إلى صفحات
    pages = [user_list[i:i+10] for i in range(0, len(user_list), 10)]
    current_page = 0
    
    # إنشاء أزرار للتصفح
    buttons = []
    if len(pages) > 1:
        if current_page > 0:
            buttons.append(Button.inline('السابق', f'admin_page_{current_page-1}'))
        if current_page < len(pages)-1:
            buttons.append(Button.inline('التالي', f'admin_page_{current_page+1}'))
    
    message = "📋 قائمة المستخدمين:\n\n" + "\n".join(pages[current_page])
    await event.edit(message, buttons=buttons)

async def start_registration(event):
    user_id = event.sender_id
    
    # التحقق إذا كان المستخدم لديه اشتراك فعال
    user_data = get_user_data(user_id)
    if user_data and is_subscription_active(user_data):
        await event.edit("لديك بالفعل اشتراك فعال!")
        return
    
    user_states[user_id] = 'waiting_for_phone'
    await event.edit('أرسل رقم هاتفك مع رمز الدولة (مثال: +1234567890):')

@bot.on(events.NewMessage)
async def message_handler(event):
    user_id = event.sender_id
    text = event.text
    
    # تجاهل الرسائل في المجموعات
    if event.is_group:
        return
    
    # معالجة حالات المستخدم المختلفة
    if user_id in user_states:
        state = user_states[user_id]
        
        if state == 'waiting_for_phone' and re.match(r'^\+\d+$', text):
            await handle_phone_input(event, text)
        
        elif state == 'waiting_for_code' and re.match(r'^\d+$', text) and len(text) == 5:
            await handle_code_input(event, text)
        
        elif state == 'waiting_for_activation_code' and re.match(r'^[A-Z0-9]{10}$', text):
            await handle_activation_code(event, text)
        
        elif state == 'waiting_for_message':
            await handle_message_input(event, text)
        
        elif state == 'waiting_for_interval' and text.isdigit():
            await handle_interval_input(event, text)
        
        elif state == 'waiting_for_password':
            await handle_password_input(event, text)
        
        # معالجة أوامر المدير
        elif state == 'admin_waiting_ban_user' and text.isdigit():
            await admin_ban_user(event, int(text))
        
        elif state == 'admin_waiting_unban_user' and text.isdigit():
            await admin_unban_user(event, int(text))
        
        elif state == 'admin_waiting_delete_user' and text.isdigit():
            await admin_delete_user(event, int(text))
        
        elif state == 'admin_waiting_broadcast':
            await admin_broadcast(event, text)
        
        else:
            await event.reply("❌ إدخال غير صحيح. حاول مرة أخرى.")
        
        # مسح حالة المستخدم بعد المعالجة
        if user_id in user_states and not state.startswith('admin_'):
            del user_states[user_id]
    
    # إذا كان المستخدم يدخل كود تفعيل بدون الضغط على الزر أولاً
    elif re.match(r'^[A-Z0-9]{10}$', text):
        await handle_activation_code(event, text)
    
    # إذا كان المستخدم يرسل رسالة عادية بدون حالة محددة
    elif not text.startswith('/'):
        await event.reply("مرحبًا! استخدم /start لبدء التفاعل مع البوت.")

async def handle_phone_input(event, phone):
    user_id = event.sender_id
    
    # إنشاء جلسة جديدة
    session_name = os.path.join(SESSIONS_DIR, str(user_id))
    client = TelegramClient(session_name, API_ID, API_HASH)
    
    try:
        await client.connect()
        sent_code = await client.send_code_request(phone)
        await event.reply('✅ تم إرسال كود التحقق إلى حسابك. أرسل الكود هنا (5 أرقام):')
        
        # حفظ حالة المستخدم للخطوة التالية
        user_states[user_id] = 'waiting_for_code'
        user_data = get_user_data(user_id)
        user_data['registration'] = {
            'phone': phone,
            'session_name': session_name,
            'phone_code_hash': sent_code.phone_code_hash
        }
        save_user_data(user_id, user_data)
        
    except Exception as e:
        await event.reply(f'❌ حدث خطأ: {str(e)}')
        if user_id in user_states:
            del user_states[user_id]

async def handle_code_input(event, code):
    user_id = event.sender_id
    user_data = get_user_data(user_id)
    
    if 'registration' not in user_data:
        await event.reply('❌ لم تبدأ عملية التسجيل بعد. استخدم /start للبدء.')
        return
    
    reg_data = user_data['registration']
    client = TelegramClient(reg_data['session_name'], API_ID, API_HASH)
    
    try:
        await client.connect()
        await client.sign_in(reg_data['phone'], code, phone_code_hash=reg_data['phone_code_hash'])
        
        # حفظ الجلسة
        user_data['session_file'] = reg_data['session_name']
        user_data['phone'] = reg_data['phone']
        del user_data['registration']
        save_user_data(user_id, user_data)
        
        await event.reply('✅ تم تسجيل الجلسة بنجاح! الآن أرسل كود التفعيل الذي حصلت عليه من المدير.')
        user_states[user_id] = 'waiting_for_activation_code'
        
    except SessionPasswordNeededError:
        await event.reply('🔐 حسابك محمي بكلمة مرور ثنائية. أرسل كلمة المرور هنا:')
        user_states[user_id] = 'waiting_for_password'
    except Exception as e:
        await event.reply(f'❌ حدث خطأ: {str(e)}')
        if user_id in user_states:
            del user_states[user_id]

async def handle_password_input(event, password):
    user_id = event.sender_id
    user_data = get_user_data(user_id)
    
    if 'registration' not in user_data:
        await event.reply('❌ لم تبدأ عملية التسجيل بعد. استخدم /start للبدء.')
        return
    
    reg_data = user_data['registration']
    client = TelegramClient(reg_data['session_name'], API_ID, API_HASH)
    
    try:
        await client.connect()
        await client.sign_in(password=password)
        
        # حفظ الجلسة
        user_data['session_file'] = reg_data['session_name']
        user_data['phone'] = reg_data['phone']
        del user_data['registration']
        save_user_data(user_id, user_data)
        
        await event.reply('✅ تم تسجيل الجلسة بنجاح! الآن أرسل كود التفعيل الذي حصلت عليه من المدير.')
        user_states[user_id] = 'waiting_for_activation_code'
        
    except Exception as e:
        await event.reply(f'❌ حدث خطأ: {str(e)}')
        if user_id in user_states:
            del user_states[user_id]

async def handle_activation_code(event, code):
    user_id = event.sender_id
    
    if not is_code_valid(code):
        await event.reply('❌ كود التفعيل غير صالح أو منتهي الصلاحية.')
        return
    
    # تفعيل الاشتراك
    user_data = get_user_data(user_id)
    expiry_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
    
    user_data['subscription'] = {
        'active': True,
        'expiry_date': expiry_date,
        'activated_at': datetime.now().strftime('%Y-%m-%d'),
        'activation_code': code
    }
    
    # تحديث حالة الكود
    code_data = get_code_data(code)
    code_data['used'] = True
    code_data['used_by'] = user_id
    code_data['used_at'] = datetime.now().strftime('%Y-%m-%d')
    save_code_data(code, code_data)
    
    save_user_data(user_id, user_data)
    
    # إرسال إشعار للمدير
    await bot.send_message(ADMIN_ID, f'✅ تم تفعيل اشتراك جديد للمستخدم {user_id} باستخدام الكود {code}.')
    
    await event.reply('✅ تم تفعيل اشتراكك بنجاح! يمكنك الآن استخدام البوت.')
    await show_main_menu(event)

async def handle_message_input(event, message):
    user_id = event.sender_id
    user_data = get_user_data(user_id)
    
    if not user_data or not is_subscription_active(user_data):
        await event.reply('❌ ليس لديك اشتراك فعال.')
        return
    
    if 'settings' not in user_data:
        user_data['settings'] = {}
    
    user_data['settings']['message'] = message
    save_user_data(user_id, user_data)
    
    await event.reply('✅ تم حفظ الكليشة بنجاح!')
    await show_main_menu(event)

async def handle_interval_input(event, interval):
    user_id = event.sender_id
    interval = int(interval)
    
    if interval < 5:
        await event.reply('❌ الحد الأدنى للفاصل الزمني هو 5 دقائق.')
        return
    
    user_data = get_user_data(user_id)
    
    if not user_data or not is_subscription_active(user_data):
        await event.reply('❌ ليس لديك اشتراك فعال.')
        return
    
    if 'settings' not in user_data:
        user_data['settings'] = {}
    
    user_data['settings']['interval'] = interval * 60  # التحويل إلى ثواني
    save_user_data(user_id, user_data)
    
    await event.reply(f'✅ تم تعيين الفاصل الزمني إلى {interval} دقائق!')
    await show_main_menu(event)

async def logout_user(event):
    user_id = event.sender_id
    
    # إيقاف النشر إذا كان نشطًا
    if user_id in active_tasks:
        await stop_publishing(user_id)
    
    # مسح بيانات الجلسة
    user_data = get_user_data(user_id)
    if user_data:
        user_data['session_file'] = None
        save_user_data(user_id, user_data)
    
    await event.edit('✅ تم تسجيل الخروج بنجاح. يمكنك العودة في أي وقت بإدخال كود التفعيل من جديد.')

async def delete_account(event):
    user_id = event.sender_id
    
    # إيقاف النشر إذا كان نشطًا
    if user_id in active_tasks:
        await stop_publishing(user_id)
    
    # حذف ملف الجلسة
    user_data = get_user_data(user_id)
    if user_data and 'session_file' in user_data and os.path.exists(user_data['session_file']):
        os.remove(user_data['session_file'])
    
    # حذف بيانات المستخدم
    if str(user_id) in users_data:
        del users_data[str(user_id)]
        save_data(users_data, USERS_FILE)
    
    await event.edit('✅ تم حذف حسابك بنجاح.')

# وظائف المدير
async def admin_ban_user(event, user_id):
    user_data = get_user_data(user_id)
    if not user_data:
        await event.reply('❌ المستخدم غير موجود.')
        return
    
    user_data['banned'] = True
    save_user_data(user_id, user_data)
    
    # إيقاف النشر إذا كان نشطًا
    if user_id in active_tasks:
        await stop_publishing(user_id)
    
    await event.reply(f'✅ تم حظر المستخدم {user_id}.')
    await bot.send_message(user_id, '❌ تم حظر حسابك من استخدام البوت.')

async def admin_unban_user(event, user_id):
    user_data = get_user_data(user_id)
    if not user_data:
        await event.reply('❌ المستخدم غير موجود.')
        return
    
    user_data['banned'] = False
    save_user_data(user_id, user_data)
    
    await event.reply(f'✅ تم فك حظر المستخدم {user_id}.')
    await bot.send_message(user_id, '✅ تم فك حظر حسابك. يمكنك الآن استخدام البوت مرة أخرى.')

async def admin_delete_user(event, user_id):
    user_data = get_user_data(user_id)
    if not user_data:
        await event.reply('❌ المستخدم غير موجود.')
        return
    
    # إيقاف النشر إذا كان نشطًا
    if user_id in active_tasks:
        await stop_publishing(user_id)
    
    # حذف ملف الجلسة
    if 'session_file' in user_data and os.path.exists(user_data['session_file']):
        os.remove(user_data['session_file'])
    
    # حذف بيانات المستخدم
    if str(user_id) in users_data:
        del users_data[str(user_id)]
        save_data(users_data, USERS_FILE)
    
    await event.reply(f'✅ تم حذف حساب المستخدم {user_id}.')

async def admin_broadcast(event, message):
    sent_count = 0
    total_count = len(users_data)
    
    for user_id in users_data.keys():
        try:
            await bot.send_message(int(user_id), f"📢 إشعار من المدير:\n\n{message}")
            sent_count += 1
        except Exception as e:
            logger.error(f"Failed to send broadcast to {user_id}: {str(e)}")
    
    await event.reply(f"✅ تم إرسال الإشعار إلى {sent_count} من أصل {total_count} مستخدم.")

# مهمة دورية للتحقق من انتهاء الصلاحية
async def check_subscriptions():
    while True:
        await asyncio.sleep(24 * 60 * 60)  # الانتظار لمدة 24 ساعة
        
        now = datetime.now()
        expired_users = []
        
        for user_id, user_data in users_data.items():
            if is_subscription_active(user_data):
                expiry_date = datetime.strptime(user_data['subscription']['expiry_date'], '%Y-%m-%d')
                days_remaining = (expiry_date - now).days
                
                if days_remaining == 3:
                    # إرسال تنبيه قبل 3 أيام من انتهاء الصلاحية
                    try:
                        await bot.send_message(int(user_id), f"⚠️ اشتراكك سينتهي خلال {days_remaining} أيام. يرجى التواصل مع المدير لتجديد الاشتراك.")
                    except Exception as e:
                        logger.error(f"Failed to send expiry warning to {user_id}: {str(e)}")
                
                if expiry_date < now:
                    # انتهاء الصلاحية
                    user_data['subscription']['active'] = False
                    save_user_data(int(user_id), user_data)
                    expired_users.append(user_id)
                    
                    # إيقاف النشر إذا كان نشطًا
                    if int(user_id) in active_tasks:
                        await stop_publishing(int(user_id))
                    
                    try:
                        await bot.send_message(int(user_id), "❌ انتهت صلاحية اشتراكك. يرجى التواصل مع المدير لتجديد الاشتراك.")
                    except Exception as e:
                        logger.error(f"Failed to send expiry notice to {user_id}: {str(e)}")
        
        # إرسال تقرير دوري للمدير
        active_users = sum(1 for uid, data in users_data.items() if is_subscription_active(data))
        total_posts = sum(data.get('statistics', {}).get('total_posts', 0) for data in users_data.values())
        expired_codes = sum(1 for code, data in codes_data.items() 
                           if 'expiry_date' in data and datetime.strptime(data['expiry_date'], '%Y-%m-%d') < datetime.now())
        
        report_msg = (
            f"📊 التقرير الدوري:\n"
            f"- المستخدمون النشطون: {active_users}\n"
            f"- إجمالي المنشورات: {total_posts}\n"
            f"- الأكواد المنتهية: {expired_codes}\n"
            f"- المستخدمون المنتهية صلاحيتهم: {len(expired_users)}"
        )
        
        try:
            await bot.send_message(ADMIN_ID, report_msg)
        except Exception as e:
            logger.error(f"Failed to send report to admin: {str(e)}")

# بدء البوت والمهام الدورية
async def main():
    # بدء مهمة التحقق من الصلاحية
    asyncio.create_task(check_subscriptions())
    
    # تشغيل البوت
    await bot.start()
    await bot.run_until_disconnected()

if __name__ == '__main__':
    # استخدام حلقة asyncio الحالية بدلاً من إنشاء حلقة جديدة
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close() 
