#!/usr/bin/env python3
"""
Bot Baccarat - Prédiction Automatique Corrigé
Canal: -1003579400443 (Prédiction + VIP)
"""
import os
import asyncio
import re
import logging
import sys
import json
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.types import ChatBannedRights
from aiohttp import web

# Configuration Telegram (depuis variables d'environnement)
API_ID = int(os.getenv('API_ID', 0))
API_HASH = os.getenv('API_HASH', '')
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))
PORT = int(os.getenv('PORT', 10000))

# ID Canal unique pour prédiction et VIP
PREDICTION_CHANNEL_ID = -1003579400443
VIP_CHANNEL_ID = -1003579400443
VIP_CHANNEL_LINK = "https://t.me/+s3y7GejUVHU0YjE0"  # À modifier selon votre lien

# Canal source par défaut
DEFAULT_SOURCE_CHANNEL_ID = -1002682552255

# Fichiers de données
USERS_FILE = "users_data.json"
PAUSE_CONFIG_FILE = "pause_config.json"
CHANNELS_CONFIG_FILE = "channels_config.json"
TRIAL_CONFIG_FILE = "trial_config.json"

# Configuration Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Vérification configuration
if not API_ID or API_ID == 0:
    logger.error("API_ID manquant")
    exit(1)
if not API_HASH:
    logger.error("API_HASH manquant")
    exit(1)
if not BOT_TOKEN:
    logger.error("BOT_TOKEN manquant")
    exit(1)

session_string = os.getenv('TELEGRAM_SESSION', '')
client = TelegramClient(StringSession(session_string), API_ID, API_HASH)

# ============================================================
# CONFIGURATION PAR DÉFAUT
# ============================================================

# Cycle de pause par défaut: 3min, 5min, 4min
DEFAULT_PAUSE_CYCLE = [180, 300, 240]

# Configuration des canaux
channels_config = {
    'source_channel_id': DEFAULT_SOURCE_CHANNEL_ID,
    'prediction_channel_id': PREDICTION_CHANNEL_ID,
    'vip_channel_id': VIP_CHANNEL_ID,
    'vip_channel_link': VIP_CHANNEL_LINK
}

# Configuration pause
pause_config = {
    'cycle': DEFAULT_PAUSE_CYCLE.copy(),
    'current_index': 0,
    'predictions_count': 0,
    'is_paused': False,
    'pause_end_time': None,
    'just_resumed': False
}

# Configuration essai
DEFAULT_TRIAL_DURATION = 1440  # 24 heures en minutes
trial_config = {
    'duration_minutes': DEFAULT_TRIAL_DURATION
}

# ============================================================
# ÉTAT GLOBAL
# ============================================================

users_data = {}
current_game_number = 0
last_source_game_number = 0
last_predicted_number = None
predictions_enabled = True
already_predicted_games = set()

# État de vérification des prédictions
verification_state = {
    'predicted_number': None,
    'predicted_suit': None,
    'current_check': 0,
    'message_id': None,
    'channel_id': None,
    'status': None,
    'base_game': None
}

# Cycle des costumes
SUIT_CYCLE = ['♥', '♦', '♣', '♠', '♦', '♥', '♠', '♣']
SUIT_DISPLAY = {
    '♥': '❤️ Cœur',
    '♦': '♦️ Carreau', 
    '♣': '♣️ Trèfle',
    '♠': '♠️ Pique'
}

# Statistiques
stats_bilan = {
    'total': 0, 'wins': 0, 'losses': 0,
    'win_details': {'✅0️⃣': 0, '✅1️⃣': 0, '✅2️⃣': 0, '✅3️⃣': 0},
    'loss_details': {'❌': 0}
}

# États conversation
user_conversation_state = {}
pending_payments = {}
admin_setting_time = {}
watch_state = {}

# ============================================================
# FONCTIONS UTILITAIRES
# ============================================================

def load_json(file_path, default=None):
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Erreur chargement {file_path}: {e}")
    return default or {}

def save_json(file_path, data):
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erreur sauvegarde {file_path}: {e}")

def load_all_configs():
    global channels_config, pause_config, trial_config, users_data
    loaded_channels = load_json(CHANNELS_CONFIG_FILE, {})
    if loaded_channels:
        channels_config.update(loaded_channels)
    # Forcer l'ID canal prédiction/VIP
    channels_config['prediction_channel_id'] = PREDICTION_CHANNEL_ID
    channels_config['vip_channel_id'] = VIP_CHANNEL_ID
    
    pause_config.update(load_json(PAUSE_CONFIG_FILE, pause_config))
    trial_config.update(load_json(TRIAL_CONFIG_FILE, trial_config))
    users_data.update(load_json(USERS_FILE, {}))
    logger.info("Configurations chargées")

def save_all_configs():
    save_json(CHANNELS_CONFIG_FILE, channels_config)
    save_json(PAUSE_CONFIG_FILE, pause_config)
    save_json(TRIAL_CONFIG_FILE, trial_config)
    save_json(USERS_FILE, users_data)

# ============================================================
# GESTION NUMÉROS ET COSTUMES
# ============================================================

def get_valid_even_numbers():
    """Génère la liste des pairs valides: 6-1436, pairs, ne finissant pas par 0"""
    valid = []
    for num in range(6, 1437):
        if num % 2 == 0 and num % 10 != 0:
            valid.append(num)
    return valid

VALID_EVEN_NUMBERS = get_valid_even_numbers()
logger.info(f"📊 Pairs valides: {len(VALID_EVEN_NUMBERS)} numéros")

def get_suit_for_number(number):
    """Retourne le costume pour un numéro pair valide"""
    if number not in VALID_EVEN_NUMBERS:
        logger.error(f"❌ Numéro {number} non valide")
        return None
    idx = VALID_EVEN_NUMBERS.index(number) % len(SUIT_CYCLE)
    return SUIT_CYCLE[idx]

def is_trigger_number(number):
    """Déclencheur: impair finissant par 1,3,5,7 ET suivant est pair valide"""
    if number % 2 == 0:
        return False
    
    last_digit = number % 10
    if last_digit not in [1, 3, 5, 7]:
        return False
    
    next_num = number + 1
    is_valid = next_num in VALID_EVEN_NUMBERS
    
    if is_valid:
        logger.info(f"🔥 DÉCLENCHEUR #{number} (suivant: #{next_num})")
    
    return is_valid

