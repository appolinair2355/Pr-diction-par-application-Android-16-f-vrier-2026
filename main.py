#!/usr/bin/env python3
"""
Point d'entrée principal - démarre sur le port Render
"""
import os
import sys
import asyncio
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

from config import API_ID, API_HASH, BOT_TOKEN, PORT, ADMIN_ID
from database import init_db
from web_server import setup_web_app

# Variables globales pour partager avec le bot
bot_client = None
admin_bot_client = None  # Client séparé pour les notifications admin

async def start_user_bot():
    """Démarre le bot principal pour les canaux"""
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from bot_logic import setup_handlers
    
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        logger.error("❌ Configuration Telegram incomplète!")
        return None
    
    session_string = os.getenv('TELEGRAM_SESSION', '')
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    
    try:
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Bot utilisateur connecté")
        
        # Setup handlers avec les IDs de canaux
        from config import (SOURCE_CHANNEL_ID, SOURCE_CHANNEL_2_ID,
                          PREDICTION_CHANNEL_ID, SUIT_MAPPING, SUIT_DISPLAY)
        
        config = {
            'PREDICTION_CHANNEL_ID': PREDICTION_CHANNEL_ID,
            'SUIT_MAPPING': SUIT_MAPPING,
            'SUIT_DISPLAY': SUIT_DISPLAY
        }
        
        source_ids = {
            'SOURCE_CHANNEL_ID': SOURCE_CHANNEL_ID,
            'SOURCE_CHANNEL_2_ID': SOURCE_CHANNEL_2_ID
        }
        
        setup_handlers(client, config, source_ids)
        
        # Test canal prédiction
        if PREDICTION_CHANNEL_ID:
            try:
                await client.get_entity(PREDICTION_CHANNEL_ID)
                logger.info("✅ Canal prédiction accessible")
            except Exception as e:
                logger.warning(f"⚠️ Canal prédition: {e}")
        
        return client
        
    except Exception as e:
        logger.error(f"❌ Erreur bot utilisateur: {e}")
        return None

async def start_admin_bot():
    """Démarre un bot séparé pour les notifications admin"""
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    
    if not all([API_ID, API_HASH]) or not ADMIN_ID:
        logger.warning("⚠️ Pas de configuration pour notifications admin")
        return None
    
    # Utiliser le même BOT_TOKEN mais pour envoyer des messages
    session_string = os.getenv('TELEGRAM_SESSION_ADMIN', '')
    client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
    
    try:
        # Démarrer avec le token du bot existant
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Bot admin notifications prêt")
        
        # Test envoi message à l'admin
        try:
            await client.send_message(ADMIN_ID, "🤖 Bot de notifications démarré!\n\nCommandes disponibles:\n/list - Liste des utilisateurs\n/add_time <email> <jours> - Ajouter du temps\n/block <email> - Bloquer utilisateur\n/unblock <email> - Débloquer utilisateur")
            logger.info("✅ Message test envoyé à l'admin")
        except Exception as e:
            logger.error(f"❌ Impossible d'envoyer à l'admin {ADMIN_ID}: {e}")
            logger.error("Vérifiez que vous avez démarré une conversation avec le bot")
        
        return client
        
    except Exception as e:
        logger.error(f"❌ Erreur bot admin: {e}")
        return None

async def start_web_server(bot_clients):
    """Démarre le serveur web"""
    from aiohttp import web
    
    app = setup_web_app(bot_clients)
    runner = web.AppRunner(app)
    
    await runner.setup()
    
    port = int(os.getenv('PORT', PORT))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    await site.start()
    logger.info(f"🌐 Serveur web: http://0.0.0.0:{port}")
    
    return runner

async def main():
    logger.info("🚀 Démarrage...")
    
    # Initialiser DB
    init_db()
    logger.info("✅ Base de données OK")
    
    # Démarrer les deux bots en parallèle
    global bot_client, admin_bot_client
    
    bot_client = await start_user_bot()
    admin_bot_client = await start_admin_bot()
    
    # Stocker pour les modules
    import web_server
    web_server.bot_client = bot_client
    web_server.admin_bot_client = admin_bot_client
    
    # Démarrer serveur web
    web_runner = await start_web_server({
        'user': bot_client,
        'admin': admin_bot_client
    })
    
    # Garder l'application en vie
    if bot_client:
        logger.info("✅ Application démarrée!")
        await bot_client.run_until_disconnected()
    else:
        while True:
            await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Arrêt")
    except Exception as e:
        logger.error(f"💥 Erreur fatale: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
