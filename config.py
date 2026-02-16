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
PREDICTION_CHANNEL_ID = parse_channel_id('PREDICTION_CHANNEL_ID', '-1002543915361')

# Admin Telegram
ADMIN_ID = int(os.getenv('ADMIN_ID') or '0')

# Credentials API Telegram
API_ID = int(os.getenv('API_ID') or '0')
API_HASH = os.getenv('API_HASH') or ''
BOT_TOKEN = os.getenv('BOT_TOKEN') or ''

# Configuration serveur
PORT = int(os.getenv('PORT') or '10000')

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
