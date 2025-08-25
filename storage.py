import json
import os
from datetime import datetime, timedelta
from config import USERS_FILE, SEARCH_TYPES_FILE, INVITES_FILE

def ensure_file_exists(file_path):
    """تأكد من وجود الملف، وإنشائه إذا لم يكن موجوداً"""
    if not os.path.exists(file_path):
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=4)

def read_json(file_path):
    """قراءة ملف JSON"""
    ensure_file_exists(file_path)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {}

def write_json(file_path, data):
    """كتابة بيانات إلى ملف JSON"""
    ensure_file_exists(file_path)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# دوال لإدارة المستخدمين
def get_user(user_id):
    """الحصول على بيانات مستخدم"""
    users = read_json(USERS_FILE)
    user_id_str = str(user_id)
    return users.get(user_id_str, {})

def save_user(user_id, user_data):
    """حفظ بيانات مستخدم"""
    users = read_json(USERS_FILE)
    user_id_str = str(user_id)
    users[user_id_str] = user_data
    write_json(USERS_FILE, users)

def get_all_users():
    """الحصول على جميع المستخدمين"""
    return read_json(USERS_FILE)

def update_user_subscription(user_id, days=30):
    """تحديث اشتراك المستخدم"""
    user = get_user(user_id)
    if not user:
        user = {}
    
    subscription_end = datetime.now() + timedelta(days=days)
    user['subscription_end'] = subscription_end.isoformat()
    user['is_banned'] = False
    
    save_user(user_id, user)

def check_subscription(user_id):
    """التحقق من صلاحية اشتراك المستخدم"""
    user = get_user(user_id)
    if not user or user.get('is_banned', False):
        return False
    
    subscription_end = user.get('subscription_end')
    if not subscription_end:
        return False
    
    try:
        end_date = datetime.fromisoformat(subscription_end)
        return end_date > datetime.now()
    except (ValueError, TypeError):
        return False

# دوال لأنواع البحث
def get_search_type(user_id):
    """الحصول على نوع البحث للمستخدم"""
    search_types = read_json(SEARCH_TYPES_FILE)
    user_id_str = str(user_id)
    return search_types.get(user_id_str, 'illustration')

def set_search_type(user_id, search_type):
    """تعيين نوع البحث للمستخدم"""
    search_types = read_json(SEARCH_TYPES_FILE)
    user_id_str = str(user_id)
    search_types[user_id_str] = search_type
    write_json(SEARCH_TYPES_FILE, search_types)

# دوال لإدارة الدعوات
def get_invite_code(user_id):
    """الحصول على كود الدعوة للمستخدم"""
    user = get_user(user_id)
    return user.get('invite_code')

def set_invite_code(user_id, invite_code):
    """تعيين كود الدعوة للمستخدم"""
    user = get_user(user_id)
    if not user:
        user = {}
    
    user['invite_code'] = invite_code
    save_user(user_id, user)

def increment_invite_count(user_id):
    """زيادة عداد الدعوات للمستخدم"""
    user = get_user(user_id)
    if not user:
        user = {}
    
    current_count = user.get('invited_count', 0)
    user['invited_count'] = current_count + 1
    save_user(user_id, user)
    
    # إذا وصل عدد الدعوات إلى 10، تفعيل الاشتراك
    if user['invited_count'] >= 10:
        update_user_subscription(user_id, 30)
    
    return user['invited_count']

def add_invite_record(invite_code, owner_id, used_by):
    """إضافة سجل دعوة"""
    invites = read_json(INVITES_FILE)
    invite_id = str(len(invites) + 1)
    invites[invite_id] = {
        'invite_code': invite_code,
        'owner_id': owner_id,
        'used_by': used_by,
        'created_at': datetime.now().isoformat()
    }
    write_json(INVITES_FILE, invites)

def find_user_by_invite_code(invite_code):
    """البحث عن مستخدم بواسطة كود الدعوة"""
    users = get_all_users()
    for user_id, user_data in users.items():
        if user_data.get('invite_code') == invite_code:
            return int(user_id)
    return None
