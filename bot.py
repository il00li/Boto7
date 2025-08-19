import os
import re
import asyncio
import sqlite3
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.errors import (
    ChatWriteForbiddenError, ChannelPrivateError, FloodWaitError,
    PhoneNumberInvalidError, SessionPasswordNeededError
)
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty

# إعدادات البوت
API_ID = 23656977
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'
BOT_TOKEN = '7917959495:AAFobh74Ped4Ffn7GaH9XSNQmiZtJnkLdMY'
MANDATORY_CHANNELS = ['crazys7', 'AWU87']
MIN_INTERVAL = 3  # الحد الأدنى للفاصل الزمني (دقائق)
ADMIN_ID = 123456789  # استبدل بمعرف المدير الفعلي

# إعداد قاعدة البيانات
DB_NAME = 'bot_db.sqlite'
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
c = conn.cursor()

# إنشاء الجداول
c.execute('''CREATE TABLE IF NOT EXISTS users (
             user_id INTEGER PRIMARY KEY,
             phone TEXT,
             session TEXT,
             invited_count INTEGER DEFAULT 0,
             is_active INTEGER DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS settings (
             user_id INTEGER PRIMARY KEY,
             interval INTEGER DEFAULT 5,
             message TEXT,
             is_publishing INTEGER DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS banned_users (
             user_id INTEGER PRIMARY KEY,
             banned_by INTEGER,
             reason TEXT)''')

c.execute('''CREATE TABLE IF NOT EXISTS invited_users (
             inviter_id INTEGER,
             invited_id INTEGER,
             PRIMARY KEY (inviter_id, invited_id))''')

c.execute('''CREATE TABLE IF NOT EXISTS publishing_groups (
             user_id INTEGER,
             group_id INTEGER,
             group_title TEXT,
             PRIMARY KEY (user_id, group_id))''')

conn.commit()

# تهيئة العميل
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ============== وظائف مساعدة ==============
async def is_subscribed(user_id):
    """التحقق من اشتراك المستخدم في القنوات الإلزامية"""
    for channel in MANDATORY_CHANNELS:
        try:
            channel_entity = await bot.get_entity(channel)
            await bot(JoinChannelRequest(channel_entity))
            participants = await bot.get_participants(channel_entity)
            if not any(participant.id == user_id for participant in participants):
                return False
        except Exception as e:
            print(f"Error checking subscription: {e}")
            return False
    return True

def generate_invite_link(user_id):
    """إنشاء رابط دعوة فريد"""
    return f"https://t.me/{BOT_TOKEN.split(':')[0]}?start=invite_{user_id}"

def get_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def update_invite_count(user_id):
    c.execute("UPDATE users SET invited_count = invited_count + 1 WHERE user_id=?", (user_id,))
    conn.commit()

def activate_user(user_id):
    c.execute("UPDATE users SET is_active=1 WHERE user_id=?", (user_id,))
    conn.commit()

def is_banned(user_id):
    c.execute("SELECT * FROM banned_users WHERE user_id=?", (user_id,))
    return c.fetchone() is not None

