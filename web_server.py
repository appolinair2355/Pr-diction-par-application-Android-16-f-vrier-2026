"""
Serveur web aiohttp - Affichage prédictions temps réel
"""
import json
import logging
from aiohttp import web
from jinja2 import Environment, FileSystemLoader, select_autoescape
from datetime import datetime

from database import (
    add_subscription_time, get_all_users, block_user, 
    unblock_user, get_user_by_email
)
from auth import (
    register_user, login_user, check_session, logout_user,
    check_admin_credentials, has_active_subscription
)
from config import ADMIN_ID, ADMIN_EMAIL, ADMIN_PASSWORD

# 🔧 IMPORT pour accéder à l'état des prédictions
from bot_logic import state as bot_state

logger = logging.getLogger(__name__)

bot_client = None
admin_bot_client = None

env = Environment(
    loader=FileSystemLoader('templates'),
    autoescape=select_autoescape(['html', 'xml'])
)

def render_template(template_name, **context):
    template = env.get_template(template_name)
    return template.render(**context)

# ... [routes existantes conservées] ...

# 🔧 NOUVEAU: Route pour données temps réel des prédictions
async def api_predictions_status(request):
    """API pour statut des prédictions en temps réel"""
    try:
        from bot_logic import state
        
        # Info pause
        pause_status = "Non"
        if state.pause_config['is_paused']:
            try:
                end_time = datetime.fromisoformat(state.pause_config['pause_end_time'])
                remaining = int((end_time - datetime.now()).total_seconds())
                if remaining > 0:
                    pause_status = f"Oui ({remaining//60}min {remaining%60}s)"
            except:
                pass
        
        cycle_mins = [x//60 for x in state.pause_config['cycle']]
        current_idx = state.pause_config['current_index'] % len(cycle_mins)
        
        data = {
            'current_game': state.current_game_number,
            'verification': {
                'active': state.verification_state['predicted_number'] is not None,
                'number': state.verification_state['predicted_number'],
                'suit': state.verification_state['predicted_suit'],
                'check': state.verification_state['current_check']
            },
            'predictions_enabled': state.predictions_enabled,
            'pause': {
                'active': state.pause_config['is_paused'],
                'status': pause_status,
                'count': state.pause_config['predictions_count'],
                'cycle': cycle_mins,
                'position': current_idx + 1
            },
            'stats': {
                'total': state.total_predictions,
                'won': state.won_predictions,
                'lost': state.lost_predictions,
                'win_rate': round((state.won_predictions / state.total_predictions * 100), 1) if state.total_predictions > 0 else 0
            },
            'history': list(state.prediction_history)[-10:],  # 10 dernières
            'timestamp': datetime.now().isoformat()
        }
        return web.json_response(data)
    except Exception as e:
        logger.error(f"Erreur API predictions: {e}")
        return web.json_response({'error': str(e)}, status=500)

# 🔧 NOUVEAU: Page web temps réel
async def predictions_live(request):
    """Page web temps réel des prédictions"""
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Prédictions Baccarat - Temps Réel</title>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="5">
    <style>
        body { 
            font-family: Arial, sans-serif; 
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white; 
            margin: 0; 
            padding: 20px;
            min-height: 100vh;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1 { text-align: center; color: #ffd700; margin-bottom: 30px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card { 
            background: rgba(255,255,255,0.1); 
            padding: 20px; 
            border-radius: 15px; 
            text-align: center;
            border: 1px solid rgba(255,255,255,0.2);
        }
        .card h3 { margin-top: 0; color: #aaa; font-size: 0.9em; text-transform: uppercase; }
        .number { font-size: 2.5em; font-weight: bold; color: #ffd700; margin: 10px 0; }
        .status-on { color: #00ff88; }
        .status-off { color: #ff4444; }
        .status-pending { color: #ffaa00; }
        .history { background: rgba(0,0,0,0.3); padding: 20px; border-radius: 15px; }
        .history h2 { color: #ffd700; margin-top: 0; }
        .pred-item { 
            display: flex; 
            justify-content: space-between; 
            padding: 10px; 
            margin: 5px 0;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
        }
        .pred-won { border-left: 4px solid #00ff88; }
        .pred-lost { border-left: 4px solid #ff4444; }
        .pred-pending { border-left: 4px solid #ffaa00; }
        .timestamp { color: #888; font-size: 0.8em; }
        .refresh { text-align: center; color: #888; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎰 Prédictions Baccarat - Temps Réel</h1>
        
        <div class="grid">
            <div class="card">
                <h3>Jeu Actuel</h3>
                <div class="number">#{{ current_game }}</div>
            </div>
            <div class="card">
                <h3>Prédictions</h3>
                <div class="number {{ 'status-on' if predictions_enabled else 'status-off' }}">
                    {{ 'ON' if predictions_enabled else 'OFF' }}
                </div>
            </div>
            <div class="card">
                <h3>Vérification</h3>
                <div class="number {{ 'status-pending' if verification_active else 'status-on' }}">
                    {{ '#' + verification_number|string if verification_active else 'Libre' }}
                </div>
                {% if verification_active %}
                <div>{{ verification_suit }} (check {{ verification_check }}/3)</div>
                {% endif %}
            </div>
            <div class="card">
                <h3>Pause</h3>
                <div class="number">{{ pause_count }}/5</div>
                <div>{{ pause_status }}</div>
            </div>
            <div class="card">
                <h3>Win Rate</h3>
                <div class="number">{{ win_rate }}%</div>
                <div>{{ total_won }} / {{ total }}</div>
            </div>
            <div class="card">
                <h3>Canal</h3>
                <div class="number" style="font-size: 1.2em;">-1003579400443</div>
            </div>
        </div>
        
        <div class="history">
            <h2>📜 Historique (10 dernières)</h2>
            {% for pred in history|reverse %}
            <div class="pred-item pred-{{ 'won' if '✅' in pred.status else 'lost' if '❌' in pred.status else 'pending' }}">
                <span>
                    <strong>#{{ pred.game_number }}</strong> 
                    {{ pred.suit }} 
                    <span class="timestamp">{{ pred.time_str }}</span>
                </span>
                <span>{{ pred.status }}</span>
            </div>
            {% endfor %}
        </div>
        
        <div class="refresh">🔄 Actualisation auto toutes les 5 secondes | {{ timestamp }}</div>
    </div>
</body>
</html>"""
    
    from bot_logic import state
    
    cycle_mins = [x//60 for x in state.pause_config['cycle']]
    current_idx = state.pause_config['current_index'] % len(cycle_mins)
    
    pause_status = "Non active"
    if state.pause_config['is_paused']:
        try:
            end_time = datetime.fromisoformat(state.pause_config['pause_end_time'])
            remaining = int((end_time - datetime.now()).total_seconds())
            if remaining > 0:
                pause_status = f"Oui ({remaining//60}min {remaining%60}s restantes)"
        except:
            pause_status = "Erreur"
    
    rendered = render_template_string(html,
        current_game=state.current_game_number,
        predictions_enabled=state.predictions_enabled,
        verification_active=state.verification_state['predicted_number'] is not None,
        verification_number=state.verification_state['predicted_number'],
        verification_suit=state.verification_state['predicted_suit'],
        verification_check=state.verification_state['current_check'],
        pause_count=state.pause_config['predictions_count'],
        pause_status=pause_status,
        win_rate=round((state.won_predictions / state.total_predictions * 100), 1) if state.total_predictions > 0 else 0,
        total_won=state.won_predictions,
        total=state.total_predictions,
        history=list(state.prediction_history),
        timestamp=datetime.now().strftime('%H:%M:%S')
    )
    
    return web.Response(text=rendered, content_type='text/html')

def render_template_string(template, **kwargs):
    from jinja2 import Template
    return Template(template).render(**kwargs)

def setup_web_app(bot_clients):
    app = web.Application()
    
    global bot_client, admin_bot_client
    bot_client = bot_clients.get('user')
    admin_bot_client = bot_clients.get('admin')
    
    # Routes existantes...
    app.router.add_get('/', index)
    app.router.add_get('/login', login_page)
    app.router.add_get('/register', register_page)
    app.router.add_post('/api/login', api_login)
    app.router.add_post('/api/register', api_register)
    app.router.add_post('/api/logout', api_logout)
    app.router.add_get('/api/predictions', api_predictions)
    
    # 🔧 NOUVEAU: Routes pour prédictions temps réel
    app.router.add_get('/live', predictions_live)
    app.router.add_get('/api/predictions-status', api_predictions_status)
    
    # Admin routes...
    app.router.add_get('/admin/login', admin_login_page)
    app.router.add_post('/api/admin/login', api_admin_login)
    app.router.add_get('/admin', admin_dashboard)
    app.router.add_get('/api/admin/users', api_admin_users)
    app.router.add_post('/api/admin/add-time', api_admin_add_time)
    app.router.add_post('/api/admin/block', api_admin_block)
    
    app.router.add_static('/static/', path='static', name='static')
    
    return app
