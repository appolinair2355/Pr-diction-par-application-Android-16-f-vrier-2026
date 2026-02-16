"""
Logique du bot Telegram
"""
import os
import re
import logging
from datetime import datetime, timedelta
from collections import deque
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)

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

state = BotState()

def extract_game_number(message: str):
    match = re.search(r"#N\s*(\d+)", message, re.IGNORECASE)
    if match:
        return int(match.group(1))
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

def get_predicted_suit(missing_suit: str, suit_mapping: dict) -> str:
    return suit_mapping.get(missing_suit, missing_suit)

def add_prediction_to_history(game_number, suit, status='⏳', rattrapage=0):
    prediction_data = {
        'game_number': game_number,
        'suit': suit,
        'status': status,
        'rattrapage': rattrapage,
        'timestamp': datetime.now().isoformat(),
        'time_str': datetime.now().strftime('%H:%M:%S')
    }
    
    for i, pred in enumerate(state.prediction_history):
        if pred['game_number'] == game_number and pred['rattrapage'] == rattrapage:
            state.prediction_history[i] = prediction_data
            return
    
    state.prediction_history.append(prediction_data)
    if status == '⏳':
        state.total_predictions += 1

def update_prediction_in_history(game_number, new_status):
    for pred in state.prediction_history:
        if pred['game_number'] == game_number:
            old_status = pred['status']
            pred['status'] = new_status
            
            if '✅' in new_status and '✅' not in old_status:
                state.won_predictions += 1
            elif '❌' in new_status and '❌' not in old_status:
                state.lost_predictions += 1
            break

def get_win_rate():
    finished = state.won_predictions + state.lost_predictions
    if finished == 0:
        return 0
    return round((state.won_predictions / finished) * 100, 1)

def should_trigger_prediction(game_number):
    if game_number <= state.last_processed_number:
        return False
    
    state.last_processed_number = game_number
    
    if state.waiting_for_odd and game_number % 2 == 1:
        state.waiting_for_odd = False
        return True
    
    if game_number % 2 == 0:
        state.waiting_for_odd = True
        logger.info(f"Numéro pair {game_number} détecté, attente impair...")
    
    return False

async def send_prediction_to_channel(target_game: int, predicted_suit: str, 
                                     base_game: int, rattrapage=0, 
                                     original_game=None, config=None):
    try:
        if rattrapage > 0:
            state.pending_predictions[target_game] = {
                'message_id': 0,
                'suit': predicted_suit,
                'base_game': base_game,
                'status': '🔮',
                'rattrapage': rattrapage,
                'original_game': original_game,
                'created_at': datetime.now().isoformat()
            }
            add_prediction_to_history(target_game, predicted_suit, '🔮', rattrapage)
            return 0

        prediction_msg = f"""🎰 PRÉDICTION #{target_game}
🎯 Couleur: {config['SUIT_DISPLAY'].get(predicted_suit, predicted_suit)} {predicted_suit}[R+3]
⏳ En attente de vérification..."""
        
        msg_id = 0
        message_sent = False

        if config['PREDICTION_CHANNEL_ID']:
            try:
                pred_msg = await state.client.send_message(
                    config['PREDICTION_CHANNEL_ID'], 
                    prediction_msg
                )
                msg_id = pred_msg.id
                message_sent = True
            except Exception as e:
                logger.error(f"Échec envoi: {e}")

        state.pending_predictions[target_game] = {
            'message_id': msg_id,
            'suit': predicted_suit,
            'base_game': base_game,
            'status': '⏳',
            'check_count': 0,
            'rattrapage': 0,
            'created_at': datetime.now().isoformat()
        }

        add_prediction_to_history(target_game, predicted_suit, '⏳', 0)
        return msg_id

    except Exception as e:
        logger.error(f"Erreur send_prediction: {e}")
        return None

def queue_prediction(target_game: int, predicted_suit: str, 
                     base_game: int, rattrapage=0, original_game=None):
    if target_game in state.queued_predictions:
        return False
    if target_game in state.pending_predictions and rattrapage == 0:
        return False

    state.queued_predictions[target_game] = {
        'target_game': target_game,
        'predicted_suit': predicted_suit,
        'base_game': base_game,
        'rattrapage': rattrapage,
        'original_game': original_game,
        'queued_at': datetime.now().isoformat()
    }
    return True

async def check_and_send_queued_predictions(current_game: int, config=None):
    state.current_game_number = current_game
    sorted_queued = sorted(state.queued_predictions.keys())
    
    for target_game in sorted_queued:
        pred_data = state.queued_predictions.pop(target_game)
        await send_prediction_to_channel(
            pred_data['target_game'],
            pred_data['predicted_suit'],
            pred_data['base_game'],
            pred_data.get('rattrapage', 0),
            pred_data.get('original_game'),
            config
        )

