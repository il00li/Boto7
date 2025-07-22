import os
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ====== CONFIG ======
BOT_TOKEN = '7968375518:AAGvEZbkoL_O1jQ2bWEL8n7bB9sx81uN__E'
CHANNEL_USERNAME = '@crazys7'
PIXABAY_API_KEY = '51444506-bffefcaf12816bd85a20222d1'
WEBHOOK_URL = 'https://boto7-r0c1.onrender.com'
PORT = int(os.environ.get('PORT', '8443'))

# ====== STATE ======
user_states = {}

# ====== LOGGING ======
logging.basicConfig(level=logging.INFO)

# ====== HELPERS ======
def check_subscription(member_status):
    return member_status.status in ['member', 'administrator', 'creator']

def fetch_pixabay_images(query):
    url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&image_type=photo&per_page=30"
    res = requests.get(url).json()
    hits = res.get('hits', [])
    return [hit['webformatURL'] for hit in hits if 'webformatURL' in hit]

# ====== HANDLERS ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
    if not check_subscription(member):
        keyboard = [[InlineKeyboardButton("✅ اشتركت", callback_data="check_subscription")]]
        await update.message.reply_text("🔒 يجب الاشتراك بالقناة أولًا:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        user_states[user_id] = {'step': 'ready'}
        keyboard = [[InlineKeyboardButton("📍 بدء البحث", callback_data="start_search")]]
        await update.message.reply_text("✅ تم التحقق من الاشتراك.\nاضغط للبدء:", reply_markup=InlineKeyboardMarkup(keyboard))

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
    if check_subscription(member):
        user_states[user_id] = {'step': 'ready'}
        keyboard = [[InlineKeyboardButton("📍 بدء البحث", callback_data="start_search")]]
        await query.edit_message_text("✅ تم التحقق، اضغط للبدء.", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await query.edit_message_text("❌ لم يتم الاشتراك بعد.\nيرجى الاشتراك وإعادة المحاولة.")

async def start_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_states[query.from_user.id] = {'step': 'waiting_keyword'}
    await query.edit_message_text("📝 أرسل الكلمة المفتاحية الآن للبحث في Pixabay:")

async def handle_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_states.get(user_id, {}).get('step') != 'waiting_keyword':
        return
    keyword = update.message.text
    results = fetch_pixabay_images(keyword)
    if not results:
        await update.message.reply_text("❌ لم يتم العثور على نتائج.")
        return
    user_states[user_id] = {'step': 'browsing', 'results': results, 'index': 0}
    await send_result(update, context, user_id)

async def send_result(update_or_query, context, user_id):
    state = user_states[user_id]
    img = state['results'][state['index']]
    caption = f"📷 نتيجة {state['index']+1} من {len(state['results'])}"
    keyboard = [
        [InlineKeyboardButton("⏮️ السابق", callback_data="prev"),
         InlineKeyboardButton("⏭️ التالي", callback_data="next")],
        [InlineKeyboardButton("✅ اختيار", callback_data="select")]
    ]
    if isinstance(update_or_query, Update):
        await context.bot.send_photo(chat_id=user_id, photo=img, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update_or_query.edit_message_media(media=InputMediaPhoto(img, caption=caption), reply_markup=InlineKeyboardMarkup(keyboard))

async def navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    state = user_states.get(user_id, {})
    if state.get('step') != 'browsing':
        return
    if query.data == 'next':
        state['index'] = (state['index'] + 1) % len(state['results'])
    elif query.data == 'prev':
        state['index'] = (state['index'] - 1) % len(state['results'])
    elif query.data == 'select':
        user_states[user_id] = {'step': 'selected'}
        await query.edit_message_caption("✅ تم اختيار الصورة. أرسل /start لبحث جديد.")
        return
    await send_result(query, context, user_id)

# ====== MAIN ======
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler('start', start))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern='check_subscription'))
    app.add_handler(CallbackQueryHandler(start_search_callback, pattern='start_search'))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_keyword))
    app.add_handler(CallbackQueryHandler(navigation_callback, pattern='^(next|prev|select)$'))

    requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
        data={"url": f"{WEBHOOK_URL}/{BOT_TOKEN}", "drop_pending_updates": True}
    )

    app.run_webhook(
        listen='0.0.0.0',
        port=PORT,
        url_path=BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
    )

if __name__ == '__main__':
    main()
