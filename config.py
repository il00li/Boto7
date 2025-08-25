import os

BOT_TOKEN = os.getenv('BOT_TOKEN', '8324471840:AAFqTHWy4-FZFIHGusm5RWk1Y240cV32SCw')
ADMIN_ID = int(os.getenv('ADMIN_ID', 6689435577))
CHANNEL_USERNAME = os.getenv('CHANNEL_USERNAME', '@iIl337')
MAIN_CHANNEL = os.getenv('MAIN_CHANNEL', '@GRABOT7')
DEVELOPER_USERNAME = os.getenv('DEVELOPER_USERNAME', '@OlIiIl7')

# مسارات ملفات التخزين
USERS_FILE = "users.json"
SEARCH_TYPES_FILE = "search_types.json"
INVITES_FILE = "invites.json"