async def update_prediction_status(game_number: int, new_status: str, config=None):
    try:
        if game_number not in state.pending_predictions:
            return False

        pred = state.pending_predictions[game_number]
        message_id = pred['message_id']
        suit = pred['suit']

        if '✅' in new_status:
            result_emoji = '🎉'
            result_text = 'GAGNÉ!'
        elif '❌' in new_status:
            result_emoji = '💔'
            result_text = 'PERDU'
        else:
            result_emoji = '⏳'
            result_text = 'EN COURS'

        updated_msg = f"""🎰 PRÉDICTION #{game_number}
🎯 Couleur: {config['SUIT_DISPLAY'].get(suit, suit)} {suit}
{result_emoji} Résultat: {result_text}"""

        if config['PREDICTION_CHANNEL_ID'] and message_id > 0:
            try:
                await state.client.edit_message(
                    config['PREDICTION_CHANNEL_ID'],
                    message_id,
                    updated_msg
                )
            except Exception as e:
                logger.error(f"Erreur mise à jour: {e}")

        update_prediction_in_history(game_number, new_status)

        # Logique blocage
        if suit not in state.suit_results_history:
            state.suit_results_history[suit] = []

        state.suit_results_history[suit].append(new_status)
        if len(state.suit_results_history[suit]) > 3:
            state.suit_results_history[suit].pop(0)

        if len(state.suit_results_history[suit]) == 3:
            if '❌' in state.suit_results_history[suit] or \
               all('✅' in r for r in state.suit_results_history[suit]):
                block_until = datetime.now() + timedelta(minutes=5)
                state.suit_block_until[suit] = block_until
                state.suit_consecutive_counts[suit] = 0
            state.suit_results_history[suit] = []

        pred['status'] = new_status

        if new_status in ['✅0️⃣', '✅1️⃣', '✅2️⃣', '✅3️⃣', '❌']:
            del state.pending_predictions[game_number]

        return True
    except Exception as e:
        logger.error(f"Erreur update_status: {e}")
        return False

async def check_prediction_result(game_number: int, first_group: str, config=None):
    if game_number in state.pending_predictions:
        pred = state.pending_predictions[game_number]
        if pred.get('rattrapage', 0) == 0:
            target_suit = pred['suit']
            if has_suit_in_group(first_group, target_suit):
                await update_prediction_status(game_number, '✅0️⃣', config)
                return
            else:
                next_target = game_number + 1
                queue_prediction(next_target, target_suit, 
                               pred['base_game'], rattrapage=1, 
                               original_game=game_number)

    for target_game, pred in list(state.pending_predictions.items()):
        if target_game == game_number and pred.get('rattrapage', 0) > 0:
            original_game = pred.get('original_game', 
                                    target_game - pred['rattrapage'])
            target_suit = pred['suit']
            rattrapage_actuel = pred['rattrapage']

            if has_suit_in_group(first_group, target_suit):
                await update_prediction_status(
                    original_game, 
                    f'✅{rattrapage_actuel}️⃣',
                    config
                )
                if target_game != original_game:
                    del state.pending_predictions[target_game]
                return
            else:
                if rattrapage_actuel < 3:
                    next_rattrapage = rattrapage_actuel + 1
                    next_target = game_number + 1
                    queue_prediction(next_target, target_suit,
                                   pred['base_game'],
                                   rattrapage=next_rattrapage,
                                   original_game=original_game)
                    del state.pending_predictions[target_game]
                else:
                    await update_prediction_status(original_game, '❌', config)
                    if target_game != original_game:
                        del state.pending_predictions[target_game]
                return

def can_predict_suit(predicted_suit: str) -> tuple[bool, str]:
    now = datetime.now()

    if state.last_predicted_suit and state.last_predicted_suit != predicted_suit:
        if state.last_predicted_suit in state.suit_consecutive_counts:
            state.suit_consecutive_counts[state.last_predicted_suit] = 0
            if state.last_predicted_suit in state.suit_block_until:
                del state.suit_block_until[state.last_predicted_suit]
        state.suit_consecutive_counts[predicted_suit] = 0
        return True, ""

    if predicted_suit in state.suit_block_until:
        block_until = state.suit_block_until[predicted_suit]
        if now < block_until:
            remaining = block_until - now
            return False, f"Bloqué {remaining.seconds//60}min"

    current_count = state.suit_consecutive_counts.get(predicted_suit, 0)
    if current_count >= 3:
        return False, "Max 3 atteint"

    return True, ""

