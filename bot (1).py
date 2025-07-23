import os
import logging
import requests
import io
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
FREEPIK_API_KEY = 'YOUR_FREEPIK_API_KEY'  # ضع هنا مفتاح Freepik API الخاص بك
WEBHOOK_URL = 'https://boto7-r0c1.onrender.com'
PORT = int(os.environ.get('PORT', '8443'))

# ====== STATE ======
user_states = {}

# ====== LOGGING ======
logging.basicConfig(level=logging.INFO)

# ====== HELPERS ======
def check_subscription(member_status):
    return member_status.status in ['member', 'administrator', 'creator']

def fetch_freepik_images(query):
    """
    البحث في Freepik API وجلب النتائج (صور، PSD، أيقونات...)
    التوثيق: https://developer.freepik.com/docs
    """
    url = f"https://api.freepik.com/v1/resources/search"
    params = {
        "query": query,
        "limit": 30,
        "order": "relevant"
    }
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {FREEPIK_API_KEY}",
    }
    try:
        res = requests.get(url, params=params, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json()
        # النتائج تكون في data['data']
        # كل عنصر قد يحتوي على: preview_url, title, id, etc.
        return [
            {
                "preview": item.get("preview_url"),
                "title": item.get("title", ""),
                "url": f"https://www.freepik.com{item.get('url', '')}"
            }
            for item in data.get('data', [])
            if item.get("preview_url")
        ]
    except Exception as e:
        print("Freepik API Error:", e)
        return []

def download_image(url):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return io.BytesIO(response.content)
    except Exception as e:
        print("Download error:", e)
    return None

# ====== HANDLERS ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
    if not check_subscription(member):
        kb = [[InlineKeyboardButton("✅ اشتركت", callback_data="check_subscription")]]
        await update.message.reply_text("🔒 يجب الاشتراك بالقناة أولًا:", reply_markup=InlineKeyboardMarkup(kb))
    else:
        user_states[user_id] = {'step': 'ready'}
        kb = [[InlineKeyboardButton("📍 بدء البحث", callback_data="start_search")]]
        await update.message.reply_text("✅ تم التحقق من الاشتراك.\nاضغط للبدء:", reply_markup=InlineKeyboardMarkup(kb))

async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    member = await context.bot.get_chat_member(CHANNEL_USERNAME, user_id)
    if check_subscription(member):
        user_states[user_id] = {'step': 'ready'}
        kb = [[InlineKeyboardButton("📍 بدء البحث", callback_data="start_search")]]
        await query.edit_message_text("✅ تم التحقق، اضغط للبدء.", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await query.edit_message_text("❌ لم يتم الاشتراك بعد.\nيرجى الاشتراك وإعادة المحاولة.")

async def start_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_states[query.from_user.id] = {'step': 'waiting_keyword'}
    await query.edit_message_text("📝 أرسل الكلمة المفتاحية الآن للبحث في Freepik:")

async def handle_keyword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_states.get(user_id, {}).get('step') != 'waiting_keyword':
        return
    keyword = update.message.text
    results = fetch_freepik_images(keyword)
    if not results:
        await update.message.reply_text("❌ لم يتم العثور على نتائج.\nجرب كلمات مثل: logo، icon، psd، Ramadan")
        return
    user_states[user_id] = {'step': 'browsing', 'results': results, 'index': 0}
    await send_result(update, context, user_id)

async def send_result(update_or_query, context, user_id):
    state = user_states[user_id]
    result = state['results'][state['index']]
    image_data = download_image(result['preview'])
    if not image_data:
        await context.bot.send_message(chat_id=user_id, text="❌ تعذر تحميل الصورة.")
        return

    caption = f"📷 نتيجة {state['index']+1} من {len(state['results'])}\n\n{result['title']}\n[رابط Freepik]({result['url']})"
    kb = [
        [InlineKeyboardButton("⏮️ السابق", callback_data="prev"),
         InlineKeyboardButton("⏭️ التالي", callback_data="next")],
        [InlineKeyboardButton("✅ اختيار", callback_data="select")]
    ]
    if isinstance(update_or_query, Update):
        await context.bot.send_photo(
            chat_id=user_id,
            photo=image_data,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        await update_or_query.edit_message_media(
            media=InputMediaPhoto(image_data, caption=caption, parse_mode="Markdown"),
            reply_markup=InlineKeyboardMarkup(kb)
        )

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