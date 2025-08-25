import random
import string

def is_subscribed(bot, user_id, channel_username):
    try:
        chat_member = bot.get_chat_member(channel_username.replace('@', ''), user_id)
        return chat_member.status in ['member', 'administrator', 'creator']
    except:
        return False

def generate_invite_code(length=10):
    characters = string.ascii_letters + string.digits
    return ''.join(random.choice(characters) for _ in range(length))
