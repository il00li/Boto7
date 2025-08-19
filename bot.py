import os
import asyncio
import sqlite3
from telethon import TelegramClient, events, Button
from telethon.errors import (
    PhoneNumberInvalidError, SessionPasswordNeededError,
    FloodWaitError
)
from telethon.sessions import StringSession

# إعدادات البوت الجديدة
API_ID = 23656977
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'
BOT_TOKEN = '7917959495:AAFobh74Ped4Ffn7GaH9XSNQmiZtJnkLdMY'
MANDATORY_CHANNELS = ['crazys7', 'AWU87']  # القنوات الإجبارية

# إعداد قاعدة البيانات
DB_NAME = 'bot_db.sqlite'
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
c = conn.cursor()

# إنشاء الجداول الأساسية
c.execute('''CREATE TABLE IF NOT EXISTS users (
             user_id INTEGER PRIMARY KEY,
             phone TEXT,
             session TEXT,
             invited_count INTEGER DEFAULT 0,
             is_active INTEGER DEFAULT 0)''')

c.execute('''CREATE TABLE IF NOT EXISTS invited_users (
             inviter_id INTEGER,
             invited_id INTEGER,
             PRIMARY KEY (inviter_id, invited_id))''')

c.execute('''CREATE TABLE IF NOT EXISTS banned_users (
             user_id INTEGER PRIMARY KEY,
             banned_by INTEGER,
             reason TEXT)''')

conn.commit()

# تهيئة عميل البوت
bot = TelegramClient('session_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ============== وظائف مساعدة ==============
async def is_subscribed(user_id):
    """التحقق من اشتراك المستخدم في القنوات الإجبارية"""
    for channel in MANDATORY_CHANNELS:
        try:
            channel_entity = await bot.get_entity(channel)
            participants = await bot.get_participants(channel_entity)
            if not any(participant.id == user_id for participant in participants):
                return False
        except Exception:
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
    user = get_user(user_id)
    return user and user[4] == 1 if user else False

def save_user_session(user_id, phone, session_str):
    c.execute("REPLACE INTO users (user_id, phone, session) VALUES (?, ?, ?)",
             (user_id, phone, session_str))
    conn.commit()

# ============== معالجة الأحداث ==============
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    args = event.pattern_match.string.split()
    
    # التحقق من الحظر
    if is_banned(user_id):
        await event.respond("⛔ تم حظرك من استخدام البوت.")
        return
    
    # معالجة رابط الدعوة إذا وجد
    if len(args) > 1 and args[1].startswith('invite_'):
        inviter_id = int(args[1].split('_')[1])
        if user_id != inviter_id:
            # تجنب تسجيل الدعوة المكررة
            c.execute("SELECT * FROM invited_users WHERE inviter_id=? AND invited_id=?", (inviter_id, user_id))
            if not c.fetchone():
                c.execute("INSERT INTO invited_users (inviter_id, invited_id) VALUES (?, ?)", (inviter_id, user_id))
                conn.commit()
                update_invite_count(inviter_id)
                # تفعيل الحساب إذا وصل عدد الدعوات إلى 5
                user_data = get_user(inviter_id)
                if user_data and user_data[3] >= 5:
                    activate_user(inviter_id)
                    await bot.send_message(inviter_id, "🎉 تم تفعيل حسابك بعدد 5 دعوات!")

    # التحقق من الاشتراك في القنوات
    if not await is_subscribed(user_id):
        await event.respond("**⚠️ يجب الاشتراك في القنوات التالية أولاً:**\n" +
                            "\n".join([f"• @{channel}" for channel in MANDATORY_CHANNELS]))
        return

    # عرض حالة المستخدم
    user = get_user(user_id)
    buttons = [[Button.inline("تسجيل الدخول", b"login")]]
    
    if not user or not user[4]:  # إذا لم يتم تفعيل الحساب
        invite_link = generate_invite_link(user_id)
        message = (
            "**🔒 يجب دعوة 5 أشخاص لتفعيل حسابك**\n"
            f"**رابط دعوتك:** {invite_link}\n"
            f"**عدد المدعوين:** {user[3] if user else 0}/5"
        )
    else:
        message = "**مرحباً بك! يمكنك تسجيل الدخول الآن**"
    
    await event.respond(message, buttons=buttons)

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
    
    # التحقق من تفعيل الحساب
    if not is_active_user(user_id):
        await event.respond("⚠️ يجب تفعيل حسابك أولاً بدعوة 5 أشخاص")
        return
    
    # بدء عملية تسجيل الدخول
    async with bot.conversation(user_id) as conv:
        await conv.send_message("📱 الرجاء إرسال رقم هاتفك (مع رمز الدولة):")
        phone_response = await conv.get_response()
        phone = phone_response.text.strip()
        
        # إرسال كود التحقق
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        
        try:
            sent = await client.send_code_request(phone)
        except PhoneNumberInvalidError:
            await event.respond("❌ رقم الهاتف غير صالح")
            return
        except FloodWaitError as e:
            await event.respond(f"⏳ تم حظرك مؤقتاً، يرجى الانتظار {e.seconds} ثانية")
            return
        
        await conv.send_message("🔢 أرسل كود التحقق (بصيغة 1 2 3 4 5):")
        code_response = await conv.get_response()
        code = ''.join(code_response.text.strip().split())
        
        try:
            await client.sign_in(phone, code=code)
        except SessionPasswordNeededError:
            await conv.send_message("🔑 الحساب محمي بكلمة مرور. أرسل كلمة المرور:")
            password_response = await conv.get_response()
            await client.sign_in(password=password_response.text.strip())
        except Exception as e:
            await event.respond(f"❌ خطأ في التسجيل: {str(e)}")
            return
        
        # حفظ الجلسة
        session_str = client.session.save()
        save_user_session(user_id, phone, session_str)
        
        await event.respond("✅ تم تسجيل الدخول بنجاح! تم حفظ الجلسة.")
        await client.disconnect()

# ============== تشغيل البوت ==============
if __name__ == "__main__":
    print("تم تشغيل البوت بنجاح!")
    bot.run_until_disconnected()
        
