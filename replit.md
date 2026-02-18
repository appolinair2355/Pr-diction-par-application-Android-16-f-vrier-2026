# Prédicteur Baccarat

## Overview
A Telegram bot and web application for Baccarat predictions. The app monitors Telegram channels for game data, generates predictions, and publishes them to a prediction channel. It also provides a web interface for users to view predictions, with admin management capabilities.

## Project Architecture
- **Language**: Python 3.11
- **Web Framework**: aiohttp (async web server)
- **Templating**: Jinja2
- **Database**: PostgreSQL (External Render DB)
- **Telegram**: Telethon library for bot functionality

## Key Files
- `main.py` - Entry point, starts bot and web server on port 5000
- `config.py` - Configuration (Telegram API credentials, channel IDs, admin settings)
- `web_server.py` - aiohttp web routes (auth, admin, predictions API)
- `bot_logic.py` - Telegram bot prediction logic
- `database.py` - PostgreSQL database management (users, sessions, predictions)
- `auth.py` - User authentication (register, login, sessions)
- `templates/` - Jinja2 HTML templates
- `static/` - CSS and JS assets

## Environment Variables Required
- `API_ID` - Telegram API ID
- `API_HASH` - Telegram API Hash
- `BOT_TOKEN` - Telegram Bot Token
- `ADMIN_ID` - Telegram Admin User ID
- `SOURCE_CHANNEL_ID` - Source channel for game data
- `SOURCE_CHANNEL_2_ID` - Secondary source channel
- `PREDICTION_CHANNEL_ID` - Channel to publish predictions
- `TELEGRAM_SESSION` - Telegram session string (optional)
- `TELEGRAM_SESSION_ADMIN` - Admin bot session string (optional)

## Recent Changes
- 2026-02-18: Migrated to PostgreSQL and updated prediction cycle
  - Database changed from SQLite to PostgreSQL (external host)
  - Prediction cycle updated: 4 predictions followed by a 3-minute pause
  - UI updated to show "X/4" for remaining predictions and real-time countdown for pause
  - Added `telegram_id` and `plain_password` fields to user records
