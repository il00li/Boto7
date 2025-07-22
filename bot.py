import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ====== CONFIG ======
BOT_TOKEN = '7968375518:AAGvEZbkoL_O1jQ2bWEL8n7bB9sx81uN__E'
CHANNEL_USERNAME = '@crazys7'
FREEPIK_API_KEY = 'FPSXd1183dea1da3476a90735318b3930ba3'
WEBHOOK_URL = 'https://boto7-r0c1.onrender.com'

# ====== STATE MANAGEMENT ======
user_states = {}

# ====== LOGGING ======
logging.basicConfig(level=logging.INFO)

# ====== UTILS ======
def check_subscription(member_status):
    return member_status.status in ['member', 'administrator', 'creator']

def fetch_freepik_results(query):
    url = f'https://api.freepik.com/v2/search?query={query}&limit=30'
    headers = {'Authorization': f'Bearer {FREEPIK_API_KEY}'}
    res = requests.get(url, headers=headers).json()
    return res.get('data', [])

# ====== HANDLERS ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)

    if not check_subscription(chat_member):
        keyboard = [[InlineKeyboardButton("✅ اشتركت", callback_data="check_subscription")]]
        await update.message.reply_text("🔒 يجب الاشتراك بالقناة أولًا:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        user_states[user_id] = {'step': 'ready'}
        keyboard = [[InlineKeyboardButton("📍 بدء البحث", callback_data="start_search")]]
        await update.message.reply_text("✅ تم التحقق من الاشتراك.\nاضغط للبدء:", reply_markup=InlineKeyboardMarkup(keyboard))

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    chat_member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
    if check_subscription(chat_member):
        user_states[user_id] = {'step': 'ready'}
        keyboard = [[InlineKeyboardButton("📍 بدء البحث", callback_data="start_search")]]
        await query.edit_message_text("✅ تم التحقق، اضغط للبدء.", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text("❌ لم يتم الاشتراك بعد.\nيرجى الاشتراك وإعادة المحاولة.")

async def start_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    user_states[user_id] = {'step': 'waiting_keyword'}
    await query.answer()
    await query.edit_message_text("📝 أرسل الكلمة المفتاحية الآن للبحث في Freepik:")

async def handle_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_states.get(user_id, {}).get('step') != 'waiting_keyword':
        return

    keyword = update.message.text
    results = fetch_freepik_results(keyword)

    if not results:
        await update.message.reply_text("❌ لم يتم العثور على نتائج.")
        return

    user_states[user_id] = {'step': 'browsing', 'results': results, 'index': 0}
    await send_result(update, context, user_id)

async def send_result(update_or_query, context, user_id):
    state = user_states[user_id]
    result = state['results'][state['index']]
    img_url = result['images']['thumbnail']
    caption = f"📷 نتيجة رقم {state['index']+1} من {len(state['results'])}"

    keyboard = [
        [InlineKeyboardButton("»", callback_data="prev"),
         InlineKeyboardButton("«", callback_data="next")],
        [InlineKeyboardButton("✅ اختيار", callback_data="select")]
    ]

    if isinstance(update_or_query, Update):
        await context.bot.send_photo(chat_id=user_id, photo=img_url, caption=caption,
                                     reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update_or_query.edit_message_media(
            media=InputMediaPhoto(media=img_url, caption=caption),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    state = user_states.get(user_id)

    if not state or state.get('step') != 'browsing':
        return

    await query.answer()

    if query.data == 'next':
        state['index'] = (state['index'] + 1) % len(state['results'])
    elif query.data == 'prev':
        state['index'] = (state['index'] - 1) % len(state['results'])
    elif query.data == 'select':
        user_states[user_id] = {'step': 'selected'}
        await query.edit_message_caption(caption="✅ تم اختيار الصورة. أرسل /start لبحث جديد.")
        return

    await send_result(query, context, user_id)

# ====== MAIN ======
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).webhook_url(WEBHOOK_URL).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern='check_subscription'))
    app.add_handler(CallbackQueryHandler(start_search_callback, pattern='start_search'))
    app.add_handler(MessageHandler(filters.TEXT, handle_keyword))
    app.add_handler(CallbackQueryHandler(navigation_callback, pattern='^(next|prev|select)$'))

    app.run_webhook()

if __name__ == '__main__':
    main()
