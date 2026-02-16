"""
Serveur web aiohttp
"""
import json
import logging
from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape
from database import (
    add_subscription_time, get_all_users, block_user, 
    unblock_user, get_user_by_email
)
from auth import (
    register_user, login_user, check_session, logout_user,
    check_admin_credentials, has_active_subscription
)
from bot_logic import state as bot_state

logger = logging.getLogger(__name__)

# Setup Jinja2
env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=select_autoescape(['html', 'xml'])
)

def render_template(template_name, **context):
    template = env.get_template(template_name)
    return template.render(**context)

async def index(request):
    """Page principale"""
    session_id = request.cookies.get('session_id')
    session = await check_session(session_id) if session_id else None
    
    if not session:
        raise web.HTTPFound('/login')
    
    # Vérifier abonnement
    if not has_active_subscription(session):
        return web.Response(
            text=render_template('expired.html', 
                               user=session,
                               lang=request.query.get('lang', 'fr')),
            content_type='text/html'
        )
    
    return web.Response(
        text=render_template('index.html',
                           user=session,
                           lang=request.query.get('lang', 'fr')),
        content_type='text/html'
    )

async def login_page(request):
    """Page de connexion"""
    return web.Response(
        text=render_template('login.html',
                           lang=request.query.get('lang', 'fr')),
        content_type='text/html'
    )

async def register_page(request):
    """Page d'inscription"""
    return web.Response(
        text=render_template('register.html',
                           lang=request.query.get('lang', 'fr')),
        content_type='text/html'
    )

async def api_login(request):
    """API connexion"""
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
    """API inscription"""
    data = await request.post()
    result = await register_user(
        data.get('email'),
        data.get('password'),
        data.get('first_name'),
        data.get('last_name')
    )
    
    if result['success']:
        # Notifier l'admin via Telegram
        await notify_admin_new_user(result['user'], request.app['bot_client'])
        return web.json_response({'success': True})
    else:
        return web.json_response({
            'success': False,
            'error': result['error']
        }, status=400)

async def notify_admin_new_user(user, bot_client):
    """Envoie notification à l'admin Telegram"""
    from config import ADMIN_ID
    if not bot_client or not ADMIN_ID:
        return
    
    try:
        msg = f"""🆕 Nouvel utilisateur inscrit !
        
👤 Nom: {user['first_name']} {user['last_name']}
📧 Email: {user['email']}
⏰ Date: {user['created_at']}

Commandes disponibles:
/add_time {user['email']} 7  (ajouter 7 jours)
/block {user['email']}      (bloquer l'utilisateur)"""
        
        await bot_client.send_message(ADMIN_ID, msg)
    except Exception as e:
        logger.error(f"Erreur notification admin: {e}")

async def api_logout(request):
    """API déconnexion"""
    session_id = request.cookies.get('session_id')
    if session_id:
        await logout_user(session_id)
    
    response = web.json_response({'success': True})
    response.del_cookie('session_id')
    return response

async def api_predictions(request):
    """API données prédictions"""
    session_id = request.cookies.get('session_id')
    session = await check_session(session_id) if session_id else None
    
    if not session or not has_active_subscription(session):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    data = {
        'predictions': list(bot_state.prediction_history),
        'total_predictions': bot_state.total_predictions,
        'won_predictions': bot_state.won_predictions,
        'lost_predictions': bot_state.lost_predictions,
        'win_rate': get_win_rate(),
        'current_game': bot_state.current_game_number,
        'prediction_channel_ok': bot_state.prediction_channel_ok,
        'user': {
            'first_name': session['first_name'],
            'subscription_end': session['subscription_end'].isoformat() \
                if session['subscription_end'] else None
        },
        'timestamp': datetime.now().isoformat()
    }
    return web.json_response(data)

def get_win_rate():
    finished = bot_state.won_predictions + bot_state.lost_predictions
    if finished == 0:
        return 0
    return round((bot_state.won_predictions / finished) * 100, 1)

async def api_user_info(request):
    """Infos utilisateur connecté"""
    session_id = request.cookies.get('session_id')
    session = await check_session(session_id) if session_id else None
    
    if not session:
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    return web.json_response({
        'first_name': session['first_name'],
        'last_name': session['last_name'],
        'email': session['email'],
        'subscription_end': session['subscription_end'].isoformat() \
            if session['subscription_end'] else None,
        'is_active': session['is_active']
    })

# Admin routes

async def admin_login_page(request):
    """Page login admin"""
    return web.Response(
        text=render_template('admin_login.html'),
        content_type='text/html'
    )

async def api_admin_login(request):
    """API login admin"""
    data = await request.post()
    
    if check_admin_credentials(data.get('email'), data.get('password')):
        response = web.json_response({'success': True})
        response.set_cookie('admin_session', 'true',
                          max_age=24*3600, httponly=True)
        return response
    
    return web.json_response({'success': False}, status=401)

async def admin_dashboard(request):
    """Dashboard admin"""
    if not request.cookies.get('admin_session'):
        raise web.HTTPFound('/admin/login')
    
    users = get_all_users()
    return web.Response(
        text=render_template('admin.html', users=users),
        content_type='text/html'
    )

async def api_admin_users(request):
    """Liste utilisateurs pour admin"""
    if not request.cookies.get('admin_session'):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    users = get_all_users()
    return web.json_response({'users': users})

async def api_admin_add_time(request):
    """Ajouter du temps à un utilisateur"""
    if not request.cookies.get('admin_session'):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    data = await request.json()
    email = data.get('email')
    days = int(data.get('days', 0))
    
    user = get_user_by_email(email)
    if not user:
        return web.json_response({'error': 'user_not_found'}, status=404)
    
    new_end = add_subscription_time(user['id'], days)
    
    # Notifier l'utilisateur si bot disponible
    bot_client = request.app.get('bot_client')
    if bot_client:
        try:
            # Trouver le chat_id de l'utilisateur via ses sessions ou autre méthode
            pass
        except:
            pass
    
    return web.json_response({
        'success': True,
        'new_end': new_end.isoformat() if new_end else None
    })

async def api_admin_block(request):
    """Bloquer/débloquer utilisateur"""
    if not request.cookies.get('admin_session'):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    data = await request.json()
    user_id = data.get('user_id')
    action = data.get('action')  # 'block' or 'unblock'
    
    if action == 'block':
        block_user(user_id)
    else:
        unblock_user(user_id)
    
    return web.json_response({'success': True})

def setup_web_app(bot_client=None):
    """Configure l'application web"""
    app = web.Application()
    
    # Stocker le client bot pour notifications
    app['bot_client'] = bot_client
    
    # Routes publiques
    app.router.add_get('/', index)
    app.router.add_get('/login', login_page)
    app.router.add_get('/register', register_page)
    
    # API auth
    app.router.add_post('/api/login', api_login)
    app.router.add_post('/api/register', api_register)
    app.router.add_post('/api/logout', api_logout)
    
    # API données
    app.router.add_get('/api/predictions', api_predictions)
    app.router.add_get('/api/user', api_user_info)
    
    # Admin
    app.router.add_get('/admin/login', admin_login_page)
    app.router.add_post('/api/admin/login', api_admin_login)
    app.router.add_get('/admin', admin_dashboard)
    app.router.add_get('/api/admin/users', api_admin_users)
    app.router.add_post('/api/admin/add-time', api_admin_add_time)
    app.router.add_post('/api/admin/block', api_admin_block)
    
    # Static files
    app.router.add_static('/static/', path='static', name='static')
    
    return app
