#!/usr/bin/env python3
"""
Point d'entrée principal - démarre sur le port Render
"""
import os
import sys
import asyncio
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Importer les modules
from config import API_ID, API_HASH, BOT_TOKEN, PORT
from database import init_db
from bot_logic import setup_handlers, state as bot_state
from web_server import setup_web_app
from telethon import TelegramClient
from telethon.sessions import StringSession

async def start_bot():
    """Démarre le bot Telegram"""
    if not all([API_ID, API_HASH, BOT_TOKEN]):
        logger.error("Configuration Telegram incomplète!")
        return None
    
    session_string = os.getenv('TELEGRAM_SESSION', '')
    client = TelegramClient(
        StringSession(session_string),
        API_ID,
        API_HASH
    )
    
    try:
        await client.start(bot_token=BOT_TOKEN)
        logger.info("✅ Bot Telegram connecté")
        
        # Setup handlers
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
                bot_state.prediction_channel_ok = True
                logger.info("✅ Canal prédiction accessible")
            except Exception as e:
                logger.warning(f"⚠️ Canal prédiction inaccessible: {e}")
        
        return client
        
    except Exception as e:
        logger.error(f"❌ Erreur démarrage bot: {e}")
        return None

async def start_web_server(bot_client):
    """Démarre le serveur web sur le port Render"""
    from aiohttp import web
    
    app = setup_web_app(bot_client)
    runner = web.AppRunner(app)
    
    await runner.setup()
    
    # Render fournit le port via variable d'environnement
    port = int(os.getenv('PORT', PORT))
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    await site.start()
    logger.info(f"🌐 Serveur web démarré sur http://0.0.0.0:{port}")
    
    return runner

async def main():
    """Fonction principale"""
    logger.info("🚀 Démarrage de l'application...")
    
    # Initialiser la base de données
    init_db()
    logger.info("✅ Base de données initialisée")
    
    # Démarrer le bot Telegram
    bot_client = await start_bot()
    
    # Démarrer le serveur web (bloque ici)
    web_runner = await start_web_server(bot_client)
    
    if bot_client:
        logger.info("✅ Application complètement démarrée!")
        # Garder le bot en vie
        await bot_client.run_until_disconnected()
    else:
        # Si pas de bot, maintenir le serveur web
        while True:
            await asyncio.sleep(3600)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Arrêt demandé par l'utilisateur")
    except Exception as e:
        logger.error(f"💥 Erreur fatale: {e}")
        sys.exit(1)
