"""
Gestion de la base de données SQLite
"""
import os
import psycopg2
import hashlib
import secrets
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from config import DATABASE_URL

def get_connection():
    """Crée une connexion à la base de données PostgreSQL"""
    return psycopg2.connect(DATABASE_URL)

def init_db():
    """Initialise la base de données PostgreSQL"""
    conn = get_connection()
    c = conn.cursor()
    
    # Table utilisateurs
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plain_password TEXT,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            subscription_end TIMESTAMP,
            is_active BOOLEAN DEFAULT TRUE,
            last_login TIMESTAMP,
            is_admin BOOLEAN DEFAULT FALSE,
            telegram_id BIGINT,
            remaining_time_seconds INTEGER DEFAULT 0
        )
    ''')
    
    # Table sessions
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL
        )
    ''')
    
    # Table prédictions
    c.execute('''
        CREATE TABLE IF NOT EXISTS predictions_log (
            id SERIAL PRIMARY KEY,
            game_number INTEGER NOT NULL,
            suit TEXT NOT NULL,
            status TEXT NOT NULL,
            rattrapage INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
    ''')
    
    conn.commit()
    c.close()
    conn.close()
    
    create_default_admin()

def create_default_admin():
    """Crée l'administrateur par défaut si non existant"""
    from config import ADMIN_EMAIL, ADMIN_PASSWORD
    
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('SELECT id FROM users WHERE email = %s', (ADMIN_EMAIL.lower(),))
    if not c.fetchone():
        password_hash = hash_password(ADMIN_PASSWORD)
        c.execute('''
            INSERT INTO users (email, password_hash, plain_password, first_name, last_name, is_active, is_admin, subscription_end)
            VALUES (%s, %s, %s, %s, %s, TRUE, TRUE, %s)
        ''', (ADMIN_EMAIL.lower(), password_hash, ADMIN_PASSWORD, 'Admin', 'System', datetime.now() + timedelta(days=3650)))
        conn.commit()
    else:
        password_hash = hash_password(ADMIN_PASSWORD)
        c.execute('''
            UPDATE users 
            SET password_hash = %s, plain_password = %s, is_admin = TRUE, is_active = TRUE 
            WHERE email = %s
        ''', (password_hash, ADMIN_PASSWORD, ADMIN_EMAIL.lower()))
        conn.commit()
    
    c.close()
    conn.close()

def hash_password(password: str) -> str:
    """Hash un mot de passe"""
    salt = secrets.token_hex(16)
    pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return salt + pwdhash.hex()

def verify_password(stored: str, provided: str) -> bool:
    """Vérifie un mot de passe"""
    salt = stored[:32]
    stored_hash = stored[32:]
    pwdhash = hashlib.pbkdf2_hmac('sha256', provided.encode(), salt.encode(), 100000)
    return pwdhash.hex() == stored_hash

def create_user(email: str, password: str, first_name: str, last_name: str) -> dict:
    """Crée un nouvel utilisateur"""
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        password_hash = hash_password(password)
        c.execute('''
            INSERT INTO users (email, password_hash, plain_password, first_name, last_name, is_admin)
            VALUES (%s, %s, %s, %s, %s, FALSE)
            RETURNING id, email, first_name, last_name, subscription_end
        ''', (email.lower(), password_hash, password, first_name, last_name))
        
        user = c.fetchone()
        conn.commit()
        return dict(user)
    except Exception:
        return None
    finally:
        c.close()
        conn.close()

def get_user_by_email(email: str) -> dict:
    """Récupère un utilisateur par email"""
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    
    c.execute('''
        SELECT id, email, password_hash, first_name, last_name, 
               subscription_end, is_active, created_at, is_admin, telegram_id
        FROM users WHERE email = %s
    ''', (email.lower(),))
    
    row = c.fetchone()
    c.close()
    conn.close()
    
    return dict(row) if row else None

def create_session(user_id: int, days: int = 7) -> str:
    """Crée une session utilisateur"""
    conn = get_connection()
    c = conn.cursor()
    
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=days)
    
    c.execute('''
        INSERT INTO sessions (session_id, user_id, expires_at)
        VALUES (%s, %s, %s)
    ''', (session_id, user_id, expires_at))
    
    conn.commit()
    c.close()
    conn.close()
    
    return session_id

def get_session(session_id: str) -> dict:
    """Récupère une session valide"""
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    
    c.execute('''
        SELECT s.session_id, s.user_id, s.expires_at,
               u.email, u.first_name, u.last_name, u.subscription_end, u.is_active, u.is_admin
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.session_id = %s AND s.expires_at > %s
    ''', (session_id, datetime.now()))
    
    row = c.fetchone()
    c.close()
    conn.close()
    
    return dict(row) if row else None

def delete_session(session_id: str):
    """Supprime une session"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('DELETE FROM sessions WHERE session_id = %s', (session_id,))
    conn.commit()
    c.close()
    conn.close()

def add_subscription_time(user_id: int, days: int):
    """Ajoute du temps d'abonnement"""
    conn = get_connection()
    c = conn.cursor()
    
    c.execute('SELECT subscription_end FROM users WHERE id = %s', (user_id,))
    row = c.fetchone()
    
    current_end = row[0] if row and row[0] else datetime.now()
    if current_end < datetime.now():
        current_end = datetime.now()
    
    new_end = current_end + timedelta(days=days)
    
    c.execute('''
        UPDATE users SET subscription_end = %s WHERE id = %s
    ''', (new_end, user_id))
    
    conn.commit()
    c.close()
    conn.close()
    
    return new_end

def get_all_users() -> list:
    """Récupère tous les utilisateurs pour l'admin"""
    conn = get_connection()
    c = conn.cursor(cursor_factory=RealDictCursor)
    
    c.execute('''
        SELECT id, email, first_name, last_name, 
               subscription_end, is_active, created_at, is_admin, plain_password
        FROM users ORDER BY created_at DESC
    ''')
    
    users = [dict(row) for row in c.fetchall()]
    c.close()
    conn.close()
    return users

def update_last_login(user_id: int):
    """Met à jour la dernière connexion"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET last_login = %s WHERE id = %s', 
              (datetime.now(), user_id))
    conn.commit()
    c.close()
    conn.close()

def log_prediction(game_number: int, suit: str, status: str):
    """Enregistre une prédiction dans la base de données"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO predictions_log (game_number, suit, status, resolved_at)
        VALUES (%s, %s, %s, %s)
    ''', (game_number, suit, status, datetime.now()))
    conn.commit()
    c.close()
    conn.close()

def get_prediction_stats():
    """Récupère les statistiques globales des prédictions"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM predictions_log WHERE status = 'WON'")
    won = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM predictions_log WHERE status = 'LOST'")
    lost = c.fetchone()[0]
    c.close()
    conn.close()
    return won, lost

def block_user(user_id: int):
    """Bloque un utilisateur"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET is_active = FALSE WHERE id = %s', (user_id,))
    conn.commit()
    c.close()
    conn.close()

def unblock_user(user_id: int):
    """Débloque un utilisateur"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('UPDATE users SET is_active = TRUE WHERE id = %s', (user_id,))
    conn.commit()
    c.close()
    conn.close()
