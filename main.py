# ========== إدارة القنوات ==========
async def check_bot_permissions(context: CallbackContext, chat_id: int) -> bool:
    """التحقق من صلاحيات البوت في القناة"""
    try:
        bot = context.bot
        chat = await bot.get_chat(chat_id)
        
        # التحقق من أن البوت مشرف
        admins = await chat.get_administrators()
        bot_admin = next((admin for admin in admins if admin.user.id == bot.id), None)
        
        if not bot_admin:
            return False
            
        # التحقق من الصلاحيات المطلوبة
        perms = bot_admin.can_post_messages and bot_admin.can_change_info
        return perms
        
    except Exception as e:
        logger.error(f"خطأ في التحقق من الصلاحيات: {e}")
        return False

async def update_channel_description(context: CallbackContext, chat_id: int, title: str):
    """تحديث وصف القناة بإضافة البوت"""
    try:
        bot = context.bot
        chat = await bot.get_chat(chat_id)
        current_desc = chat.description or ""
        bot_username = (await bot.get_me()).username
        
        # إضافة البوت إذا لم يكن موجودًا
        if f"@{bot_username}" not in current_desc:
            new_desc = f"{current_desc}\n\n@{bot_username}" if current_desc else f"@{bot_username}"
            await bot.set_chat_description(chat_id, new_desc)
            logger.info(f"تم تحديث وصف القناة {title}")
            
    except Exception as e:
        logger.error(f"خطأ في تحديث الوصف: {e}")

# ========== النشر التلقائي ==========
async def scheduled_post(context: CallbackContext):
    """نشر المحتوى المجدول"""
    try:
        channels = get_all_channels()
        now = datetime.now(TIMEZONE)
        
        for channel in channels:
            channel_id, title, schedule, next_post = channel[1:5]
            next_post = datetime.strptime(next_post, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=TIMEZONE)
            
            if now >= next_post:
                try:
                    # توليد المحتوى
                    phrase = await generate_phrase()
                    
                    # إرسال المحتوى
                    await context.bot.send_message(
                        chat_id=channel_id,
                        text=phrase
                    )
                    logger.info(f"تم النشر في قناة: {title}")
                    
                    # تحديث وقت النشر التالي
                    hours = int(schedule.split('h')[0])
                    new_next_post = now + timedelta(hours=hours)
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    cursor.execute('''
                    UPDATE channels SET next_post = ? 
                    WHERE channel_id = ?
                    ''', (new_next_post, channel_id))
                    conn.commit()
                    conn.close()
                    
                except Exception as e:
                    logger.error(f"خطأ في النشر للقناة {title}: {e}")
                    # إزالة القناة إذا لم يعد البوت موجودًا
                    try:
                        await context.bot.get_chat(channel_id)
                    except:
                        remove_channel(channel_id)
                        logger.info(f"تم إزالة القناة {title} من الجدولة")
    except Exception as e:
        logger.error(f"خطأ في جدولة النشر: {e}")

# ========== واجهة المستخدم ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البدء"""
    user = update.effective_user
    await update.message.reply_text(
        f"مرحبًا {user.first_name}!\n\n"
        "أنا بوت النشر التلقائي للعبارات العاطفية ✨\n"
        "يمكنك إضافتي إلى قناتك ثم تحديد جدول النشر:\n"
        "• كل 6 ساعات\n"
        "• كل 12 ساعة\n"
        "• كل 24 ساعة\n\n"
        "بعد إضافتي إلى قناتك، استخدم /setup لتحديد الجدول"
    )

