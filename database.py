"""
Gestion de la base de données SQLite
"""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import secrets

DB_PATH = Path('data/baccarat.db')

def init_db():
    """Initialise la base de données"""
    DB_PATH.parent.mkdir(exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Table utilisateurs
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            subscription_end TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            last_login TIMESTAMP
        )
    ''')
    
    # Table sessions
    c.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    
    # Table prédictions (pour historique)
    c.execute('''
        CREATE TABLE IF NOT EXISTS predictions_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_number INTEGER NOT NULL,
            suit TEXT NOT NULL,
            status TEXT NOT NULL,
            rattrapage INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        )
    ''')
    
    conn.commit()
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
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    try:
        password_hash = hash_password(password)
        c.execute('''
            INSERT INTO users (email, password_hash, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (email.lower(), password_hash, first_name, last_name))
        
        user_id = c.lastrowid
        conn.commit()
        
        return {
            'id': user_id,
            'email': email.lower(),
            'first_name': first_name,
            'last_name': last_name,
            'subscription_end': None
        }
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_user_by_email(email: str) -> dict:
    """Récupère un utilisateur par email"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        SELECT id, email, password_hash, first_name, last_name, 
               subscription_end, is_active, created_at
        FROM users WHERE email = ?
    ''', (email.lower(),))
    
    row = c.fetchone()
    conn.close()
    
    if row:
        return {
            'id': row[0],
            'email': row[1],
            'password_hash': row[2],
            'first_name': row[3],
            'last_name': row[4],
            'subscription_end': row[5],
            'is_active': row[6],
            'created_at': row[7]
        }
    return None

def create_session(user_id: int, days: int = 7) -> str:
    """Crée une session utilisateur"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    session_id = secrets.token_urlsafe(32)
    expires_at = datetime.now() + timedelta(days=days)
    
    c.execute('''
        INSERT INTO sessions (session_id, user_id, expires_at)
        VALUES (?, ?, ?)
    ''', (session_id, user_id, expires_at))
    
    conn.commit()
    conn.close()
    
    return session_id

def get_session(session_id: str) -> dict:
    """Récupère une session valide"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        SELECT s.session_id, s.user_id, s.expires_at,
               u.email, u.first_name, u.last_name, u.subscription_end, u.is_active
        FROM sessions s
        JOIN users u ON s.user_id = u.id
        WHERE s.session_id = ? AND s.expires_at > ?
    ''', (session_id, datetime.now()))
    
    row = c.fetchone()
    conn.close()
    
    if row:
        return {
            'session_id': row[0],
            'user_id': row[1],
            'expires_at': row[2],
            'email': row[3],
            'first_name': row[4],
            'last_name': row[5],
            'subscription_end': row[6],
            'is_active': row[7]
        }
    return None

def delete_session(session_id: str):
    """Supprime une session"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM sessions WHERE session_id = ?', (session_id,))
    conn.commit()
    conn.close()

def add_subscription_time(user_id: int, days: int):
    """Ajoute du temps d'abonnement"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('SELECT subscription_end FROM users WHERE id = ?', (user_id,))
    row = c.fetchone()
    
    current_end = row[0] if row[0] else datetime.now()
    if isinstance(current_end, str):
        current_end = datetime.fromisoformat(current_end)
    
    if current_end < datetime.now():
        current_end = datetime.now()
    
    new_end = current_end + timedelta(days=days)
    
    c.execute('''
        UPDATE users SET subscription_end = ? WHERE id = ?
    ''', (new_end, user_id))
    
    conn.commit()
    conn.close()
    
    return new_end

def get_all_users() -> list:
    """Récupère tous les utilisateurs pour l'admin"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        SELECT id, email, first_name, last_name, 
               subscription_end, is_active, created_at
        FROM users ORDER BY created_at DESC
    ''')
    
    users = []
    for row in c.fetchall():
        users.append({
            'id': row[0],
            'email': row[1],
            'first_name': row[2],
            'last_name': row[3],
            'subscription_end': row[4],
            'is_active': row[5],
            'created_at': row[6]
        })
    
    conn.close()
    return users

def update_last_login(user_id: int):
    """Met à jour la dernière connexion"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET last_login = ? WHERE id = ?', 
              (datetime.now(), user_id))
    conn.commit()
    conn.close()

def block_user(user_id: int):
    """Bloque un utilisateur"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET is_active = 0 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()

def unblock_user(user_id: int):
    """Débloque un utilisateur"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE users SET is_active = 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