def get_trigger_target(number):
    """Retourne le numéro pair à prédire"""
    if not is_trigger_number(number):
        return None
    return number + 1

# ============================================================
# GESTION CANAUX - COMMANDES
# ============================================================

def get_source_channel_id():
    return channels_config.get('source_channel_id', DEFAULT_SOURCE_CHANNEL_ID)

def get_prediction_channel_id():
    return channels_config.get('prediction_channel_id', PREDICTION_CHANNEL_ID)

def get_vip_channel_id():
    return channels_config.get('vip_channel_id', VIP_CHANNEL_ID)

def get_vip_channel_link():
    return channels_config.get('vip_channel_link', VIP_CHANNEL_LINK)

def set_source_channel(channel_id):
    channels_config['source_channel_id'] = channel_id
    save_json(CHANNELS_CONFIG_FILE, channels_config)
    logger.info(f"Canal source mis à jour: {channel_id}")

# ============================================================
# GESTION UTILISATEURS
# ============================================================

def get_user(user_id: int) -> dict:
    user_id_str = str(user_id)
    if user_id_str not in users_data:
        users_data[user_id_str] = {
            'registered': False, 'nom': None, 'prenom': None, 'pays': None,
            'trial_started': None, 'trial_used': False, 'trial_joined_at': None,
            'subscription_end': None, 'vip_expires_at': None, 'is_in_channel': False,
            'total_time_added': 0, 'pending_payment': False, 'awaiting_screenshot': False
        }
        save_json(USERS_FILE, users_data)
    return users_data[user_id_str]

def update_user(user_id: int, data: dict):
    users_data[str(user_id)].update(data)
    save_json(USERS_FILE, users_data)

