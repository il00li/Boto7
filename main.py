import telebot
from telebot.types import ReplyKeyboardRemove
from config import BOT_TOKEN, ADMIN_USER_ID, CHANNEL_USERNAME
import handlers
import utils

bot = telebot.TeleBot(BOT_TOKEN)

# متغيرات البحث
user_search_data = {}

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # التحقق من المرجع إذا كان موجودًا
    if len(message.text.split()) > 1:
        ref_code = message.text.split()[1]
        if ref_code.startswith('ref_'):
            utils.add_invited_user(ref_code, user_id)
    
    # التحقق من الاشتراك في القناة
    if not handlers.check_subscription(bot, user_id):
        text, markup = handlers.subscription_message()
        bot.send_message(chat_id, text, reply_markup=markup)
    else:
        text, markup = handlers.main_menu()
        bot.send_message(chat_id, text, reply_markup=markup)

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text
    
    # التحقق من الاشتراك أولاً
    if not handlers.check_subscription(bot, user_id):
        text_msg, markup = handlers.subscription_message()
        bot.send_message(chat_id, text_msg, reply_markup=markup)
        return
    
    if text == "نوع البحث 🍇":
        text_msg, markup = handlers.search_type_menu()
        bot.send_message(chat_id, text_msg, reply_markup=markup)
    
    elif text == "بدء البحث 🫐":
        if not utils.check_membership(user_id):
            text_msg, markup, admin_msg = handlers.no_membership_message(user_id)
            bot.send_message(chat_id, text_msg, reply_markup=markup)
            
            # إرسال رسالة إلى المدير
            bot.send_message(ADMIN_USER_ID, admin_msg)
        else:
            bot.send_message(chat_id, "أدخل كلمة البحث:", reply_markup=ReplyKeyboardRemove())
            bot.register_next_step_handler(message, process_search_query)
    
    elif user_id in user_search_data and 'waiting_for_query' in user_search_data[user_id]:
        process_search_query(message)

