import os
import asyncio
import re
import logging
import sys
import json
from datetime import datetime, timedelta, timezone
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from aiohttp import web
from config import (
    API_ID, API_HASH, BOT_TOKEN, ADMIN_ID,
    PORT, SUIT_DISPLAY
)

# Fichiers de configuration
CHANNELS_CONFIG_FILE = "channels_config.json"
PAUSE_CONFIG_FILE = "pause_config.json"

# Configuration par défaut des canaux - ID PRÉDICTION MODIFIÉ
DEFAULT_SOURCE_CHANNEL_ID = -1002682552255
DEFAULT_PREDICTION_CHANNEL_ID = -1003579400443  # ← NOUVEL ID

# --- Configuration Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

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

# --- Variables Globales ---
channels_config = {
    'source_channel_id': DEFAULT_SOURCE_CHANNEL_ID,
    'prediction_channel_id': DEFAULT_PREDICTION_CHANNEL_ID
}

# Cycle de pause par défaut: 3min, 5min, 4min
DEFAULT_PAUSE_CYCLE = [180, 300, 240]
pause_config = {
    'cycle': DEFAULT_PAUSE_CYCLE.copy(),
    'current_index': 0,
    'predictions_count': 0,
    'is_paused': False,
    'pause_end_time': None,
    'just_resumed': False
}

# État global
current_game_number = 0
last_source_game_number = 0
last_predicted_number = None
predictions_enabled = True
already_predicted_games = set()

# État de vérification
verification_state = {
    'predicted_number': None,
    'predicted_suit': None,
    'current_check': 0,
    'message_id': None,
    'channel_id': None,
    'status': None,
    'base_game': None,
    'sent_at': None,
    'verification_history': []
}

SUIT_CYCLE = ['♥', '♦', '♣', '♠', '♦', '♥', '♠', '♣']

# Historique complet pour le dashboard
predictions_history = []
max_history_size = 100

# ============================================================
# FONCTIONS DE CHARGEMENT/SAUVEGARDE
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
    global channels_config, pause_config
    channels_config.update(load_json(CHANNELS_CONFIG_FILE, channels_config))
    pause_config.update(load_json(PAUSE_CONFIG_FILE, pause_config))
    logger.info("Configurations chargées")

def save_all_configs():
    save_json(CHANNELS_CONFIG_FILE, channels_config)
    save_json(PAUSE_CONFIG_FILE, pause_config)

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
# GESTION CANAUX
# ============================================================

def get_source_channel_id():
    return channels_config.get('source_channel_id', DEFAULT_SOURCE_CHANNEL_ID)

def get_prediction_channel_id():
    return channels_config.get('prediction_channel_id', DEFAULT_PREDICTION_CHANNEL_ID)

def set_channels(source_id=None, prediction_id=None):
    if source_id:
        channels_config['source_channel_id'] = source_id
    if prediction_id:
        channels_config['prediction_channel_id'] = prediction_id
    save_json(CHANNELS_CONFIG_FILE, channels_config)
    logger.info(f"Canaux mis à jour")

# ============================================================
# SYSTÈME DE PRÉDICTION ET VÉRIFICATION
# ============================================================

async def send_prediction(target_game: int, predicted_suit: str, base_game: int):
    """Envoie une prédiction au canal configuré"""
    global verification_state, last_predicted_number, predictions_history
    
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
        
        now = datetime.now()
        verification_state = {
            'predicted_number': target_game,
            'predicted_suit': predicted_suit,
            'current_check': 0,
            'message_id': sent_msg.id,
            'channel_id': prediction_channel_id,
            'status': 'pending',
            'base_game': base_game,
            'sent_at': now.isoformat(),
            'verification_history': []
        }
        
        last_predicted_number = target_num
        
        # Ajouter à l'historique
        predictions_history.append({
            'type': 'prediction',
            'game_number': target_game,
            'suit': predicted_suit,
            'base_game': base_game,
            'status': 'pending',
            'timestamp': now.isoformat(),
            'checks': []
        })
        
        # Garder seulement les 100 dernières
        if len(predictions_history) > max_history_size:
            predictions_history.pop(0)
        
        logger.info(f"🚀 PRÉDICTION #{target_game} ({predicted_suit}) LANCÉE vers {prediction_channel_id}")
        logger.info(f"🔍 Attente vérification: #{target_game} (check 0/3)")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur envoi prédiction: {e}")
        return False

