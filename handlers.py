import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import config
import utils

def check_subscription(bot, user_id):
    try:
        chat_member = bot.get_chat_member(config.CHANNEL_USERNAME, user_id)
        return chat_member.status not in ['left', 'kicked']
    except:
        return False

def subscription_message():
    markup = InlineKeyboardMarkup()
    channel_btn = InlineKeyboardButton("القناة", url=f"https://t.me/{config.CHANNEL_USERNAME[1:]}")
    check_btn = InlineKeyboardButton("تحقق 👀", callback_data="check_subscription")
    markup.add(channel_btn, check_btn)
    return "(／。＼)ノ\nاشتراك في القناة عبر الزر بالأسفل ثم اضغط على \"تحقق 👀\"", markup

def main_menu():
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton("نوع البحث 🍇", callback_data="search_type")
    btn2 = InlineKeyboardButton("بدء البحث 🫐", callback_data="start_search")
    markup.add(btn1, btn2)
    return "(＾▽＾)／ \nاختر نوع البحث من\" نوع البحث 🍇\" وابدء البحث عبر \"بدء البحث 🫐\"\nالمطور @OlIiIl7", markup

def search_type_menu():
    markup = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton("Illustration | رسوم", callback_data="search_illustration")
    btn2 = InlineKeyboardButton("Photo | صور", callback_data="search_photo")
    btn3 = InlineKeyboardButton("Video | فيديو", callback_data="search_video")
    back_btn = InlineKeyboardButton("رجوع 🔙", callback_data="back_main")
    markup.add(btn1)
    markup.add(btn2)
    markup.add(btn3)
    markup.add(back_btn)
    return "اختر نوع البحث:", markup

def no_membership_message(user_id):
    markup = InlineKeyboardMarkup()
    request_btn = InlineKeyboardButton("طلب الاشتراك 💌", url=f"https://t.me/{config.ADMIN_USERNAME[1:]}")
    free_btn = InlineKeyboardButton("اشتراك مجاني 🏖️", callback_data="free_membership")
    markup.add(request_btn, free_btn)
    
    # إرسال رسالة إلى المدير
    message = f"مستخدم جد
