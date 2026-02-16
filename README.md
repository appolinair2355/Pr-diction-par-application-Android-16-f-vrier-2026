# Bot Prédiction Baccarat

Bot Telegram de prédiction automatique pour Baccarat.

## Configuration

1. Remplir `config.py` avec vos identifiants
2. Déployer sur Render ou VPS

## Commandes Admin

- `/start` - Démarrer le bot
- `/stop` - Arrêter les prédictions
- `/resume` - Reprendre les prédictions
- `/forcestop` - Débloquer le système
- `/predictinfo` - Statut système
- `/clearverif` - Effacer vérification bloquée
- `/setchannel` - Configurer les canaux
- `/pausecycle` - Modifier cycle de pause
- `/bilan` - Statistiques
- `/reset` - Reset stats

## Dashboard Web

Accessible sur l'URL Render (ex: https://votre-bot.onrender.com)

## Variables d'environnement (Render)

- `API_ID` - Votre API ID Telegram
- `API_HASH` - Votre API Hash Telegram
- `BOT_TOKEN` - Token du bot (@BotFather)
- `ADMIN_ID` - Votre ID Telegram
- `PORT` - Port du serveur web (10000)
- 