def process_search_query(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    query = message.text
    
    if user_id not in user_search_data:
        return
    
    search_type = user_search_data[user_id]['type']
    
    if search_type in ["photo", "illustration"]:
        results = handlers.search_unsplash(query, search_type)
    else:  # video
        results = handlers.search_pixabay_videos(query)
    
    if not results:
        bot.send_message(chat_id, "لم يتم العثور على نتائج للبحث المطلوب.")
        return
    
    user_search_data[user_id] = {
        'results': results,
        'query': query,
        'type': search_type,
        'current_index': 0
    }
    
    show_search_result(user_id, chat_id, 0)

def show_search_result(user_id, chat_id, index):
    if user_id not in user_search_data:
        return
    
    data = user_search_data[user_id]
    results = data['results']
    
    if index >= len(results):
        return
    
    result = results[index]
    media_url, caption = handlers.format_result(result, data['type'], data['query'], index)
    
    markup = handlers.create_results_navigation(index, len(results), data['type'], data['query'])
    
    if data['type'] in ["photo", "illustration"]:
        bot.send_photo(chat_id, media_url, caption=caption, reply_markup=markup)
    else:  # video
        bot.send_video(chat_id, media_url, caption=caption, reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    data = call.data
    
    # التحقق من الاشتراك أولاً
    if not handlers.check_subscription(bot, user_id):
        text_msg, markup = handlers.subscription_message()
        bot.edit_message_text(text_msg, chat_id, call.message.message_id, reply_markup=markup)
        return
    
    if data == "check_subscription":
        if handlers.check_subscription(bot, user_id):
            text_msg, markup = handlers.main_menu()
            bot.edit_message_text(text_msg, chat_id, call.message.message_id, reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "لم تشترك في القناة بعد!")
    
    elif data == "free_membership":
        invite_link = utils.generate_invite_link(user_id)
        bot.send_message(chat_id, f"ادعُ 10 أصدقاء للحصول على عضوية مجانية.\nرابط الدعوة: {invite_link}")
    
    elif data == "back_main":
        text_msg, markup = handlers.main_menu()
        bot.edit_message_text(text_msg, chat_id, call.message.message_id, reply_markup=markup)
    
    elif data.startswith(("search_photo", "search_illustration", "search_video")):
        search_type = data.split("_")[1]
        user_search_data[user_id] = {
            'type': search_type,
            'waiting_for_query': True
        }
        bot.send_message(chat_id, "أدخل كلمة البحث:", reply_markup=ReplyKeyboardRemove())
        bot.delete_message(chat_id, call.message.message_id)
    
    elif data.startswith(("prev_", "next_", "download_")):
        action_parts = data.split("_")
        action = action_parts[0]
        index = int(action_parts[1])
        search_type = action_parts[2]
        query = "_".join(action_parts[3:])
        
        if action in ["prev", "next"]:
            show_search_result(user_id, chat_id, index)
            bot.delete_message(chat_id, call.message.message_id)
        
        elif action == "download":
            # إرسال النتيجة إلى القناة بدون أزرار
            if user_id in user_search_data:
                result = user_search_data[user_id]['results'][index]
                media_url, caption = handlers.format_result(result, search_type, query, index)
                
                if search_type in ["photo", "illustration"]:
                    bot.send_photo(CHANNEL_USERNAME, media_url, caption=caption)
                else:  # video
                    bot.send_video(CHANNEL_USERNAME, media_url, caption=caption)
                
                bot.answer_callback_query(call.id, "تم الإرسال إلى القناة!")

# أوامر المدير
@bot.message_handler(commands=['ban', 'unban', 'activate', 'deactivate', 'broadcast'])
def handle_admin_commands(message):
    user_id = message.from_user.id
    
    if user_id != ADMIN_USER_ID:
        bot.reply_to(message, "ليس لديك صلاحية للوصول إلى هذه الأوامر.")
        return
    
    command = message.text.split()[0]
    parts = message.text.split()
    
    if len(parts) < 2 and command != '/broadcast':
        bot.reply_to(message, "استخدام خاطئ. يرجى تقديم معرّف المستخدم.")
        return
    
    if command == '/ban':
        target_id = int(parts[1])
        db = utils.load_database()
        if str(target_id) not in db['banned']:
            db['banned'].append(str(target_id))
            utils.save_database(db)
            bot.reply_to(message, f"تم حظر المستخدم {target_id}.")
        else:
            bot.reply_to(message, f"المستخدم {target_id} محظور بالفعل.")
    
    elif command == '/unban':
        target_id = int(parts[1])
        db = utils.load_database()
        if str(target_id) in db['banned']:
            db['banned'].remove(str(target_id))
            utils.save_database(db)
            bot.reply_to(message, f"تم إلغاء حظر المستخدم {target_id}.")
        else:
            bot.reply_to(message, f"المستخدم {target_id} غير محظور.")
    
    elif command == '/activate':
        target_id = int(parts[1])
        utils.activate_membership(target_id)
        bot.reply_to(message, f"تم تفعيل العضوية للمستخدم {target_id}.")
    
    elif command == '/deactivate':
        target_id = int(parts[1])
        db = utils.load_database()
        if str(target_id) in db['memberships']:
            del db['memberships'][str(target_id)]
            utils.save_database(db)
            bot.reply_to(message, f"تم إلغاء تفعيل العضوية للمستخدم {target_id}.")
        else:
            bot.reply_to(message, f"لم يكن للمستخدم {target_id} عضوية مفعلة.")
    
    elif command == '/broadcast':
        if len(parts) < 2:
            bot.reply_to(message, "يرجى تقديم رسالة للبث.")
            return
        
        broadcast_message = " ".join(parts[1:])
        db = utils.load_database()
        
        # إرسال الرسالة لجميع المستخدمين
        for user in db['users']:
            try:
                bot.send_message(user, f"إشعار من الإدارة:\n\n{broadcast_message}")
            except:
                continue
        
        bot.reply_to(message, "تم إرسال الرسالة إلى جميع المستخدمين.")

if __name__ == "__main__":
    print("Bot is running...")
    bot.infinity_polling()
