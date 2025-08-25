from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import DEVELOPER_USERNAME, CHANNEL_USERNAME

def main_menu_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    keyboard.add(
        InlineKeyboardButton("بدء البحث 🫐", callback_data="start_search"),
        InlineKeyboardButton("نوع البحث 🍇", callback_data="search_type"),
        InlineKeyboardButton("معلومات 🪻", callback_data="info"),
        InlineKeyboardButton("اشتراك مجاني 🏖️", callback_data="free_subscription")
    )
    
    return keyboard

def search_type_keyboard(selected_type=None):
    keyboard = InlineKeyboardMarkup(row_width=1)
    
    types = [
        ("Illustration | رسومات", "illustration"),
        ("Photo | صور", "photo"),
        ("Video | فيديو", "video")
    ]
    
    for name, callback in types:
        if selected_type == callback:
            name = f"🪐 {name}"
        keyboard.add(InlineKeyboardButton(name, callback_data=f"set_type_{callback}"))
    
    keyboard.add(InlineKeyboardButton("رجوع", callback_data="back_to_main"))
    
    return keyboard

def subscription_keyboard(user_id):
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    keyboard.add(
        InlineKeyboardButton("طلب الاشتراك من المطور", url=f"tg://user?id={DEVELOPER_USERNAME.replace('@', '')}"),
        InlineKeyboardButton("اشتراك مجاني 🏖️", callback_data="free_subscription"),
        InlineKeyboardButton("تحقق 👀", callback_data="check_subscription")
    )
    
    return keyboard

def force_subscribe_keyboard():
    keyboard = InlineKeyboardMarkup()
    
    keyboard.add(
        InlineKeyboardButton("اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}"),
        InlineKeyboardButton("تحقق 👀", callback_data="check_subscription")
    )
    
    return keyboard

def admin_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    keyboard.add(
        InlineKeyboardButton("إرسال إشعار للجميع", callback_data="admin_broadcast"),
        InlineKeyboardButton("عرض المستخدمين", callback_data="admin_list_users"),
        InlineKeyboardButton("حظر مستخدم", callback_data="admin_ban_user"),
        InlineKeyboardButton("رفع حظر مستخدم", callback_data="admin_unban_user")
    )
    
    return keyboard
