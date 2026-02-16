"""
Serveur web aiohttp
"""
import json
import logging
from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime
from telethon import events  # 🔧 IMPORT MANQUANT!

from database import (
    add_subscription_time, get_all_users, block_user, 
    unblock_user, get_user_by_email
)
from auth import (
    register_user, login_user, check_session, logout_user,
    check_admin_credentials, has_active_subscription
)
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# Variables globales pour les bots
bot_client = None
admin_bot_client = None

env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=select_autoescape(['html', 'xml'])
)

def render_template(template_name, **context):
    template = env.get_template(template_name)
    return template.render(**context)

async def notify_admin_new_user(user):
    """Envoie notification à l'admin via Telegram"""
    if not admin_bot_client or not ADMIN_ID:
        logger.warning("⚠️ Pas de bot admin configuré pour notification")
        return False
    
    try:
        msg = f"""🆕 NOUVEL INSCRIPTION!

👤 Nom: {user['first_name']} {user['last_name']}
📧 Email: {user['email']}
📅 Date: {datetime.now().strftime('%d/%m/%Y %H:%M')}

⚡ Actions rapides:
• /add_time {user['email']} 7
• /add_time {user['email']} 30
• /block {user['email']}"""
        
        await admin_bot_client.send_message(int(ADMIN_ID), msg)
        logger.info(f"✅ Notification envoyée à l'admin pour {user['email']}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur notification admin: {e}")
        return False

# ============ ROUTES PUBLIQUES ============

async def index(request):
    """Page principale"""
    session_id = request.cookies.get('session_id')
    session = await check_session(session_id) if session_id else None
    
    if not session:
        raise web.HTTPFound('/login')
    
    if not has_active_subscription(session):
        return web.Response(
            text=render_template('expired.html', user=session, lang='fr'),
            content_type='text/html'
        )
    
    return web.Response(
        text=render_template('index.html', user=session, lang='fr'),
        content_type='text/html'
    )

async def login_page(request):
    return web.Response(
        text=render_template('login.html'),
        content_type='text/html'
    )

async def register_page(request):
    return web.Response(
        text=render_template('register.html'),
        content_type='text/html'
    )

# ============ API AUTH ============

async def api_login(request):
    data = await request.post()
    result = await login_user(data.get('email'), data.get('password'))
    
    if result['success']:
        response = web.json_response({
            'success': True,
            'user': result['user']
        })
        response.set_cookie('session_id', result['session_id'],
                          max_age=7*24*3600, httponly=True)
        return response
    else:
        return web.json_response({
            'success': False,
            'error': result['error']
        }, status=401)

async def api_register(request):
    data = await request.post()
    result = await register_user(
        data.get('email'),
        data.get('password'),
        data.get('first_name'),
        data.get('last_name')
    )
    
    if result['success']:
        # Notifier l'admin
        await notify_admin_new_user(result['user'])
        return web.json_response({'success': True})
    else:
        return web.json_response({
            'success': False,
            'error': result['error']
        }, status=400)

async def api_logout(request):
    session_id = request.cookies.get('session_id')
    if session_id:
        await logout_user(session_id)
    
    response = web.json_response({'success': True})
    response.del_cookie('session_id')
    return response

# ============ API DONNÉES ============

async def api_predictions(request):
    """API données prédictions"""
    session_id = request.cookies.get('session_id')
    session = await check_session(session_id) if session_id else None
    
    if not session or not has_active_subscription(session):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    from bot_logic import state as bot_state
    
    data = {
        'predictions': list(bot_state.prediction_history),
        'total_predictions': bot_state.total_predictions,
        'won_predictions': bot_state.won_predictions,
        'lost_predictions': bot_state.lost_predictions,
        'win_rate': get_win_rate(),
        'current_game': bot_state.current_game_number,
        'user': {
            'first_name': session['first_name'],
            'subscription_end': session['subscription_end'].isoformat() if session['subscription_end'] else None
        },
        'timestamp': datetime.now().isoformat()
    }
    return web.json_response(data)

def get_win_rate():
    from bot_logic import state as bot_state
    finished = bot_state.won_predictions + bot_state.lost_predictions
    if finished == 0:
        return 0
    return round((bot_state.won_predictions / finished) * 100, 1)

# ============ ADMIN ROUTES ============

async def admin_login_page(request):
    return web.Response(
        text=render_template('admin_login.html'),
        content_type='text/html'
    )

async def api_admin_login(request):
    data = await request.post()
    
    if check_admin_credentials(data.get('email'), data.get('password')):
        response = web.json_response({'success': True})
        response.set_cookie('admin_session', 'true',
                          max_age=24*3600, httponly=True)
        return response
    
    return web.json_response({'success': False}, status=401)

async def admin_dashboard(request):
    if not request.cookies.get('admin_session'):
        raise web.HTTPFound('/admin/login')
    
    users = get_all_users()
    return web.Response(
        text=render_template('admin.html', users=users),
        content_type='text/html'
    )

async def api_admin_users(request):
    if not request.cookies.get('admin_session'):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    users = get_all_users()
    return web.json_response({'users': users})

