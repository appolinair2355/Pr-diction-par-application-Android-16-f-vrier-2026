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

def render_template_string(template, **kwargs):
    from jinja2 import Template
    return Template(template).render(**kwargs)

# ============================================================
# ROUTES PAGES (AJOUTÉES - MANQUANTES AVANT)
# ============================================================

async def index(request):
    """Page d'accueil - redirige vers /live"""
    raise web.HTTPFound('/live')

async def login_page(request):
    """Page de connexion"""
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Connexion - Baccarat Bot</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
        }
        .login-box {
            background: rgba(255,255,255,0.1);
            padding: 40px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.2);
            width: 90%;
            max-width: 400px;
        }
        h1 { color: #ffd700; text-align: center; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #aaa; }
        input {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            background: rgba(0,0,0,0.3);
            color: white;
            font-size: 16px;
        }
        input:focus { outline: 2px solid #ffd700; }
        button {
            width: 100%;
            padding: 15px;
            border: none;
            border-radius: 8px;
            background: linear-gradient(135deg, #ffd700 0%, #ffaa00 100%);
            color: #1a1a2e;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover { transform: scale(1.02); }
        .links { text-align: center; margin-top: 20px; }
        .links a { color: #00ff88; text-decoration: none; }
        .links a:hover { text-decoration: underline; }
        .error { color: #ff4444; text-align: center; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>🔐 Connexion</h1>
        <div id="error" class="error"></div>
        <form id="loginForm">
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" required>
            </div>
            <div class="form-group">
                <label>Mot de passe</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">Se connecter</button>
        </form>
        <div class="links">
            <p>Pas de compte ? <a href="/register">S'inscrire</a></p>
            <p><a href="/">← Retour à l'accueil</a></p>
        </div>
    </div>
    <script>
        document.getElementById('loginForm').onsubmit = async (e) => {
            e.preventDefault();
            const form = new FormData(e.target);
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    email: form.get('email'),
                    password: form.get('password')
                })
            });
            const data = await res.json();
            if (data.success) {
                window.location.href = '/';
            } else {
                document.getElementById('error').textContent = data.error || 'Erreur de connexion';
            }
        };
    </script>
</body>
</html>"""
    return web.Response(text=html, content_type='text/html')

async def register_page(request):
    """Page d'inscription"""
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Inscription - Baccarat Bot</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
        }
        .register-box {
            background: rgba(255,255,255,0.1);
            padding: 40px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.2);
            width: 90%;
            max-width: 400px;
        }
        h1 { color: #ffd700; text-align: center; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #aaa; }
        input {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            background: rgba(0,0,0,0.3);
            color: white;
            font-size: 16px;
        }
        input:focus { outline: 2px solid #ffd700; }
        button {
            width: 100%;
            padding: 15px;
            border: none;
            border-radius: 8px;
            background: linear-gradient(135deg, #00ff88 0%, #00cc6a 100%);
            color: #1a1a2e;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover { transform: scale(1.02); }
        .links { text-align: center; margin-top: 20px; }
        .links a { color: #ffd700; text-decoration: none; }
        .links a:hover { text-decoration: underline; }
        .error { color: #ff4444; text-align: center; margin-bottom: 15px; }
    </style>
</head>
<body>
    <div class="register-box">
        <h1>📝 Inscription</h1>
        <div id="error" class="error"></div>
        <form id="registerForm">
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" required>
            </div>
            <div class="form-group">
                <label>Mot de passe</label>
                <input type="password" name="password" required minlength="6">
            </div>
            <button type="submit">S'inscrire</button>
        </form>
        <div class="links">
            <p>Déjà un compte ? <a href="/login">Se connecter</a></p>
            <p><a href="/">← Retour à l'accueil</a></p>
        </div>
    </div>
    <script>
        document.getElementById('registerForm').onsubmit = async (e) => {
            e.preventDefault();
            const form = new FormData(e.target);
            const res = await fetch('/api/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    email: form.get('email'),
                    password: form.get('password')
                })
            });
            const data = await res.json();
            if (data.success) {
                alert('Inscription réussie !');
                window.location.href = '/login';
            } else {
                document.getElementById('error').textContent = data.error || 'Erreur d\\'inscription';
            }
        };
    </script>
</body>
</html>"""
    return web.Response(text=html, content_type='text/html')

async def admin_login_page(request):
    """Page de connexion admin"""
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Admin - Baccarat Bot</title>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
        }
        .login-box {
            background: rgba(255,255,255,0.1);
            padding: 40px;
            border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.2);
            width: 90%;
            max-width: 400px;
        }
        h1 { color: #ff4444; text-align: center; margin-bottom: 30px; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; color: #aaa; }
        input {
            width: 100%;
            padding: 12px;
            border: none;
            border-radius: 8px;
            background: rgba(0,0,0,0.3);
            color: white;
            font-size: 16px;
        }
        button {
            width: 100%;
            padding: 15px;
            border: none;
            border-radius: 8px;
            background: linear-gradient(135deg, #ff4444 0%, #cc0000 100%);
            color: white;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
        }
        .back { text-align: center; margin-top: 20px; }
        .back a { color: #888; text-decoration: none; }
    </style>
</head>
<body>
    <div class="login-box">
        <h1>👑 Admin</h1>
        <form id="adminForm">
            <div class="form-group">
                <label>Email Admin</label>
                <input type="email" name="email" required>
            </div>
            <div class="form-group">
                <label>Mot de passe</label>
                <input type="password" name="password" required>
            </div>
            <button type="submit">Connexion</button>
        </form>
        <div class="back"><a href="/">← Retour</a></div>
    </div>
    <script>
        document.getElementById('adminForm').onsubmit = async (e) => {
            e.preventDefault();
            const form = new FormData(e.target);
            const res = await fetch('/api/admin/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    email: form.get('email'),
                    password: form.get('password')
                })
            });
            const data = await res.json();
            if (data.success) {
                window.location.href = '/admin';
            } else {
                alert('Accès refusé');
            }
        };
    </script>
</body>
</html>"""
    return web.Response(text=html, content_type='text/html')

async def admin_dashboard(request):
    """Dashboard admin"""
    html = """<!DOCTYPE html>
<html>
<head>
    <title>Dashboard Admin - Baccarat Bot</title>
    <meta charset="UTF-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            color: white;
            padding: 20px;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid rgba(255,255,255,0.2);
        }
        h1 { color: #ffd700; }
        .logout {
            background: #ff4444;
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            text-decoration: none;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: rgba(255,255,255,0.1);
            padding: 20px;
            border-radius: 15px;
            border: 1px solid rgba(255,255,255,0.2);
        }
        .card h3 { color: #aaa; margin-bottom: 15px; }
        input, select {
            width: 100%;
            padding: 10px;
            margin-bottom: 10px;
            border: none;
            border-radius: 8px;
            background: rgba(0,0,0,0.3);
            color: white;
        }
        button {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            background: #00ff88;
            color: #1a1a2e;
            font-weight: bold;
            cursor: pointer;
        }
        button.danger { background: #ff4444; color: white; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th { color: #ffd700; }
        .status-active { color: #00ff88; }
        .status-blocked { color: #ff4444; }
        .status-expired { color: #ffaa00; }
    </style>
</head>
<body>
    <div class="header">
        <h1>👑 Dashboard Admin</h1>
        <a href="#" onclick="logout()" class="logout">Déconnexion</a>
    </div>
    
    <div class="grid">
        <div class="card">
            <h3>⏱️ Ajouter du temps</h3>
            <input type="email" id="addEmail" placeholder="Email utilisateur">
            <input type="number" id="addDays" placeholder="Nombre de jours" min="1">
            <button onclick="addTime()">Ajouter</button>
        </div>
        
        <div class="card">
            <h3>🚫 Bloquer/Débloquer</h3>
            <input type="email" id="blockEmail" placeholder="Email utilisateur">
            <button onclick="blockUser()" class="danger">Bloquer</button>
            <button onclick="unblockUser()">Débloquer</button>
        </div>
        
        <div class="card">
            <h3>📊 Accès rapide</h3>
            <a href="/live" style="color: #00ff88;">→ Voir les prédictions live</a>
        </div>
    </div>
    
    <div class="card">
        <h3>👥 Utilisateurs</h3>
        <div id="usersList">Chargement...</div>
    </div>
    
    <script>
        async function loadUsers() {
            const res = await fetch('/api/admin/users');
            const data = await res.json();
            const div = document.getElementById('usersList');
            if (!data.users || data.users.length === 0) {
                div.innerHTML = '<p>Aucun utilisateur</p>';
                return;
            }
            let html = '<table><tr><th>Email</th><th>Statut</th><th>Expiration</th></tr>';
            data.users.forEach(u => {
                const status = u.is_blocked ? '<span class="status-blocked">Bloqué</span>' : 
                              u.is_active ? '<span class="status-active">Actif</span>' : 
                              '<span class="status-expired">Expiré</span>';
                html += `<tr>
                    <td>${u.email}</td>
                    <td>${status}</td>
                    <td>${u.subscription_end || 'N/A'}</td>
                </tr>`;
            });
            html += '</table>';
            div.innerHTML = html;
        }
        
        async function addTime() {
            const email = document.getElementById('addEmail').value;
            const days = document.getElementById('addDays').value;
            if (!email || !days) return alert('Remplissez tous les champs');
            
            const res = await fetch('/api/admin/add-time', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, days: parseInt(days)})
            });
            const data = await res.json();
            alert(data.message || data.error);
            loadUsers();
        }
        
        async function blockUser() {
            const email = document.getElementById('blockEmail').value;
            if (!email) return;
            const res = await fetch('/api/admin/block', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, action: 'block'})
            });
            const data = await res.json();
            alert(data.message || data.error);
            loadUsers();
        }
        
        async function unblockUser() {
            const email = document.getElementById('blockEmail').value;
            if (!email) return;
            const res = await fetch('/api/admin/block', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, action: 'unblock'})
            });
            const data = await res.json();
            alert(data.message || data.error);
            loadUsers();
        }
        
        async function logout() {
            await fetch('/api/logout', {method: 'POST'});
            window.location.href = '/';
        }
        
        loadUsers();
    </script>
</body>
</html>"""
    return web.Response(text=html, content_type='text/html')

# ============================================================
# API ROUTES
# ============================================================

async def api_login(request):
    """API connexion"""
    try:
        data = await request.json()
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return web.json_response({'success': False, 'error': 'Champs requis'})
        
        result = login_user(email, password)
        if result['success']:
            # Créer session
            response = web.json_response({'success': True})
            # TODO: Implémenter les cookies de session si nécessaire
            return response
        else:
            return web.json_response({'success': False, 'error': result.get('error', 'Erreur')})
    except Exception as e:
        logger.error(f"Erreur login: {e}")
        return web.json_response({'success': False, 'error': str(e)})

async def api_register(request):
    """API inscription"""
    try:
        data = await request.json()
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return web.json_response({'success': False, 'error': 'Champs requis'})
        
        result = register_user(email, password)
        return web.json_response(result)
    except Exception as e:
        logger.error(f"Erreur register: {e}")
        return web.json_response({'success': False, 'error': str(e)})

async def api_logout(request):
    """API déconnexion"""
    return web.json_response({'success': True})

async def api_predictions(request):
    """API liste prédictions utilisateur"""
    # TODO: Vérifier session et retourner prédictions
    return web.json_response({'predictions': []})

async def api_admin_login(request):
    """API connexion admin"""
    try:
        data = await request.json()
        email = data.get('email')
        password = data.get('password')
        
        if check_admin_credentials(email, password):
            return web.json_response({'success': True})
        else:
            return web.json_response({'success': False, 'error': 'Accès refusé'})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

async def api_admin_users(request):
    """API liste utilisateurs"""
    try:
        users = get_all_users()
        return web.json_response({'users': users})
    except Exception as e:
        logger.error(f"Erreur users: {e}")
        return web.json_response({'users': []})

async def api_admin_add_time(request):
    """API ajouter temps"""
    try:
        data = await request.json()
        email = data.get('email')
        days = data.get('days', 0)
        
        if not email or days <= 0:
            return web.json_response({'success': False, 'error': 'Paramètres invalides'})
        
        user = get_user_by_email(email)
        if not user:
            return web.json_response({'success': False, 'error': 'Utilisateur non trouvé'})
        
        add_subscription_time(user['id'], days)
        return web.json_response({'success': True, 'message': f'{days} jours ajoutés à {email}'})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

async def api_admin_block(request):
    """API bloquer/débloquer"""
    try:
        data = await request.json()
        email = data.get('email')
        action = data.get('action')
        
        if not email:
            return web.json_response({'success': False, 'error': 'Email requis'})
        
        user = get_user_by_email(email)
        if not user:
            return web.json_response({'success': False, 'error': 'Utilisateur non trouvé'})
        
        if action == 'block':
            block_user(user['id'])
            return web.json_response({'success': True, 'message': f'{email} bloqué'})
        else:
            unblock_user(user['id'])
            return web.json_response({'success': True, 'message': f'{email} débloqué'})
    except Exception as e:
        return web.json_response({'success': False, 'error': str(e)})

# ============================================================
# ROUTES PRÉDICTIONS TEMPS RÉEL
# ============================================================

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

# ============================================================
# SETUP APPLICATION
# ============================================================

def setup_web_app(bot_clients):
    app = web.Application()
    
    global bot_client, admin_bot_client
    bot_client = bot_clients.get('user')
    admin_bot_client = bot_clients.get('admin')
    
    # Routes pages
    app.router.add_get('/', index)
    app.router.add_get('/login', login_page)
    app.router.add_get('/register', register_page)
    
    # Routes API auth
    app.router.add_post('/api/login', api_login)
    app.router.add_post('/api/register', api_register)
    app.router.add_post('/api/logout', api_logout)
    app.router.add_get('/api/predictions', api_predictions)
    
    # Routes prédictions temps réel
    app.router.add_get('/live', predictions_live)
    app.router.add_get('/api/predictions-status', api_predictions_status)
    
    # Routes admin
    app.router.add_get('/admin/login', admin_login_page)
    app.router.add_post('/api/admin/login', api_admin_login)
    app.router.add_get('/admin', admin_dashboard)
    app.router.add_get('/api/admin/users', api_admin_users)
    app.router.add_post('/api/admin/add-time', api_admin_add_time)
    app.router.add_post('/api/admin/block', api_admin_block)
    
    # Static files
    app.router.add_static('/static/', path='static', name='static')
    
    return app