async def update_prediction_status(status: str):
    """Met à jour le statut de la prédiction"""
    global verification_state, predictions_history
    
    if verification_state['predicted_number'] is None:
        logger.error("❌ Aucune prédiction à mettre à jour")
        return False
    
    try:
        predicted_num = verification_state['predicted_number']
        predicted_suit = verification_state['predicted_suit']
        
        if status == "❌":
            status_text = "❌ PERDU"
            final_status = "lost"
        else:
            status_text = f"{status} GAGNÉ"
            final_status = "won"
        
        updated_text = f"""🎰 **PRÉDICTION #{predicted_num}**
🎯 Couleur: {SUIT_DISPLAY.get(predicted_suit, predicted_suit)}
📊 Statut: {status_text}"""
        
        await client.edit_message(
            verification_state['channel_id'],
            verification_state['message_id'],
            updated_text
        )
        
        # Mettre à jour l'historique
        for pred in reversed(predictions_history):
            if pred['type'] == 'prediction' and pred['game_number'] == predicted_num and pred['status'] == 'pending':
                pred['status'] = final_status
                pred['result'] = status
                break
        
        if status in ['✅0️⃣', '✅1️⃣', '✅2️⃣', '✅3️⃣']:
            logger.info(f"🎉 #{predicted_num} GAGNÉ ({status})")
        elif status == '❌':
            logger.info(f"💔 #{predicted_num} PERDU")
        
        logger.info(f"🔓 SYSTÈME LIBÉRÉ - Nouvelle prédiction possible")
        
        verification_state = {
            'predicted_number': None, 'predicted_suit': None,
            'current_check': 0, 'message_id': None,
            'channel_id': None, 'status': None, 'base_game': None,
            'sent_at': None, 'verification_history': []
        }
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur mise à jour statut: {e}")
        return False

# ============================================================
# ANALYSE MESSAGES SOURCE
# ============================================================

def extract_game_number(message: str) -> int:
    """Extrait le numéro de jeu du message (supporte #N, #R, #X, etc.)"""
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
    
    logger.debug(f"Costumes trouvés dans premier groupe '{first_group}': {suits}")
    return suits

def is_message_editing(message_text: str) -> bool:
    """Vérifie si le message est en cours d'édition (commence par ⏰)"""
    return message_text.strip().startswith('⏰')

def is_message_finalized(message_text: str) -> bool:
    """Vérifie si le message est finalisé (contient ✅ ou 🔰)"""
    return '✅' in message_text or '🔰' in message_text

async def process_verification_step(game_number: int, message_text: str):
    """Traite UNE étape de vérification"""
    global verification_state, predictions_history
    
    if verification_state['predicted_number'] is None:
        return
    
    predicted_num = verification_state['predicted_number']
    predicted_suit = verification_state['predicted_suit']
    current_check = verification_state['current_check']
    
    expected_number = predicted_num + current_check
    if game_number != expected_number:
        logger.warning(f"⚠️ Reçu #{game_number} != attendu #{expected_number}")
        return
    
    suits = extract_suits_from_first_group(message_text)
    logger.info(f"🔍 Vérification #{game_number}: premier groupe contient {suits}, attendu {predicted_suit}")
    
    # Enregistrer cette vérification dans l'historique
    check_record = {
        'check_number': current_check,
        'game_number': game_number,
        'suits_found': suits,
        'expected_suit': predicted_suit,
        'timestamp': datetime.now().isoformat(),
        'found': predicted_suit in suits
    }
    verification_state['verification_history'].append(check_record)
    
    # Mettre à jour l'historique global
    for pred in reversed(predictions_history):
        if pred['type'] == 'prediction' and pred['game_number'] == predicted_num and pred['status'] == 'pending':
            pred['checks'].append(check_record)
            break
    
    if predicted_suit in suits:
        status = f"✅{current_check}️⃣"
        logger.info(f"🎉 GAGNÉ! Costume {predicted_suit} trouvé dans premier groupe au check {current_check}")
        await update_prediction_status(status)
        return
    
    if current_check < 3:
        verification_state['current_check'] += 1
        next_num = predicted_num + verification_state['current_check']
        logger.info(f"❌ Check {current_check} échoué sur #{game_number}, prochain: #{next_num}")
    else:
        logger.info(f"💔 PERDU après 4 vérifications (jusqu'à #{game_number})")
        await update_prediction_status("❌")