async def api_admin_add_time(request):
    if not request.cookies.get('admin_session'):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    data = await request.json()
    email = data.get('email')
    days = int(data.get('days', 0))
    
    user = get_user_by_email(email)
    if not user:
        return web.json_response({'error': 'user_not_found'}, status=404)
    
    new_end = add_subscription_time(user['id'], days)
    
    # Notifier l'utilisateur si possible
    if admin_bot_client and user.get('telegram_id'):
        try:
            await admin_bot_client.send_message(
                user['telegram_id'],
                f"✅ {days} jours ajoutés à votre abonnement!\nNouvelle expiration: {new_end.strftime('%d/%m/%Y')}"
            )
        except:
            pass
    
    return web.json_response({
        'success': True,
        'new_end': new_end.isoformat() if new_end else None
    })

async def api_admin_block(request):
    if not request.cookies.get('admin_session'):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    data = await request.json()
    user_id = data.get('user_id')
    action = data.get('action')
    
    if action == 'block':
        block_user(user_id)
    else:
        unblock_user(user_id)
    
    return web.json_response({'success': True})

# ============ COMMANDES TELEGRAM ADMIN ============

async def handle_admin_commands(event):
    """Gère les commandes admin dans Telegram"""
    if not event.is_private:
        return
    
    sender_id = event.sender_id
    if str(sender_id) != str(ADMIN_ID):
        return
    
    text = event.message.message
    parts = text.split()
    command = parts[0].lower() if parts else ''
    
    try:
        if command == '/list':
            users = get_all_users()
            msg = "📋 LISTE DES UTILISATEURS\n\n"
            for u in users[:20]:  # Limite à 20
                status = "🟢" if u['is_active'] else "🔴"
                sub = u['subscription_end'][:10] if u['subscription_end'] else "Non abonné"
                msg += f"{status} {u['first_name']} {u['last_name']}\n📧 {u['email']}\n📅 {sub}\n\n"
            await event.reply(msg)
            
        elif command == '/add_time' and len(parts) >= 3:
            email = parts[1]
            days = int(parts[2])
            user = get_user_by_email(email)
            if user:
                new_end = add_subscription_time(user['id'], days)
                await event.reply(f"✅ {days} jours ajoutés à {email}\nNouvelle date: {new_end}")
            else:
                await event.reply(f"❌ Utilisateur {email} non trouvé")
                
        elif command == '/block' and len(parts) >= 2:
            email = parts[1]
            user = get_user_by_email(email)
            if user:
                block_user(user['id'])
                await event.reply(f"🚫 {email} bloqué")
            else:
                await event.reply(f"❌ {email} non trouvé")
                
        elif command == '/unblock' and len(parts) >= 2:
            email = parts[1]
            user = get_user_by_email(email)
            if user:
                unblock_user(user['id'])
                await event.reply(f"✅ {email} débloqué")
            else:
                await event.reply(f"❌ {email} non trouvé")
                
        elif command == '/help':
            await event.reply("""📚 COMMANDES ADMIN:

/list - Liste des utilisateurs
/add_time <email> <jours> - Ajouter du temps
/block <email> - Bloquer utilisateur
/unblock <email> - Débloquer utilisateur
/stats - Statistiques

Exemple: /add_time user@email.com 7""")
            
        elif command == '/stats':
            from bot_logic import state as bot_state
            await event.reply(f"""📊 STATISTIQUES BOT:

🎯 Prédictions: {bot_state.total_predictions}
✅ Gagnés: {bot_state.won_predictions}
❌ Perdus: {bot_state.lost_predictions}
📈 Win Rate: {get_win_rate()}%
🎮 Jeu actuel: #{bot_state.current_game_number}""")
            
    except Exception as e:
        await event.reply(f"❌ Erreur: {e}")

def setup_web_app(bot_clients):
    app = web.Application()
    
    # Stocker les clients
    global bot_client, admin_bot_client
    bot_client = bot_clients.get('user')
    admin_bot_client = bot_clients.get('admin')
    
    # Ajouter handler commandes admin si bot admin disponible
    if admin_bot_client:
        @admin_bot_client.on(events.NewMessage(pattern='/'))
        async def admin_cmd_handler(event):
            await handle_admin_commands(event)
    
    # Routes
    app.router.add_get('/', index)
    app.router.add_get('/login', login_page)
    app.router.add_get('/register', register_page)
    
    app.router.add_post('/api/login', api_login)
    app.router.add_post('/api/register', api_register)
    app.router.add_post('/api/logout', api_logout)
    
    app.router.add_get('/api/predictions', api_predictions)
    
    # Admin
    app.router.add_get('/admin/login', admin_login_page)
    app.router.add_post('/api/admin/login', api_admin_login)
    app.router.add_get('/admin', admin_dashboard)
    app.router.add_get('/api/admin/users', api_admin_users)
    app.router.add_post('/api/admin/add-time', api_admin_add_time)
    app.router.add_post('/api/admin/block', api_admin_block)
    
    # Static
    app.router.add_static('/static/', path='static', name='static')
    
    return app
