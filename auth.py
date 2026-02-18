"""
Gestion de l'authentification
"""
from database import (
    create_user, get_user_by_email, verify_password, 
    create_session, get_session, delete_session,
    update_last_login
)
from config import ADMIN_EMAIL, ADMIN_PASSWORD

async def register_user(email: str, password: str, first_name: str, last_name: str):
    """Inscription d'un nouvel utilisateur"""
    # Vérifier si email valide
    if '@' not in email or '.' not in email:
        return {'success': False, 'error': 'email_invalid'}
    
    # Vérifier longueur mot de passe
    if len(password) < 6:
        return {'success': False, 'error': 'password_too_short'}
    
    # Créer l'utilisateur
    user = create_user(email, password, first_name, last_name)
    if not user:
        return {'success': False, 'error': 'email_exists'}
    
    return {'success': True, 'user': user}

async def login_user(email: str, password: str):
    """Connexion utilisateur (y compris admin)"""
    user = get_user_by_email(email)
    if not user:
        return {'success': False, 'error': 'invalid_credentials'}
    
    if not verify_password(user['password_hash'], password):
        return {'success': False, 'error': 'invalid_credentials'}
    
    if not user['is_active']:
        return {'success': False, 'error': 'account_blocked'}
    
    # Forcer admin pour l'email principal
    is_admin_user = user.get('is_admin', False) or user['email'] == ADMIN_EMAIL
    
    # Met à jour dernière connexion
    update_last_login(user['id'])
    
    # Crée une session
    session_id = create_session(user['id'])
    
    return {
        'success': True,
        'session_id': session_id,
        'user': {
            'id': user['id'],
            'email': user['email'],
            'first_name': user['first_name'],
            'last_name': user['last_name'],
            'subscription_end': user['subscription_end'],
            'is_admin': is_admin_user
        }
    }

async def check_session(session_id: str):
    """Vérifie une session"""
    if not session_id:
        return None
    return get_session(session_id)

async def logout_user(session_id: str):
    """Déconnexion"""
    delete_session(session_id)
    return {'success': True}

def check_admin_credentials(email: str, password: str):
    """Vérifie les credentials admin (ancienne méthode)"""
    return email == ADMIN_EMAIL and password == ADMIN_PASSWORD

def has_active_subscription(user: dict) -> bool:
    """Vérifie si l'abonnement est actif"""
    from datetime import datetime
    
    if not user.get('subscription_end'):
        return False
    
    sub_end = user['subscription_end']
    if isinstance(sub_end, str):
        sub_end = datetime.fromisoformat(sub_end)
    
    return sub_end > datetime.now()

def is_admin(user: dict) -> bool:
    """Vérifie si l'utilisateur est admin"""
    return user.get('is_admin', False) or user.get('email') == ADMIN_EMAIL
