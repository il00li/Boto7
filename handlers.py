import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import requests
from config import CHANNEL_USERNAME, ADMIN_USERNAME, ADMIN_USER_ID, PIXABAY_API_KEY, UNSPLASH_ACCESS_KEY
import utils

# متغيرات البحث
user_search_data = {}

def check_subscription(bot, user_id):
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return chat_member.status not in ['left', 'kicked']
    except:
        return False

def subscription_message():
    markup = InlineKeyboardMarkup()
    channel_btn = InlineKeyboardButton("القناة", url=f"https://t.me/{CHANNEL_USERNAME[1:]}")
    check_btn = InlineKeyboardButton("تحقق 👀", callback_data="check_subscription")
    markup.add(channel_btn, check_btn)
    return "(／。＼)ノ\nاشتراك في القناة عبر الزر بالأسفل ثم اضغط على \"تحقق 👀\"", markup

def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = KeyboardButton("نوع البحث 🍇")
    btn2 = KeyboardButton("بدء البحث 🫐")
    markup.add(btn1, btn2)
    return "(＾▽＾)／ \nاختر نوع البحث من\" نوع البحث 🍇\" وابدء البحث عبر \"بدء البحث 🫐\"\nالمطور @OlIiIl7", markup

def search_type_menu():
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton("Illustration (unsplash)", callback_data="search_illustration")
    btn2 = InlineKeyboardButton("Photo (unsplash)", callback_data="search_photo")
    btn3 = InlineKeyboardButton("Video (pixabay)", callback_data="search_video")
    back_btn = InlineKeyboardButton("رجوع 🔙", callback_data="back_main")
    markup.add(btn1)
    markup.add(btn2)
    markup.add(btn3)
    markup.add(back_btn)
    return "اختر نوع البحث:", markup

def no_membership_message(user_id):
    markup = InlineKeyboardMarkup()
    request_btn = InlineKeyboardButton("طلب الاشتراك 💌", url=f"https://t.me/{ADMIN_USERNAME[1:]}")
    free_btn = InlineKeyboardButton("اشتراك مجاني 🏖️", callback_data="free_membership")
    markup.add(request_btn, free_btn)
    
    # إرسال رسالة إلى المدير
    message = f"مستخدم جديد يطلب الاشتراك:\nID: {user_id}"
    
    return "(ง'‌-'‌)ง\nليس لديك صلاحية البحث، انقر على الزر أدناه لطلب الاشتراك", markup, message

def search_unsplash(query, search_type="photo"):
    url = "https://api.unsplash.com/search/photos"
    headers = {
        "Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"
    }
    params = {
        "query": query,
        "per_page": 10,
        "content_filter": "high"
    }
    
    if search_type == "illustration":
        params["orientation"] = "squarish"
    
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        return response.json()["results"]
    return []

def search_pixabay_videos(query):
    url = "https://pixabay.com/api/videos/"
    params = {
        "key": PIXABAY_API_KEY,
        "q": query,
        "per_page": 10
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code == 200:
        return response.json()["hits"]
    return []

def create_results_navigation(current_index, total_results, search_type, query):
    markup = InlineKeyboardMarkup()
    
    if current_index > 0:
        prev_btn = InlineKeyboardButton("السابق 🌳", callback_data=f"prev_{current_index-1}_{search_type}_{query}")
        markup.add(prev_btn)
    
    if current_index < total_results - 1:
        next_btn = InlineKeyboardButton("التالي 🌳", callback_data=f"next_{current_index+1}_{search_type}_{query}")
        if markup.row_width == 0:
            markup.add(next_btn)
        else:
            markup.add(next_btn, row=0)
    
    download_btn = InlineKeyboardButton("تحميل 🌴", callback_data=f"download_{current_index}_{search_type}_{query}")
    markup.add(download_btn)
    
    return markup

def format_result(result, search_type, query, index):
    if search_type in ["photo", "illustration"]:
        caption = f"#{search_type.capitalize()}\nكلمة البحث: {query}\n\nالمصدر: Unsplash"
        return result["urls"]["regular"], caption
    else:  # video
        caption = f"#Video\nكلمة البحث: {query}\n\nالمصدر: Pixabay"
        return result["videos"]["medium"]["url"], caption