async def check_and_launch_prediction(game_number: int):
    """Vérifie et lance une prédiction avec CYCLE DE PAUSE"""
    global pause_config
    
    if verification_state['predicted_number'] is not None:
        logger.warning(f"⛔ BLOQUÉ: Prédiction #{verification_state['predicted_number']} en attente de vérification. Déclencheur #{game_number} ignoré.")
        return
    
    if pause_config['is_paused']:
        try:
            end_time = datetime.fromisoformat(pause_config['pause_end_time'])
            if datetime.now() < end_time:
                remaining = int((end_time - datetime.now()).total_seconds())
                logger.info(f"⏸️ Pause active: {remaining}s restantes")
                return
            pause_config['is_paused'] = False
            pause_config['just_resumed'] = True
            save_json(PAUSE_CONFIG_FILE, pause_config)
            logger.info("🔄 Pause terminée, reprise")
        except:
            pause_config['is_paused'] = False
    
    if not is_trigger_number(game_number):
        return
    
    target_num = get_trigger_target(game_number)
    if not target_num or target_num in already_predicted_games:
        return
    
    pause_config['predictions_count'] += 1
    current_count = pause_config['predictions_count']
    
    logger.info(f"📊 Prédiction {current_count}/5 avant pause")
    
    if current_count >= 5:
        cycle = pause_config['cycle']
        idx = pause_config['current_index'] % len(cycle)
        duration = cycle[idx]
        
        pause_config['is_paused'] = True
        pause_config['pause_end_time'] = (datetime.now() + timedelta(seconds=duration)).isoformat()
        pause_config['current_index'] += 1
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
        
        pause_config['predictions_count'] = 0
        save_json(PAUSE_CONFIG_FILE, pause_config)
        
        return
    
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
        
        # Ajouter à l'historique des messages source
        predictions_history.append({
            'type': 'source_message',
            'game_number': game_number,
            'message': message_text[:100],
            'is_editing': is_editing,
            'is_finalized': is_finalized,
            'timestamp': datetime.now().isoformat()
        })
        if len(predictions_history) > max_history_size:
            predictions_history.pop(0)
        
        # VÉRIFICATION PRÉCÉDENTE
        if verification_state['predicted_number'] is not None:
            predicted_num = verification_state['predicted_number']
            current_check = verification_state['current_check']
            expected_number = predicted_num + current_check
            
            if is_editing and game_number == expected_number:
                logger.info(f"⏳ Message #{game_number} en édition, attente finalisation")
                return
            
            if game_number == expected_number:
                if is_finalized or not is_editing:
                    logger.info(f"✅ Numéro #{game_number} finalisé/disponible, vérification...")
                    await process_verification_step(game_number, message_text)
                    
                    if verification_state['predicted_number'] is not None:
                        logger.info(f"⏳ Prédiction #{verification_state['predicted_number']} toujours en cours")
                        return
                    else:
                        logger.info("✅ Vérification terminée, système libre")
                else:
                    logger.info(f"⏳ Attente finalisation pour #{game_number}")
            else:
                logger.info(f"⏭️ Attente #{expected_number}, reçu #{game_number}")
            
            return
        
        # NOUVEAU LANCEMENT
        await check_and_launch_prediction(game_number)
        
        current_game_number = game_number
        last_source_game_number = game_number
        
    except Exception as e:
        logger.error(f"❌ Erreur traitement message: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ============================================================
# COMMANDES ADMIN
# ============================================================

@client.on(events.NewMessage(pattern='/start'))
async def cmd_start(event):
    if event.is_group or event.is_channel:
        return
    
    user_id = event.sender_id
    
    if user_id == ADMIN_ID:
        await event.respond("""👑 **ADMINISTRATEUR**

Commandes:
/stop /resume /forcestop - Contrôle
/predictinfo - Statut système
/clearverif - Débloquer
/setchannel - Canaux
/pausecycle - Cycle pause
/bilan - Stats
/reset - Reset stats
/help - Aide""")
        return
    
    await event.respond("""👋 **Bot Prédiction Baccarat**

Ce bot est privé. Contactez l'administrateur pour l'utiliser.""")

@client.on(events.NewMessage(pattern='/help'))
async def cmd_help(event):
    if event.is_group or event.is_channel:
        return
    
    user_id = event.sender_id
    
    if user_id == ADMIN_ID:
        await event.respond("""📖 **AIDE ADMINISTRATEUR**

**Contrôle:**
/stop - Arrêter prédictions
/resume - Reprendre prédictions  
/forcestop - Forcer arrêt immédiat

**Monitoring:**
/predictinfo - Statut système prédiction
/clearverif - Effacer vérification bloquée
/bilan - Statistiques prédictions

**Configuration:**
/setchannel source ID - Canal source
/setchannel prediction ID - Canal prédiction  
/pausecycle - Voir/modifier cycle pause

**Dashboard:** Disponible sur l'URL Render""")
        return
    
    await event.respond("""📖 **AIDE**

Ce bot est réservé aux administrateurs.""")

@client.on(events.NewMessage(pattern='/stop'))
async def cmd_stop(event):
    if event.sender_id != ADMIN_ID:
        return
    global predictions_enabled
    predictions_enabled = False
    await event.respond("🛑 **PRÉDICTIONS ARRÊTÉES**")

@client.on(events.NewMessage(pattern='/forcestop'))
async def cmd_forcestop(event):
    if event.sender_id != ADMIN_ID:
        return
    
    global predictions_enabled, verification_state, already_predicted_games
    
    predictions_enabled = False
    old_pred = verification_state['predicted_number']
    
    verification_state = {
        'predicted_number': None, 'predicted_suit': None,
        'current_check': 0, 'message_id': None,
        'channel_id': None, 'status': None, 'base_game': None,
        'sent_at': None, 'verification_history': []
    }
    
    already_predicted_games.clear()
    
    msg = "🚨 **ARRÊT FORCÉ**\n\n"
    msg += f"🛑 Prédictions désactivées\n"
    msg += f"🔓 Système débloqué"
    if old_pred:
        msg += f"\n🗑️ Prédiction #{old_pred} effacée"
    
    await event.respond(msg)

@client.on(events.NewMessage(pattern='/resume'))
async def cmd_resume(event):
    if event.sender_id != ADMIN_ID:
        return
    global predictions_enabled
    predictions_enabled = True
    await event.respond("🚀 **PRÉDICTIONS REPRISES**")

@client.on(events.NewMessage(pattern='/predictinfo'))
async def cmd_predictinfo(event):
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
    
    await event.respond(f"""📊 **STATUT SYSTÈME**

🎯 Source: #{current_game_number}
🔍 Vérification: {verif_info}
🟢 Prédictions: {'ON' if predictions_enabled else 'OFF'}

⏸️ **CYCLE DE PAUSE:**
• Actif: {'Oui' if pause_config['is_paused'] else 'Non'}
• Compteur: {pause_config['predictions_count']}/5
• Cycle: {cycle_mins} minutes
• Position: {current_idx + 1}/{len(cycle_mins)}
• Prochaine pause: {cycle_mins[next_pause_idx]} min

💡 /pausecycle pour modifier
💡 /clearverif si bloqué
💡 /forcestop pour débloquer""")

@client.on(events.NewMessage(pattern='/clearverif'))
async def cmd_clearverif(event):
    if event.sender_id != ADMIN_ID:
        return
    
    global verification_state
    old = verification_state['predicted_number']
    
    verification_state = {
        'predicted_number': None, 'predicted_suit': None,
        'current_check': 0, 'message_id': None,
        'channel_id': None, 'status': None, 'base_game': None,
        'sent_at': None, 'verification_history': []
    }
    
    await event.respond(f"✅ **{'Vérification #' + str(old) + ' effacée' if old else 'Aucune vérification'}**\n🚀 Système libéré")

@client.on(events.NewMessage(pattern=r'^/pausecycle(\s*[\d\s,]*)?$'))
async def cmd_pausecycle(event):
    if event.sender_id != ADMIN_ID:
        return
    
    message_text = event.message.message.strip()
    parts = message_text.split()
    
    if len(parts) == 1:
        cycle_mins = [x//60 for x in pause_config['cycle']]
        current_idx = pause_config['current_index'] % len(pause_config['cycle'])
        
        next_pauses = []
        for i in range(3):
            idx = (pause_config['current_index'] + i) % len(cycle_mins)
            next_pauses.append(f"{cycle_mins[idx]}min")
        
        await event.respond(f"""⏸️ **CONFIGURATION CYCLE DE PAUSE**

**Cycle configuré:** {cycle_mins} minutes
**Ordre d'exécution:** {' → '.join([f'{m}min' for m in cycle_mins])} → recommence

**État actuel:**
• Position: {current_idx + 1}/{len(cycle_mins)}
• Compteur: {pause_config['predictions_count']}/5 prédictions
• Prochaines pauses: {' → '.join(next_pauses)}

**Modifier le cycle:**
`/pausecycle 3,5,4` (minutes, séparées par virgule)""")
        return
    
    try:
        cycle_str = ' '.join(parts[1:])
        cycle_str = cycle_str.replace(' ', '').replace(',', ',')
        new_cycle_mins = [int(x.strip()) for x in cycle_str.split(',') if x.strip()]
        
        if not new_cycle_mins or any(x <= 0 for x in new_cycle_mins):
            await event.respond("❌ Le cycle doit contenir des nombres positifs (minutes)")
            return
        
        new_cycle = [x * 60 for x in new_cycle_mins]
        pause_config['cycle'] = new_cycle
        pause_config['current_index'] = 0
        save_json(PAUSE_CONFIG_FILE, pause_config)
        
        await event.respond(f"""✅ **CYCLE MIS À JOUR**

**Nouveau cycle:** {new_cycle_mins} minutes
**Ordre:** {' → '.join([f'{m}min' for m in new_cycle_mins])} → recommence

🔄 Prochaine série: 5 prédictions puis {new_cycle_mins[0]} minutes de pause""")
        
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}\n\nFormat: `/pausecycle 3,5,4`")

@client.on(events.NewMessage(pattern=r'^/setchannel(\s+.+)?$'))
async def cmd_setchannel(event):
    if event.sender_id != ADMIN_ID:
        return
    
    parts = event.message.message.strip().split()
    
    if len(parts) < 3:
        await event.respond(f"""📺 **CONFIGURATION CANAUX**

**Actuel:**
• Source: `{get_source_channel_id()}`
• Prédiction: `{get_prediction_channel_id()}`

**Modifier:**
`/setchannel source -1001234567890`
`/setchannel prediction -1003579400443`""")
        return
    
    try:
        ctype = parts[1].lower()
        cid = int(parts[2])
        
        if ctype == 'source':
            set_channels(source_id=cid)
            await event.respond(f"✅ **Canal source:**\n`{cid}`")
            
        elif ctype == 'prediction':
            set_channels(prediction_id=cid)
            await event.respond(f"✅ **Canal prédiction:**\n`{cid}`\n\n🎯 Les prédictions seront envoyées ici")
        else:
            await event.respond("❌ Type invalide. Utilisez: source ou prediction")
            
    except Exception as e:
        await event.respond(f"❌ Erreur: {e}")

@client.on(events.NewMessage(pattern='/bilan'))
async def cmd_bilan(event):
    if event.sender_id != ADMIN_ID:
        return
    
    total = sum(1 for p in predictions_history if p['type'] == 'prediction')
    won = sum(1 for p in predictions_history if p['type'] == 'prediction' and p.get('status') == 'won')
    lost = sum(1 for p in predictions_history if p['type'] == 'prediction' and p.get('status') == 'lost')
    pending = sum(1 for p in predictions_history if p['type'] == 'prediction' and p.get('status') == 'pending')
    
    if total == 0:
        await event.respond("📊 Aucune prédiction enregistrée")
        return
    
    win_rate = (won / (won + lost) * 100) if (won + lost) > 0 else 0
    
    await event.respond(f"""📊 **BILAN PRÉDICTIONS**

🎯 **Total:** {total}
✅ **Victoires:** {won}
❌ **Défaites:** {lost}
⏳ **En cours:** {pending}
📈 **Taux:** {win_rate:.1f}%""")

@client.on(events.NewMessage(pattern='/reset'))
async def cmd_reset(event):
    if event.sender_id != ADMIN_ID:
        return
    
    global predictions_history, already_predicted_games, verification_state
    
    predictions_history = []
    already_predicted_games.clear()
    
    old_pred = verification_state['predicted_number']
    verification_state = {
        'predicted_number': None, 'predicted_suit': None,
        'current_check': 0, 'message_id': None,
        'channel_id': None, 'status': None, 'base_game': None,
        'sent_at': None, 'verification_history': []
    }
    
    await event.respond(f"""🚨 **RESET EFFECTUÉ**

🗑️ **Réinitialisé:**
• Historique des prédictions
• Historique des messages{f" (#{old_pred})" if old_pred else ""}

✅ Système prêt!""")

@client.on(events.NewMessage)
async def handle_messages(event):
    if event.is_group or event.is_channel:
        if event.chat_id == get_source_channel_id():
            await process_source_message(event)
        return
    
    if event.message.message.startswith('/'):
        return

@client.on(events.MessageEdited)
async def handle_edit(event):
    if event.is_group or event.is_channel:
        if event.chat_id == get_source_channel_id():
            await process_source_message(event, is_edit=True)

# ============================================================
# SERVEUR WEB - DASHBOARD COMPLET
# ============================================================

def get_status_color(status):
    if status == 'won':
        return '#28a745'
    elif status == 'lost':
        return '#dc3545'
    elif status == 'pending':
        return '#ffc107'
    return '#6c757d'

def format_time(iso_time):
    if not iso_time:
        return "N/A"
    try:
        dt = datetime.fromisoformat(iso_time)
        return dt.strftime('%H:%M:%S')
    except:
        return iso_time

async def web_index(request):
    """Page principale du dashboard"""
    cycle_mins = [x//60 for x in pause_config['cycle']]
    current_idx = pause_config['current_index'] % len(cycle_mins)
    
    total_pred = sum(1 for p in predictions_history if p['type'] == 'prediction')
    won = sum(1 for p in predictions_history if p['type'] == 'prediction' and p.get('status') == 'won')
    lost = sum(1 for p in predictions_history if p['type'] == 'prediction' and p.get('status') == 'lost')
    pending = sum(1 for p in predictions_history if p['type'] == 'prediction' and p.get('status') == 'pending')
    
    win_rate = (won / (won + lost) * 100) if (won + lost) > 0 else 0
    
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prédicteur Baccarat - Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            min-height: 100vh;
            color: white;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            backdrop-filter: blur(10px);
        }}
        
        h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        
        .subtitle {{
            opacity: 0.9;
            font-size: 1.1em;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: rgba(255,255,255,0.15);
            padding: 20px;
            border-radius: 15px;
            text-align: center;
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255,255,255,0.2);
            transition: transform 0.3s;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        
        .stat-number {{
            font-size: 2.5em;
            font-weight: bold;
            color: #ffd700;
            margin: 10px 0;
        }}
        
        .stat-label {{
            font-size: 0.9em;
            opacity: 0.9;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .status-badge {{
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: bold;
            margin-top: 5px;
        }}
        
        .status-on {{
            background: #28a745;
        }}
        
        .status-off {{
            background: #dc3545;
        }}
        
        .status-pause {{
            background: #ffc107;
            color: #000;
        }}
        
        .section {{
            background: rgba(255,255,255,0.1);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
            backdrop-filter: blur(10px);
        }}
        
        .section h2 {{
            margin-bottom: 15px;
            color: #ffd700;
            border-bottom: 2px solid rgba(255,215,0,0.3);
            padding-bottom: 10px;
        }}
        
        .prediction-list {{
            max-height: 600px;
            overflow-y: auto;
        }}
        
        .prediction-item {{
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
            padding: 15px;
            margin-bottom: 10px;
            border-left: 4px solid;
            transition: all 0.3s;
        }}
        
        .prediction-item:hover {{
            background: rgba(0,0,0,0.3);
            transform: translateX(5px);
        }}
        
        .prediction-won {{
            border-left-color: #28a745;
        }}
        
        .prediction-lost {{
            border-left-color: #dc3545;
        }}
        
        .prediction-pending {{
            border-left-color: #ffc107;
            animation: pulse 2s infinite;
        }}
        
        @keyframes pulse {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
            100% {{ opacity: 1; }}
        }}
        
        .prediction-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
            flex-wrap: wrap;
            gap: 10px;
        }}
        
        .prediction-number {{
            font-size: 1.3em;
            font-weight: bold;
        }}
        
        .prediction-suit {{
            font-size: 1.5em;
        }}
        
        .prediction-status {{
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 0.85em;
            font-weight: bold;
        }}
        
        .checks-list {{
            margin-top: 10px;
            padding-left: 20px;
            font-size: 0.9em;
            opacity: 0.9;
        }}
        
        .check-item {{
            margin: 5px 0;
            padding: 5px;
            background: rgba(255,255,255,0.05);
            border-radius: 5px;
        }}
        
        .check-found {{
            color: #28a745;
        }}
        
        .check-not-found {{
            color: #dc3545;
        }}
        
        .source-message {{
            background: rgba(100,100,100,0.2);
            border-left-color: #6c757d;
            font-size: 0.9em;
        }}
        
        .message-text {{
            font-family: monospace;
            background: rgba(0,0,0,0.2);
            padding: 8px;
            border-radius: 5px;
            margin-top: 5px;
            word-break: break-all;
        }}
        
        .timestamp {{
            font-size: 0.8em;
            opacity: 0.7;
        }}
        
        .info-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 15px;
        }}
        
        .info-item {{
            background: rgba(0,0,0,0.2);
            padding: 15px;
            border-radius: 10px;
        }}
        
        .info-label {{
            font-size: 0.85em;
            opacity: 0.8;
            margin-bottom: 5px;
        }}
        
        .info-value {{
            font-size: 1.2em;
            font-weight: bold;
            color: #ffd700;
        }}
        
        .refresh-indicator {{
            text-align: center;
            padding: 10px;
            font-size: 0.9em;
            opacity: 0.7;
        }}
        
        @media (max-width: 768px) {{
            .stats-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
            h1 {{
                font-size: 1.8em;
            }}
        }}
    </style>
    <meta http-equiv="refresh" content="5">
