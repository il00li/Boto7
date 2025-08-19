import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneNumberInvalidError
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

# قاموس لتخزين حالات المستخدمين
user_sessions = {}

# قاموس لتخزين جلسات المستخدمين النشطين
active_sessions = {}

# إيموجي للمؤشرات
EMOJI_SPINNER = ["🔄", "⏳", "📡", "⚡", "🌐", "📶"]

# دالة لعرض مؤشر التحميل
async def show_loading(message, text, edit=False):
    for emoji in EMOJI_SPINNER:
        if edit:
            await message.edit_text(f"{emoji} {text}")
        else:
            await message.reply_text(f"{emoji} {text}")
        await asyncio.sleep(0.5)

# handler لبدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = """
🌟 **مرحباً بك في بوت إدارة الجلسات!** 🌟

⚡ **المميزات:**
• إنشاء جلسات آمنة لحسابك
• إدارة حسابات متعددة
• حماية بياناتك الشخصية
• واجهة سهلة الاستخدام

🔐 **ماذا يمكنك أن تفعل؟**
- تسجيل الدخول إلى حسابك
- عرض معلومات الحساب
- إدارة الجلسات النشطة
- تسجيل الخروج الآمن

اضغط على الزر أدناه لبدء رحلة الأمان! 🚀
"""
    
    keyboard = [
        [InlineKeyboardButton("🔐 تسجيل الدخول", callback_data='login')],
        [InlineKeyboardButton("📊 معلومات الحساب", callback_data='info'),
         InlineKeyboardButton("📋 حالة الجلسة", callback_data='status')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# handler لزر Inline
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'login':
        user_id = query.from_user.id
        user_sessions[user_id] = {'step': 'phone'}
        await query.edit_message_text(
            "📱 **مرحلة تسجيل الدخول**\n\n"
            "يرجى إرسال رقم هاتفك مع رمز الدولة:\n"
            "مثال: `+201234567890` أو `+966512345678`\n\n"
            "⚠️ تأكد من صحة الرقم قبل الإرسال!",
            parse_mode='Markdown'
        )
    
    elif query.data == 'info':
        user_id = query.from_user.id
        if user_id in active_sessions:
            await me(update, context, query=query)
        else:
            await query.edit_message_text(
                "❌ **ليس لديك جلسة نشطة**\n\n"
                "يجب عليك تسجيل الدخول أولاً لعرض معلومات حسابك.",
                parse_mode='Markdown'
            )
    
    elif query.data == 'status':
        user_id = query.from_user.id
        if user_id in active_sessions:
            await query.edit_message_text(
                "✅ **حالة الجلسة:** نشطة\n\n"
                "يمكنك استخدام جميع ميزات البوت الآن! 🎉",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "❌ **حالة الجلسة:** غير نشطة\n\n"
                "اضغط على 'تسجيل الدخول' لبدء الجلسة.",
                parse_mode='Markdown'
            )

# handler لمعالجة الرسائل
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in user_sessions:
        return
    
    session_data = user_sessions[user_id]
    
    if session_data['step'] == 'phone':
        # حفظ رقم الهاتف والانتقال لخطوة الرمز
        phone_number = update.message.text.strip()
        
        # التحقق من صحة رقم الهاتف
        if not phone_number.startswith('+'):
            await update.message.reply_text(
                "❌ **رقم هاتف غير صحيح**\n\n"
                "يجب أن يبدأ رقم الهاتف بعلامة `+` متبوعة برمز الدولة.\n"
                "مثال: `+201234567890`",
                parse_mode='Markdown'
            )
            return
        
        session_data['phone'] = phone_number
        
        # إرسال رسالة الانتظار مع مؤشر
        wait_message = await update.message.reply_text("🔄 **جاري الاتصال بخوادم التلجرام...**")
        
        try:
            # إنشاء جلسة جديدة
            session = StringSession()
            client = TelegramClient(session, API_ID, API_HASH)
            
            # الاتصال وإرسال طلب الكود
            await client.connect()
            
            # عرض مؤشر التحميل
            loading_message = await update.message.reply_text("📡 **جاري إرسال طلب التحقق...**")
            await show_loading(loading_message, "**جارٍ الاتصال بحسابك...**", edit=True)
            
            # إرسال طلب الكود
            result = await client.send_code_request(phone_number)
            session_data['phone_code_hash'] = result.phone_code_hash
            session_data['client'] = client
            session_data['step'] = 'code'
            
            await loading_message.edit_text(
                "✅ **تم إرسال طلب التحقق بنجاح!**\n\n"
                "📨 **تم إرسال رمز التحقق إلى:**\n"
                f"`{phone_number}`\n\n"
                "🔢 **أرسل الرمز الذي استلمته الآن:**\n"
                "مثال: `12345`\n\n"
                "⏰ **ملاحظة:** الرمز صالح لمدة 5 دقائق فقط!",
                parse_mode='Markdown'
            )
            
        except PhoneNumberInvalidError:
            await wait_message.edit_text(
                "❌ **رقم الهاتف غير صالح**\n\n"
                "يرجى التحقق من رقم الهاتف وإعادة المحاولة.\n"
                "تأكد من إضافة رمز الدولة بشكل صحيح.",
                parse_mode='Markdown'
            )
            if user_id in user_sessions:
                del user_sessions[user_id]
            
        except Exception as e:
            error_msg = str(e)
            if "flood" in error_msg.lower():
                await wait_message.edit_text(
                    "⏰ **تم تجاوز الحد المسموح**\n\n"
                    "لقد طلبت العديد من الرموز في وقت قصير.\n"
                    "يرجى الانتظار بعض الوقت قبل المحاولة مرة أخرى.",
                    parse_mode='Markdown'
                )
            else:
                await wait_message.edit_text(
                    f"❌ **حدث خطأ غير متوقع:**\n\n`{error_msg}`\n\n"
                    "يرجى المحاولة مرة أخرى لاحقاً.",
                    parse_mode='Markdown'
                )
            if user_id in user_sessions:
                del user_sessions[user_id]
    
    elif session_data['step'] == 'code':
        # حفظ الرمز ومحاولة تسجيل الدخول
        code = update.message.text.strip()
        
        if not code.isdigit():
            await update.message.reply_text(
                "❌ **رمز تحقق غير صحيح**\n\n"
                "يجب أن يتكون رمز التحقق من أرقام فقط.\n"
                "مثال: `12345`",
                parse_mode='Markdown'
            )
            return
        
        session_data['code'] = code
        
        # عرض مؤشر التحميل
        loading_message = await update.message.reply_text("🔐 **جاري التحقق من الرمز...**")
        await show_loading(loading_message, "**جارٍ تسجيل الدخول إلى حسابك...**", edit=True)
        
        try:
            client = session_data['client']
            
            # محاولة تسجيل الدخول بالرمز
            try:
                await client.sign_in(
                    phone=session_data['phone'],
                    code=session_data['code'],
                    phone_code_hash=session_data['phone_code_hash']
                )
                
                # حفظ الجلسة النشطة
                active_sessions[user_id] = {
                    'client': client,
                    'session_string': client.session.save()
                }
                
                await loading_message.edit_text(
                    "🎉 **تم تسجيل الدخول بنجاح!**\n\n"
                    "✅ **حسابك الآن متصل بالبوت**\n\n"
                    "يمكنك الآن استخدام الأوامر التالية:\n"
                    "• `/me` - عرض معلومات الحساب\n"
                    "• `/logout` - تسجيل الخروج\n"
                    "• `/status` - حالة الجلسة\n\n"
                    "🔒 **جلستك آمنة ومشفرة**",
                    parse_mode='Markdown'
                )
                
            except SessionPasswordNeededError:
                # إذا كان الحساب محمي بكلمة مرور ثنائية
                session_data['step'] = 'password'
                await loading_message.edit_text(
                    "🔐 **حسابك محمي بكلمة مرور ثنائية**\n\n"
                    "يرجى إرسال كلمة المرور الآن:",
                    parse_mode='Markdown'
                )
                return
                
            except Exception as e:
                await loading_message.edit_text(
                    f"❌ **فشل تسجيل الدخول:**\n\n`{str(e)}`\n\n"
                    "يرجى المحاولة مرة أخرى من البداية.",
                    parse_mode='Markdown'
                )
                # تنظيف البيانات في حالة الفشل
                if user_id in user_sessions:
                    del user_sessions[user_id]
                await client.disconnect()
                return
            
            # تنظيف بيانات الجلسة المؤقتة بعد النجاح
            if user_id in user_sessions:
                del user_sessions[user_id]
            
        except Exception as e:
            await loading_message.edit_text(
                f"❌ **حدث خطأ غير متوقع:**\n\n`{str(e)}`\n\n"
                "يرجى المحاولة مرة أخرى لاحقاً.",
                parse_mode='Markdown'
            )
            # تنظيف البيانات في حالة الفشل
            if user_id in user_sessions:
                del user_sessions[user_id]
    
    elif session_data['step'] == 'password':
        # معالجة كلمة المرور الثنائية
        password = update.message.text
        
        loading_message = await update.message.reply_text("🔐 **جاري التحقق من كلمة المرور...**")
        await show_loading(loading_message, "**جارٍ تسجيل الدخول النهائي...**", edit=True)
        
        try:
            client = session_data['client']
            await client.sign_in(password=password)
            
            # حفظ الجلسة النشطة
            active_sessions[user_id] = {
                'client': client,
                'session_string': client.session.save()
            }
            
            await loading_message.edit_text(
                "🎉 **تم تسجيل الدخول بنجاح!**\n\n"
                "✅ **تم تفعيل الحماية الثنائية**\n\n"
                "حسابك الآن آمن ومتصل بالبوت بشكل كامل! 🛡️",
                parse_mode='Markdown'
            )
            
            # تنظيف بيانات الجلسة المؤقتة
            if user_id in user_sessions:
                del user_sessions[user_id]
                
        except Exception as e:
            await loading_message.edit_text(
                f"❌ **كلمة المرور غير صحيحة:**\n\n`{str(e)}`\n\n"
                "يرجى إعادة إدخال كلمة المرور الصحيحة:",
                parse_mode='Markdown'
            )

# handler لعرض معلومات الحساب
async def me(update: Update, context: ContextTypes.DEFAULT_TYPE, query=None):
    if query:
        user_id = query.from_user.id
        message = query
    else:
        user_id = update.message.from_user.id
        message = update.message
    
    if user_id not in active_sessions:
        if query:
            await query.edit_message_text("❌ ليس لديك جلسة نشطة.")
        else:
            await message.reply_text("❌ ليس لديك جلسة نشطة.")
        return
    
    try:
        loading_msg = await message.reply_text("📊 **جاري جلب معلومات الحساب...**")
        await show_loading(loading_msg, "**جارٍ تحميل البيانات...**", edit=True)
        
        client = active_sessions[user_id]['client']
        me = await client.get_me()
        
        user_info = f"""
