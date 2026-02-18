"""
Logique du bot Telegram - VERSION CORRIGÉE AVEC PRÉDICTION AUTOMATIQUE
Canal: -1003579400443
"""
import os
import re
import logging
from datetime import datetime, timedelta
from collections import deque
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

# ID Canal prédiction (fixe)
PREDICTION_CHANNEL_ID = -1003579400443

# Variables globales partagées
class BotState:
    def __init__(self):
        self.pending_predictions = {}
        self.queued_predictions = {}
        self.processed_messages = set()
        self.current_game_number = 0
        self.last_source_game_number = 0
        self.prediction_history = deque(maxlen=100)
        self.total_predictions = 0
        self.won_predictions = 0
        self.lost_predictions = 0
        self.last_processed_number = 0
        self.waiting_for_odd = False
        self.suit_consecutive_counts = {}
        self.suit_results_history = {}
        self.suit_block_until = {}
        self.last_predicted_suit = None
        self.suit_first_prediction_time = {}
        self.client = None
        self.prediction_channel_ok = False
        # 🔧 NOUVEAU: État pour prédiction automatique
        self.verification_state = {
            'predicted_number': None,
            'predicted_suit': None,
            'current_check': 0,
            'message_id': None,
            'status': None,
            'base_game': None
        }
        self.predictions_enabled = True
        self.pause_config = {
            'cycle': [180, 300, 240],  # 3min, 5min, 4min
            'current_index': 0,
            'predictions_count': 0,
            'is_paused': False,
            'pause_end_time': None
        }

state = BotState()

# ============================================================
# FONCTIONS DE BASE (conservées de votre code)
# ============================================================