</head>
<body>
    <div class="container">
        <header>
            <h1>🎰 Prédicteur Baccarat</h1>
            <div class="subtitle">Dashboard de surveillance en temps réel</div>
        </header>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Jeu Actuel</div>
                <div class="stat-number">#{current_game_number}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Prédictions</div>
                <div class="stat-number">{total_pred}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Victoires</div>
                <div class="stat-number" style="color: #28a745;">{won}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Défaites</div>
                <div class="stat-number" style="color: #dc3545;">{lost}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">En Cours</div>
                <div class="stat-number" style="color: #ffc107;">{pending}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Win Rate</div>
                <div class="stat-number">{win_rate:.1f}%</div>
            </div>
        </div>
        
        <div class="section">
            <h2>⚙️ Statut Système</h2>
            <div class="info-grid">
                <div class="info-item">
                    <div class="info-label">Prédictions</div>
                    <div class="info-value">
                        {'🟢 ACTIF' if predictions_enabled else '🔴 ARRÊTÉ'}
                        <span class="status-badge {'status-on' if predictions_enabled else 'status-off'}">
                            {'ON' if predictions_enabled else 'OFF'}
                        </span>
                    </div>
                </div>
                <div class="info-item">
                    <div class="info-label">Vérification en cours</div>
                    <div class="info-value">
                        {f"#{verification_state['predicted_number']} ({verification_state['predicted_suit']})" if verification_state['predicted_number'] else "Aucune"}
                    </div>
                </div>
                <div class="info-item">
                    <div class="info-label">Cycle de Pause</div>
                    <div class="info-value">
                        {'⏸️ EN PAUSE' if pause_config['is_paused'] else '▶️ Actif'}
                        {f" ({pause_config['predictions_count']}/5)" if not pause_config['is_paused'] else ''}
                    </div>
                </div>
                <div class="info-item">
                    <div class="info-label">Prochaine Pause</div>
                    <div class="info-value">{cycle_mins[current_idx]} min</div>
                </div>
            </div>
        </div>
        
        <div class="section">
            <h2>📊 Historique des Prédictions & Vérifications</h2>
            <div class="prediction-list">
                {generate_predictions_html()}
            </div>
        </div>
        
        <div class="refresh-indicator">
            🔄 Dernière mise à jour: {datetime.now().strftime('%H:%M:%S')} | Actualisation auto dans 5s
        </div>
    </div>
