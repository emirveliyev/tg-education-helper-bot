import os
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "data/bot_data.sqlite3")
dir_path = os.path.dirname(DB_PATH)
if dir_path and not os.path.exists(dir_path):
    os.makedirs(dir_path, exist_ok=True)

def get_connection():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY,
        username TEXT,
        phone TEXT,
        accepted INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        meta TEXT,
        tests TEXT,
        created_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
    )
    """)
    conn.commit()
    conn.close()

def add_or_update_user(user_id: int, username: Optional[str], phone: Optional[str], accepted: bool = False):
    now = datetime.utcnow().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    if row:
        cur.execute("""
            UPDATE users
            SET username = ?, phone = ?, accepted = ?, updated_at = ?
            WHERE id = ?
        """, (username, phone, int(bool(accepted)), now, user_id))
    else:
        cur.execute("""
            INSERT INTO users (id, username, phone, accepted, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, phone, int(bool(accepted)), now))
    conn.commit()
    conn.close()

def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, phone, accepted, created_at, updated_at FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {
            "id": row["id"],
            "username": row["username"],
            "phone": row["phone"],
            "accepted": bool(row["accepted"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    return None

def list_users() -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, phone, accepted, created_at, updated_at FROM users")
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "username": r["username"],
            "phone": r["phone"],
            "accepted": bool(r["accepted"]),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]

def save_test(user_id: int, meta: dict, tests: list) -> int:
    now = datetime.utcnow().isoformat()
    meta_json = json.dumps(meta, ensure_ascii=False)
    tests_json = json.dumps(tests, ensure_ascii=False)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO tests (user_id, meta, tests, created_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, meta_json, tests_json, now))
    last_id = cur.lastrowid
    conn.commit()
    conn.close()
    return last_id

init_db()