👤 **معلومات الحساب:**

🏷️ **الاسم:** {me.first_name or 'غير محدد'}
📛 **اسم العائلة:** {me.last_name or 'غير محدد'}
🔗 **اسم المستخدم:** @{me.username or 'غير محدد'}
🆔 **ID:** `{me.id}`
📞 **رقم الهاتف:** `{me.phone or 'غير معروف'}`
✅ **م verifي:** {'نعم' if me.verified else 'لا'}
🤖 **بوت:** {'نعم' if me.bot else 'لا'}

🔐 **الجلسة نشطة ومفعلة** ✅
"""
        await loading_msg.edit_text(user_info, parse_mode='Markdown')
        
    except Exception as e:
        await loading_msg.edit_text(f"❌ حدث خطأ: {str(e)}")

# handler لإنهاء الجلسة
async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in active_sessions:
        await update.message.reply_text("❌ ليس لديك جلسة نشطة.")
        return
    
    try:
        loading_msg = await update.message.reply_text("🔒 **جاري تسجيل الخروج...**")
        await show_loading(loading_msg, "**جارٍ إنهاء الجلسة...**", edit=True)
        
        client = active_sessions[user_id]['client']
        await client.disconnect()
        del active_sessions[user_id]
        
        await loading_msg.edit_text(
            "✅ **تم تسجيل الخروج بنجاح!**\n\n"
            "🔓 **تم قطع الاتصال بحسابك بشكل آمن**\n\n"
            "يمكنك تسجيل الدخول مرة أخرى في أي وقت.",
            parse_mode='Markdown'
        )
    except Exception as e:
        await loading_msg.edit_text(f"❌ حدث خطأ أثناء تسجيل الخروج: {str(e)}")

# handler لعرض حالة الجلسة
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id in active_sessions:
        await update.message.reply_text(
            "✅ **حالة الجلسة:** نشطة 🟢\n\n"
            "يمكنك استخدام جميع ميزات البوت الآن! 🎉",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ **حالة الجلسة:** غير نشطة 🔴\n\n"
            "اضغط على 'تسجيل الدخول' لبدء الجلسة.",
            parse_mode='Markdown'
        )

# الدالة الرئيسية
def main():
    # إنشاء Application الخاص بالبوت
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("me", me))
    application.add_handler(CommandHandler("logout", logout))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # بدء البوت
    print("🤖 البوت يعمل الآن...")
    print("📍 انتظر الرسائل من المستخدمين")
    application.run_polling()

if __name__ == '__main__':
    main()
