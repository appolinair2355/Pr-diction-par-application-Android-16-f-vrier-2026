"""
Configuration du bot Telegram de prédiction Baccarat
"""
import os

def parse_channel_id(env_var: str, default: str) -> int:
    value = os.getenv(env_var) or default
    channel_id = int(value)
    if channel_id > 0 and len(str(channel_id)) >= 10:
        channel_id = -channel_id
    return channel_id

# Canaux Telegram
SOURCE_CHANNEL_ID = parse_channel_id('SOURCE_CHANNEL_ID', '-1002682552255')
SOURCE_CHANNEL_2_ID = parse_channel_id('SOURCE_CHANNEL_2_ID', '-1002674389383')
PREDICTION_CHANNEL_ID = parse_channel_id('PREDICTION_CHANNEL_ID', '-1003579400443')

# Credentials API Telegram
API_ID = int(os.getenv('API_ID') or '29177661')
API_HASH = os.getenv('API_HASH') or 'a8639172fa8d35dbfd8ea46286d349ab'
BOT_TOKEN = os.getenv('BOT_TOKEN') or '7722770680:AAEblHwJ13_GebBWBFmIo5ioiGYYgDaP2iQ'

# Admin Telegram
ADMIN_ID = int(os.getenv('ADMIN_ID') or '1190237801')

# Configuration serveur
PORT = int(os.getenv('PORT') or '5000')

# Admin web
ADMIN_EMAIL = 'sossoukouam@gmail.com'
ADMIN_PASSWORD = 'arrow0291'

# Mapping des couleurs
SUIT_MAPPING = {
    '♠': '♣',
    '♥': '♠',
    '♦': '♥',
    '♣': '♦',
}

SUIT_DISPLAY = {
    '♠': '♠️',
    '♥': '❤️',
    '♦': '♦️',
    '♣': '♣️'
}

ALL_SUITS = ['♠', '♥', '♦', '♣']