def increment_suit_counter(predicted_suit: str):
    now = datetime.now()
    if predicted_suit not in state.suit_consecutive_counts or \
       state.suit_consecutive_counts.get(predicted_suit, 0) == 0:
        state.suit_first_prediction_time[predicted_suit] = now
        state.suit_consecutive_counts[predicted_suit] = 1
    else:
        state.suit_consecutive_counts[predicted_suit] += 1
    state.last_predicted_suit = predicted_suit

async def process_stats_message(message_text: str, config=None):
    stats = parse_stats_message(message_text)
    if not stats:
        return

    pairs = [('♦', '♠'), ('♥', '♣')]

    for s1, s2 in pairs:
        if s1 in stats and s2 in stats:
            v1, v2 = stats[s1], stats[s2]
            diff = abs(v1 - v2)

            if diff >= 6:
                predicted_suit = s1 if v1 < v2 else s2

                can_predict, reason = can_predict_suit(predicted_suit)
                if not can_predict:
                    return False

                if state.last_source_game_number > 0:
                    target_game = state.last_source_game_number + 1
                    
                    if should_trigger_prediction(state.last_source_game_number):
                        if queue_prediction(target_game, predicted_suit,
                                          state.last_source_game_number):
                            increment_suit_counter(predicted_suit)
                    else:
                        queue_prediction(target_game, predicted_suit,
                                       state.last_source_game_number)
                        increment_suit_counter(predicted_suit)
                return

def is_message_finalized(message: str) -> bool:
    return '✅' in message or '🔰' in message or \
           '▶️' in message or 'FIN' in message.upper()

async def process_source_message(message_text: str, chat_id: int,
                                 source_ids: dict, is_finalized=False,
                                 config=None):
    try:
        if chat_id == source_ids['SOURCE_CHANNEL_2_ID']:
            await process_stats_message(message_text, config)
            return

        game_number = extract_game_number(message_text)
        if game_number is None:
            return

        state.current_game_number = game_number
        state.last_source_game_number = game_number

        message_hash = f"{game_number}_{message_text[:30]}"
        if message_hash in state.processed_messages:
            return
        state.processed_messages.add(message_hash)

        if should_trigger_prediction(game_number):
            await check_and_send_queued_predictions(game_number, config)

        if is_finalized:
            groups = extract_parentheses_groups(message_text)
            if len(groups) >= 1:
                first_group = groups[0]
                await check_prediction_result(game_number, first_group, config)

    except Exception as e:
        logger.error(f"Erreur process_source: {e}")

async def handle_message(event, config, source_ids):
    try:
        chat = await event.get_chat()
        chat_id = chat.id
        if hasattr(chat, 'broadcast') and chat.broadcast:
            if not str(chat_id).startswith('-100'):
                chat_id = int(f"-100{abs(chat_id)}")

        message_text = event.message.message
        
        if chat_id == source_ids['SOURCE_CHANNEL_2_ID']:
            await process_source_message(message_text, chat_id, 
                                        source_ids, False, config)
            return
            
        if chat_id == source_ids['SOURCE_CHANNEL_ID']:
            await process_source_message(message_text, chat_id,
                                        source_ids, False, config)
            
            if is_message_finalized(message_text):
                await process_source_message(message_text, chat_id,
                                            source_ids, True, config)

    except Exception as e:
        logger.error(f"Erreur handle_message: {e}")

async def handle_edited_message(event, config, source_ids):
    try:
        chat = await event.get_chat()
        chat_id = chat.id
        if hasattr(chat, 'broadcast') and chat.broadcast:
            if not str(chat_id).startswith('-100'):
                chat_id = int(f"-100{abs(chat_id)}")

        if chat_id == source_ids['SOURCE_CHANNEL_ID']:
            message_text = event.message.message
            if is_message_finalized(message_text):
                await process_source_message(message_text, chat_id,
                                            source_ids, True, config)
    except Exception as e:
        logger.error(f"Erreur handle_edited: {e}")

def setup_handlers(client, config, source_ids):
    state.client = client
    
    @client.on(events.NewMessage(pattern='/start'))
    async def cmd_start(event):
        if event.is_group or event.is_channel:
            return
        await event.respond("🤖 Bot actif!\nCommandes: /status, /set_a")

    @client.on(events.NewMessage(pattern=r'^/set_a (\d+)$'))
    async def cmd_set_a(event):
        if event.is_group or event.is_channel:
            return
        # Gérer via web_server pour admin check
        pass

    @client.on(events.NewMessage())
    async def on_message(event):
        await handle_message(event, config, source_ids)

    @client.on(events.MessageEdited())
    async def on_edited(event):
        await handle_edited_message(event, config, source_ids)