</body>
</html>"""
    return web.Response(text=html, content_type='text/html')

def generate_predictions_html():
    """Génère le HTML pour la liste des prédictions"""
    if not predictions_history:
        return '<div style="text-align: center; padding: 40px; opacity: 0.7;">Aucune prédiction enregistrée</div>'
    
    html = ''
    for item in reversed(predictions_history[-50:]):
        if item['type'] == 'prediction':
            status = item.get('status', 'pending')
            status_class = f'prediction-{status}'
            status_text = {
                'won': '✅ GAGNÉ',
                'lost': '❌ PERDU',
                'pending': '⏳ EN ATTENTE'
            }.get(status, status)
            
            status_color = get_status_color(status)
            
            checks_html = ''
            if item.get('checks'):
                checks_html = '<div class="checks-list">'
                for check in item['checks']:
                    found_class = 'check-found' if check.get('found') else 'check-not-found'
                    found_text = '✓ Trouvé' if check.get('found') else '✗ Non trouvé'
                    checks_html += f'''
                        <div class="check-item {found_class}">
                            Check {check['check_number']}: #{check['game_number']} 
                            (attendu: {check['expected_suit']}, trouvé: {', '.join(check['suits_found']) or 'rien'}) 
                            - {found_text}
                        </div>
                    '''
                checks_html += '</div>'
            
            html += f'''
                <div class="prediction-item {status_class}">
                    <div class="prediction-header">
                        <div>
                            <span class="prediction-number">Prédiction #{item['game_number']}</span>
                            <span class="prediction-suit">{item['suit']}</span>
                        </div>
                        <span class="prediction-status" style="background: {status_color};">
                            {status_text}
                        </span>
                    </div>
                    <div class="timestamp">Base: #{item['base_game']} | Envoi: {format_time(item['timestamp'])}</div>
                    {checks_html}
                </div>
            '''
            
        elif item['type'] == 'source_message':
            html += f'''
                <div class="prediction-item source-message">
                    <div class="prediction-header">
                        <span class="prediction-number">📩 Message Source #{item['game_number']}</span>
                        <span class="timestamp">{format_time(item['timestamp'])}</span>
                    </div>
                    <div class="message-text">{item['message']}</div>
                    <div style="margin-top: 5px; font-size: 0.85em;">
                        {'⏰ En édition' if item.get('is_editing') else ''} 
                        {'✅ Finalisé' if item.get('is_finalized') else ''}
                    </div>
                </div>
            '''
    
    return html

async def web_api_stats(request):
    """API JSON pour les stats"""
    total_pred = sum(1 for p in predictions_history if p['type'] == 'prediction')
    won = sum(1 for p in predictions_history if p['type'] == 'prediction' and p.get('status') == 'won')
    lost = sum(1 for p in predictions_history if p['type'] == 'prediction' and p.get('status') == 'lost')
    pending = sum(1 for p in predictions_history if p['type'] == 'prediction' and p.get('status') == 'pending')
    
    data = {
        'current_game': current_game_number,
        'predictions_enabled': predictions_enabled,
        'is_paused': pause_config['is_paused'],
        'pause_count': pause_config['predictions_count'],
        'stats': {
            'total': total_pred,
            'won': won,
            'lost': lost,
            'pending': pending,
            'win_rate': (won / (won + lost) * 100) if (won + lost) > 0 else 0
        },
        'current_verification': {
            'predicted_number': verification_state['predicted_number'],
            'predicted_suit': verification_state['predicted_suit'],
            'current_check': verification_state['current_check'],
            'status': verification_state['status']
        } if verification_state['predicted_number'] else None,
        'last_update': datetime.now().isoformat()
    }
    
    return web.json_response(data)

async def start_web():
    app = web.Application()
    app.router.add_get('/', web_index)
    app.router.add_get('/api/stats', web_api_stats)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, '0.0.0.0', PORT).start()
    logger.info(f"🌐 Dashboard web démarré sur le port {PORT}")

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
    logger.info(f"⏸️ Cycle pause: {cycle_mins} min")
    logger.info(f"⏸️ Position cycle: {(pause_config['current_index'] % len(cycle_mins)) + 1}/{len(cycle_mins)}")
    logger.info(f"🌐 Dashboard: http://localhost:{PORT}")
    logger.info("=" * 60)
    
    await client.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
