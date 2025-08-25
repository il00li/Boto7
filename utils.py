import json
import random
import string
import time
from config import BOT_USERNAME

def load_database():
    try:
        with open('database.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"users": {}, "invites": {}, "memberships": {}, "banned": []}

def save_database(db):
    with open('database.json', 'w') as f:
        json.dump(db, f, indent=4)

def generate_ref_code():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=10))

def generate_invite_link(user_id):
    db = load_database()
    ref_code = f"ref_{generate_ref_code()}"
    db['invites'][ref_code] = {
        "creator": user_id,
        "created_at": time.time(),
        "used_by": []
    }
    save_database(db)
    return f"https://t.me/{BOT_USERNAME[1:]}?start={ref_code}"

def check_membership(user_id):
    db = load_database()
    user_id_str = str(user_id)
    
    if user_id_str in db['banned']:
        return False
        
    if user_id_str in db['memberships']:
        expiry = db['memberships'][user_id_str]['expiry']
        if time.time() < expiry:
            return True
        else:
            # انتهت العضوية
            del db['memberships'][user_id_str]
            save_database(db)
    
    return False

def activate_membership(user_id, duration_days=30):
    db = load_database()
    user_id_str = str(user_id)
    
    expiry = time.time() + (duration_days * 24 * 60 * 60)
    db['memberships'][user_id_str] = {
        "activated_at": time.time(),
        "expiry": expiry
    }
    save_database(db)

def get_invites_count(user_id):
    db = load_database()
    count = 0
    
    for ref_code, data in db['invites'].items():
        if data['creator'] == user_id:
            count += len(data['used_by'])
    
    return count

def add_invited_user(ref_code, user_id):
    db = load_database()
    
    if ref_code in db['invites']:
        if user_id not in db['invites'][ref_code]['used_by']:
            db['invites'][ref_code]['used_by'].append(user_id)
            save_database(db)
            
            # التحقق إذا وصل عدد الدعوات إلى 10
            creator_id = db['invites'][ref_code]['creator']
            invites_count = get_invites_count(creator_id)
            
            if invites_count >= 10:
                activate_membership(creator_id)
            
            return True
    
    return False
