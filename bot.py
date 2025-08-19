import os
import asyncio
import sqlite3
from telethon import TelegramClient, events, Button
from telethon.errors import (
    PhoneNumberInvalidError, SessionPasswordNeededError,
    FloodWaitError, ChannelPrivateError, UserNotParticipantError
)
from telethon.sessions import StringSession
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.tl.types import InputPeerChannel

# إعدادات البوت
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

conn.commit()

# تهيئة عميل البوت
bot = TelegramClient('session_bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# ============== وظائف مساعدة ==============
async def is_subscribed(user_id):
    """التحقق من اشتراك المستخدم في القنوات الإجبارية (محدثة)"""
    for channel in MANDATORY_CHANNELS:
        try:
            # الحصول على معلومات القناة
            channel_entity = await bot.get_entity(channel)
            
            # التحقق من اشتراك المستخدم
            await bot(GetParticipantRequest(
                channel=InputPeerChannel(channel_entity.id, channel_entity.access_hash),
                participant=user_id
            ))
        except UserNotParticipantError:
            return False
        except (ValueError, ChannelPrivateError):
            # إذا لم يكن البوت مشرفاً أو حدث خطأ
            try:
                # طريقة بديلة للتحقق
                participants = await bot.get_participants(channel_entity)
                if not any(participant.id == user_id for participant in participants):
                    return False
            except Exception:
                return False
        except Exception as e:
            print(f"خطأ في التحقق من الاشتراك: {str(e)}")
            return False
    return True

def generate_invite_link(user_id):
    """إنشاء رابط دعوة فريد"""
    return f"https://t.me/{BOT_TOKEN.split(':')[0]}?start=invite_{user_id}"

def get_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return c.fetchone()

def create_user(user_id):
    c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

def update_invite_count(user_id):
    c.execute("UPDATE users SET invited_count = invited_count + 1 WHERE user_id=?", (user_id,))
    conn.commit()
    # تفعيل الحساب إذا وصل عدد الدعوات إلى 5
    c.execute("SELECT invited_count FROM users WHERE user_id=?", (user_id,))
    count = c.fetchone()[0]
    if count >= 5:
        c.execute("UPDATE users SET is_active=1 WHERE user_id=?", (user_id,))
        conn.commit()
        return True
    return False

def is_active_user(user_id):
    c.execute("SELECT is_active FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    return row and row[0] == 1 if row else False

def save_user_session(user_id, phone, session_str):
    c.execute("UPDATE users SET phone=?, session=?, is_active=1 WHERE user_id=?", 
             (phone, session_str, user_id))
    conn.commit()

# ============== معالجة الأحداث ==============
@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    user_id = event.sender_id
    args = event.pattern_match.string.split()
    
    # إنشاء مستخدم جديد إذا لم يكن موجوداً
    create_user(user_id)
    
    # معالجة رابط الدعوة إذا وجد
    if len(args) > 1 and args[1].startswith('invite_'):
        inviter_id = int(args[1].split('_')[1])
        if user_id != inviter_id:
            # تجنب تسجيل الدعوة المكررة
            c.execute("SELECT * FROM invited_users WHERE inviter_id=? AND invited_id=?", (inviter_id, user_id))
            if not c.fetchone():
                c.execute("INSERT INTO invited_users (inviter_id, invited_id) VALUES (?, ?)", (inviter_id, user_id))
                conn.commit()
                # تحديث عدد الدعوات وتفعيل الحساب إذا لزم الأمر
                if update_invite_count(inviter_id):
                    await bot.send_message(inviter_id, "🎉 تم تفعيل حسابك بعدد 5 دعوات!")

    # التحقق من الاشتراك في القنوات
    if not await is_subscribed(user_id):
        await event.respond(
            "**⚠️ يجب الاشتراك في القنوات التالية أولاً:**\n" +
            "\n".join([f"• @{channel}" for channel in MANDATORY_CHANNELS]) +
            "\n\nبعد الاشتراك، أعد استخدام الأمر /start"
        )
        return

    # التحقق من تفعيل الحساب
    if not is_active_user(user_id):
        invite_link = generate_invite_link(user_id)
        c.execute("SELECT invited_count FROM users WHERE user_id=?", (user_id,))
        count = c.fetchone()[0]
        
        await event.respond(
            f"**🔒 يجب دعوة 5 أشخاص لتفعيل حسابك**\n"
            f"**عدد المدعوين الحالي:** {count}/5\n"
            f"**رابط الدعوة الخاص بك:** {invite_link}\n\n"
            "قم بمشاركة رابط الدعوة أعلاه مع أصدقائك. "
            "بعد دعوة 5 أشخاص، سيتم تفعيل حسابك تلقائياً."
        )
        return
    
    # إذا كان الحساب مفعلاً - عرض خيار تسجيل الدخول
    await event.respond(
        "**✅ تم تفعيل حسابك بنجاح!**\n"
        "يمكنك الآن تسجيل الدخول لحفظ جلسة التلجرام.",
        buttons=[Button.inline("تسجيل الدخول", b"login")]
    )

@bot.on(events.CallbackQuery(data=b"login"))
async def login_handler(event):
    user_id = event.sender_id
    
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
        
        await event.respond(
            "✅ تم تسجيل الدخول بنجاح!\n"
            f"**رقم الهاتف:** `{phone}`\n"
            f"**جلسة التلجرام:**\n`{session_str}`"
        )
        await client.disconnect()

# ============== تشغيل البوت ==============
if __name__ == "__main__":
    print("تم تشغيل البوت بنجاح!")
    bot.run_until_disconnected()
