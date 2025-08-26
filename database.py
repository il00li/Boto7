import sqlite3

def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, 
                  username TEXT, 
                  search_type TEXT DEFAULT NULL,
                  is_subscribed INTEGER DEFAULT 0,
                  referral_code TEXT,
                  referred_count INTEGER DEFAULT 0,
                  is_banned INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

def add_user(user_id, username, referral_code):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (id, username, referral_code) VALUES (?, ?, ?)",
              (user_id, username, referral_code))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def update_search_type(user_id, search_type):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET search_type = ? WHERE id = ?", (search_type, user_id))
    conn.commit()
    conn.close()

def set_subscription(user_id, is_subscribed):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET is_subscribed = ? WHERE id = ?", (is_subscribed, user_id))
    conn.commit()
    conn.close()

def increment_referral(referrer_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET referred_count = referred_count + 1 WHERE id = ?", (referrer_id,))
    c.execute("SELECT referred_count FROM users WHERE id = ?", (referrer_id,))
    count = c.fetchone()[0]
    conn.commit()
    conn.close()
    return count

def ban_user(user_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def unban_user(user_id):
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("UPDATE users SET is_banned = 0 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

def get_all_user_ids():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE is_banned = 0")
    ids = [row[0] for row in c.fetchall()]
    conn.close()
    return ids

def generate_referral_code(user_id):
    return f"ref{user_id}" 
