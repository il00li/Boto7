import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, events, sync
from telethon.sessions import StringSession
from telethon.tl.types import MessageEntityMentionName
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, Channel, Chat, User
import aiofiles
import logging

# إعدادات API
API_ID = 23656977
API_HASH = '49d3f43531a92b3f5bc403766313ca1e'
BOT_TOKEN = '8324471840:AAEX2W5x02F-NKZTt7qM0NNovrrF-gFRBsU'

# إعدادات المدير
ADMIN_IDS = [123456789]  # استبدل بأرقام هويات المديرين

# إعدادات الملفات
USERS_FILE = 'users.json'
CODES_FILE = 'codes.json'
SETTINGS_DIR = 'user_settings'

# إنشاء الدلائل إذا لم تكن موجودة
os.makedirs(SETTINGS_DIR, exist_ok=True)

# إعداد التسجيل
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TelegramAutoPostBot:
    def __init__(self):
        self.bot = None
        self.user_clients = {}
        self.posting_tasks = {}
        self.user_data = self.load_data(USERS_FILE)
        self.codes_data = self.load_data(CODES_FILE)
        self.main_menu_text = """
🤖 **بوت النشر التلقائي**

◂ لتشغيل البوت يجب أن تمتلك كود تفعيل ساري المفعول
◂ البوت مخصص للنشر التلقائي في القنوات والمجموعات

**▾ الإعدادات الحالية:**
◂ الكليشة: {}
◂ الفاصل الزمني: {} دقيقة
◂ حالة النشر: {}
◂ الوقت المتبقي: {}

**▾ الإحصائيات:**
◂ عدد المنشورات: {}
◂ عدد المجموعات: {}
◂ حالة الاشتراك: {}
"""
    
    def load_data(self, filename):
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {filename}: {e}")
        return {}
    
    def save_data(self, data, filename):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")
    
    def get_user_file(self, user_id):
        return os.path.join(SETTINGS_DIR, f"{user_id}.json")
    
    def load_user_settings(self, user_id):
        user_file = self.get_user_file(user_id)
        try:
            if os.path.exists(user_file):
                with open(user_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading user settings for {user_id}: {e}")
        return {
            'message': 'لم يتم تعيين كليشة بعد',
            'interval': 5,
            'is_posting': False,
            'posts_count': 0,
            'groups_count': 0,
            'subscription_expiry': None,
            'session_string': None
        }
    
    def save_user_settings(self, user_id, settings):
        user_file = self.get_user_file(user_id)
        try:
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Error saving user settings for {user_id}: {e}")
    
    async def start(self):
        self.bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)
        
        # تعريف الأحداث
        @self.bot.on(events.NewMessage(pattern='/start'))
        async def start_handler(event):
            user_id = event.sender_id
            if user_id not in self.user_data:
                self.user_data[user_id] = {
                    'username': event.sender.username,
                    'first_name': event.sender.first_name,
                    'last_name': event.sender.last_name,
                    'registered_at': datetime.now().isoformat(),
                    'is_banned': False
                }
                self.save_data(self.user_data, USERS_FILE)
                
                # إرسال إشعار للمدير
                for admin_id in ADMIN_IDS:
                    try:
                        await self.bot.send_message(
                            admin_id,
                            f"👤 مستخدم جديد\n\n"
                            f"🆔: {user_id}\n"
                            f"👤: {event.sender.first_name}\n"
                            f"📧: @{event.sender.username}\n"
                            f"📅: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                        )
                    except Exception as e:
                        logger.error(f"Error notifying admin: {e}")
            
            await self.show_main_menu(event)
        
        @self.bot.on(events.NewMessage(pattern='تسجيل'))
        async def register_handler(event):
            user_id = event.sender_id
            
            if self.user_data.get(user_id, {}).get('is_banned', False):
                await event.reply("❌ تم حظرك من استخدام البوت.")
                return
            
            settings = self.load_user_settings(user_id)
            
            # التحقق من الاشتراك
            if not await self.check_subscription(user_id, event):
                return
            
            if settings.get('session_string'):
                await event.reply("✅ لديك جلسة نشطة بالفعل.")
                return
            
            async with self.bot.conversation(event.chat_id) as conv:
                await conv.send_message("📱 يرجى إدخال رقم هاتفك (مع رمز الدولة):")
                phone_response = await conv.get_response()
                phone = phone_response.text.strip()
                
                try:
                    client = TelegramClient(StringSession(), API_ID, API_HASH)
                    await client.connect()
                    
                    sent = await client.send_code_request(phone)
                    
                    await conv.send_message("🔑 تم إرسال كود التحقق، يرجى إدخاله:")
                    code_response = await conv.get_response()
                    code = code_response.text.strip()
                    
                    await client.sign_in(phone, code)
                    
                    # حفظ جلسة المستخدم
                    session_string = client.session.save()
                    settings['session_string'] = session_string
                    self.save_user_settings(user_id, settings)
                    
                    await conv.send_message("✅ تم تسجيل الجلسة بنجاح!")
                    await client.disconnect()
                    
                except Exception as e:
                    await conv.send_message(f"❌ حدث خطأ: {str(e)}")
        
        @self.bot.on(events.NewMessage(pattern='تعيين الكليشة'))
        async def set_message_handler(event):
            user_id = event.sender_id
            
            if self.user_data.get(user_id, {}).get('is_banned', False):
                await event.reply("❌ تم حظرك من استخدام البوت.")
                return
            
            settings = self.load_user_settings(user_id)
            
            # التحقق من الاشتراك
            if not await self.check_subscription(user_id, event):
                return
            
            async with self.bot.conversation(event.chat_id) as conv:
                await conv.send_message("📝 يرجى إرسال الكليشة النصية:")
                message_response = await conv.get_response()
                
                # التحقق من أن الرسالة نصية فقط
                if message_response.media or any(entity for entity in (message_response.entities or []) 
                   if isinstance(entity, MessageEntityMentionName)):
                    await conv.send_message("❌ غير مسموح بإرفاق الوسائط أو الروابط.")
                    return
                
                settings['message'] = message_response.text
                self.save_user_settings(user_id, settings)
                
                await conv.send_message("✅ تم حفظ الكليشة بنجاح!")
        
        @self.bot.on(events.NewMessage(pattern='تعيين الفاصل'))
        async def set_interval_handler(event):
            user_id = event.sender_id
            
            if self.user_data.get(user_id, {}).get('is_banned', False):
                await event.reply("❌ تم حظرك من استخدام البوت.")
                return
            
            settings = self.load_user_settings(user_id)
            
            # التحقق من الاشتراك
            if not await self.check_subscription(user_id, event):
                return
            
            async with self.bot.conversation(event.chat_id) as conv:
                await conv.send_message("⏰ يرجى إدخال الفاصل الزمني بين المنشورات (بالدقائق، الحد الأدنى 5 دقائق):")
                interval_response = await conv.get_response()
                
                try:
                    interval = max(5, int(interval_response.text.strip()))
                    settings['interval'] = interval
                    self.save_user_settings(user_id, settings)
                    
                    await conv.send_message(f"✅ تم تعيين الفاصل الزمني إلى {interval} دقائق!")
                except ValueError:
                    await conv.send_message("❌ يرجى إدخال رقم صحيح.")
        
        @self.bot.on(events.NewMessage(pattern='تشغيل'))
        async def start_posting_handler(event):
            user_id = event.sender_id
            
            if self.user_data.get(user_id, {}).get('is_banned', False):
                await event.reply("❌ تم حظرك من استخدام البوت.")
                return
            
            settings = self.load_user_settings(user_id)
            
            # التحقق من الاشتراك
            if not await self.check_subscription(user_id, event):
                return
            
            if not settings.get('session_string'):
                await event.reply("❌ لم تقم بتسجيل جلسة بعد. استخدم زر 'تسجيل' أولاً.")
                return
            
            if not settings.get('message') or settings.get('message') == 'لم يتم تعيين كليشة بعد':
                await event.reply("❌ لم تقم بتعيين كليشة بعد. استخدم زر 'تعيين الكليشة' أولاً.")
                return
            
            if settings.get('is_posting'):
                await event.reply("✅ النشر يعمل بالفعل!")
                return
            
            # بدء النشر
            settings['is_posting'] = True
            self.save_user_settings(user_id, settings)
            
            # إنشاء مهمة النشر
            self.posting_tasks[user_id] = asyncio.create_task(self.posting_loop(user_id))
            
            await event.reply("✅ تم بدء النشر التلقائي!")
            
            # إرسال إشعار للمدير
            for admin_id in ADMIN_IDS:
                try:
                    await self.bot.send_message(
                        admin_id,
                        f"▶️ بدأ المستخدم النشر\n\n"
                        f"🆔: {user_id}\n"
                        f"👤: {self.user_data[user_id].get('first_name', 'غير معروف')}\n"
                        f"📅: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    )
                except Exception as e:
                    logger.error(f"Error notifying admin: {e}")
        
        @self.bot.on(events.NewMessage(pattern='إيقاف'))
        async def stop_posting_handler(event):
            user_id = event.sender_id
            
            if self.user_data.get(user_id, {}).get('is_banned', False):
                await event.reply("❌ تم حظرك من استخدام البوت.")
                return
            
            settings = self.load_user_settings(user_id)
            
            if not settings.get('is_posting'):
                await event.reply("❌ النشر ليس نشطاً حالياً.")
                return
            
            # إيقاف النشر
            settings['is_posting'] = False
            self.save_user_settings(user_id, settings)
            
            if user_id in self.posting_tasks:
                self.posting_tasks[user_id].cancel()
                del self.posting_tasks[user_id]
            
            await event.reply("⏹️ تم إيقاف النشر التلقائي!")
            
            # إرسال إشعار للمدير
            for admin_id in ADMIN_IDS:
                try:
                    await self.bot.send_message(
                        admin_id,
                        f"⏹️ أوقف المستخدم النشر\n\n"
                        f"🆔: {user_id}\n"
                        f"👤: {self.user_data[user_id].get('first_name', 'غير معروف')}\n"
                        f"📅: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                    )
                except Exception as e:
                    logger.error(f"Error notifying admin: {e}")
        
        @self.bot.on(events.NewMessage(pattern='إعداد الحساب'))
        async def account_settings_handler(event):
            user_id = event.sender_id
            
            if self.user_data.get(user_id, {}).get('is_banned', False):
                await event.reply("❌ تم حظرك من استخدام البوت.")
                return
            
            # التحقق من الاشتراك
            if not await self.check_subscription(user_id, event):
                return
            
            buttons = [
                [
                    Button.inline("تغيير الكليشة", b"change_message"),
                    Button.inline("تغيير الفاصل", b"change_interval")
                ],
                [Button.inline("حذف الحساب", b"delete_account")],
                [Button.inline("رجوع", b"back_to_main")]
            ]
            
            await event.reply("⚙️ **إعدادات الحساب:**", buttons=buttons)
        
        @self.bot.on(events.NewMessage(pattern='تسجيل الخروج'))
        async def logout_handler(event):
            user_id = event.sender_id
            
            if self.user_data.get(user_id, {}).get('is_banned', False):
                await event.reply("❌ تم حظرك من استخدام البوت.")
                return
            
            settings = self.load_user_settings(user_id)
            
            # إيقاف النشر إذا كان نشطاً
            if settings.get('is_posting'):
                settings['is_posting'] = False
                if user_id in self.posting_tasks:
                    self.posting_tasks[user_id].cancel()
                    del self.posting_tasks[user_id]
            
            # حذف جلسة المستخدم
            settings['session_string'] = None
            self.save_user_settings(user_id, settings)
            
            await event.reply("✅ تم تسجيل الخروج بنجاح! يمكنك العودة في أي وقت بإدخال كود التفعيل مرة أخرى.")
        
        @self.bot.on(events.NewMessage(pattern='إحصائيات'))
        async def stats_handler(event):
            user_id = event.sender_id
            
            if self.user_data.get(user_id, {}).get('is_banned', False):
                await event.reply("❌ تم حظرك من استخدام البوت.")
                return
            
            settings = self.load_user_settings(user_id)
            
            # التحقق من الاشتراك
            if not await self.check_subscription(user_id, event):
                return
            
            # حساب الوقت المتبقي للنشر القادم
            next_post = "غير نشط"
            if settings.get('is_posting'):
                next_post = f"{settings.get('interval', 5)} دقائق"
            
            # حساب حالة الاشتراك
            subscription_status = "غير مفعل"
            if settings.get('subscription_expiry'):
                expiry_date = datetime.fromisoformat(settings['subscription_expiry'])
                if expiry_date > datetime.now():
                    subscription_status = f"نشط حتى {expiry_date.strftime('%Y-%m-%d')}"
                else:
                    subscription_status = "منتهي الصلاحية"
            
            stats_text = self.main_menu_text.format(
                settings.get('message', 'لم يتم تعيين'),
                settings.get('interval', 5),
                "نشط" if settings.get('is_posting') else "متوقف",
                next_post,
                settings.get('posts_count', 0),
                settings.get('groups_count', 0),
                subscription_status
            )
            
            await event.reply(stats_text)
        
        # معالجة أحداث الزر للادمن
        @self.bot.on(events.NewMessage(pattern='/admin'))
        async def admin_handler(event):
            user_id = event.sender_id
            
            if user_id not in ADMIN_IDS:
                await event.reply("❌ ليس لديك صلاحية الدخول إلى这部分.")
                return
            
            buttons = [
                [Button.inline("إنشاء كود تفعيل", b"generate_code")],
                [Button.inline("حظر مستخدم", b"ban_user")],
                [Button.inline("رفع حظر مستخدم", b"unban_user")],
                [Button.inline("حذف حساب مستخدم", b"delete_user")],
                [Button.inline("إرسال إشعار عام", b"broadcast")],
                [Button.inline("إحصائيات المدير", b"admin_stats")]
            ]
            
            await event.reply("🛠️ **لوحة تحكم المدير:**", buttons=buttons)
        
        # بدء تشغيل البوت
        logger.info("Starting bot...")
        await self.bot.run_until_disconnected()
    
    async def check_subscription(self, user_id, event):
        settings = self.load_user_settings(user_id)
        
        if settings.get('subscription_expiry'):
            expiry_date = datetime.fromisoformat(settings['subscription_expiry'])
            if expiry_date > datetime.now():
                return True
            else:
                await event.reply("❌ انتهت صلاحية اشتراكك. يرجى التواصل مع المدير لتجديده.")
                return False
        
        # إذا لم يكن هناك اشتراك، اطلب كود التفعيل
        async with self.bot.conversation(event.chat_id) as conv:
            await conv.send_message("🔑 لم يتم تفعيل اشتراكك. يرجى إدخال كود التفعيل:")
            code_response = await conv.get_response()
            code = code_response.text.strip()
            
            if code in self.codes_data and not self.codes_data[code].get('used', False):
                # تفعيل الكود
                self.codes_data[code]['used'] = True
                self.codes_data[code]['used_by'] = user_id
                self.codes_data[code]['used_at'] = datetime.now().isoformat()
                
                # تعيين تاريخ انتهاء الصلاحية (شهر من الآن)
                expiry_date = datetime.now() + timedelta(days=30)
                settings['subscription_expiry'] = expiry_date.isoformat()
                self.save_user_settings(user_id, settings)
                
                self.save_data(self.codes_data, CODES_FILE)
                
                await conv.send_message("✅ تم تفعيل الاشتراك بنجاح! صلاحية الاشتراك شهر من اليوم.")
                
                # إرسال إشعار للمدير
                for admin_id in ADMIN_IDS:
                    try:
                        await self.bot.send_message(
                            admin_id,
                            f"✅ تم تفعيل كود اشتراك\n\n"
                            f"🆔 المستخدم: {user_id}\n"
                            f"👤 الاسم: {self.user_data[user_id].get('first_name', 'غير معروف')}\n"
                            f"🔑 الكود: {code}\n"
                            f"📅 الانتهاء: {expiry_date.strftime('%Y-%m-%d')}"
                        )
                    except Exception as e:
                        logger.error(f"Error notifying admin: {e}")
                
                return True
            else:
                await conv.send_message("❌ كود التفعيل غير صالح أو مستخدم already.")
                return False
    
    async def show_main_menu(self, event):
        user_id = event.sender_id
        
        if self.user_data.get(user_id, {}).get('is_banned', False):
            await event.reply("❌ تم حظرك من استخدام البوت.")
            return
        
        settings = self.load_user_settings(user_id)
        
        # التحقق من الاشتراك
        if not await self.check_subscription(user_id, event):
            return
        
        # حساب الوقت المتبقي للنشر القادم
        next_post = "غير نشط"
        if settings.get('is_posting'):
            next_post = f"{settings.get('interval', 5)} دقائق"
        
        # حساب حالة الاشتراك
        subscription_status = "غير مفعل"
        if settings.get('subscription_expiry'):
            expiry_date = datetime.fromisoformat(settings['subscription_expiry'])
            if expiry_date > datetime.now():
                subscription_status = f"نشط حتى {expiry_date.strftime('%Y-%m-%d')}"
            else:
                subscription_status = "منتهي الصلاحية"
        
        menu_text = self.main_menu_text.format(
            settings.get('message', 'لم يتم تعيين'),
            settings.get('interval', 5),
            "نشط" if settings.get('is_posting') else "متوقف",
            next_post,
            settings.get('posts_count', 0),
            settings.get('groups_count', 0),
            subscription_status
        )
        
        buttons = [
            [Button.inline("تسجيل", b"register"), Button.inline("تعيين الكليشة", b"set_message")],
            [Button.inline("تعيين الفاصل", b"set_interval"), Button.inline("تشغيل", b"start_posting")],
            [Button.inline("إيقاف", b"stop_posting"), Button.inline("إعداد الحساب", b"account_settings")],
            [Button.inline("تسجيل الخروج", b"logout"), Button.inline("إحصائيات", b"stats")]
        ]
        
        await event.reply(menu_text, buttons=buttons)
    
    async def posting_loop(self, user_id):
        settings = self.load_user_settings(user_id)
        
        if not settings.get('session_string'):
            return
        
        # إنشاء عميل للمستخدم
        client = TelegramClient(
            StringSession(settings['session_string']),
            API_ID,
            API_HASH
        )
        
        await client.start()
        
        try:
            while settings.get('is_posting', False):
                # الحصول على الدردشات (قنوات ومجموعات)
                dialogs = await client.get_dialogs()
                
                groups = []
                for dialog in dialogs:
                    if dialog.is_group or dialog.is_channel:
                        # استبعاد الدردشات الخاصة والمحظورة
                        if not dialog.entity.broadcast and not getattr(dialog.entity, 'restricted', False):
                            groups.append(dialog.entity)
                
                # تحديث عدد المجموعات
                settings['groups_count'] = len(groups)
                self.save_user_settings(user_id, settings)
                
                # إرسال الرسالة إلى جميع المجموعات
                for group in groups:
                    try:
                        await client.send_message(group.id, settings['message'])
                        settings['posts_count'] += 1
                        self.save_user_settings(user_id, settings)
                        
                        # تأخير قصير بين الرسائل
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.error(f"Error posting to group {group.id}: {e}")
                
                # الانتظار للفاصل الزمني المحدد
                interval_minutes = settings.get('interval', 5)
                for i in range(interval_minutes * 60):
                    if not settings.get('is_posting', False):
                        break
                    await asyncio.sleep(1)
                
                # إعادة تحميل الإعدادات في كل دورة
                settings = self.load_user_settings(user_id)
        
        except Exception as e:
            logger.error(f"Error in posting loop for user {user_id}: {e}")
        finally:
            await client.disconnect()
    
    async def generate_code(self, event):
        # إنشاء كود تفعيل عشوائي
        import random
        import string
        
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        # حفظ الكود
        self.codes_data[code] = {
            'created_at': datetime.now().isoformat(),
            'created_by': event.sender_id,
            'used': False
        }
        
        self.save_data(self.codes_data, CODES_FILE)
        
        await event.reply(f"✅ تم إنشاء كود التفعيل:\n`{code}`\n\nصلاحية الكود: 30 يومًا من first use.")
    
    async def send_admin_stats(self, event):
        active_users = 0
        total_posts = 0
        active_subscriptions = 0
        
        for user_id in self.user_data:
            if self.user_data[user_id].get('is_banned', False):
                continue
            
            settings = self.load_user_settings(user_id)
            
            if settings.get('subscription_expiry'):
                expiry_date = datetime.fromisoformat(settings['subscription_expiry'])
                if expiry_date > datetime.now():
                    active_subscriptions += 1
            
            if settings.get('is_posting', False):
                active_users += 1
            
            total_posts += settings.get('posts_count', 0)
        
        stats_text = f"""
📊 **إحصائيات المدير:**

👥 المستخدمون المسجلون: {len(self.user_data)}
👤 المستخدمون النشطون: {active_users}
📤 إجمالي المنشورات: {total_posts}
🔑 الاشتراكات النشطة: {active_subscriptions}
🔄 الأكواد المتاحة: {len([c for c in self.codes_data if not self.codes_data[c].get('used', False)])}
        """
        
        await event.reply(stats_text)

# تشغيل البوت
if __name__ == '__main__':
    bot = TelegramAutoPostBot()
    asyncio.run(bot.start())