def extract_game_number(message: str):
    """Extrait le numéro du jeu du message source"""
    # Recherche format #N123 ou #N 123
    match = re.search(r"#N\s*(\d+)", message, re.IGNORECASE)
    if match:
        return int(match.group(1))
    
    # Recherche format ( #N123 )
    match = re.search(r"\(\s*#N\s*(\d+)", message, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # Fallback sur un numéro de 3-4 chiffres
    match = re.search(r"\b(\d{3,4})\b", message)
    if match:
        return int(match.group(1))
    return None

def parse_stats_message(message: str):
    stats = {}
    patterns = {
        '♠': r'♠️?\s*:\s*(\d+)',
        '♥': r'♥️?\s*:\s*(\d+)',
        '♦': r'♦️?\s*:\s*(\d+)',
        '♣': r'♣️?\s*:\s*(\d+)'
    }
    for suit, pattern in patterns.items():
        match = re.search(pattern, message)
        if match:
            stats[suit] = int(match.group(1))
    return stats

def extract_parentheses_groups(message: str):
    return re.findall(r"\(([^)]*)\)", message)

def normalize_suits(group_str: str) -> str:
    normalized = group_str.replace('❤️', '♥').replace('❤', '♥').replace('♥️', '♥')
    normalized = normalized.replace('♠️', '♠').replace('♦️', '♦').replace('♣️', '♣')
    return normalized

def has_suit_in_group(group_str: str, target_suit: str) -> bool:
    normalized = normalize_suits(group_str)
    target_normalized = normalize_suits(target_suit)
    suits = ['♠', '♥', '♦', '♣']
    for suit in suits:
        if suit in target_normalized and suit in normalized:
            return True
    return False

# ============================================================
# SYSTÈME PRÉDICTION AUTOMATIQUE (NOUVEAU)
# ============================================================

def get_valid_even_numbers():
    """Génère les pairs valides: 6-1436, pairs, ne finissant pas par 0"""
    return [n for n in range(6, 1437) if n % 2 == 0 and n % 10 != 0]

VALID_EVEN_NUMBERS = get_valid_even_numbers()
SUIT_CYCLE = ['♥', '♦', '♣', '♠', '♦', '♥', '♠', '♣']
SUIT_DISPLAY = {'♥': '❤️ Cœur', '♦': '♦️ Carreau', '♣': '♣️ Trèfle', '♠': '♠️ Pique'}

def get_suit_for_number(number):
    """Retourne le costume pour un numéro pair valide"""
    if number not in VALID_EVEN_NUMBERS:
        return None
    idx = VALID_EVEN_NUMBERS.index(number) % len(SUIT_CYCLE)
    return SUIT_CYCLE[idx]

def is_trigger_number(number):
    """Déclencheur: impair finissant par 1,3,5,7 ET suivant est pair valide"""
    if number is None:
        return False
    if number % 2 == 0:
        return False
    last_digit = number % 10
    if last_digit not in [1, 3, 5, 7]:
        return False
    next_num = number + 1
    return next_num in VALID_EVEN_NUMBERS

def get_trigger_target(number):
    """Retourne le numéro pair à prédire"""
    if not is_trigger_number(number):
        return None
    return number + 1

async def send_prediction_to_channel(target_game: int, predicted_suit: str, base_game: int, config=None):
    """Envoie une prédiction au canal"""
    if not state.predictions_enabled:
        logger.warning("⛔ Prédictions désactivées")
        return None
    
    if state.verification_state['predicted_number'] is not None:
        logger.warning(f"⛔ Prédiction #{state.verification_state['predicted_number']} en cours")
        return None
    
    try:
        # Tenter de convertir en entier si possible (ID numérique)
        try:
            # Nettoyage de l'ID (certains utilisateurs mettent des espaces ou des tirets mal placés)
            clean_id = str(PREDICTION_CHANNEL_ID).strip()
            if clean_id.startswith('-100'):
                channel_id = int(clean_id)
            elif clean_id.isdigit():
                channel_id = int(f"-100{clean_id}")
            else:
                channel_id = clean_id
        except (ValueError, TypeError):
            channel_id = PREDICTION_CHANNEL_ID
        
        prediction_msg = f"""🎰 **PRÉDICTION #{target_game}**
🎯 **Couleur:** {SUIT_DISPLAY.get(predicted_suit, predicted_suit)}
⏳ **Statut:** EN ATTENTE DU RÉSULTAT..."""
        
        # S'assurer que le client a l'entité
        try:
            entity = await state.client.get_entity(channel_id)
            pred_msg = await state.client.send_message(entity, prediction_msg)
        except Exception as e:
            logger.error(f"❌ Erreur envoi (tentative fallback): {e}")
            # Fallback direct avec l'ID si get_entity échoue
            pred_msg = await state.client.send_message(channel_id, prediction_msg)
        
        state.verification_state = {
            'predicted_number': target_game,
            'predicted_suit': predicted_suit,
            'current_check': 0,
            'message_id': pred_msg.id,
            'channel_id': channel_id,
            'status': 'pending',
            'base_game': base_game
        }
        
        state.total_predictions += 1
        
        # Ajouter à l'historique
        prediction_data = {
            'game_number': target_game,
            'suit': predicted_suit,
            'status': '⏳',
            'timestamp': datetime.now().isoformat(),
            'time_str': datetime.now().strftime('%H:%M:%S')
        }
        state.prediction_history.append(prediction_data)
        
        logger.info(f"🚀 PRÉDICTION #{target_game} ({predicted_suit}) ENVOYÉE")
        return pred_msg.id
        
    except Exception as e:
        logger.error(f"❌ Erreur envoi prédiction: {e}")
        return None

async def update_prediction_status(status: str):
    """Met à jour le statut de la prédiction"""
    if state.verification_state['predicted_number'] is None:
        return False
    
    try:
        predicted_num = state.verification_state['predicted_number']
        predicted_suit = state.verification_state['predicted_suit']
        message_id = state.verification_state['message_id']
        channel_id = state.verification_state['channel_id']
        
        if status == "❌":
            status_text = "❌ PERDU"
            state.lost_predictions += 1
        else:
            status_text = f"{status} GAGNÉ"
            state.won_predictions += 1
        
        # Log to database
        from database import log_prediction
        log_prediction(predicted_num, predicted_suit, "WON" if "GAGNÉ" in status_text else "LOST")
        
        updated_msg = f"""🎰 **PRÉDICTION #{predicted_num}**
🎯 **Couleur:** {SUIT_DISPLAY.get(predicted_suit, predicted_suit)}
📊 **Statut:** {status_text}"""
        
        await state.client.edit_message(channel_id, message_id, updated_msg)
        
        # Mettre à jour l'historique
        for pred in state.prediction_history:
            if pred['game_number'] == predicted_num:
                pred['status'] = status
                break
        
        logger.info(f"✅ Prédiction #{predicted_num} mise à jour: {status}")
        
        # Reset état
        state.verification_state = {
            'predicted_number': None, 'predicted_suit': None,
            'current_check': 0, 'message_id': None,
            'channel_id': None, 'status': None, 'base_game': None
        }
        
        # S'assurer que le numéro actuel est mis à jour
        state.current_game_number = predicted_num
        state.last_source_game_number = predicted_num
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur mise à jour: {e}")
        return False

async def process_verification_step(game_number: int, first_group: str):
    """Traite une étape de vérification"""
    if state.verification_state['predicted_number'] is None:
        return
    
    predicted_num = state.verification_state['predicted_number']
    predicted_suit = state.verification_state['predicted_suit']
    current_check = state.verification_state['current_check']
    
    expected_number = predicted_num + current_check
    if game_number != expected_number:
        return
    
    suits = extract_suits_from_group(first_group)
    logger.info(f"🔍 Vérification #{game_number}: {suits}, attendu {predicted_suit}")
    
    if predicted_suit in suits:
        status = f"✅{current_check}️⃣"
        await update_prediction_status(status)
        return
    
    if current_check < 3:
        state.verification_state['current_check'] += 1
        next_num = predicted_num + state.verification_state['current_check']
        logger.info(f"❌ Check {current_check} échoué, prochain: #{next_num}")
    else:
        logger.info(f"💔 PERDU après 4 vérifications")
        await update_prediction_status("❌")

def extract_suits_from_group(group_str: str) -> list:
    """Extrait les costumes d'un groupe"""
    normalized = normalize_suits(group_str)
    return [s for s in ['♥', '♠', '♦', '♣'] if s in normalized]

async def check_and_launch_prediction(game_number: int):
    """Vérifie et lance une prédiction"""
    # Bloquer si prédiction en cours
    if state.verification_state['predicted_number'] is not None:
        logger.warning(f"⛔ BLOQUÉ: Prédiction en attente de vérification")
        return
    
    # Vérifier pause
    if state.pause_config['is_paused']:
        try:
            end_time = datetime.fromisoformat(state.pause_config['pause_end_time'])
            if datetime.now() < end_time:
                return
            state.pause_config['is_paused'] = False
            logger.info("🔄 Pause terminée")
        except:
            state.pause_config['is_paused'] = False
    
    # Vérifier déclencheur
    if not is_trigger_number(game_number):
        return
    
    target_num = get_trigger_target(game_number)
    if not target_num:
        return
    
    # Cycle de pause
    state.pause_config['predictions_count'] += 1
    if state.pause_config['predictions_count'] >= 5:
        cycle = state.pause_config['cycle']
        idx = state.pause_config['current_index'] % len(cycle)
        duration = cycle[idx]
        
        state.pause_config['is_paused'] = True
        state.pause_config['pause_end_time'] = (datetime.now() + timedelta(seconds=duration)).isoformat()
        state.pause_config['current_index'] += 1
        state.pause_config['predictions_count'] = 0
        
        minutes = duration // 60
        logger.info(f"⏸️ PAUSE: {minutes}min")
        
        try:
            await state.client.send_message(
                PREDICTION_CHANNEL_ID,
                f"⏸️ **PAUSE**\n⏱️ {minutes} minutes..."
            )
        except Exception as e:
            logger.error(f"Erreur message pause: {e}")
        
        return
    
    # Lancer prédiction
    suit = get_suit_for_number(target_num)
    if suit:
        await send_prediction_to_channel(target_num, suit, game_number)

# ============================================================
# TRAITEMENT MESSAGES SOURCE (MODIFIÉ)
# ============================================================

def is_message_finalized(message: str) -> bool:
    return '✅' in message or '🔰' in message or '▶️' in message or 'FIN' in message.upper()

def is_message_editing(message: str) -> bool:
    return message.strip().startswith('⏰')

async def process_source_message(message_text: str, chat_id: int, source_ids: dict, is_finalized=False, config=None):
    """Traite les messages du canal source avec prédiction automatique"""
    try:
        # Log pour debug
        logger.info(f"Traitement message source: chat_id={chat_id}, attendu={source_ids.get('SOURCE_CHANNEL_ID')}")
        
        # Vérifier si c'est le canal source
        if str(chat_id) != str(source_ids.get('SOURCE_CHANNEL_ID')):
            return
        
        game_number = extract_game_number(message_text)
        logger.info(f"Numéro de jeu extrait: {game_number}")
        if game_number is None:
            return
        
        state.current_game_number = game_number
        state.last_source_game_number = game_number
        
        # Éviter doublons
        message_hash = f"{game_number}_{message_text[:30]}"
        if message_hash in state.processed_messages:
            return
        state.processed_messages.add(message_hash)
        
        is_editing = is_message_editing(message_text)
        is_final = is_message_finalized(message_text)
        
        # Vérification prédiction en cours
        if state.verification_state['predicted_number'] is not None:
            predicted_num = state.verification_state['predicted_number']
            current_check = state.verification_state['current_check']
            expected_number = predicted_num + current_check
            
            if is_editing and game_number == expected_number:
                logger.info(f"⏳ Message #{game_number} en édition, attente")
                return
            
            if game_number == expected_number and (is_final or not is_editing):
                groups = extract_parentheses_groups(message_text)
                if groups:
                    await process_verification_step(game_number, groups[0])
            
            return  # Jamais de nouveau lancement si vérification en cours
        
        # Nouveau lancement
        await check_and_launch_prediction(game_number)
        
        # Vérifier résultat si finalisé
        if is_finalized:
            groups = extract_parentheses_groups(message_text)
            if len(groups) >= 1 and state.verification_state['predicted_number'] is not None:
                await process_verification_step(game_number, groups[0])
        
    except Exception as e:
        logger.error(f"Erreur process_source: {e}")
        import traceback
        logger.error(traceback.format_exc())

# ============================================================
# HANDLERS (conservés et modifiés)
# ============================================================

async def handle_message(event, config, source_ids):
    """Gestionnaire de messages principal"""
    try:
        chat = await event.get_chat()
        chat_id = chat.id
        if hasattr(chat, 'broadcast') and chat.broadcast:
            if not str(chat_id).startswith('-100'):
                chat_id = int(f"-100{abs(chat_id)}")
        
        message_text = event.message.message
        
        # Traiter uniquement le canal source
        if chat_id == source_ids.get('SOURCE_CHANNEL_ID'):
            is_final = is_message_finalized(message_text)
            await process_source_message(message_text, chat_id, source_ids, is_final, config)
        
    except Exception as e:
        logger.error(f"Erreur handle_message: {e}")

async def handle_edited_message(event, config, source_ids):
    """Gestionnaire des messages édités"""
    try:
        chat = await event.get_chat()
        chat_id = chat.id
        if hasattr(chat, 'broadcast') and chat.broadcast:
            if not str(chat_id).startswith('-100'):
                chat_id = int(f"-100{abs(chat_id)}")
        
        if chat_id == source_ids.get('SOURCE_CHANNEL_ID'):
            message_text = event.message.message
            await process_source_message(message_text, chat_id, source_ids, False, config)
            
    except Exception as e:
        logger.error(f"Erreur handle_edited: {e}")

# ============================================================
# COMMANDES ADMIN POUR PRÉDICTIONS
# ============================================================

def setup_handlers(client, config, source_ids):
    """Configure les gestionnaires d'événements"""
    state.client = client
    
    # 🔧 Update initial stats from database
    try:
        from database import get_prediction_stats
        won, lost = get_prediction_stats()
        state.won_predictions = won
        state.lost_predictions = lost
        state.total_predictions = won + lost
    except Exception as e:
        logger.error(f"Error loading stats: {e}")
    
    @client.on(events.NewMessage(pattern='/start'))
    async def cmd_start(event):
        if event.is_group or event.is_channel:
            return
        
        sender_id = event.sender_id
        admin_id = config.get('ADMIN_ID')
        
        # Log pour debug
        logger.info(f"Debug /start: sender_id={sender_id} (type={type(sender_id)}), admin_id={admin_id} (type={type(admin_id)})")
        
        if str(sender_id) == str(admin_id):
            await event.respond("""👑 **ADMIN**

Commandes:
/stop - Arrêter prédictions
/resume - Reprendre
/forcestop - Débloquer
/predictinfo - Statut
/clearverif - Effacer vérification
/pausecycle - Voir cycle pause
/bilan - Stats
/help - Aide""")
        else:
            await event.respond("🤖 Bot actif! Contactez l'admin pour accès.")
    
    @client.on(events.NewMessage(pattern='/stop'))
    async def cmd_stop(event):
        if str(event.sender_id) != str(config.get('ADMIN_ID')):
            return
        state.predictions_enabled = False
        await event.respond("🛑 Prédictions ARRÊTÉES")
    
    @client.on(events.NewMessage(pattern='/resume'))
    async def cmd_resume(event):
        if str(event.sender_id) != str(config.get('ADMIN_ID')):
            return
        state.predictions_enabled = True
        await event.respond("🚀 Prédictions REPRISES")
    
    @client.on(events.NewMessage(pattern='/forcestop'))
    async def cmd_forcestop(event):
        if str(event.sender_id) != str(config.get('ADMIN_ID')):
            return
        state.predictions_enabled = False
        old = state.verification_state['predicted_number']
        state.verification_state = {
            'predicted_number': None, 'predicted_suit': None,
            'current_check': 0, 'message_id': None,
            'channel_id': None, 'status': None, 'base_game': None
        }
        await event.respond(f"🚨 Arrêt forcé. Prédiction #{old} effacée." if old else "🚨 Système débloqué")
    
    @client.on(events.NewMessage(pattern='/predictinfo'))
    async def cmd_predictinfo(event):
        if str(event.sender_id) != str(config.get('ADMIN_ID')):
            return
        
        verif = state.verification_state
        verif_info = f"#{verif['predicted_number']} ({verif['predicted_suit']})" if verif['predicted_number'] else "Aucune"
        
        cycle_mins = [x//60 for x in state.pause_config['cycle']]
        idx = state.pause_config['current_index'] % len(cycle_mins)
        
        pause_status = "Non"
        if state.pause_config['is_paused']:
            try:
                end = datetime.fromisoformat(state.pause_config['pause_end_time'])
                remaining = int((end - datetime.now()).total_seconds())
                if remaining > 0:
                    pause_status = f"Oui ({remaining//60}min)"
            except:
                pass
        
        await event.respond(f"""📊 STATUT

🎯 Source: #{state.current_game_number}
🔍 Vérification: {verif_info}
🟢 Prédictions: {'ON' if state.predictions_enabled else 'OFF'}

⏸️ Pause: {pause_status}
• Compteur: {state.pause_config['predictions_count']}/4
• Cycle: {cycle_mins} min
• Position: {idx+1}/{len(cycle_mins)}""")
    
    @client.on(events.NewMessage(pattern='/clearverif'))
    async def cmd_clearverif(event):
        if str(event.sender_id) != str(config.get('ADMIN_ID')):
            return
        old = state.verification_state['predicted_number']
        state.verification_state = {
            'predicted_number': None, 'predicted_suit': None,
            'current_check': 0, 'message_id': None,
            'channel_id': None, 'status': None, 'base_game': None
        }
        await event.respond(f"✅ Vérification #{old} effacée" if old else "✅ Système libre")
    
    @client.on(events.NewMessage(pattern=r'^/pausecycle'))
    async def cmd_pausecycle(event):
        if str(event.sender_id) != str(config.get('ADMIN_ID')):
            return
        
        parts = event.message.text.split()
        cycle_mins = [x//60 for x in state.pause_config['cycle']]
        idx = state.pause_config['current_index'] % len(cycle_mins)
        
        if len(parts) == 1:
            await event.respond(f"""⏸️ CYCLE PAUSE

Cycle: {cycle_mins} min
Position: {idx+1}/{len(cycle_mins)}
Compteur: {state.pause_config['predictions_count']}/4

Modifier: /pausecycle 3,5,4""")
        else:
            try:
                new_mins = [int(x) for x in parts[1].split(',') if x.strip()]
                if new_mins and all(x > 0 for x in new_mins):
                    state.pause_config['cycle'] = [x * 60 for x in new_mins]
                    state.pause_config['current_index'] = 0
                    await event.respond(f"✅ Cycle: {new_mins} min")
                else:
                    await event.respond("❌ Nombres positifs requis")
            except Exception as e:
                await event.respond(f"❌ Erreur: {e}")
    
    @client.on(events.NewMessage(pattern='/bilan'))
    async def cmd_bilan(event):
        if str(event.sender_id) != str(config.get('ADMIN_ID')):
            return
        
        if state.total_predictions == 0:
            await event.respond("📊 Aucune prédiction")
            return
        
        win_rate = (state.won_predictions / state.total_predictions) * 100 if state.total_predictions > 0 else 0
        
        await event.respond(f"""📊 BILAN

🎯 Total: {state.total_predictions}
✅ Gagnés: {state.won_predictions} ({win_rate:.1f}%)
❌ Perdus: {state.lost_predictions}""")
    
    @client.on(events.NewMessage(pattern='/help'))
    async def cmd_help(event):
        if event.sender_id != config.get('ADMIN_ID'):
            return
        await event.respond("""📖 COMMANDES

/stop /resume - Contrôle
/forcestop - Débloquer
/predictinfo - Statut
/clearverif - Effacer
/pausecycle - Cycle pause
/bilan - Stats""")
    
    @client.on(events.NewMessage())
    async def on_message(event):
        await handle_message(event, config, source_ids)

    @client.on(events.MessageEdited())
    async def on_edited_message(event):
        await handle_edited_message(event, config, source_ids)
    
    @client.on(events.MessageEdited())
    async def on_edited(event):
        await handle_edited_message(event, config, source_ids)