async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إعداد الجدول الزمني"""
    user = update.effective_user
    keyboard = [
        [InlineKeyboardButton("كل 6 ساعات", callback_data='6h')],
        [InlineKeyboardButton("كل 12 ساعة", callback_data='12h')],
        [InlineKeyboardButton("كل 24 ساعة", callback_data='24h')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "⏰ اختر جدول النشر التلقائي للقناة:",
        reply_markup=reply_markup
    )

async def new_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة إضافة البوت إلى قناة جديدة"""
    bot_id = context.bot.id
    for member in update.message.new_chat_members:
        if member.id == bot_id:
            chat = update.effective_chat
            chat_id = chat.id
            title = chat.title
            
            # التحقق من الصلاحيات
            if not await check_bot_permissions(context, chat_id):
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ يلزم منحي صلاحيتين:\n1. نشر الرسائل\n2. تغيير معلومات المجموعة\n\nالرجاء تعديل الصلاحيات ثم أعد إضافتي."
                )
                await context.bot.leave_chat(chat_id)
                return
                
            # تحديث وصف القناة
            await update_channel_description(context, chat_id, title)
            
            # إرسال رسالة ترحيب
            keyboard = [[InlineKeyboardButton("تحديد جدول النشر ⏰", callback_data='setup_schedule')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ تم تفعيل البوت بنجاح في قناة {title}!\n\nالرجاء تحديد جدول النشر:",
                reply_markup=reply_markup
    )
# ========== معالجة الأزرار ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغطات الأزرار"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    
    # تحديد الجدول الزمني
    if query.data in ['6h', '12h', '24h']:
        channel = get_channel(chat_id)
        
        if not channel:
            # إذا كانت القناة غير مسجلة
            next_post = add_channel(chat_id, query.message.chat.title, query.data)
            await query.edit_message_text(
                text=f"⏰ تم تعيين جدول النشر: كل {query.data}\n\n"
                     f"⏳ أول منشور سيكون في: {next_post.strftime('%Y-%m-%d %H:%M')}",
                reply_markup=None
            )
        else:
            # تحديث الجدول الزمني
            next_post = update_schedule(chat_id, query.data)
            await query.edit_message_text(
                text=f"🔄 تم تحديث جدول النشر: كل {query.data}\n\n"
                     f"⏳ المنشور التالي في: {next_post.strftime('%Y-%m-%d %H:%M')}",
                reply_markup=None
            )
    
    # طلب تحديد الجدول الزمني
    elif query.data == 'setup_schedule':
        keyboard = [
            [InlineKeyboardButton("كل 6 ساعات", callback_data='6h')],
            [InlineKeyboardButton("كل 12 ساعة", callback_data='12h')],
            [InlineKeyboardButton("كل 24 ساعة", callback_data='24h')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text="⏰ اختر جدول النشر التلقائي للقناة:",
            reply_markup=reply_markup
        )
    
    # إيقاف النشر
    elif query.data == 'stop_schedule':
        remove_channel(chat_id)
        await query.edit_message_text(
            text="⛔ تم إيقاف النشر التلقائي في هذه القناة",
            reply_markup=None
        )

# ========== إدارة القنوات ==========
async def manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة القنوات"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # التحقق من أن الأمر في قناة
    if chat_id > 0:
        await update.message.reply_text("⚠️ هذا الأمر يعمل فقط في القنوات")
        return
    
    channel = get_channel(chat_id)
    
    if not channel:
        await update.message.reply_text("❌ هذه القناة غير مسجلة. استخدم /setup لتسجيلها.")
        return
    
    # عرض معلومات القناة
    _, _, title, schedule, next_post = channel
    next_post = datetime.strptime(next_post, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=TIMEZONE)
    
    keyboard = [
        [InlineKeyboardButton("تغيير الجدول الزمني", callback_data='setup_schedule')],
        [InlineKeyboardButton("إيقاف النشر التلقائي", callback_data='stop_schedule')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📋
     # ========== معالجة الأزرار ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالجة ضغطات الأزرار"""
    query = update.callback_query
    await query.answer()
    
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    
    # تحديد الجدول الزمني
    if query.data in ['6h', '12h', '24h']:
        channel = get_channel(chat_id)
        
        if not channel:
            # إذا كانت القناة غير مسجلة
            next_post = add_channel(chat_id, query.message.chat.title, query.data)
            await query.edit_message_text(
                text=f"⏰ تم تعيين جدول النشر: كل {query.data}\n\n"
                     f"⏳ أول منشور سيكون في: {next_post.strftime('%Y-%m-%d %H:%M')}",
                reply_markup=None
            )
        else:
            # تحديث الجدول الزمني
            next_post = update_schedule(chat_id, query.data)
            await query.edit_message_text(
                text=f"🔄 تم تحديث جدول النشر: كل {query.data}\n\n"
                     f"⏳ المنشور التالي في: {next_post.strftime('%Y-%m-%d %H:%M')}",
                reply_markup=None
            )
    
    # طلب تحديد الجدول الزمني
    elif query.data == 'setup_schedule':
        keyboard = [
            [InlineKeyboardButton("كل 6 ساعات", callback_data='6h')],
            [InlineKeyboardButton("كل 12 ساعة", callback_data='12h')],
            [InlineKeyboardButton("كل 24 ساعة", callback_data='24h')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            text="⏰ اختر جدول النشر التلقائي للقناة:",
            reply_markup=reply_markup
        )
    
    # إيقاف النشر
    elif query.data == 'stop_schedule':
        remove_channel(chat_id)
        await query.edit_message_text(
            text="⛔ تم إيقاف النشر التلقائي في هذه القناة",
            reply_markup=None
        )

# ========== إدارة القنوات ==========
async def manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إدارة القنوات"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # التحقق من أن الأمر في قناة
    if chat_id > 0:
        await update.message.reply_text("⚠️ هذا الأمر يعمل فقط في القنوات")
        return
    
    channel = get_channel(chat_id)
    
    if not channel:
        await update.message.reply_text("❌ هذه القناة غير مسجلة. استخدم /setup لتسجيلها.")
        return
    
    # عرض معلومات القناة
    _, _, title, schedule, next_post = channel
    next_post = datetime.strptime(next_post, '%Y-%m-%d %H:%M:%S.%f').replace(tzinfo=TIMEZONE)
    
    keyboard = [
        [InlineKeyboardButton("تغيير الجدول الزمني", callback_data='setup_schedule')],
        [InlineKeyboardButton("إيقاف النشر التلقائي", callback_data='stop_schedule')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📋 إدارة القناة: {title}\n\n"
        f"⏱️ الجدول الحالي: كل {schedule}\n"
        f"⏳ المنشور التالي: {next_post.strftime('%Y-%m-%d %H:%M')}\n\n"
        "اختر الإجراء المطلوب:",
        reply_markup=reply_markup
    )

# ========== تشغيل البوت ==========
def main():
    # تهيئة قاعدة البيانات
    init_db()
    
    # إنشاء تطبيق البوت مع JobQueue مخصص
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إنشاء JobQueue يدويًا
    job_queue = JobQueue()
    job_queue.set_application(application)
    job_queue.run_repeating(scheduled_post, interval=300, first=10)
    job_queue.start()
    
    # تسجيل الأوامر
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setup", setup))
    application.add_handler(CommandHandler("manage", manage))
    
    # معالجات الأزرار
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # معالجة إضافة البوت إلى قنوات
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_chat_members))
    
    logger.info("بدأ البوت في العمل...")
    application.run_polling()

if __name__ == "__main__":
    main()   