def is_user_subscribed(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    user = get_user(user_id)
    if not user.get('subscription_end'):
        return False
    try:
        end_time = datetime.fromisoformat(user['subscription_end'])
        return datetime.now() < end_time
    except:
        return False

def is_trial_active(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    user = get_user(user_id)
    if user.get('trial_used') or not user.get('trial_joined_at'):
        return False
    try:
        trial_end = datetime.fromisoformat(user['trial_joined_at']) + timedelta(minutes=trial_config['duration_minutes'])
        return datetime.now() < trial_end
    except:
        return False

def format_time_remaining(expiry_iso: str) -> str:
    try:
        expiry = datetime.fromisoformat(expiry_iso)
        remaining = expiry - datetime.now()
        if remaining.total_seconds() <= 0:
            return "Expiré"
        total_seconds = int(remaining.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        parts = []
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")
        return " ".join(parts)
    except:
        return "Inconnu"

def get_remaining_time(user_id: int) -> str:
    if user_id == ADMIN_ID:
        return "∞ (Admin)"
    user = get_user(user_id)
    if is_user_subscribed(user_id):
        return format_time_remaining(user['subscription_end'])
    elif is_trial_active(user_id):
        trial_end = datetime.fromisoformat(user['trial_joined_at']) + timedelta(minutes=trial_config['duration_minutes'])
        remaining = int((trial_end - datetime.now()).total_seconds())
        return format_seconds(remaining)
    return "Expiré"

def format_seconds(seconds: int) -> str:
    if seconds <= 0:
        return "Expiré"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if secs > 0 or (hours == 0 and minutes == 0):
        parts.append(f"{secs}s")
    return " ".join(parts)

def parse_duration(input_str: str) -> int:
    input_str = input_str.strip().lower()
    if input_str.isdigit():
        return int(input_str)
    if input_str.endswith('h'):
        try:
            return int(float(input_str[:-1]) * 60)
        except:
            return 0
    if input_str.endswith('m'):
        try:
            return int(input_str[:-1])
        except:
            return 0
    return 0

# ============================================================
# GESTION VIP
# ============================================================

async def delete_message_after_delay(chat_id: int, message_id: int, delay_seconds: int):
    await asyncio.sleep(delay_seconds)
    try:
        await client.delete_messages(chat_id, [message_id])
    except:
        pass

async def add_user_to_vip(user_id: int, duration_minutes: int, is_trial: bool = False):
    """Ajoute un utilisateur au VIP avec lien qui disparaît en 10s"""
    if user_id == ADMIN_ID:
        return True
    
    try:
        now = datetime.now()
        expires_at = now + timedelta(minutes=duration_minutes)
        
        update_data = {
            'vip_joined_at': now.isoformat(),
            'vip_expires_at': expires_at.isoformat(),
            'subscription_end': expires_at.isoformat(),
            'is_in_channel': True,
            'total_time_added': get_user(user_id).get('total_time_added', 0) + duration_minutes,
            'pending_payment': False,
            'awaiting_screenshot': False
        }
        
        if is_trial:
            update_data['trial_joined_at'] = now.isoformat()
        else:
            update_data['trial_used'] = True
        
        update_user(user_id, update_data)
        
        time_str = format_time_remaining(expires_at.isoformat())
        vip_link = get_vip_channel_link()
        
        link_msg = await client.send_message(user_id, f"""🎉 **{'ESSAI GRATUIT' if is_trial else 'ABONNEMENT'} ACTIVÉ!** 🎉

✅ **Accès VIP confirmé!**
⏳ **Temps restant:** {time_str}
📅 **Expire le:** {expires_at.strftime('%d/%m/%Y à %H:%M')}

🔗 **Lien du canal VIP:**
{vip_link}

⚠️ **CE LIEN DISPARAÎT DANS 10 SECONDES!**
🚨 **REJOIGNEZ IMMÉDIATEMENT!**

Vous serez retiré automatiquement à l'expiration.""")
        
        asyncio.create_task(delete_message_after_delay(user_id, link_msg.id, 10))
        
        user = get_user(user_id)
        await client.send_message(ADMIN_ID, f"""✅ **{'ESSAI' if is_trial else 'PAIEMENT'} ACTIVÉ**

🆔 `{user_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}
🌍 {user.get('pays', 'N/A')}
⏱️ {duration_minutes} minutes
⏳ Expire: {time_str}
📊 Total: {user.get('total_time_added', 0)} min""")
        
        asyncio.create_task(auto_kick_user(user_id, duration_minutes * 60))
        
        logger.info(f"✅ Utilisateur {user_id} ajouté au VIP pour {duration_minutes}min")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur ajout VIP {user_id}: {e}")
        return False

async def extend_user_time(user_id: int, additional_minutes: int):
    """Prolonge le temps d'un utilisateur"""
    try:
        user = get_user(user_id)
        
        if is_user_subscribed(user_id) or is_trial_active(user_id):
            current_end = datetime.fromisoformat(user.get('subscription_end') or user.get('vip_expires_at'))
            new_end = current_end + timedelta(minutes=additional_minutes)
        else:
            new_end = datetime.now() + timedelta(minutes=additional_minutes)
        
        update_user(user_id, {
            'subscription_end': new_end.isoformat(),
            'vip_expires_at': new_end.isoformat(),
            'total_time_added': user.get('total_time_added', 0) + additional_minutes,
            'is_in_channel': True
        })
        
        time_str = format_time_remaining(new_end.isoformat())
        
        await client.send_message(user_id, f"""⏱️ **TEMPS AJOUTÉ!**

✅ {additional_minutes} minutes ajoutées!
📅 Nouvelle fin: {new_end.strftime('%d/%m/%Y à %H:%M')}
⏳ Temps restant: {time_str}

🚀 Profitez bien!""")
        
        await client.send_message(ADMIN_ID, f"""✅ **TEMPS PROLONGÉ**

🆔 `{user_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}
⏱️ Ajouté: {additional_minutes} minutes
⏳ Nouveau total: {time_str}
📅 Expire: {new_end.strftime('%d/%m/%Y %H:%M')}""")
        
        remaining_seconds = int((new_end - datetime.now()).total_seconds())
        asyncio.create_task(auto_kick_user(user_id, remaining_seconds))
        
        logger.info(f"✅ Temps prolongé pour {user_id}: +{additional_minutes}min")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur prolongation {user_id}: {e}")
        return False

async def auto_kick_user(user_id: int, delay_seconds: int):
    """Expulse automatiquement après le délai"""
    if user_id == ADMIN_ID:
        return
    
    await asyncio.sleep(delay_seconds)
    
    try:
        if is_user_subscribed(user_id):
            logger.info(f"Utilisateur {user_id} a renouvelé, annulation expulsion")
            return
        
        user = get_user(user_id)
        entity = await client.get_input_entity(get_vip_channel_id())
        
        await client.kick_participant(entity, user_id)
        await client(EditBannedRequest(
            channel=entity, participant=user_id,
            banned_rights=ChatBannedRights(until_date=None, view_messages=False)
        ))
        
        update_user(user_id, {
            'vip_expires_at': None, 'subscription_end': None,
            'is_in_channel': False, 'trial_used': True
        })
        
        await client.send_message(user_id, """⏰ **VOTRE ACCÈS EST TERMINÉ**

💳 Pour réintégrer le canal:
/payer""")
        
        await client.send_message(ADMIN_ID, f"""🚫 **UTILISATEUR RETIRÉ**

🆔 `{user_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}""")
        
        logger.info(f"🚫 Utilisateur {user_id} expulsé")
        
    except Exception as e:
        logger.error(f"Erreur expulsion {user_id}: {e}")

# ============================================================
# SYSTÈME DE PRÉDICTION AUTOMATIQUE
# ============================================================

async def send_prediction(target_game: int, predicted_suit: str, base_game: int):
    """Envoie une prédiction au canal configuré"""
    global verification_state, last_predicted_number
    
    if not predictions_enabled:
        logger.warning("⛔ Prédictions désactivées")
        return False
    
    if verification_state['predicted_number'] is not None:
        logger.error(f"⛔ BLOQUÉ: Prédiction #{verification_state['predicted_number']} en cours!")
        return False
    
    try:
        prediction_channel_id = get_prediction_channel_id()
        entity = await client.get_input_entity(prediction_channel_id)
        
        prediction_text = f"""🎰 **PRÉDICTION #{target_game}**
🎯 Couleur: {SUIT_DISPLAY.get(predicted_suit, predicted_suit)}
⏳ Statut: EN ATTENTE DU RÉSULTAT..."""
        
        sent_msg = await client.send_message(entity, prediction_text)
        
        verification_state = {
            'predicted_number': target_game,
            'predicted_suit': predicted_suit,
            'current_check': 0,
            'message_id': sent_msg.id,
            'channel_id': prediction_channel_id,
            'status': 'pending',
            'base_game': base_game
        }
        
        last_predicted_number = target_game
        
        logger.info(f"🚀 PRÉDICTION #{target_game} ({predicted_suit}) LANCÉE")
        logger.info(f"🔍 Attente vérification: #{target_game} (check 0/3)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur envoi prédiction: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

async def update_prediction_status(status: str):
    """Met à jour le statut de la prédiction dans le canal"""
    global verification_state, stats_bilan
    
    if verification_state['predicted_number'] is None:
        logger.error("❌ Aucune prédiction à mettre à jour")
        return False
    
    try:
        predicted_num = verification_state['predicted_number']
        predicted_suit = verification_state['predicted_suit']
        
        if status == "❌":
            status_text = "❌ PERDU"
        else:
            status_text = f"{status} GAGNÉ"
        
        updated_text = f"""🎰 **PRÉDICTION #{predicted_num}**
🎯 Couleur: {SUIT_DISPLAY.get(predicted_suit, predicted_suit)}
📊 Statut: {status_text}"""
        
        await client.edit_message(
            verification_state['channel_id'],
            verification_state['message_id'],
            updated_text
        )
        
        # Mise à jour stats
        if status in ['✅0️⃣', '✅1️⃣', '✅2️⃣', '✅3️⃣']:
            stats_bilan['total'] += 1
            stats_bilan['wins'] += 1
            stats_bilan['win_details'][status] = stats_bilan['win_details'].get(status, 0) + 1
            logger.info(f"🎉 #{predicted_num} GAGNÉ ({status})")
        elif status == '❌':
            stats_bilan['total'] += 1
            stats_bilan['losses'] += 1
            logger.info(f"💔 #{predicted_num} PERDU")
        
        logger.info("🔓 SYSTÈME LIBÉRÉ - Nouvelle prédiction possible")
        
        # Reset état
        verification_state = {
            'predicted_number': None, 'predicted_suit': None,
            'current_check': 0, 'message_id': None,
            'channel_id': None, 'status': None, 'base_game': None
        }
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur mise à jour statut: {e}")
        return False

# ============================================================
# ANALYSE MESSAGES SOURCE
# ============================================================

def extract_game_number(message: str) -> int:
    """Extrait le numéro de jeu du message"""
    match = re.search(r"#N\s*(\d+)", message, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    patterns = [
        r"^#(\d+)",
        r"N\s*(\d+)",
        r"Numéro\s*(\d+)",
        r"Game\s*(\d+)"
    ]
    
    for pattern in patterns:
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None

def extract_suits_from_first_group(message_text: str) -> list:
    """Extrait les costumes du PREMIER groupe de parenthèses"""
    matches = re.findall(r"\(([^)]+)\)", message_text)
    if not matches:
        return []
    
    first_group = matches[0]
    normalized = first_group.replace('❤️', '♥').replace('❤', '♥')
    normalized = normalized.replace('♠️', '♠').replace('♦️', '♦').replace('♣️', '♣')
    normalized = normalized.replace('♥️', '♥')
    
    suits = []
    for suit in ['♥', '♠', '♦', '♣']:
        if suit in normalized:
            suits.append(suit)
    
    return suits

def is_message_editing(message_text: str) -> bool:
    """Vérifie si le message est en cours d'édition"""
    return message_text.strip().startswith('⏰')

def is_message_finalized(message_text: str) -> bool:
    """Vérifie si le message est finalisé"""
    return '✅' in message_text or '🔰' in message_text

async def process_verification_step(game_number: int, message_text: str):
    """Traite UNE étape de vérification"""
    global verification_state
    
    if verification_state['predicted_number'] is None:
        return
    
    predicted_num = verification_state['predicted_number']
    predicted_suit = verification_state['predicted_suit']
    current_check = verification_state['current_check']
    
    expected_number = predicted_num + current_check
    if game_number != expected_number:
        return
    
    suits = extract_suits_from_first_group(message_text)
    logger.info(f"🔍 Vérification #{game_number}: {suits}, attendu {predicted_suit}")
    
    if predicted_suit in suits:
        status = f"✅{current_check}️⃣"
        logger.info(f"🎉 GAGNÉ! {predicted_suit} trouvé au check {current_check}")
        await update_prediction_status(status)
        return
    
    if current_check < 3:
        verification_state['current_check'] += 1
        next_num = predicted_num + verification_state['current_check']
        logger.info(f"❌ Check {current_check} échoué, prochain: #{next_num}")
    else:
        logger.info(f"💔 PERDU après 4 vérifications")
        await update_prediction_status("❌")

async def check_and_launch_prediction(game_number: int):
    """Vérifie et lance une prédiction avec cycle de pause"""
    global pause_config
    
    # Bloquer si prédiction en cours
    if verification_state['predicted_number'] is not None:
        logger.warning(f"⛔ BLOQUÉ: Prédiction #{verification_state['predicted_number']} en attente")
        return
    
    # Vérifier pause active
    if pause_config['is_paused']:
        try:
            end_time = datetime.fromisoformat(pause_config['pause_end_time'])
            if datetime.now() < end_time:
                remaining = int((end_time - datetime.now()).total_seconds())
                logger.info(f"⏸️ Pause active: {remaining}s")
                return
            pause_config['is_paused'] = False
            pause_config['just_resumed'] = True
            save_json(PAUSE_CONFIG_FILE, pause_config)
            logger.info("🔄 Pause terminée")
        except:
            pause_config['is_paused'] = False
    
    # Vérifier déclencheur
    if not is_trigger_number(game_number):
        return
    
    target_num = get_trigger_target(game_number)
    if not target_num or target_num in already_predicted_games:
        return
    
    # Cycle de pause
    pause_config['predictions_count'] += 1
    current_count = pause_config['predictions_count']
    
    logger.info(f"📊 Prédiction {current_count}/5 avant pause")
    
    # Si 5 atteint, déclencher pause
    if current_count >= 5:
        cycle = pause_config['cycle']
        idx = pause_config['current_index'] % len(cycle)
        duration = cycle[idx]
        
        pause_config['is_paused'] = True
        pause_config['pause_end_time'] = (datetime.now() + timedelta(seconds=duration)).isoformat()
        pause_config['current_index'] += 1
        pause_config['predictions_count'] = 0
        save_json(PAUSE_CONFIG_FILE, pause_config)
        
        minutes = duration // 60
        logger.info(f"⏸️ PAUSE: {minutes}min")
        
        try:
            await client.send_message(
                get_prediction_channel_id(),
                f"⏸️ **PAUSE**\n⏱️ {minutes} minutes..."
            )
        except Exception as e:
            logger.error(f"Erreur envoi message pause: {e}")
        
        return
    
    # Lancer prédiction
    suit = get_suit_for_number(target_num)
    if suit:
        success = await send_prediction(target_num, suit, game_number)
        if success:
            already_predicted_games.add(target_num)
            logger.info(f"✅ Prédiction #{target_num} lancée ({current_count}/5)")

async def process_source_message(event, is_edit: bool = False):
    """Traite les messages du canal source"""
    global current_game_number, last_source_game_number
    
    try:
        message_text = event.message.message
        game_number = extract_game_number(message_text)
        
        if game_number is None:
            return
        
        is_editing = is_message_editing(message_text)
        is_finalized = is_message_finalized(message_text)
        
        log_type = "ÉDITÉ" if is_edit else "NOUVEAU"
        log_status = "⏰" if is_editing else ("✅" if is_finalized else "📝")
        logger.info(f"📩 {log_status} {log_type}: #{game_number}")
        
        # Vérification prédiction en cours
        if verification_state['predicted_number'] is not None:
            predicted_num = verification_state['predicted_number']
            current_check = verification_state['current_check']
            expected_number = predicted_num + current_check
            
            if is_editing and game_number == expected_number:
                logger.info(f"⏳ Message #{game_number} en édition, attente finalisation")
                return
            
            if game_number == expected_number:
                if is_finalized or not is_editing:
                    logger.info(f"✅ Numéro #{game_number} finalisé, vérification...")
                    await process_verification_step(game_number, message_text)
                    
                    if verification_state['predicted_number'] is not None:
                        logger.info(f"⏳ Prédiction #{verification_state['predicted_number']} toujours en cours")
                        return
                    else:
                        logger.info("✅ Vérification terminée")
                else:
                    logger.info(f"⏳ Attente finalisation pour #{game_number}")
            
            return  # Jamais de nouveau lancement si vérification en cours
        
        # Nouveau lancement (système libre)
        await check_and_launch_prediction(game_number)
        
        current_game_number = game_number
        last_source_game_number = game_number
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement message: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ============================================================
# COMMANDES UTILISATEURS
# ============================================================

@client.on(events.NewMessage(pattern='/start'))
async def cmd_start(event):
    if event.is_group or event.is_channel:
        return
    
    user_id = event.sender_id
    
    if user_id == ADMIN_ID:
        await event.respond("""👑 **ADMINISTRATEUR**

Commandes disponibles:
/stop - Arrêter prédictions
/resume - Reprendre prédictions  
/forcestop - Forcer arrêt immédiat
/predictinfo - Statut système
/clearverif - Débloquer système
/pausecycle - Voir/modifier cycle pause
/setchannel - Voir/modifier canaux
/bilan - Statistiques
/reset - Reset stats
/help - Aide complète""")
        return
    
    user = get_user(user_id)
    
    if user.get('registered'):
        remaining = get_remaining_time(user_id)
        await event.respond(f"""👋 Bonjour {user.get('prenom', '')}!

📊 **Votre Statut:** {'✅ Abonné' if is_user_subscribed(user_id) else '🎁 Essai' if is_trial_active(user_id) else '❌ Inactif'}
⏳ **Temps restant:** {remaining}

💡 /payer pour renouveler
💡 /status pour voir votre temps
💡 /help pour aide""")
        return
    
    user_conversation_state[user_id] = 'awaiting_nom'
    await event.respond("""👋 **Bienvenue sur le Bot Baccarat!**

🎰 Système de prédictions automatiques

📝 **Étape 1/3:** Votre nom de famille?""")

@client.on(events.NewMessage(pattern='/help'))
async def cmd_help(event):
    if event.is_group or event.is_channel:
        return
    
    user_id = event.sender_id
    
    if user_id == ADMIN_ID:
        await event.respond("""📖 **AIDE ADMINISTRATEUR**

**Contrôle Prédictions:**
/stop - Arrêter prédictions
/resume - Reprendre prédictions  
/forcestop - Forcer arrêt immédiat (déblocage)

**Monitoring:**
/predictinfo - Statut complet système
/clearverif - Effacer vérification bloquée

**Configuration:**
/setchannel - Voir canaux configurés
/pausecycle - Voir/modifier cycle pause

**Statistiques:**
/bilan - Stats prédictions
/reset - Reset stats

**Support:** @Kouamappoloak""")
        return
    
    remaining = get_remaining_time(event.sender_id)
    
    await event.respond(f"""📖 **AIDE UTILISATEUR**

/start - Inscription / Voir statut
/status - Voir votre temps restant: {remaining}
/payer - Renouveler abonnement
/help - Cette aide

**Comment ça marche:**
1️⃣ Inscrivez-vous avec /start
2️⃣ Recevez 24h d'essai gratuit
3️⃣ Payez avec /payer pour continuer
4️⃣ Rejoignez le canal VIP rapidement (lien 10s)

Le bot prédit automatiquement les numéros pairs valides!

**Support:** @Kouamappoloak""")

@client.on(events.NewMessage(pattern='/status'))
async def cmd_status(event):
    if event.is_group or event.is_channel:
        return
    
    user_id = event.sender_id
    user = get_user(user_id)
    
    if not user.get('registered'):
        await event.respond("❌ /start pour vous inscrire")
        return
    
    remaining = get_remaining_time(user_id)
    status = "👑 ADMIN" if user_id == ADMIN_ID else "✅ Abonné" if is_user_subscribed(user_id) else "🎁 Essai actif" if is_trial_active(user_id) else "❌ Inactif"
    
    await event.respond(f"""📊 **VOTRE STATUT**

👤 {user.get('prenom', '')} {user.get('nom', '')}
🌍 {user.get('pays', 'N/A')}
📊 {status}
⏳ **Temps restant:** {remaining}

💡 /payer pour renouveler""")

@client.on(events.NewMessage(pattern='/payer'))
async def cmd_payer(event):
    if event.is_group or event.is_channel:
        return
    
    user_id = event.sender_id
    if user_id == ADMIN_ID:
        await event.respond("👑 Accès illimité")
        return
    
    user = get_user(user_id)
    if not user.get('registered'):
        await event.respond("❌ Inscrivez-vous d'abord avec /start")
        return
    
    await event.respond("""💳 **PAIEMENT**

1️⃣ Effectuez le virement selon les instructions reçues
2️⃣ Envoyez la capture d'écran ici
3️⃣ L'admin valide → Accès immédiat

⚠️ **Important:** Le lien d'accès disparaît après 10 secondes, rejoignez immédiatement!""")
    
    update_user(user_id, {'awaiting_screenshot': True})

# ============================================================
# COMMANDES ADMIN - CONTRÔLE PRÉDICTIONS
# ============================================================

@client.on(events.NewMessage(pattern='/stop'))
async def cmd_stop(event):
    if event.sender_id != ADMIN_ID:
        return
    global predictions_enabled
    predictions_enabled = False
    await event.respond("🛑 **PRÉDICTIONS ARRÊTÉES**")

@client.on(events.NewMessage(pattern='/resume'))
async def cmd_resume(event):
    if event.sender_id != ADMIN_ID:
        return
    global predictions_enabled
    predictions_enabled = True
    await event.respond("🚀 **PRÉDICTIONS REPRISES**")

@client.on(events.NewMessage(pattern='/forcestop'))
async def cmd_forcestop(event):
    """Force l'arrêt complet et débloque le système"""
    if event.sender_id != ADMIN_ID:
        return
    
    global predictions_enabled, verification_state, already_predicted_games
    
    predictions_enabled = False
    old_pred = verification_state['predicted_number']
    
    verification_state = {
        'predicted_number': None, 'predicted_suit': None,
        'current_check': 0, 'message_id': None,
        'channel_id': None, 'status': None, 'base_game': None
    }
    
    already_predicted_games.clear()
    
    msg = "🚨 **ARRÊT FORCÉ**\n\n"
    msg += f"🛑 Prédictions désactivées\n"
    msg += f"🔓 Système débloqué"
    if old_pred:
        msg += f"\n🗑️ Prédiction #{old_pred} effacée"
    
    await event.respond(msg)

@client.on(events.NewMessage(pattern='/predictinfo'))
async def cmd_predictinfo(event):
    """Statut complet du système de prédiction"""
    if event.sender_id != ADMIN_ID:
        return
    
    verif_info = "Aucune"
    if verification_state['predicted_number']:
        next_check = verification_state['predicted_number'] + verification_state['current_check']
        verif_info = f"""#{verification_state['predicted_number']} ({verification_state['predicted_suit']})
Check: {verification_state['current_check']}/3
Attend: #{next_check}"""
    
    cycle_mins = [x//60 for x in pause_config['cycle']]
    current_idx = pause_config['current_index'] % len(pause_config['cycle'])
    next_pause_idx = (pause_config['current_index']) % len(pause_config['cycle'])
    
    # Info pause
    pause_info = "Non"
    if pause_config['is_paused']:
        try:
            end_time = datetime.fromisoformat(pause_config['pause_end_time'])
            remaining = int((end_time - datetime.now()).total_seconds())
            if remaining > 0:
                pause_info = f"Oui ({remaining//60}min {remaining%60}s)"
            else:
                pause_info = "Terminée (reprise imminente)"
        except:
            pause_info = "Erreur"
    
    await event.respond(f"""📊 **STATUT SYSTÈME PRÉDICTION**

🎯 **Source:** #{current_game_number}
🔍 **Vérification:** {verif_info}
🟢 **Prédictions:** {'ON' if predictions_enabled else 'OFF'}

⏸️ **CYCLE DE PAUSE:**
• Actif: {pause_info}
• Compteur: {pause_config['predictions_count']}/5
• Cycle: {cycle_mins} minutes
• Position: {current_idx + 1}/{len(cycle_mins)}
• Prochaine pause: {cycle_mins[next_pause_idx]} min

💡 /pausecycle pour modifier
💡 /clearverif si bloqué
💡 /forcestop pour débloquer""")

@client.on(events.NewMessage(pattern='/clearverif'))
async def cmd_clearverif(event):
    """Efface la vérification en cours"""
    if event.sender_id != ADMIN_ID:
        return
    
    global verification_state
    old = verification_state['predicted_number']
    
    verification_state = {
        'predicted_number': None, 'predicted_suit': None,
        'current_check': 0, 'message_id': None,
        'channel_id': None, 'status': None, 'base_game': None
    }
    
    await event.respond(f"✅ **{'Vérification #' + str(old) + ' effacée' if old else 'Aucune vérification'}**\n🚀 Système libéré")

@client.on(events.NewMessage(pattern=r'^/pausecycle(\s*[\d\s,]*)?$'))
async def cmd_pausecycle(event):
    """Configure le cycle de pause"""
    if event.sender_id != ADMIN_ID:
        return
    
    message_text = event.message.message.strip()
    parts = message_text.split()
    
    # Afficher configuration actuelle
    if len(parts) == 1:
        cycle_mins = [x//60 for x in pause_config['cycle']]
        current_idx = pause_config['current_index'] % len(cycle_mins)
        
        # Calculer prochaines pauses
        next_pauses = []
        for i in range(3):
            idx = (pause_config['current_index'] + i) % len(cycle_mins)
            next_pauses.append(f"{cycle_mins[idx]}min")
        
        # Info pause actuelle
        pause_status = "Non"
        if pause_config['is_paused']:
            try:
                end_time = datetime.fromisoformat(pause_config['pause_end_time'])
                remaining = int((end_time - datetime.now()).total_seconds())
                if remaining > 0:
                    pause_status = f"Oui (fin dans {remaining//60}min)"
            except:
                pass
        
        await event.respond(f"""⏸️ **CONFIGURATION CYCLE DE PAUSE**

**Cycle configuré:** {cycle_mins} minutes
**Ordre d'exécution:** {' → '.join([f'{m}min' for m in cycle_mins])} → recommence

**État actuel:**
• Pause active: {pause_status}
• Position: {current_idx + 1}/{len(cycle_mins)}
• Compteur: {pause_config['predictions_count']}/5 prédictions
• Prochaines pauses: {' → '.join(next_pauses)}

**Modifier le cycle:**
`/pausecycle 3,5,4` (minutes, séparées par virgule)
`/pausecycle 5,10,7,3` (autant de valeurs que voulu)

**Fonctionnement:**
Après chaque 5 prédictions → pause selon le cycle configuré""")
        return
    
    # Modifier le cycle
    try:
        cycle_str = ' '.join(parts[1:])
        cycle_str = cycle_str.replace(' ', '').replace(',', ',')
        new_cycle_mins = [int(x.strip()) for x in cycle_str.split(',') if x.strip()]
        
        if not new_cycle_mins or any(x <= 0 for x in new_cycle_mins):
            await event.respond("❌ Le cycle doit contenir des nombres positifs (minutes)")
            return
        
        # Convertir en secondes et sauvegarder
        new_cycle = [x * 60 for x in new_cycle_mins]
        pause_config['cycle'] = new_cycle
        pause_config['current_index'] = 0  # Reset position
        save_json(PAUSE_CONFIG_FILE, pause_config)
        
        await event.respond(f"""✅ **CYCLE MIS À JOUR**

**Nouveau cycle:** {new_cycle_mins} minutes
**Ordre:** {' → '.join([f'{m}min' for m in new_cycle_mins])} → recommence

🔄 Prochaine série: 5 prédictions puis {new_cycle_mins[0]} minutes de pause""")
        
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}\n\nFormat: `/pausecycle 3,5,4`")

@client.on(events.NewMessage(pattern=r'^/setchannel(\s+.+)?$'))
async def cmd_setchannel(event):
    """Voir et modifier les canaux configurés"""
    if event.sender_id != ADMIN_ID:
        return
    
    parts = event.message.message.strip().split()
    
    if len(parts) == 1:
        # Afficher configuration actuelle
        await event.respond(f"""📺 **CONFIGURATION CANAUX**

**Actuels:**
• 📥 Source: `{get_source_channel_id()}`
• 🎯 Prédiction: `{get_prediction_channel_id()}`
• ⭐ VIP: `{get_vip_channel_id()}`
• 🔗 Lien VIP: {get_vip_channel_link()}

**Modifier source:**
`/setchannel source -1001234567890`

⚠️ Les canaux Prédiction et VIP sont fixés à:
`{PREDICTION_CHANNEL_ID}`""")
        return
    
    try:
        ctype = parts[1].lower()
        
        if ctype == 'source':
            if len(parts) < 3:
                await event.respond("❌ Fournissez l'ID du canal source\nFormat: `/setchannel source -1001234567890`")
                return
            
            cid = int(parts[2])
            set_source_channel(cid)
            await event.respond(f"✅ **Canal source mis à jour:**\n`{cid}`")
        else:
            await event.respond(f"""❌ Type non modifiable

Seul le canal source peut être modifié.
Canal prédiction/VIP fixé à: `{PREDICTION_CHANNEL_ID}`

Usage: `/setchannel source -1001234567890`""")
            
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")

@client.on(events.NewMessage(pattern='/bilan'))
async def cmd_bilan(event):
    """Statistiques des prédictions"""
    if event.sender_id != ADMIN_ID:
        return
    
    if stats_bilan['total'] == 0:
        await event.respond("📊 Aucune prédiction enregistrée")
        return
    
    win_rate = (stats_bilan['wins'] / stats_bilan['total']) * 100
    
    await event.respond(f"""📊 **BILAN PRÉDICTIONS**

🎯 **Total:** {stats_bilan['total']}
✅ **Victoires:** {stats_bilan['wins']} ({win_rate:.1f}%)
❌ **Défaites:** {stats_bilan['losses']}

**Détails victoires:**
• Immédiat (N): {stats_bilan['win_details'].get('✅0️⃣', 0)}
• 2ème chance (N+1): {stats_bilan['win_details'].get('✅1️⃣', 0)}
• 3ème chance (N+2): {stats_bilan['win_details'].get('✅2️⃣', 0)}
• 4ème chance (N+3): {stats_bilan['win_details'].get('✅3️⃣', 0)}""")

@client.on(events.NewMessage(pattern='/reset'))
async def cmd_reset(event):
    """Reset uniquement les stats"""
    if event.sender_id != ADMIN_ID:
        return
    
    global stats_bilan, already_predicted_games, verification_state
    
    nb_users = len([u for u in users_data if int(u) != ADMIN_ID])
    old_pred = verification_state['predicted_number']
    
    stats_bilan = {
        'total': 0, 'wins': 0, 'losses': 0,
        'win_details': {'✅0️⃣': 0, '✅1️⃣': 0, '✅2️⃣': 0, '✅3️⃣': 0},
        'loss_details': {'❌': 0}
    }
    
    already_predicted_games.clear()
    
    verification_state = {
        'predicted_number': None, 'predicted_suit': None,
        'current_check': 0, 'message_id': None,
        'channel_id': None, 'status': None, 'base_game': None
    }
    
    await event.respond(f"""🚨 **RESET STATS EFFECTUÉ**

✅ **Conservé:**
• {nb_users} utilisateurs
• Abonnements actifs
• Configuration canaux
• Cycle de pause

🗑️ **Réinitialisé:**
• Statistiques prédictions{f" (#{old_pred})" if old_pred else ""}
• Historique prédictions
• Système débloqué""")

# ============================================================
# GESTION MESSAGES ET PAIEMENTS
# ============================================================

@client.on(events.NewMessage)
async def handle_messages(event):
    # Canal source - traitement automatique
    if event.is_group or event.is_channel:
        if event.chat_id == get_source_channel_id():
            await process_source_message(event)
        return
    
    # Commandes ignorées
    if event.message.message.startswith('/'):
        return
    
    user_id = event.sender_id
    
    # Admin - saisie durée après validation paiement
    if user_id == ADMIN_ID and user_id in admin_setting_time:
        state = admin_setting_time[user_id]
        if state['step'] == 'awaiting_duration':
            minutes = parse_duration(event.message.message.strip())
            
            if minutes < 2:
                await event.respond("❌ Minimum 2 minutes")
                return
            if minutes > 45000:
                await event.respond("❌ Maximum 750 heures")
                return
            
            target_id = state['target_user_id']
            del admin_setting_time[user_id]
            
            if target_id in pending_payments:
                del pending_payments[target_id]
            
            await add_user_to_vip(target_id, minutes, is_trial=False)
            return
    
    # Inscription conversation
    if user_id in user_conversation_state:
        state = user_conversation_state[user_id]
        text = event.message.message.strip()
        
        if state == 'awaiting_nom':
            update_user(user_id, {'nom': text})
            user_conversation_state[user_id] = 'awaiting_prenom'
            await event.respond("✅ **Étape 2/3:** Votre prénom?")
            return
        
        elif state == 'awaiting_prenom':
            update_user(user_id, {'prenom': text})
            user_conversation_state[user_id] = 'awaiting_pays'
            await event.respond("✅ **Étape 3/3:** Votre pays?")
            return
        
        elif state == 'awaiting_pays':
            update_user(user_id, {
                'pays': text, 'registered': True,
                'trial_started': datetime.now().isoformat()
            })
            del user_conversation_state[user_id]
            
            await add_user_to_vip(user_id, trial_config['duration_minutes'], is_trial=True)
            await event.respond(f"🎉 **Inscription réussie!**\n⏳ Essai gratuit: {trial_config['duration_minutes']} minutes\n\n⚠️ Rejoignez vite le canal, le lien disparaît en 10 secondes!")
            return
    
    # Capture paiement
    user = get_user(user_id)
    if user.get('awaiting_screenshot') and event.message.photo:
        pending_payments[user_id] = {'time': datetime.now().isoformat()}
        
        buttons = [
            [Button.inline("✅ Valider", data=f"validate_{user_id}")],
            [Button.inline("❌ Rejeter", data=f"reject_{user_id}")]
        ]
        
        await client.send_file(ADMIN_ID, event.message.photo, caption=f"""🔔 **NOUVEAU PAIEMENT**

🆔 `{user_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}
🌍 {user.get('pays', 'N/A')}
⏰ {datetime.now().strftime('%H:%M:%S')}""", buttons=buttons)
        
        update_user(user_id, {'awaiting_screenshot': False})
        await event.respond("⏳ Paiement en cours de validation...")
        return

@client.on(events.CallbackQuery(data=re.compile(rb'validate_(\d+)')))
async def handle_validate(event):
    if event.sender_id != ADMIN_ID:
        await event.answer("❌", alert=True)
        return
    
    user_id = int(event.data_match.group(1).decode())
    
    if user_id not in pending_payments:
        await event.answer("Déjà traité", alert=True)
        return
    
    admin_setting_time[ADMIN_ID] = {
        'target_user_id': user_id,
        'step': 'awaiting_duration'
    }
    
    user = get_user(user_id)
    await event.edit(f"""✅ **VALIDATION PAIEMENT**

🆔 `{user_id}`
👤 {user.get('prenom', '')} {user.get('nom', '')}

📝 **Durée d'abonnement?**
• `60` = 60 minutes
• `2h` = 2 heures
• `5h` = 5 heures
• `24h` = 24 heures

**Min:** 2 minutes | **Max:** 750 heures

Envoyez la durée:""")

@client.on(events.CallbackQuery(data=re.compile(rb'reject_(\d+)')))
async def handle_reject(event):
    if event.sender_id != ADMIN_ID:
        await event.answer("❌", alert=True)
        return
    
    user_id = int(event.data_match.group(1).decode())
    
    if user_id in pending_payments:
        del pending_payments[user_id]
    
    await event.edit("❌ **Paiement rejeté**")
    
    try:
        await client.send_message(user_id, "❌ Paiement refusé. Contactez @Kouamappoloak")
    except:
        pass

@client.on(events.MessageEdited)
async def handle_edit(event):
    if event.is_group or event.is_channel:
        if event.chat_id == get_source_channel_id():
            await process_source_message(event, is_edit=True)

# ============================================================
# SERVEUR WEB (PORT RENDER)
# ============================================================

async def web_index(request):
    """Page web de statut"""
    cycle_mins = [x//60 for x in pause_config['cycle']]
    current_idx = pause_config['current_index'] % len(cycle_mins)
    
    # Info pause
    pause_status = "Non"
    if pause_config['is_paused']:
        try:
            end_time = datetime.fromisoformat(pause_config['pause_end_time'])
            remaining = int((end_time - datetime.now()).total_seconds())
            if remaining > 0:
                pause_status = f"Oui ({remaining//60}min)"
        except:
            pass
    
    html = f"""<!DOCTYPE html>
<html>
<head><title>Bot Baccarat - Statut</title>
<style>
body {{ font-family: Arial; background: linear-gradient(135deg, #1e3c72, #2a5298); color: white; text-align: center; padding: 50px; }}
.status {{ background: rgba(255,255,255,0.1); padding: 20px; border-radius: 10px; display: inline-block; margin: 10px; min-width: 150px; }}
.number {{ font-size: 2em; color: #ffd700; font-weight: bold; }}
.label {{ font-size: 0.9em; opacity: 0.8; margin-bottom: 5px; }}
</style></head>
<body>
<h1>🎰 Bot Baccarat - Statut</h1>
<div class="status"><div class="label">Jeu Actuel</div><div class="number">#{current_game_number}</div></div>
<div class="status"><div class="label">Utilisateurs</div><div class="number">{len([u for u in users_data if int(u) != ADMIN_ID])}</div></div>
<div class="status"><div class="label">Vérification</div><div class="number">{verification_state['predicted_number'] or 'Libre'}</div></div>
<div class="status"><div class="label">Prédictions</div><div class="number">{'🟢 ON' if predictions_enabled else '🔴 OFF'}</div></div>
<div class="status"><div class="label">Pause</div><div class="number">{pause_config['predictions_count']}/5</div></div>
<div class="status"><div class="label">Statut Pause</div><div class="number">{pause_status}</div></div>
<p style="margin-top: 30px; opacity: 0.8;">
⏸️ Cycle: {cycle_mins} min | Position: {current_idx + 1}/{len(cycle_mins)}
</p>
<p>🔄 {datetime.now().strftime('%H:%M:%S')}</p>
<p style="margin-top: 20px; font-size: 0.8em; opacity: 0.6;">
Canal Prédiction/VIP: {PREDICTION_CHANNEL_ID}
</p>
</body></html>"""
    return web.Response(text=html, content_type='text/html')

async def start_web():
    app = web.Application()
    app.router.add_get('/', web_index)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🌐 Serveur web démarré sur port {PORT}")

# ============================================================
# DÉMARRAGE
# ============================================================

async def main():
    load_all_configs()
    await start_web()
    await client.start(bot_token=BOT_TOKEN)
    
    cycle_mins = [x//60 for x in pause_config['cycle']]
    
    logger.info("=" * 60)
    logger.info("🚀 BOT BACCARAT DÉMARRÉ")
    logger.info(f"👑 Admin ID: {ADMIN_ID}")
    logger.info(f"📺 Source: {get_source_channel_id()}")
    logger.info(f"🎯 Prédiction: {get_prediction_channel_id()}")
    logger.info(f"⭐ VIP: {get_vip_channel_id()}")
    logger.info(f"⏸️ Cycle pause: {cycle_mins} min")
    logger.info(f"⏸️ Position cycle: {(pause_config['current_index'] % len(cycle_mins)) + 1}/{len(cycle_mins)}")
    logger.info("=" * 60)
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