def is_active_user(user_id):
    c.execute("SELECT is_active FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return row and row[0] == 1 if row else False

def get_user_session(user_id):
    c.execute("SELECT session FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return row[0] if row else None

async def get_user_groups(user_id):
    """الحصول على مجموعات المستخدم"""
    session_str = get_user_session(user_id)
    if not session_str:
        return []
    
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    await client.start()
    
    groups = []
    dialogs = await client.get_dialogs()
    for dialog in dialogs:
        if dialog.is_group:
            groups.append(dialog.entity)
    
    await client.disconnect()
    return groups

# ============== معالجة الأحداث ==============
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    args = event.pattern_match.string.split()[1] if len(event.pattern_match.string.split()) > 1 else None
    
    # التحقق من الحظر
    if is_banned(user_id):
        await event.respond("⛔ تم حظرك من استخدام البوت.")
        return
    
    # معالجة رابط الدعوة
    if args and args.startswith('invite_'):
        inviter_id = int(args.split('_')[1])
        # تجنب أن يدعو المستخدم نفسه
        if user_id != inviter_id:
            # تحقق إذا كان المستخدم الجديد مسجل بالفعل
            c.execute("SELECT * FROM invited_users WHERE inviter_id=? AND invited_id=?", (inviter_id, user_id))
            if not c.fetchone():
                c.execute("INSERT INTO invited_users (inviter_id, invited_id) VALUES (?, ?)", (inviter_id, user_id))
                conn.commit()
                update_invite_count(inviter_id)
                # تحقق إذا وصل العدد إلى 5 لتفعيل الحساب
                user_data = get_user(inviter_id)
                if user_data and user_data[3] >= 5:  # invited_count
                    activate_user(inviter_id)
                    await bot.send_message(inviter_id, "🎉 تم تفعيل حسابك بعدد 5 دعوات!")
    
    # التحقق من الاشتراك في القنوات
    if not await is_subscribed(user_id):
        await event.respond("**⚠️ يجب الاشتراك في القنوات التالية أولاً:**\n" +
                            "\n".join([f"• @{channel}" for channel in MANDATORY_CHANNELS]))
        return
    
    user = get_user(user_id)
    buttons = []
    
    # إذا لم يكن مسجل أو غير مفعل
    if not user or not user[4]:  # is_active
        invite_link = generate_invite_link(user_id)
        buttons = [
            [Button.inline("تسجيل الدخول", b"login")],
            [Button.inline("مساعدة", b"help")]
        ]
        await event.respond(
            "**🔒 يجب دعوة 5 أشخاص أولاً لتفعيل حسابك**\n" +
            f"**رابط دعوتك:** {invite_link}\n" +
            f"**عدد المدعوين:** {user[3] if user else 0}/5",
            buttons=buttons
        )
        return
    
    # القائمة الرئيسية للمستخدم المفعل
    buttons = [
        [Button.inline("تسجيل الدخول", b"login")],
        [Button.inline("إعداد النشر", b"publish_settings")],
        [Button.inline("مساعدة", b"help")]
    ]
    await event.respond("**مرحباً بك في البوت!**", buttons=buttons)

@bot.on(events.CallbackQuery(data=b"login"))
async def login_handler(event):
    user_id = event.sender_id
    # التحقق من الحظر
    if is_banned(user_id):
        await event.respond("⛔ تم حظرك من استخدام البوت.")
        return
    
    # التحقق من الاشتراك
    if not await is_subscribed(user_id):
        await event.respond("**⚠️ يجب الاشتراك في القنوات أولاً.**")
        return
    
    async with bot.conversation(user_id) as conv:
        await conv.send_message("📱 الرجاء إرسال رقم هاتفك (مع رمز الدولة):")
        phone_response = await conv.get_response()
        phone = phone_response.text
        
        # إرسال كود التحقق
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        try:
            sent = await client.send_code_request(phone)
        except PhoneNumberInvalidError:
            await event.respond("❌ رقم الهاتف غير صالح")
            return
        
        await conv.send_message("🔢 أرسل كود التحقق (بصيغة 1 2 3 4 5):")
        code_response = await conv.get_response()
        code = ''.join(code_response.text.split())
        
        try:
            await client.sign_in(phone, code=code)
        except SessionPasswordNeededError:
            await conv.send_message("🔑 الحساب محمي بكلمة مرور. أرسل كلمة المرور:")
            password_response = await conv.get_response()
            await client.sign_in(password=password_response.text)
        except Exception as e:
            await event.respond(f"❌ خطأ في التسجيل: {str(e)}")
            return
        
        session_str = client.session.save()
        # حفظ الجلسة في قاعدة البيانات
        c.execute("REPLACE INTO users (user_id, phone, session) VALUES (?, ?, ?)",
                 (user_id, phone, session_str))
        conn.commit()
        await event.respond("✅ تم تسجيل الدخول بنجاح!")
        await client.disconnect()

@bot.on(events.CallbackQuery(data=b"publish_settings"))
async def publish_settings_handler(event):
    user_id = event.sender_id
    if not is_active_user(user_id):
        await event.respond("⚠️ يجب تفعيل حسابك أولاً بدعوة 5 أشخاص")
        return
    
    buttons = [
        [Button.inline("الفاصل الزمني", b"set_interval")],
        [Button.inline("تعيين الكليشة", b"set_message")],
        [Button.inline("بدء النشر", b"start_publishing")],
        [Button.inline("إيقاف النشر", b"stop_publishing")]
    ]
    await event.edit("**⚙️ إعدادات النشر:**", buttons=buttons)

@bot.on(events.CallbackQuery(data=b"set_interval"))
async def set_interval_handler(event):
    user_id = event.sender_id
    async with bot.conversation(user_id) as conv:
        await conv.send_message("⏱ الرجاء إرسال الفاصل الزمني (بالدقائق - الحد الأدنى 3 دقائق):")
        response = await conv.get_response()
        try:
            interval = max(int(response.text), MIN_INTERVAL)
            c.execute("REPLACE INTO settings (user_id, interval) VALUES (?, ?)",
                     (user_id, interval))
            conn.commit()
            await event.respond(f"✅ تم تعيين الفاصل الزمني إلى {interval} دقائق")
        except ValueError:
            await event.respond("❌ قيمة غير صالحة")

@bot.on(events.CallbackQuery(data=b"set_message"))
async def set_message_handler(event):
    user_id = event.sender_id
    async with bot.conversation(user_id) as conv:
        await conv.send_message("💬 أرسل الكليشة التي تريد نشرها:")
        response = await conv.get_response()
        message = response.text
        c.execute("REPLACE INTO settings (user_id, message) VALUES (?, ?)",
                 (user_id, message))
        conn.commit()
        await event.respond("✅ تم تعيين الكليشة بنجاح")

# ============== النشر التلقائي ==============
async def auto_publish(user_id):
    while True:
        # التحقق من حالة النشر
        c.execute("SELECT is_publishing FROM settings WHERE user_id=?", (user_id,))
        setting = c.fetchone()
        if not setting or not setting[0]:
            break
            
        # الحصول على الإعدادات
        c.execute("SELECT interval, message FROM settings WHERE user_id=?", (user_id,))
        interval, message = c.fetchone()
        
        # إذا لم توجد رسالة
        if not message:
            break
            
        # الحصول على الجلسة
        session_str = get_user_session(user_id)
        if not session_str:
            break
        
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await client.start()
        
        # الحصول على المجموعات
        groups = await get_user_groups(user_id)
        
        for group in groups:
            try:
                await client.send_message(group.id, message)
            except (ChatWriteForbiddenError, ChannelPrivateError):
                continue  # تخطي المجموعات الممنوعة أو الخاصة
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)  # الانتظار في حالة الفيضان
            except Exception as e:
                print(f"Error sending message to {group.id}: {e}")
        
        await asyncio.sleep(interval * 60)
        await client.disconnect()

@bot.on(events.CallbackQuery(data=b"start_publishing"))
async def start_publishing_handler(event):
    user_id = event.sender_id
    c.execute("UPDATE settings SET is_publishing=1 WHERE user_id=?", (user_id,))
    conn.commit()
    asyncio.create_task(auto_publish(user_id))
    await event.respond("✅ بدأ النشر التلقائي")

@bot.on(events.CallbackQuery(data=b"stop_publishing"))
async def stop_publishing_handler(event):
    user_id = event.sender_id
    c.execute("UPDATE settings SET is_publishing=0 WHERE user_id=?", (user_id,))
    conn.commit()
    await event.respond("⛔ تم إيقاف النشر التلقائي")

# ============== ميزات المدير ==============
@bot.on(events.NewMessage(pattern='/ban'))
async def ban_handler(event):
    if event.sender_id != ADMIN_ID:
        return
        
    try:
        user_id = int(event.text.split()[1])
        c.execute("INSERT OR REPLACE INTO banned_users (user_id, banned_by) VALUES (?, ?)",
                 (user_id, event.sender_id))
        conn.commit()
        await event.respond(f"✅ تم حظر المستخدم {user_id}")
    except Exception as e:
        await event.respond(f"❌ خطأ: {str(e)}")

@bot.on(events.NewMessage(pattern='/unban'))
async def unban_handler(event):
    if event.sender_id != ADMIN_ID:
        return
        
    try:
        user_id = int(event.text.split()[1])
        c.execute("DELETE FROM banned_users WHERE user_id=?", (user_id,))
        conn.commit()
        await event.respond(f"✅ تم إلغاء حظر المستخدم {user_id}")
    except Exception as e:
        await event.respond(f"❌ خطأ: {str(e)}")

@bot.on(events.NewMessage(pattern='/numbers'))
async def numbers_handler(event):
    if event.sender_id != ADMIN_ID:
        return
        
    try:
        page = int(event.text.split()[1]) if len(event.text.split()) > 1 else 1
        offset = (page - 1) * 10
        
        c.execute("SELECT phone FROM users LIMIT 10 OFFSET ?", (offset,))
        numbers = c.fetchall()
        
        response = f"📱 الأرقام المسجلة (الصفحة {page}):\n"
        for i, num in enumerate(numbers):
            response += f"{i+1}. {num[0]}\n"
            
        buttons = []
        if page > 1:
            buttons.append(Button.inline("السابق", data=f"prev_{page-1}"))
        if len(numbers) == 10:
            buttons.append(Button.inline("التالي", data=f"next_{page+1}"))
        
        await event.respond(response, buttons=buttons)
    except Exception as e:
        await event.respond(f"❌ خطأ: {str(e)}")

@bot.on(events.CallbackQuery(pattern=rb'(prev|next)_(\d+)'))
async def pagination_handler(event):
    if event.sender_id != ADMIN_ID:
        return
        
    action, page = event.pattern_match.groups()
    page = int(page)
    offset = (page - 1) * 10
    
    c.execute("SELECT phone FROM users LIMIT 10 OFFSET ?", (offset,))
    numbers = c.fetchall()
    
    response = f"📱 الأرقام المسجلة (الصفحة {page}):\n"
    for i, num in enumerate(numbers):
        response += f"{i+1}. {num[0]}\n"
    
    buttons = []
    if page > 1:
        buttons.append(Button.inline("السابق", data=f"prev_{page-1}"))
    if len(numbers) == 10:
        buttons.append(Button.inline("التالي", data=f"next_{page+1}"))
    
    await event.edit(response, buttons=buttons)

@bot.on(events.NewMessage(pattern='/broadcast'))
async def broadcast_handler(event):
    if event.sender_id != ADMIN_ID:
        return
        
    try:
        message = event.text.replace('/broadcast', '').strip()
        if not message:
            await event.respond("❌ يرجى إضافة الرسالة بعد الأمر")
            return
            
        c.execute("SELECT user_id FROM users")
        users = c.fetchall()
        
        for user_id in users:
            try:
                await bot.send_message(user_id[0], message)
                await asyncio.sleep(0.5)  # تجنب حظر التلجرام
            except Exception as e:
                print(f"Failed to send to {user_id[0]}: {e}")
        
        await event.respond(f"✅ تم إرسال الإشعار إلى {len(users)} مستخدم")
    except Exception as e:
        await event.respond(f"❌ خطأ: {str(e)}")

# ============== تشغيل البوت ==============
if __name__ == "__main__":
    print("Starting bot...")
    bot.run_until_disconnected()
