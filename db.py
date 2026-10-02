import os
from pathlib import Path

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor


def _load_local_env():
    """Load simple KEY=VALUE entries from the project-local, git-ignored .env file."""
    env_path = Path(__file__).with_name(".env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_local_env()

POSTGRES_CONFIG = {
    "dbname": "postgres",
    "user": os.environ.get("POSTGRES_USER", "postgres"),
    "password": os.environ.get("POSTGRES_PASSWORD"),
    "host": os.environ.get("POSTGRES_HOST", "localhost"),
    "port": os.environ.get("POSTGRES_PORT", "5432"),
}

if not POSTGRES_CONFIG["password"]:
    raise RuntimeError("Set POSTGRES_PASSWORD in the environment or project .env file.")

DB_CONFIG = {
    **POSTGRES_CONFIG,
    "dbname": "geo_data",
}


def ensure_database():
    """Create the application database using a connection to PostgreSQL's postgres DB."""
    conn = psycopg2.connect(**POSTGRES_CONFIG)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_CONFIG["dbname"],))
            if cur.fetchone() is None:
                # PostgreSQL does not allow a bind parameter for a database identifier.
                cur.execute(sql.SQL("CREATE DATABASE {} TEMPLATE template0").format(
                    sql.Identifier(DB_CONFIG["dbname"])
                ))
    finally:
        conn.close()


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def init_db():
    ensure_database()
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'student'))
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS attendance (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL,
                    latitude DOUBLE PRECISION,
                    longitude DOUBLE PRECISION
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS campus_location (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT 'College Campus',
                    latitude DOUBLE PRECISION NOT NULL,
                    longitude DOUBLE PRECISION NOT NULL,
                    radius INTEGER NOT NULL DEFAULT 100,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_profiles (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                    full_name TEXT,
                    degree TEXT,
                    branch TEXT,
                    specialization TEXT,
                    year TEXT,
                    section TEXT,
                    is_complete BOOLEAN DEFAULT FALSE,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS subjects (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    total_hours INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_subjects (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                    subject_id INTEGER REFERENCES subjects(id) ON DELETE CASCADE,
                    UNIQUE(user_id, subject_id)
                )
            """)
            cur.execute("""
                ALTER TABLE attendance
                ADD COLUMN IF NOT EXISTS subject_id INTEGER REFERENCES subjects(id) ON DELETE SET NULL
            """)
            cur.execute("SELECT 1 FROM campus_location LIMIT 1")
            if cur.fetchone() is None:
                cur.execute("""
                    INSERT INTO campus_location (name, latitude, longitude, radius)
                    VALUES (%s, %s, %s, %s)
                """, ("College Campus", 12.9716, 77.5946, 100))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_campus_location():
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM campus_location ORDER BY id DESC LIMIT 1")
            return cur.fetchone()
    finally:
        conn.close()


def get_student_profile(user_id):
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM student_profiles WHERE user_id = %s", (user_id,))
            return cur.fetchone()
    finally:
        conn.close()
